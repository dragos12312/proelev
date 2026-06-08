<script setup>
// dashboard the user lands on after logging in. role-aware: shows the
// quick-access tiles that matter for that role plus a panel with the
// homeworks that are coming up next.
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { homeworksApi, notificationsApi, gradebookApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const router = useRouter()

const upcoming   = ref([])
const unread     = ref(0)
const avg        = ref(null)
const loading    = ref(true)

const role = computed(() => currentUser.value?.role || null)
const displayName = computed(() => currentUser.value?.name || 'Utilizator')

const greeting = computed(() => {
  const h = new Date().getHours()
  if (h < 5)  return 'Bună noaptea'
  if (h < 12) return 'Bună dimineața'
  if (h < 18) return 'Bună ziua'
  return 'Bună seara'
})

const roleLabel = computed(() => {
  switch (role.value) {
    case 'admin':   return 'administrator'
    case 'teacher': return 'profesor'
    case 'student': return 'elev'
    case 'parent':  return 'părinte'
    default:        return 'utilizator'
  }
})

async function loadEverything() {
  loading.value = true
  try {
    // upcoming homeworks: same listing the homeworks page uses, but trimmed
    const page = await homeworksApi.list(1, 5)
    const items = Array.isArray(page?.items) ? page.items : (Array.isArray(page) ? page : [])
    // sort by due date ascending, future first, then most-overdue last
    const today = new Date(); today.setHours(0,0,0,0)
    upcoming.value = items
      .map(h => ({ ...h, _d: new Date(h.dueDate) }))
      .sort((a, b) => a._d - b._d)
      .slice(0, 5)
  } catch (e) {
    upcoming.value = []
  }

  try {
    const { count } = await notificationsApi.unreadCount()
    unread.value = count
  } catch { unread.value = 0 }

  // student/parent get an at-a-glance average from the gradebook
  if (role.value === 'student' || role.value === 'parent') {
    try {
      const g = await gradebookApi.mine()
      if (g.viewKind === 'student') {
        avg.value = g.data.average
      } else if (g.viewKind === 'parent' && g.children.length > 0) {
        // for a parent with multiple kids, just show the first one's average
        avg.value = g.children[0].average
      }
    } catch { avg.value = null }
  }

  loading.value = false
}

onMounted(loadEverything)

function isOverdue(due) {
  const today = new Date(); today.setHours(0,0,0,0)
  return new Date(due) < today
}

// tile config per role. each tile = { label, route, hint, color }
const tiles = computed(() => {
  const base = [
    { label: 'Teme',         route: '/homeworks',     hint: 'Listă completă', color: '#185FA5' },
    { label: 'Notificări',   route: '/notifications', hint: `${unread.value} necitite`, color: '#d32f2f' },
    { label: 'Mesaje',       route: '/messages',      hint: 'Chat în direct', color: '#2a9d2a' },
    { label: 'Catalog',      route: '/catalog',       hint: 'Note și medii',  color: '#7b3f9f' },
    { label: 'Orar',         route: '/orar',          hint: 'Program săptămânal', color: '#0288d1' },
  ]
  if (role.value === 'admin') {
    base.push({ label: 'Admin', route: '/admin', hint: 'Coduri și utilizatori', color: '#333' })
  }
  return base
})
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="" />
      <div class="main">

        <div class="hero">
          <div>
            <div class="hero-greet">{{ greeting }}, {{ displayName }}!</div>
            <div class="hero-sub">Ești conectat ca <b>{{ roleLabel }}</b>.</div>
          </div>
          <div class="hero-stats">
            <div v-if="unread > 0" class="stat">
              <div class="stat-num">{{ unread }}</div>
              <div class="stat-label">notificări necitite</div>
            </div>
            <div v-if="avg !== null" class="stat">
              <div class="stat-num">{{ avg }}</div>
              <div class="stat-label">media generală</div>
            </div>
            <div class="stat">
              <div class="stat-num">{{ upcoming.length }}</div>
              <div class="stat-label">teme apropiate</div>
            </div>
          </div>
        </div>

        <div class="row">
          <div class="tiles">
            <div v-for="t in tiles" :key="t.label"
                 class="tile" :style="{ borderTop: `4px solid ${t.color}` }"
                 @click="router.push(t.route)">
              <div class="tile-label">{{ t.label }}</div>
              <div class="tile-hint">{{ t.hint }}</div>
            </div>
          </div>

          <div class="upcoming-panel">
            <h3>Următoarele teme</h3>
            <div v-if="loading" class="muted">Se încarcă...</div>
            <div v-else-if="upcoming.length === 0" class="muted">
              Nicio temă apropiată. 🎉
            </div>
            <div v-else class="upcoming-list">
              <div v-for="hw in upcoming" :key="hw.id"
                   class="up-item" :class="{ overdue: isOverdue(hw.dueDate) }"
                   @click="router.push(`/homeworks/${hw.id}`)">
                <div class="up-main">
                  <div class="up-title">{{ hw.title }}</div>
                  <div class="up-meta">{{ hw.subject }} · {{ hw.assignedClass }}</div>
                </div>
                <div class="up-due">{{ hw.dueDate }}</div>
              </div>
            </div>
          </div>
        </div>

      </div>
    </div>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; }
