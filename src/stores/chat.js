// chat store, lives outside any component so the sidebar, the header and the
// panel all share the same state
//
// the websocket is opened as soon as the user is logged in and stays open
// while they are around, that way dms keep arriving even when the panel is
// closed, the sidebar shows an unread badge and a toast pops in the corner

import { ref, computed, watch } from 'vue'
import { chatApi, createChatWebSocket } from '../api.js'
import { currentUser, authToken } from '../utils/auth.js'

// ─── reactive state ──────────────────────────────────────────────────────────
export const chatOpen        = ref(false)
export const rooms           = ref([])
export const otherUsers      = ref([])
export const activeRoom      = ref(null)
export const messages        = ref([])
export const unread          = ref({})              // { [room_id]: count }
export const lastNotification = ref(null)           // { room, message, ts }

// ─── derived ────────────────────────────────────────────────────────────────
export const totalUnread = computed(() =>
  Object.values(unread.value).reduce((s, n) => s + n, 0)
)

// ─── websocket plumbing ─────────────────────────────────────────────────────
let ws = null
let reconnectTimer = null

function connectWs() {
  if (ws || !currentUser.value) return
  ws = createChatWebSocket((evt) => {
    if (evt.type === 'message') handleIncoming(evt)
  })
  ws.addEventListener('open', () => {
    if (!currentUser.value || !authToken.value) return
    // server identifies us by decoding the bearer token, no plain user_id
    ws.send(JSON.stringify({
      type: 'hello',
      token: authToken.value,
    }))
    // refresh sidebar after the hello so the rooms list is current
    loadSidebar()
  })
  ws.addEventListener('close', () => {
    ws = null
    // reconnect after a moment if the user is still logged in
    if (currentUser.value) {
      reconnectTimer = setTimeout(() => { reconnectTimer = null; connectWs() }, 2000)
    }
  })
}

function disconnectWs() {
  if (reconnectTimer) { clearTimeout(reconnectTimer); reconnectTimer = null }
  if (ws) { ws.close(); ws = null }
  // wipe state on logout
  rooms.value = []
  otherUsers.value = []
  activeRoom.value = null
  messages.value = []
  unread.value = {}
  lastNotification.value = null
}

// open and close the websocket as the user logs in or out
watch(currentUser, (u) => {
  if (u) connectWs()
  else   disconnectWs()
}, { immediate: true })

// ─── incoming messages ──────────────────────────────────────────────────────
function handleIncoming(evt) {
  const me = currentUser.value
  // append to the active room if we are looking at it
  if (activeRoom.value && evt.room_id === activeRoom.value.id) {
    messages.value.push(evt.message)
    if (chatOpen.value) return  // user is reading, no badge no toast
  }

  // skip our own echo for unread/notification bookkeeping
  if (me && evt.message.author_id === me.id) return

  // bump the unread counter for this room
  unread.value = { ...unread.value, [evt.room_id]: (unread.value[evt.room_id] || 0) + 1 }

  // make sure we know about the room, the dm could have been created on the fly
  let room = rooms.value.find(r => r.id === evt.room_id)
  if (!room) {
    loadSidebar().then(() => {
      const r = rooms.value.find(rr => rr.id === evt.room_id)
      if (r) maybeNotify(r, evt.message)
    })
    return
  }
  maybeNotify(room, evt.message)
}

function maybeNotify(room, message) {
  // only toast for dms, the global room would spam
  if (room.type !== 'dm') return
  // dont toast while the user is already looking at this room
  if (chatOpen.value && activeRoom.value && activeRoom.value.id === room.id) return
  lastNotification.value = { room, message, ts: Date.now() }
}

// ─── public actions ─────────────────────────────────────────────────────────
export function markRead(roomId) {
  if (unread.value[roomId]) {
    const next = { ...unread.value }
    delete next[roomId]
    unread.value = next
  }
}

export async function loadSidebar() {
  if (!currentUser.value) return
  rooms.value      = await chatApi.myRooms()
  otherUsers.value = await chatApi.users()
}

export async function selectRoom(room) {
  activeRoom.value = room
  markRead(room.id)
  messages.value = await chatApi.history(room.id)
  // tell the server we want this rooms broadcasts, idempotent on the server side
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ type: 'subscribe', room_id: room.id }))
  }
}

export function sendMessage(text) {
  text = (text || '').trim()
  if (!text || !activeRoom.value || !ws || ws.readyState !== 1) return
  ws.send(JSON.stringify({ type: 'message', room_id: activeRoom.value.id, text }))
}

export async function openDmWith(other) {
  const room = await chatApi.openDm(other.id)
  await loadSidebar()
  // subscribe explicitly since the room is brand new
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ type: 'subscribe', room_id: room.id }))
  }
  selectRoom(rooms.value.find(r => r.id === room.id) || room)
}

export async function createSpecialRoom(name) {
  name = (name || '').trim()
  if (!name) return
  const ids = otherUsers.value.map(u => u.id).join(',')
  const room = await chatApi.createRoom(name, ids)
  await loadSidebar()
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ type: 'subscribe', room_id: room.id }))
  }
  selectRoom(rooms.value.find(r => r.id === room.id) || room)
}
