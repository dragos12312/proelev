<script setup>
// little toast that pops in the top right when a new dm arrives while the
// user is not on the messages page, click it to jump to the conversation,
// hides itself after a few seconds
import { ref, watch, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { lastNotification, selectRoom } from '../stores/chat.js'

const router = useRouter()
const visible = ref(false)
let hideTimer = null

watch(lastNotification, (n) => {
  if (!n) { visible.value = false; return }
  visible.value = true
  if (hideTimer) clearTimeout(hideTimer)
  hideTimer = setTimeout(() => { visible.value = false }, 5000)
})

onUnmounted(() => { if (hideTimer) clearTimeout(hideTimer) })

async function openIt() {
  if (!lastNotification.value) return
  const room = lastNotification.value.room
  visible.value = false
  await router.push('/messages')
  selectRoom(room)
}
</script>

<template>
  <transition name="toast">
    <div v-if="visible && lastNotification" class="toast" @click="openIt">
      <div class="dot">m</div>
      <div class="body">
        <div class="title">Mesaj nou de la {{ lastNotification.message.author_name }}</div>
        <div class="text">{{ lastNotification.message.text }}</div>
      </div>
    </div>
  </transition>
</template>

<style scoped>
.toast {
  position: fixed;
  top: 80px;
  right: 16px;
  z-index: 1100;
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 10px 14px;
  background: white;
  color: #333;
  border: 1px solid #185FA5;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.15);
  font-family: 'Inter', sans-serif;
  cursor: pointer;
  max-width: 320px;
}
.toast:hover { background: #f5faff; }
.dot {
  width: 32px; height: 32px;
  display: flex; align-items: center; justify-content: center;
  border-radius: 50%;
  background: #e0ecf8;
  font-size: 16px;
  flex-shrink: 0;
}
.body { min-width: 0; }
.title { font-weight: 700; font-size: 13px; color: #185FA5; }
.text {
  font-size: 13px; color: #555;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  max-width: 240px;
  margin-top: 2px;
}

.toast-enter-active, .toast-leave-active { transition: all 0.25s ease; }
.toast-enter-from, .toast-leave-to {
  opacity: 0; transform: translateX(20px);
}
</style>
