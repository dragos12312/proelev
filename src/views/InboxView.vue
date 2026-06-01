<script setup>
// silver, mock email inbox so the lab teacher can see the codes that the
// auth flow "sends" without setting up real SMTP
// when logged in, GET /auth/inbox returns the caller's mail (admin sees all)
// when not logged in, the user types an email and we hit the public
// /auth/inbox/last endpoint to fetch the latest message
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { auth } from '../api.js'
import { currentUser } from '../utils/auth.js'

const router = useRouter()
const messages = ref([])
const error    = ref('')
const probeEmail = ref('')   // used when not logged in
const probeMsg   = ref(null)
let refreshTimer = null

const loggedIn = computed(() => !!currentUser.value)

async function loadMine() {
  try {
    messages.value = await auth.inbox()
    error.value = ''
  } catch (e) {
    error.value = e.message || 'Eroare'
  }
}

async function loadProbe() {
  error.value = ''
  probeMsg.value = null
  if (!probeEmail.value.trim()) return
  try {
    const res = await fetch(
      (import.meta.env.VITE_API_URL || 'http://localhost:8000')
      + `/auth/inbox/last?to=${encodeURIComponent(probeEmail.value.trim())}`,
      { headers: { 'ngrok-skip-browser-warning': 'true' } },
    )
    if (!res.ok) {
      error.value = res.status === 404 ? 'Niciun mesaj' : 'Eroare'
      return
    }
    probeMsg.value = await res.json()
  } catch (e) {
    error.value = e.message || 'Eroare'
  }
}

function formatLocal(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = n => String(n).padStart(2, '0')
  return `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

onMounted(() => {
  if (loggedIn.value) {
    loadMine()
    refreshTimer = setInterval(loadMine, 4000)
  }
})
onUnmounted(() => { if (refreshTimer) clearInterval(refreshTimer) })
</script>

<template>
  <div style="position: relative" v-if="loggedIn">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">INBOX MOCK</h2>
          <div class="muted">se reîmprospătează la 4s</div>
        </div>

        <div v-if="error" class="api-error">{{ error }}</div>

        <div class="cards">
          <div v-for="m in messages" :key="m.id" class="card">
            <div class="head">
              <span class="to">→ {{ m.to }}</span>
              <span class="when">{{ formatLocal(m.created_at) }}</span>
            </div>
            <div class="subj">{{ m.subject }}</div>
            <pre class="body">{{ m.body }}</pre>
            <div class="code" v-if="m.code">COD: {{ m.code }}</div>
          </div>
          <p v-if="messages.length === 0" class="empty">Inbox-ul este gol.</p>
        </div>
      </div>
    </div>
  </div>

  <!-- not logged in: fallback panel for fetching one message at a time -->
  <div v-else class="landing">
    <h1 class="title">Inbox mock</h1>
    <p class="hint">Caută cel mai recent mesaj trimis către un email.</p>
    <div v-if="error" class="api-error">{{ error }}</div>
    <div class="field">
      <input v-model="probeEmail" type="text" placeholder="E-MAIL" class="input"
             @keyup.enter="loadProbe" />
      <button class="btn-load" @click="loadProbe">Caută</button>
    </div>
    <div v-if="probeMsg" class="card">
      <div class="head">
        <span class="to">→ {{ probeMsg.to }}</span>
        <span class="when">{{ formatLocal(probeMsg.created_at) }}</span>
      </div>
      <div class="subj">{{ probeMsg.subject }}</div>
      <pre class="body">{{ probeMsg.body }}</pre>
      <div class="code" v-if="probeMsg.code">COD: {{ probeMsg.code }}</div>
    </div>
    <p class="register-link">
      <span class="link" @click="router.push('/login')">Înapoi la conectare</span>
    </p>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; }
.main { flex: 1; min-width: 0; padding: clamp(12px, 2.5vw, 24px); padding-right: clamp(40px, 6vw, 80px); font-family: 'Inter', sans-serif; }
.toolbar { display: flex; align-items: baseline; justify-content: space-between; margin-bottom: 16px; gap: 16px; flex-wrap: wrap; }
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; }
.muted { color: #888; font-size: 13px; }
.api-error { background: #ffe5e5; color: #cc0000; padding: 8px 12px; border-radius: 6px; margin-bottom: 12px; }
.cards { display: flex; flex-direction: column; gap: 12px; }
.card { background: white; border: 1px solid #e0e0e0; border-radius: 10px; padding: 12px 14px; }
.head { display: flex; justify-content: space-between; font-size: 12px; color: #777; }
.to { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; }
.subj { font-weight: 700; color: #333; margin: 4px 0; }
.body { font-family: 'Inter', sans-serif; font-size: 13px; color: #444; white-space: pre-wrap; margin: 6px 0; }
.code { display: inline-block; background: #185FA5; color: white; padding: 4px 10px; border-radius: 6px; font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-weight: 700; }
.empty { color: #888; font-style: italic; text-align: center; padding: 20px; }

/* not logged in fallback */
.landing {
  min-height: 100vh; padding: clamp(20px, 4vw, 40px) clamp(20px, 5vw, 60px);
  background: white; font-family: 'Inter', sans-serif;
  display: flex; flex-direction: column; align-items: center; gap: 12px;
}
.landing .title { font-size: clamp(28px, 5vw, 60px); color: #185FA5; font-weight: 900; }
.landing .hint  { color: #444; font-size: clamp(12px, 1.3vw, 14px); }
.landing .field { display: flex; gap: 8px; width: clamp(280px, 50vw, 480px); }
.landing .input {
  flex: 1; padding: 10px 14px; border: 1px solid #ccc; border-radius: 10px;
  font-size: 14px; font-family: 'Inter', sans-serif; outline: none;
}
.landing .input:focus { border-color: #185FA5; }
.landing .btn-load {
  padding: 10px 16px; background: #185FA5; color: white; border: none;
  border-radius: 10px; cursor: pointer; font-weight: 700;
}
.register-link .link { color: #185FA5; font-weight: 700; cursor: pointer; }
.register-link .link:hover { text-decoration: underline; }
</style>
