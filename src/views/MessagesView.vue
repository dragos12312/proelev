<script setup>
// silver chat, full page version, same layout as the other pages so the
// header and the profile avatar match the rest of the app
import { ref, nextTick, watch, onMounted, onUnmounted } from 'vue'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import {
  rooms, otherUsers, activeRoom, messages, chatOpen,
  loadSidebar, selectRoom, sendMessage, openDmWith, createSpecialRoom,
  markRead,
} from '../stores/chat.js'
import { currentUser, isAdmin } from '../utils/auth.js'

const draft       = ref('')
const newRoomName = ref('')
const messagesBox = ref(null)

// while we are on this page the store knows the user is reading,
// so badges dont accumulate for the room they are looking at
onMounted(async () => {
  chatOpen.value = true
  await loadSidebar()
  // pick the global room if nothing is selected yet
  if (!activeRoom.value && rooms.value.length) {
    selectRoom(rooms.value.find(r => r.type === 'global') || rooms.value[0])
  }
})
onUnmounted(() => { chatOpen.value = false })

// scroll to the bottom whenever a new message lands or the room changes
watch([messages, activeRoom], async () => {
  await nextTick()
  const el = messagesBox.value
  if (el) el.scrollTop = el.scrollHeight
}, { deep: true })

function send() {
  if (!draft.value.trim()) return
  sendMessage(draft.value)
  draft.value = ''
}

async function pickUser(other) { await openDmWith(other) }

async function makeRoom() {
  if (!newRoomName.value.trim()) return
  await createSpecialRoom(newRoomName.value)
  newRoomName.value = ''
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="mesaje" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">MESAJE</h2>
        </div>

        <div class="chat-wrap">
          <!-- inner sidebar with rooms and dm targets -->
          <aside class="rooms-pane">
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
              <li v-for="u in otherUsers" :key="u.id" @click="pickUser(u)">
                <span class="dot" :class="u.role === 'admin' ? 'admin' : 'user'"></span>
                {{ u.name }}
              </li>
            </ul>

            <div v-if="isAdmin()" class="admin-tools">
              <h4>Camera nouă (admin)</h4>
              <input v-model="newRoomName" type="text" placeholder="nume cameră" @keyup.enter="makeRoom" />
              <button @click="makeRoom">Creează</button>
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
                <input v-model="draft" type="text" placeholder="Scrie un mesaj..." @keyup.enter="send" />
                <button @click="send" :disabled="!draft.trim()">Trimite</button>
              </div>
            </template>
          </section>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; }
.main {
  flex: 1; min-width: 0;
  padding: clamp(12px, 2.5vw, 24px); padding-right: clamp(40px, 6vw, 80px);
  font-family: 'Inter', sans-serif;
  display: flex; flex-direction: column;
}
.toolbar { margin-bottom: 16px; }
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; }

.chat-wrap {
  display: flex;
  flex: 1;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  overflow: hidden;
  background: white;
  height: calc(100vh - 200px);
  min-height: 400px;
}

/* rooms + people */
.rooms-pane {
  width: 240px; max-width: 40%;
  border-right: 1px solid #e0e0e0;
  padding: 12px; overflow-y: auto;
  flex-shrink: 0;
}
.rooms-pane h4 {
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
  font-size: 13px; border: 1px solid #ccc; border-radius: 6px;
  font-family: 'Inter', sans-serif;
}
.admin-tools button {
  width: 100%; padding: 6px 10px; background: #185FA5; color: white;
  border: none; border-radius: 6px; cursor: pointer; font-size: 13px;
}

/* conversation pane */
.conv { flex: 1; display: flex; flex-direction: column; min-width: 0; }
.placeholder { padding: 32px; color: #888; text-align: center; }
.conv-title {
  padding: 10px 16px; border-bottom: 1px solid #e0e0e0;
  font-weight: 600; color: #333; font-size: 14px;
}
.messages {
  flex: 1; overflow-y: auto; padding: 12px 16px; display: flex; flex-direction: column;
  gap: 10px; background: #fafafa;
}
.msg {
  max-width: 80%; padding: 8px 12px; border-radius: 10px;
  background: white; border: 1px solid #e0e0e0;
  font-size: 13px; word-wrap: break-word;
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
  font-size: 13px; outline: none;
}
.input-row input:focus { border-color: #185FA5; }
.input-row button {
  padding: 8px 18px; border-radius: 18px; background: #185FA5; color: white;
  border: none; cursor: pointer; font-size: 13px;
}
.input-row button:disabled { opacity: 0.4; cursor: not-allowed; }

@media (max-width: 700px) {
  .rooms-pane { width: 180px; }
  .chat-wrap { height: calc(100vh - 220px); }
}
@media (max-width: 480px) {
  .rooms-pane { width: 140px; padding: 8px; }
}
</style>
