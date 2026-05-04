<script setup>
// top bar that every logged in page reuses, logo title and the chat toggle
import { ref } from 'vue'
import logo from '../assets/logo.png'
import ChatPanel from './ChatPanel.vue'
import { currentUser } from '../utils/auth.js'

// chat panel slides in over the page when this is true
const chatOpen = ref(false)
</script>

<template>
  <div class="header">
    <img :src="logo" alt="ProElev Logo" class="logo" />
    <div class="title-block">
      <h1 class="title">ProElev</h1>
      <p class="tagline">Perseverența duce la reușite!</p>
    </div>
    <!-- only show the chat button when logged in, the panel needs a user id -->
    <button v-if="currentUser" class="chat-btn" @click="chatOpen = true" title="Chat">💬</button>
    <ChatPanel :open="chatOpen" @close="chatOpen = false" />
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');

.header {
  display: flex;
  align-items: center;
  gap: clamp(8px, 2vw, 16px);
  padding: clamp(10px, 2vw, 20px) clamp(12px, 3vw, 20px);
  border-bottom: 3px solid black;
  font-family: 'Inter', sans-serif;
  overflow: hidden;
  position: relative;
}

.logo {
  position: relative;
  width: clamp(48px, 9vw, 120px);
  height: auto;
  border-radius: 20px;
  flex-shrink: 0;
}

.title-block {
  display: flex;
  flex-direction: column;
  flex: 1;
  align-items: center;
  text-align: center;
  padding-right: clamp(40px, 9vw, 120px); /* leaves room for the profile avatar and chat button */
  min-width: 0;
}

.title {
  font-size: clamp(26px, 5vw, 60px);
  color: #185FA5;
  font-weight: 900;
  line-height: 1;
}

.tagline {
  font-size: clamp(12px, 2vw, 24px);
  color: #185FA5;
  white-space: normal;
  text-align: center;
  width: 100%;
}

/* chat button sits between the title and the profile avatar in the top right */
.chat-btn {
  position: absolute;
  right: clamp(56px, 8vw, 96px);
  top: 50%;
  transform: translateY(-50%);
  width: clamp(36px, 4vw, 48px);
  height: clamp(36px, 4vw, 48px);
  border-radius: 50%;
  background: #185FA5;
  color: white;
  border: none;
  font-size: clamp(16px, 2vw, 22px);
  cursor: pointer;
}
.chat-btn:hover { background: #134d87; }

@media (max-width: 600px) {
  .title-block { padding-right: 96px; }
}
</style>
