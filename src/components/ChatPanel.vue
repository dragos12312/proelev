<script setup>
// silver chat, slide out panel that talks to the chat router
// rooms sidebar on the left, active conversation on the right, message input at the bottom
// the data layer in the backend is tinydb, transport is websocket plus rest for history
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { chatApi, createChatWebSocket } from '../api.js'
import { currentUser, isAdmin } from '../utils/auth.js'

const props = defineProps({ open: Boolean })
const emit  = defineEmits(['close'])

const rooms        = ref([])
const otherUsers   = ref([])
const activeRoom   = ref(null)
const messages     = ref([])
const draft        = ref('')
const newRoomName  = ref('')
const showAdminUi  = ref(false)
let ws = null
const messagesBox  = ref(null)

// load the rooms i can see and the people i can dm
async function loadSidebar() {
  if (!currentUser.value) return
  rooms.value = await chatApi.myRooms(currentUser.value.id)
  otherUsers.value = await chatApi.users(currentUser.value.id)
  // pick the global room by default the first time the panel opens
  if (!activeRoom.value && rooms.value.length) {
    selectRoom(rooms.value.find(r => r.type === 'global') || rooms.value[0])
  }
}

async function selectRoom(room) {
  activeRoom.value = room
  messages.value = await chatApi.history(room.id, currentUser.value.id)
  await nextTick()
  scrollToBottom()
  // tell the ws we are listening to this room so we get its broadcasts
  if (ws && ws.readyState === 1) {
    ws.send(JSON.stringify({ type: 'subscribe', room_id: room.id }))
  }
}

async function openDmWith(other) {
  const room = await chatApi.openDm(currentUser.value.id, other.id)
  await loadSidebar()
  selectRoom(rooms.value.find(r => r.id === room.id) || room)
}

async function createSpecialRoom() {
  const name = (newRoomName.value || '').trim()
  if (!name) return
  // include every other user in the room by default, simplest interface
  const ids = otherUsers.value.map(u => u.id).join(',')
  const room = await chatApi.createRoom(currentUser.value.id, name, ids)
  newRoomName.value = ''
  await loadSidebar()
  selectRoom(rooms.value.find(r => r.id === room.id) || room)
}

function send() {
  const text = (draft.value || '').trim()
  if (!text || !activeRoom.value || !ws || ws.readyState !== 1) return
  ws.send(JSON.stringify({ type: 'message', room_id: activeRoom.value.id, text }))
  draft.value = ''
}

function scrollToBottom() {
  const el = messagesBox.value
  if (el) el.scrollTop = el.scrollHeight
}

// open the ws once when the panel mounts, keep it alive while the panel is open
onMounted(async () => {
  if (!currentUser.value) return
  await loadSidebar()
  ws = createChatWebSocket((evt) => {
    if (evt.type === 'message') {
      // only render the broadcast if it is for the active room
      if (activeRoom.value && evt.room_id === activeRoom.value.id) {
        messages.value.push(evt.message)
        nextTick(scrollToBottom)
      }
    }
  })
  ws.addEventListener('open', () => {
    ws.send(JSON.stringify({
      type: 'hello',
      user_id: currentUser.value.id,
      user_name: currentUser.value.name,
    }))
  })
})

onUnmounted(() => {
  if (ws) ws.close()
})

// when the user logs out the panel auto closes since currentUser becomes null
watch(currentUser, (u) => {
  if (!u) emit('close')
})
</script>

