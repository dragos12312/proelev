<script setup>
// dashboard the user lands on after logging in. school-wide announcement
// banner at the top (admin can post new ones from here too), then a grid
// of subject cards. clicking a card opens that subject's Teams-style hub.
import { ref, onMounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { lookups, schoolAnnouncementsApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const router = useRouter()

const subjects     = ref([])
const announcements = ref([])
const showCompose  = ref(false)
const newTitle     = ref('')
const newBody      = ref('')
const newKind      = ref('info')
const composeErr   = ref('')

const isAdmin = computed(() => currentUser.value?.role === 'admin')

async function loadAll() {
  try {
    subjects.value = await lookups.subjects()
  } catch {
    subjects.value = [
      { id: null, name: 'Matematică' },
      { id: null, name: 'Limba Română' },
      { id: null, name: 'Științele naturii' },
      { id: null, name: 'Limba Engleză' },
      { id: null, name: 'Istorie' },
      { id: null, name: 'Geografie' },
      { id: null, name: 'Educație fizică' },
    ]
  }
  try {
    announcements.value = await schoolAnnouncementsApi.list()
  } catch {
    announcements.value = []
  }
}

onMounted(loadAll)

function openSubject(s) {
  if (s.id) router.push(`/subject/${s.id}`)
  else      router.push(`/subject/0?name=${encodeURIComponent(s.name)}`)
}

async function postAnnouncement() {
  composeErr.value = ''
  if (!newTitle.value.trim()) {
    composeErr.value = 'Titlul este obligatoriu'; return
  }
  try {
    await schoolAnnouncementsApi.create(newTitle.value.trim(), newBody.value.trim() || null, newKind.value)
    newTitle.value = ''; newBody.value = ''
    showCompose.value = false
    await loadAll()
  } catch (e) {
    composeErr.value = e.message || 'Eroare'
  }
}

async function archive(id) {
  if (!confirm('Sigur arhivezi acest anunț?')) return
  try {
    await schoolAnnouncementsApi.archive(id)
    await loadAll()
  } catch (e) { alert(e.message || 'Eroare') }
}

function bannerClass(k) {
  if (k === 'warning') return 'kind-warn'
  if (k === 'event')   return 'kind-event'
  return 'kind-info'
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="" />
      <div class="main">

        <!-- school-wide announcements banner -->
        <div v-if="announcements.length > 0" class="announce-stack">
          <div v-for="a in announcements" :key="a.id"
               :class="['announce', bannerClass(a.kind)]">
            <div class="ann-body">
              <div class="ann-title">{{ a.title }}</div>
              <div v-if="a.body" class="ann-text">{{ a.body }}</div>
              <div class="ann-meta">de {{ a.createdByName || 'admin' }}</div>
            </div>
            <button v-if="isAdmin" class="ann-archive" @click="archive(a.id)">Arhivează</button>
          </div>
        </div>

        <!-- admin-only compose -->
        <div v-if="isAdmin" class="admin-compose">
          <button class="btn-toggle" @click="showCompose = !showCompose">
            {{ showCompose ? 'Închide' : 'Postează un anunț general' }}
          </button>
          <div v-if="showCompose" class="compose-card">
            <input v-model="newTitle" type="text" placeholder="Titlu anunț" maxlength="200" />
            <textarea v-model="newBody" rows="3" placeholder="Detalii (opțional)" maxlength="1000"></textarea>
            <select v-model="newKind">
              <option value="info">Informativ</option>
              <option value="warning">Atenționare</option>
              <option value="event">Eveniment</option>
            </select>
            <button class="btn-go" @click="postAnnouncement">Postează</button>
            <div v-if="composeErr" class="err">{{ composeErr }}</div>
          </div>
        </div>

        <div class="grid">
          <div v-for="s in subjects"
               :key="s.id || s.name"
               class="card"
               @click="openSubject(s)">
            {{ s.name }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; }
.main {
  flex: 1;
  padding: clamp(16px, 3vw, 40px);
  padding-top: clamp(20px, 3vw, 40px);
  padding-right: clamp(40px, 6vw, 80px);
  font-family: 'Inter', sans-serif;
  min-width: 0;
}

/* announcements */
.announce-stack { display: flex; flex-direction: column; gap: 10px; margin-bottom: 18px; }
.announce {
  display: flex; gap: 12px; padding: 12px 16px; border-radius: 10px;
  border-left: 4px solid transparent;
  background: #eef5fb;
}
.announce.kind-info  { border-left-color: #185FA5; background: #eef5fb; }
.announce.kind-warn  { border-left-color: #d32f2f; background: #fff0f0; }
.announce.kind-event { border-left-color: #2a9d2a; background: #eaf7e8; }
.ann-body { flex: 1; min-width: 0; }
.ann-title { font-weight: 700; color: #185FA5; font-size: 14px; }
.ann-text  { font-size: 13px; color: #333; margin-top: 4px; white-space: pre-wrap; }
.ann-meta  { font-size: 11px; color: #888; margin-top: 4px; }
.ann-archive {
  background: none; border: 1px solid #d0d7e2; color: #555;
  padding: 4px 10px; border-radius: 6px; font-size: 12px; cursor: pointer;
  font-family: 'Inter', sans-serif; align-self: flex-start;
}
.ann-archive:hover { background: white; }

.admin-compose { margin-bottom: 18px; }
.btn-toggle {
  background: #185FA5; color: white; border: none; padding: 8px 16px;
  border-radius: 8px; cursor: pointer; font-family: 'Inter', sans-serif;
  font-weight: 700; font-size: 13px;
}
.btn-toggle:hover { background: #134d87; }
.compose-card {
  background: white; border: 1px solid #d0d7e2; border-radius: 10px;
  padding: 12px; margin-top: 10px;
  display: flex; flex-direction: column; gap: 8px; max-width: 600px;
}
.compose-card input, .compose-card textarea, .compose-card select {
  padding: 8px 10px; border: 1px solid #d0d7e2; border-radius: 6px;
  font-family: 'Inter', sans-serif; font-size: 13px;
}
.btn-go {
  background: #2a9d2a; color: white; border: none; padding: 8px 20px;
  border-radius: 8px; cursor: pointer; font-weight: 700; align-self: flex-end;
  font-family: 'Inter', sans-serif;
}
.btn-go:hover { background: #228022; }
.err { background: #ffe5e5; color: #cc0000; padding: 6px 10px; border-radius: 6px; font-size: 13px; }

/* subject grid */
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: clamp(12px, 2vw, 24px);
}
@media (max-width: 480px) {
  .grid { grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px; }
}
.card {
  background-color: #f0f0f0;
  border-radius: 12px;
  padding: clamp(12px, 2vw, 24px);
  font-size: clamp(12px, 1.4vw, 16px);
  font-weight: 700;
  color: #185FA5;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  aspect-ratio: 1;
  transition: background-color 0.2s, transform 0.1s;
}
.card:hover { background-color: #dde8f5; transform: translateY(-2px); }

@media (max-width: 480px) {
  .main { padding-top: 16px; }
  .card { font-size: 13px; padding: 10px; }
  .announce { flex-direction: column; }
}
</style>