.main {
  flex: 1; min-width: 0;
  padding: clamp(16px, 3vw, 28px);
  padding-right: clamp(40px, 6vw, 80px);
  font-family: 'Inter', sans-serif;
}

.hero {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 16px;
  background: linear-gradient(135deg, #185FA5, #2a78c5);
  color: white; padding: clamp(16px, 3vw, 28px);
  border-radius: 14px; margin-bottom: 20px;
}
.hero-greet { font-size: clamp(18px, 2.6vw, 26px); font-weight: 700; }
.hero-sub { opacity: 0.85; margin-top: 4px; font-size: 14px; }
.hero-stats { display: flex; gap: clamp(12px, 2vw, 24px); flex-wrap: wrap; }
.stat {
  background: rgba(255,255,255,0.16); padding: 10px 16px;
  border-radius: 10px; min-width: 110px; text-align: center;
}
.stat-num { font-size: clamp(20px, 3vw, 28px); font-weight: 700; }
.stat-label { font-size: 11px; opacity: 0.9; }

.row {
  display: grid;
  grid-template-columns: 2fr 1fr;
  gap: 20px;
}
@media (max-width: 900px) {
  .row { grid-template-columns: 1fr; }
}

.tiles {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(170px, 1fr));
  gap: clamp(10px, 1.8vw, 16px);
  align-content: start;
}
.tile {
  background: white; border: 1px solid #e0e6ee; border-radius: 12px;
  padding: 18px 16px; cursor: pointer; transition: transform 0.1s, box-shadow 0.1s;
}
.tile:hover { transform: translateY(-2px); box-shadow: 0 6px 18px rgba(0,0,0,0.08); }
.tile-label { font-size: 16px; font-weight: 700; color: #185FA5; }
.tile-hint { font-size: 12px; color: #888; margin-top: 4px; }

.upcoming-panel {
  background: white; border: 1px solid #e0e6ee; border-radius: 12px;
  padding: clamp(12px, 2vw, 18px);
}
.upcoming-panel h3 { margin: 0 0 12px; color: #185FA5; font-size: 14px; }
.muted { color: #888; font-size: 13px; }
.upcoming-list { display: flex; flex-direction: column; gap: 8px; }
.up-item {
  display: flex; justify-content: space-between; align-items: center; gap: 12px;
  padding: 10px 12px; border: 1px solid #eef2f7; border-radius: 8px;
  cursor: pointer; transition: background 0.1s;
}
.up-item:hover { background: #f5faff; }
.up-item.overdue { border-left: 3px solid #cc0000; }
.up-title { font-weight: 700; font-size: 13px; color: #185FA5; }
.up-meta  { font-size: 11px; color: #888; margin-top: 2px; }
.up-due {
  font-size: 12px; color: #555; background: #f0f5fb;
  padding: 4px 10px; border-radius: 999px; white-space: nowrap;
}
.up-item.overdue .up-due { background: #ffe0e0; color: #cc0000; }
</style>