<template>
  <div class="chat-overlay" v-if="open" @click.self="$emit('close')">
    <div class="chat-panel">
      <header>
        <h3>Chat</h3>
        <button class="close" @click="$emit('close')">×</button>
      </header>

      <div class="body">
        <!-- left sidebar with rooms and dm targets -->
        <aside>
          <h4>Camere</h4>
          <ul class="room-list">
            <li v-for="r in rooms" :key="r.id"
                :class="{ active: activeRoom && activeRoom.id === r.id }"
                @click="selectRoom(r)">
              <span class="room-type">{{ r.type === 'global' ? '🌐' : r.type === 'dm' ? '💬' : '#' }}</span>
              {{ r.name }}
            </li>
          </ul>

          <h4>Persoane</h4>
          <ul class="user-list">
            <li v-for="u in otherUsers" :key="u.id" @click="openDmWith(u)">
              <span class="dot" :class="u.role === 'admin' ? 'admin' : 'user'"></span>
              {{ u.name }}
            </li>
          </ul>

          <div v-if="isAdmin()" class="admin-tools">
            <h4>Camera nouă (admin)</h4>
            <input v-model="newRoomName" type="text" placeholder="nume camera" />
            <button @click="createSpecialRoom">Creează</button>
          </div>
        </aside>

        <!-- right pane, active conversation -->
        <section class="conv">
          <div v-if="!activeRoom" class="placeholder">Selectează o cameră</div>
          <template v-else>
            <div class="conv-title">{{ activeRoom.name }}</div>
            <div class="messages" ref="messagesBox">
              <div v-for="m in messages" :key="m.id" class="msg"
                   :class="{ own: currentUser && m.author_id === currentUser.id }">
                <div class="meta">
                  <strong>{{ m.author_name }}</strong>
                  <span>{{ m.created_at }}</span>
                </div>
                <div class="text">{{ m.text }}</div>
              </div>
              <div v-if="messages.length === 0" class="empty">Niciun mesaj încă.</div>
            </div>
            <div class="input-row">
              <input v-model="draft" type="text" placeholder="Scrie un mesaj..."
                     @keyup.enter="send" />
              <button @click="send" :disabled="!draft.trim()">Trimite</button>
            </div>
          </template>
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.chat-overlay {
  position: fixed; inset: 0; background: rgba(0,0,0,0.4);
  z-index: 1000; display: flex; justify-content: flex-end;
}
.chat-panel {
  width: min(900px, 95vw); height: 100vh; background: white;
  display: flex; flex-direction: column; box-shadow: -4px 0 12px rgba(0,0,0,0.15);
}
header {
  display: flex; align-items: center; justify-content: space-between;
  padding: 12px 16px; border-bottom: 1px solid #e0e0e0;
  background: #185FA5; color: white;
}
header h3 { margin: 0; font-size: 16px; font-family: 'Inter', sans-serif; }
.close {
  background: transparent; border: none; color: white; font-size: 24px;
  cursor: pointer; line-height: 1;
}

.body { display: flex; flex: 1; min-height: 0; }

aside {
  width: 260px; max-width: 40%; border-right: 1px solid #e0e0e0;
  padding: 12px; overflow-y: auto; font-family: 'Inter', sans-serif;
}
aside h4 {
  margin: 12px 0 6px; font-size: 12px; text-transform: uppercase; color: #666;
  letter-spacing: 0.05em;
}
ul { list-style: none; padding: 0; margin: 0; }
.room-list li, .user-list li {
  padding: 8px 10px; border-radius: 6px; cursor: pointer;
  font-size: 13px; display: flex; align-items: center; gap: 8px;
}
.room-list li:hover, .user-list li:hover { background: #f0f0f0; }
.room-list li.active { background: #e0ecf8; color: #185FA5; font-weight: 600; }
.room-type { width: 18px; text-align: center; }
.dot { width: 8px; height: 8px; border-radius: 50%; flex-shrink: 0; }
.dot.admin { background: #cc0000; }
.dot.user  { background: #2a9d2a; }

.admin-tools input {
  width: 100%; box-sizing: border-box; padding: 6px 8px; margin: 4px 0;
  font-family: 'Inter', sans-serif; font-size: 13px; border: 1px solid #ccc; border-radius: 6px;
}
.admin-tools button {
  width: 100%; padding: 6px 10px; background: #185FA5; color: white;
  border: none; border-radius: 6px; cursor: pointer; font-size: 13px;
}

.conv { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.placeholder { padding: 32px; color: #888; text-align: center; }
.conv-title {
  padding: 10px 16px; border-bottom: 1px solid #e0e0e0;
  font-weight: 600; color: #333; font-family: 'Inter', sans-serif; font-size: 14px;
}
.messages {
  flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column;
  gap: 10px; background: #fafafa;
}
.msg {
  max-width: 80%; padding: 8px 12px; border-radius: 10px;
  background: white; border: 1px solid #e0e0e0;
  font-family: 'Inter', sans-serif; font-size: 13px; word-wrap: break-word;
}
.msg.own { align-self: flex-end; background: #e0ecf8; border-color: #b0c4de; }
.msg .meta {
  display: flex; gap: 8px; font-size: 11px; color: #888; margin-bottom: 2px;
}
.msg .meta strong { color: #333; }
.msg .text { white-space: pre-wrap; }
.empty { color: #999; text-align: center; margin-top: 24px; font-style: italic; }

.input-row {
  display: flex; gap: 8px; padding: 10px 16px; border-top: 1px solid #e0e0e0; background: white;
}
.input-row input {
  flex: 1; padding: 8px 12px; border-radius: 18px; border: 1px solid #ccc;
  font-family: 'Inter', sans-serif; font-size: 13px; outline: none;
}
.input-row input:focus { border-color: #185FA5; }
.input-row button {
  padding: 8px 18px; border-radius: 18px; background: #185FA5; color: white;
  border: none; cursor: pointer; font-size: 13px;
}
.input-row button:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 600px) {
  aside { width: 180px; }
}
</style>
