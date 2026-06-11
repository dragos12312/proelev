<script setup>
// full-page notifications feed. mirrors the bell dropdown but with more room,
// filter buttons (all / unread), and grouping by day so the user can scan
// what happened this week
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { notificationsApi } from '../api.js'

const router = useRouter()

const items   = ref([])
const loading = ref(false)
const filter  = ref('all')   // 'all' | 'unread'

async function reload() {
  loading.value = true
  try {
    items.value = await notificationsApi.list(filter.value === 'unread', 100)
  } catch (e) {
    console.error('[NotificationsView] load error', e)
  } finally {
    loading.value = false
  }
}

async function open(n) {
  if (!n.read) {
    n.read = true
    try { await notificationsApi.markRead(n.id) } catch {}
  }
  if (n.link) router.push(n.link)
}

async function markAll() {
  try { await notificationsApi.markAllRead() } catch {}
  for (const n of items.value) n.read = true
}

function setFilter(f) {
  filter.value = f
  reload()
}

// group by date (yyyy-mm-dd) so we can render a sticky day separator
const grouped = computed(() => {
  const out = []
  let lastDay = null
  for (const n of items.value) {
    const day = (n.createdAt || '').slice(0, 10) || 'fără dată'
    if (day !== lastDay) {
      out.push({ kind: 'day', day, label: friendlyDay(day) })
      lastDay = day
    }
    out.push({ kind: 'item', n })
  }
  return out
})

function friendlyDay(day) {
  const now = new Date()
  const today = now.toISOString().slice(0, 10)
  const y = new Date(now); y.setDate(y.getDate() - 1)
  const yd = y.toISOString().slice(0, 10)
  if (day === today) return 'Azi'
  if (day === yd)    return 'Ieri'
  return day
}

function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso); if (isNaN(d.getTime())) return iso
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  return `${hh}:${mm}`
}

// short label per notification kind, makes it easier to scan
function kindLabel(k) {
  switch (k) {
    case 'homework_new':   return 'Temă nouă'
    case 'submission_new': return 'Submisie'
    case 'grade_given':    return 'Notă'
    case 'chat_message':   return 'Mesaj'
    default:               return k
  }
}

onMounted(reload)
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="notificari" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">NOTIFICĂRI</h2>
          <div class="filters">
            <button :class="{ active: filter === 'all' }"    @click="setFilter('all')">Toate</button>
            <button :class="{ active: filter === 'unread' }" @click="setFilter('unread')">Necitite</button>
            <button class="mark-all" @click="markAll">Marchează tot ca citit</button>
          </div>
        </div>

        <div v-if="loading" class="muted">Se încarcă...</div>
        <div v-else-if="items.length === 0" class="empty">
          <p v-if="filter === 'unread'">Nicio notificare necitită. 🎉</p>
          <p v-else>Nicio notificare încă.</p>
        </div>

        <div v-else class="feed">
          <template v-for="(row, i) in grouped" :key="i">
            <div v-if="row.kind === 'day'" class="day-sep">{{ row.label }}</div>
            <div v-else class="notif-row" :class="{ unread: !row.n.read }" @click="open(row.n)">
              <span class="kind-tag">{{ kindLabel(row.n.kind) }}</span>
              <div class="notif-main">
                <div class="notif-title">{{ row.n.title }}</div>
                <div v-if="row.n.body" class="notif-body">{{ row.n.body }}</div>
              </div>
              <div class="notif-time">{{ fmtTime(row.n.createdAt) }}</div>
            </div>
          </template>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; }
.main {
  flex: 1; min-width: 0;
  padding: clamp(12px, 2.5vw, 24px);
  padding-right: clamp(40px, 6vw, 80px);
  font-family: 'Inter', sans-serif;
}
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; flex-wrap: wrap; gap: 12px;
}
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; }
.filters { display: flex; gap: 8px; flex-wrap: wrap; }
.filters button {
  background: white; border: 1px solid #d0d7e2; padding: 6px 14px;
  border-radius: 999px; cursor: pointer; font-family: 'Inter', sans-serif;
  font-size: 13px; color: #185FA5;
}
.filters button.active { background: #185FA5; color: white; border-color: #185FA5; }
.filters button:hover:not(.active) { background: #f0f5fb; }
.mark-all { color: #555 !important; }

.empty { text-align: center; color: #888; padding: 40px 0; font-size: 14px; }
.muted { color: #888; }

.feed { display: flex; flex-direction: column; gap: 6px; }
.day-sep {
  font-size: 12px; color: #185FA5; font-weight: 700; text-transform: uppercase;
  margin: 14px 0 4px; padding-bottom: 4px; border-bottom: 1px dashed #b5d0f0;
}

.notif-row {
  display: flex; gap: 12px; align-items: flex-start;
  background: white; border: 1px solid #e0e6ee; border-radius: 10px;
  padding: 10px 14px; cursor: pointer; transition: background 0.1s ease;
}
.notif-row:hover { background: #f5faff; }
.notif-row.unread {
  background: #e9f1fb;
  border-left: 4px solid #185FA5;
  padding-left: 11px;
}
.notif-row.unread:hover { background: #dde9f7; }

.kind-tag {
  flex-shrink: 0; font-size: 11px; font-weight: 700;
  background: #185FA5; color: white;
  padding: 3px 8px; border-radius: 4px;
  align-self: flex-start; margin-top: 2px;
}
.notif-main { flex: 1; min-width: 0; }
.notif-title { font-weight: 700; color: #185FA5; font-size: 14px; }
.notif-body  { color: #444; font-size: 13px; margin-top: 2px; white-space: pre-wrap; word-break: break-word; }
.notif-time  { color: #888; font-size: 12px; flex-shrink: 0; align-self: center; }

@media (max-width: 700px) {
  .filters button { padding: 5px 10px; font-size: 12px; }
  .notif-row { padding: 8px 10px; gap: 8px; }
  .kind-tag { font-size: 10px; padding: 2px 6px; }
  .notif-title { font-size: 13px; }
  .notif-body  { font-size: 12px; }
}
@media (max-width: 480px) {
  .notif-row { flex-direction: column; align-items: flex-start; }
  .notif-time { align-self: flex-end; font-size: 11px; }
}
</style>
