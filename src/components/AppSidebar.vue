<script setup>
// left side nav, TEME, MESAJE and ADMIN actually do something
// the rest are placeholders
// MESAJE opens the chat panel and shows an unread count badge
// ADMIN only appears for admins
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import bell from '../assets/bell.png'
import message from '../assets/message.png'
import calendar from '../assets/calendar.png'
import test from '../assets/test.png'
import book from '../assets/book.png'
import notebook from '../assets/notebook.png'
import { isAdmin } from '../utils/auth.js'
import { totalUnread } from '../stores/chat.js'

const router = useRouter()

defineProps({
  active: {
    type: String,
    default: ''
  }
})

// every active item routes to its own page, no modal anywhere
const items = computed(() => {
  const base = [
    { key: 'notificari', label: 'NOTIFICĂRI', icon: bell, route: '/notifications' },
    { key: 'mesaje',     label: 'MESAJE',     icon: message, route: '/messages' },
    { key: 'orar',       label: 'ORAR',       icon: calendar, route: '/orar' },
    { key: 'teme',       label: 'TEME',       icon: book, route: '/homeworks' },
    { key: 'catalog',    label: 'CATALOG',    icon: notebook, route: '/catalog' },
  ]
  if (isAdmin()) {
    base.push({ key: 'admin', label: 'ADMIN', icon: bell, route: '/admin' })
  }
  return base
})

function navigate(item) {
  if (item.route) router.push(item.route)
}
</script>

<template>
  <div class="sidebar">
    <div v-for="item in items"
         :key="item.key"
         class="item"
         :class="{ selected: active === item.key }"
         @click="navigate(item)">
      <div class="icon-wrap">
        <img :src="item.icon" :alt="item.label" class="icon" />
        <!-- unread badge only on MESAJE -->
        <span v-if="item.key === 'mesaje' && totalUnread > 0" class="badge">{{ totalUnread }}</span>
      </div>
      <span class="label">{{ item.label }}</span>
    </div>
  </div>
</template>

<style scoped>
.sidebar {
  width: clamp(64px, 14vw, 200px);
  height: 100vh;
  border-right: 1px solid silver;
  font-family: 'Inter', sans-serif;
  padding-top: 20px;
  position: sticky;
  top: 0;
  flex-shrink: 0;
  background: white;
}

.item {
  display: flex;
  align-items: center;
  gap: clamp(4px, 1vw, 12px);
  padding: clamp(8px, 1.2vw, 14px) clamp(8px, 1.2vw, 16px);
  cursor: pointer;
}

.item:hover {
  background-color: #f0f0f0;
}

.selected {
  background-color: #e0e0e0;
}

.icon-wrap {
  position: relative;
  flex-shrink: 0;
}

.icon {
  width: clamp(24px, 3.5vw, 48px);
  height: clamp(24px, 3.5vw, 48px);
}

/* small red bubble in the corner of MESAJE when there are unread messages */
.badge {
  position: absolute;
  top: -4px;
  right: -4px;
  background: #cc0000;
  color: white;
  font-size: 10px;
  font-weight: 700;
  min-width: 16px;
  height: 16px;
  padding: 0 4px;
  border-radius: 8px;
  display: flex;
  align-items: center;
  justify-content: center;
  border: 2px solid white;
  box-sizing: border-box;
  line-height: 1;
}

.label {
  color: #185FA5;
  font-weight: 700;
  font-size: clamp(10px, 1.4vw, 18px);
}

/* Tablet: collapse to icons-only so more width goes to content */
@media (max-width: 900px) {
  .label { display: none; }
  .sidebar { width: 72px; padding-top: 12px; }
  .item { justify-content: center; padding: 12px 8px; }
}

/* Phones: slim strip */
@media (max-width: 480px) {
  .sidebar { width: 56px; }
  .icon { width: 28px; height: 28px; }
  .item { padding: 10px 6px; }
}
</style>
