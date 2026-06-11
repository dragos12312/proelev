<script setup>
// notification bell in the header. shows a small red badge with the unread
// count; click toggles a dropdown with the feed (newest first).
//
// polling: every 20s we refresh the unread count. when the panel is open we
// fetch the full list once. when the user clicks a notification we mark it
// read and navigate to its link.
import { ref, computed, onMounted, onUnmounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import { notificationsApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const router = useRouter()

const open      = ref(false)
const unread    = ref(0)
const items     = ref([])
const loading   = ref(false)
let   pollTimer = null
const POLL_MS   = 20000

const isAuthed = computed(() => !!currentUser.value)

async function refreshCount() {
  if (!isAuthed.value) return
  try {
    const { count } = await notificationsApi.unreadCount()
    unread.value = count
  } catch {
    // a single failure shouldn't kill the polling loop, keep the last good value
  }
}

async function refreshList() {
  if (!isAuthed.value) return
  loading.value = true
  try {
    items.value = await notificationsApi.list(false, 50)
  } catch {
    items.value = []
  } finally {
    loading.value = false
  }
}

async function toggle() {
  open.value = !open.value
  if (open.value) await refreshList()
}

async function clickItem(n) {
  // optimistically flip the read state so the badge updates instantly
  if (!n.read) {
    n.read = true
    unread.value = Math.max(0, unread.value - 1)
    try { await notificationsApi.markRead(n.id) } catch {}
  }
  open.value = false
  if (n.link) router.push(n.link)
}

async function markAll() {
  try { await notificationsApi.markAllRead() } catch {}
  for (const n of items.value) n.read = true
  unread.value = 0
}

// close the panel when the user clicks outside of it
function onDocClick(e) {
  const panel = document.querySelector('.notif-panel')
  const bell  = document.querySelector('.notif-bell')
  if (!open.value) return
  if (panel && panel.contains(e.target)) return
  if (bell  && bell.contains(e.target))  return
  open.value = false
}

onMounted(() => {
  refreshCount()
  pollTimer = setInterval(refreshCount, POLL_MS)
  document.addEventListener('click', onDocClick)
})

onUnmounted(() => {
  if (pollTimer) clearInterval(pollTimer)
  document.removeEventListener('click', onDocClick)
})

// when the user logs in mid-session, kick a fresh fetch
watch(currentUser, (v) => { if (v) refreshCount() })

// turn the iso timestamp into something short, "azi 14:32" / "ieri 09:11"
// / "2026-06-05 18:00"
function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const yesterday = new Date(now); yesterday.setDate(yesterday.getDate() - 1)
  const isYesterday = d.toDateString() === yesterday.toDateString()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  if (sameDay)     return `azi ${hh}:${mm}`
  if (isYesterday) return `ieri ${hh}:${mm}`
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')} ${hh}:${mm}`
}
</script>

<template>
  <div v-if="isAuthed" class="notif-wrap">
    <button class="notif-bell" :class="{ active: open }" @click="toggle" aria-label="Notificări">
      <span class="bell-icon">N</span>
      <span v-if="unread > 0" class="badge">{{ unread > 99 ? '99+' : unread }}</span>
    </button>
    <transition name="panel">
      <div v-if="open" class="notif-panel">
        <div class="panel-head">
          <span class="panel-title">Notificări</span>
          <button v-if="unread > 0" class="mark-all" @click="markAll">Marchează tot ca citit</button>
        </div>
        <div v-if="loading" class="panel-empty">Se încarcă...</div>
        <div v-else-if="items.length === 0" class="panel-empty">Nicio notificare încă.</div>
        <div v-else class="panel-list">
          <div v-for="n in items" :key="n.id"
               class="notif-item"
               :class="{ unread: !n.read }"
               @click="clickItem(n)">
            <div class="notif-title">{{ n.title }}</div>
            <div v-if="n.body" class="notif-body">{{ n.body }}</div>
            <div class="notif-time">{{ fmtTime(n.createdAt) }}</div>
          </div>
        </div>
      </div>
    </transition>
  </div>
</template>

<style scoped>
.notif-wrap {
  position: absolute;
  top: clamp(10px, 1.5vw, 18px);
  right: clamp(48px, 6vw, 76px);  /* left of the profile avatar */
  z-index: 50;
  font-family: 'Inter', sans-serif;
}

.notif-bell {
  position: relative;
  background: white;
  border: 2px solid #185FA5;
  width: clamp(38px, 5vw, 46px);
  height: clamp(38px, 5vw, 46px);
  border-radius: 50%;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 6px rgba(0,0,0,0.08);
  transition: transform 0.1s ease;
}
.notif-bell:hover { transform: translateY(-1px); }
.notif-bell.active { background: #e9f1fb; }
.bell-icon { font-size: clamp(16px, 2vw, 20px); line-height: 1; }

.badge {
  position: absolute;
  top: -4px; right: -4px;
  background: #d32f2f;
  color: white;
  font-size: 11px;
  font-weight: 700;
  min-width: 18px;
  height: 18px;
  border-radius: 10px;
  padding: 0 5px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid white;
  line-height: 1;
}

.notif-panel {
  position: absolute;
  top: calc(100% + 8px);
  right: 0;
  width: min(360px, 90vw);
  max-height: 480px;
  background: white;
  border: 1px solid #d0d7e2;
  border-radius: 12px;
  box-shadow: 0 8px 24px rgba(0,0,0,0.18);
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.panel-head {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 10px 14px;
  border-bottom: 1px solid #e8eef5;
  background: #fafcff;
}
.panel-title { font-weight: 700; color: #185FA5; font-size: 14px; }
.mark-all {
  background: none; border: none; color: #185FA5; font-size: 12px;
  cursor: pointer; font-family: 'Inter', sans-serif;
}
.mark-all:hover { text-decoration: underline; }

.panel-empty {
  padding: 30px 16px; text-align: center; color: #888; font-size: 13px;
}
.panel-list {
  overflow-y: auto;
  max-height: 420px;
}
.notif-item {
  padding: 10px 14px;
  border-bottom: 1px solid #f0f3f7;
  cursor: pointer;
  transition: background-color 0.1s ease;
  background: white;
}
.notif-item:hover { background: #f5faff; }
.notif-item:last-child { border-bottom: none; }
/* unread items get a slightly more blue tint so they're easy to spot */
.notif-item.unread {
  background: #e9f1fb;
  border-left: 3px solid #185FA5;
  padding-left: 11px;  /* compensate for the left border */
}
.notif-item.unread:hover { background: #dde9f7; }

.notif-title { font-weight: 700; font-size: 13px; color: #185FA5; }
.notif-body  { font-size: 12px; color: #444; margin-top: 2px; white-space: pre-wrap; word-break: break-word; }
.notif-time  { font-size: 11px; color: #888; margin-top: 4px; }

.panel-enter-active, .panel-leave-active { transition: all 0.18s ease; }
.panel-enter-from, .panel-leave-to {
  opacity: 0; transform: translateY(-6px);
}
</style>
