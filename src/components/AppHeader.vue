<script setup>
// top bar that every logged in page reuses, just the logo and the title
// the toast notification mounts here so dms pop up on any page
import logo from '../assets/logo.png'
import ChatNotification from './ChatNotification.vue'
</script>

<template>
  <div class="header">
    <img :src="logo" alt="ProElev Logo" class="logo" />
    <div class="title-block">
      <h1 class="title">ProElev</h1>
      <p class="tagline">Perseverența duce la reușite!</p>
    </div>
    <ChatNotification />
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
  padding-right: clamp(40px, 9vw, 120px); /* leaves room for the profile avatar */
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

@media (max-width: 600px) {
  .title-block { padding-right: 48px; }
}
</style>
