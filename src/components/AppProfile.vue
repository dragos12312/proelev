<script setup>
// little profile avatar that floats in the top right corner
// it sticks just under the header so we watch the header size and move with it
// click it to open a tiny menu with logout, name, role
import template from '../assets/template.png'
import { ref, onMounted, onUnmounted } from 'vue'
import { useRouter } from 'vue-router'
import { currentUser, logout as clearSession } from '../utils/auth.js'
import { auth } from '../api.js'

const router = useRouter()
const top    = ref(0)
const open   = ref(false)
let observer = null

onMounted(() => {
  const header = document.querySelector('.header')
  if (!header) return
  const update = () => {
    const rect = header.getBoundingClientRect()
    top.value = rect.bottom + window.scrollY
  }
  update()
  observer = new ResizeObserver(update)
  observer.observe(header)
})

onUnmounted(() => {
  if (observer) observer.disconnect()
})

async function logout() {
  // call the server so it revokes the session jti, then wipe locally
  try { await auth.logout() } catch {}
  clearSession()
  router.replace('/login')
}
</script>

<template>
  <div class="profile" :style="{ top: top + 'px' }">
    <img :src="template" alt="Profile" class="profile-pic" @click="open = !open" />
    <div v-if="open && currentUser" class="menu" @click.stop>
      <div class="who">
        <strong>{{ currentUser.name }}</strong>
        <span class="role">{{ currentUser.role }}</span>
      </div>
      <button class="profile-btn" @click="router.push('/profile'); open = false">Profil & setări</button>
      <button class="logout" @click="logout">Deconectare</button>
    </div>
  </div>
</template>

<style scoped>
.profile {
  position: absolute;
  right: clamp(6px, 2vw, 16px);
  padding: clamp(4px, 1vw, 8px);
  z-index: 9999;
}

.profile-pic {
  display: block;
  width: clamp(28px, 3vw, 48px);
  height: clamp(28px, 3vw, 48px);
  border-radius: 50%;
  cursor: pointer;
  object-fit: cover;
}

.menu {
  position: absolute;
  right: 0;
  margin-top: 6px;
  background: white;
  border: 1px solid #e0e0e0;
  border-radius: 10px;
  box-shadow: 0 4px 16px rgba(0,0,0,0.12);
  padding: 12px;
  min-width: 180px;
  display: flex;
  flex-direction: column;
  gap: 10px;
  font-family: 'Inter', sans-serif;
}
.who { display: flex; flex-direction: column; line-height: 1.2; font-size: 13px; }
.role { color: #888; text-transform: uppercase; font-size: 11px; letter-spacing: 0.05em; }
.profile-btn {
  background: #185FA5; color: white; border: none;
  border-radius: 6px; padding: 8px 10px;
  cursor: pointer; font-size: 13px; font-weight: 700;
  font-family: 'Inter', sans-serif;
}
.profile-btn:hover { background: #134d87; }
.logout {
  background: #cc0000; color: white; border: none;
  border-radius: 6px; padding: 8px 10px;
  cursor: pointer; font-size: 13px; font-weight: 700;
}
.logout:hover { background: #a00000; }
</style>
