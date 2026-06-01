<script setup>
// gold, admin only panel
// shows the observation list at the top with dismiss buttons
// then the most recent action log entries underneath
// auto refreshes every 5 seconds so you can watch suspicious activity build up
import { ref, onMounted, onUnmounted, computed } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { adminApi, statsApi } from '../api.js'
import { currentUser, isAdmin } from '../utils/auth.js'

const router = useRouter()

// kick non admins back to the main page, no panel for them
if (!isAdmin()) {
  router.replace('/main')
}

const observations = ref([])
const logs         = ref([])
const includeDismissed = ref(false)
const filterUserId = ref('')
const error        = ref('')

let refreshTimer = null

async function loadAll() {
  if (!isAdmin()) return
  try {
    observations.value = await adminApi.observations(includeDismissed.value)
    const filt = filterUserId.value ? parseInt(filterUserId.value) : null
    const res  = await adminApi.logs(1, 100, filt)
    logs.value = res.items
    error.value = ''
  } catch (e) {
    error.value = e.message || 'eroare'
  }
}

async function dismiss(uid) {
  try {
    await adminApi.dismiss(uid)
    await loadAll()
  } catch (e) {
    error.value = e.message || 'eroare'
  }
}


// ── perf demo & ai run-now ───────────────────────────────────────────────
const perf       = ref(null)
const perfBusy   = ref(false)
const aiBusy     = ref(false)
const aiResult   = ref(null)

async function runPerf() {
  perfBusy.value = true
  try {
    perf.value = await statsApi.perfDemo()
  } catch (e) {
    error.value = e.message || 'eroare la perf demo'
  } finally {
    perfBusy.value = false
  }
}

async function runAi() {
  aiBusy.value = true
  try {
    aiResult.value = await adminApi.runAi()
    await loadAll()  // pull the freshly written observations
  } catch (e) {
    error.value = e.message || 'eroare la ai'
  } finally {
    aiBusy.value = false
  }
}

function perfBar(ms, max) {
  if (!max) return '0%'
  return `${Math.min(100, (ms / max) * 100)}%`
}

function statusClass(s) {
  if (s >= 500) return 'st-server'
  if (s >= 400) return 'st-client'
  if (s >= 300) return 'st-redir'
  return 'st-ok'
}

// format an iso utc string in the browser local timezone, e.g. 2026-05-04 10:58:23
function formatLocal(iso) {
  if (!iso) return ''
  const d = new Date(iso)
  if (isNaN(d.getTime())) return iso
  const pad = n => String(n).padStart(2, '0')
  return `${d.getFullYear()}-${pad(d.getMonth()+1)}-${pad(d.getDate())} `
       + `${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`
}

// auto refresh, the lab teacher should see the list change while we generate suspicious traffic
onMounted(() => {
  loadAll()
  refreshTimer = setInterval(loadAll, 5000)
})
onUnmounted(() => {
  if (refreshTimer) clearInterval(refreshTimer)
})
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">PANOU ADMIN</h2>
          <div class="muted">se reîmprospătează la 5s</div>
        </div>

        <div v-if="error" class="api-error">{{ error }}</div>

        <!-- assignment 5 gold, perf demo of the heavy m2m stat -->
        <section class="card">
          <header>
            <h3>Performanță statistică M2M (/stats/by-tag)</h3>
            <button class="btn-action" :disabled="perfBusy" @click="runPerf">
              {{ perfBusy ? 'Rulez...' : 'Rulează demo' }}
            </button>
          </header>
          <div v-if="perf" class="perf-body">
            <div class="rows">
              <span>tags: <b>{{ perf.rows.tags }}</b></span>
              <span>students: <b>{{ perf.rows.students }}</b></span>
              <span>tag links: <b>{{ perf.rows.tag_links }}</b></span>
            </div>
            <div class="perf-grid">
              <template v-for="key in ['naive', 'indexed', 'cache_miss', 'cache_hit']" :key="key">
                <div class="perf-label">{{ key }}</div>
                <div class="perf-track">
                  <div class="perf-fill" :class="{ slow: key === 'naive' }"
                       :style="{ width: perfBar(perf.ms[key], perf.ms.naive) }"></div>
                </div>
                <div class="perf-value">{{ perf.ms[key] }} ms</div>
              </template>
            </div>
            <p class="perf-note">
              Speed-up indexed vs naive:
              <b>{{ perf.ms.naive && perf.ms.indexed ? (perf.ms.naive / perf.ms.indexed).toFixed(1) : '-' }}×</b>
              ·
              cache hit vs naive:
              <b>{{ perf.ms.naive && perf.ms.cache_hit ? (perf.ms.naive / Math.max(perf.ms.cache_hit, 0.01)).toFixed(0) : '-' }}×</b>
            </p>
          </div>
          <p v-else class="empty">
            Apasă „Rulează demo" pentru a măsura cele trei moduri.
            Rulează scripts/seed_heavy.py întâi, altfel timpii nu vor fi vizibili.
          </p>
        </section>

        <!-- assignment 5 gold, ai run-now button + last cycle result -->
        <section class="card">
          <header>
            <h3>Detector AI (Isolation Forest)</h3>
            <button class="btn-action" :disabled="aiBusy" @click="runAi">
              {{ aiBusy ? 'Rulez...' : 'Rulează detector AI' }}
            </button>
          </header>
          <div v-if="aiResult">
            <p>Ciclu: {{ aiResult.fitted ? 'fitat' : 'nefitat' }}, useri: <b>{{ aiResult.users }}</b></p>
            <p v-if="aiResult.flagged && aiResult.flagged.length">
              Flagged: <b>{{ aiResult.flagged.length }}</b> · scoruri:
              <code v-for="f in aiResult.flagged" :key="f.user_id" class="score-chip">
                #{{ f.user_id }}: {{ f.score.toFixed(2) }}
              </code>
            </p>
            <p v-else class="empty">Niciun user marcat ca anomal.</p>
          </div>
          <p v-else class="empty">
            Detectorul rulează automat la fiecare 30s în fundal. Apasă „Rulează detector AI"
            pentru a forța un ciclu imediat.
          </p>
        </section>

        <!-- observation list -->
        <section class="card">
          <header>
            <h3>Lista de observație</h3>
            <label class="filter">
              <input type="checkbox" v-model="includeDismissed" @change="loadAll" />
              include dismissed
            </label>
          </header>

          <table v-if="observations.length">
            <thead>
              <tr>
                <th>USER</th>
                <th>ROL</th>
                <th>SCOR</th>
                <th>MOTIV</th>
                <th>PRIMA OARĂ</th>
                <th>ULTIMA OARĂ</th>
                <th></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="o in observations" :key="o.id" :class="{ dismissed: o.dismissed }">
                <td>
                  <div class="who">
                    <strong>{{ o.user_name || 'necunoscut' }} <span class="uid">#{{ o.user_id }}</span></strong>
                    <span class="email">{{ o.user_email }}</span>
                  </div>
                </td>
                <td><span class="role-pill" :class="o.user_role">{{ o.user_role }}</span></td>
                <td class="score">{{ o.score }}</td>
                <td class="reason">{{ o.reason }}</td>
                <td>{{ formatLocal(o.first_flagged_at) }}</td>
                <td>{{ formatLocal(o.last_flagged_at) }}</td>
                <td>
                  <button v-if="!o.dismissed" class="btn-dismiss" @click="dismiss(o.user_id)">Dismiss</button>
                  <span v-else class="muted">dismis</span>
                </td>
              </tr>
            </tbody>
          </table>
          <p v-else class="empty">Niciun utilizator pe lista de observație.</p>
        </section>

        <!-- recent action log -->
        <section class="card">
          <header>
            <h3>Activitate recentă</h3>
            <label class="filter">
              filtrează după user id:
              <input type="text" v-model="filterUserId" @keyup.enter="loadAll" placeholder="ex 2" />
              <button @click="loadAll">aplicare</button>
            </label>
          </header>

          <div class="logs-scroll">
            <table>
              <thead>
                <tr>
                  <th>WHEN</th>
                  <th>LAST</th>
                  <th>COUNT</th>
                  <th>USER</th>
                  <th>METHOD</th>
                  <th>ACTION</th>
                  <th>PATH</th>
                  <th>STATUS</th>
                </tr>
              </thead>
              <tbody>
                <tr v-for="l in logs" :key="l.id">
                  <td class="mono">{{ formatLocal(l.created_at) }}</td>
                  <td class="mono">{{ formatLocal(l.last_seen_at) }}</td>
                  <td><span class="count" :class="{ many: l.count > 1 }">×{{ l.count }}</span></td>
                  <td>
                    <div v-if="l.user_id">
                      {{ l.user_name || 'necunoscut' }} <span class="uid">#{{ l.user_id }}</span>
                      <span class="muted">({{ l.role || '-' }})</span>
                    </div>
                    <span v-else class="muted">anonim</span>
                  </td>
                  <td><span class="method" :class="l.method.toLowerCase()">{{ l.method }}</span></td>
                  <td class="mono">{{ l.action }}</td>
                  <td class="mono path">{{ l.path }}</td>
                  <td><span class="status" :class="statusClass(l.status)">{{ l.status }}</span></td>
                </tr>
                <tr v-if="logs.length === 0">
                  <td colspan="8" class="empty">Niciun eveniment.</td>
                </tr>
              </tbody>
            </table>
          </div>
        </section>
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
}
.toolbar {
  display: flex; align-items: baseline; justify-content: space-between;
  margin-bottom: 16px; gap: 16px; flex-wrap: wrap;
}
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; }
.muted { color: #888; font-size: 13px; }
.api-error { background: #ffe5e5; color: #cc0000; padding: 8px 12px; border-radius: 6px; margin-bottom: 12px; }

.card { background: #fff; border: 1px solid #e0e0e0; border-radius: 10px; padding: 14px; margin-bottom: 16px; }
.card header {
  display: flex; align-items: center; justify-content: space-between;
  margin-bottom: 10px; flex-wrap: wrap; gap: 8px;
}
.card h3 { font-size: 15px; color: #333; margin: 0; }
.filter { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #555; }
.filter input[type="text"] { padding: 4px 8px; border: 1px solid #ccc; border-radius: 4px; font-size: 13px; width: 80px; }
.filter button { padding: 4px 10px; background: #185FA5; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }

table { width: 100%; border-collapse: collapse; font-size: 13px; }
th, td { padding: 6px 8px; text-align: left; border-bottom: 1px solid #f0f0f0; }
th {
  color: white;
  background: #185FA5;
  font-size: 11px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
}
/* round the corners of the header strip to match the card */
thead tr th:first-child { border-top-left-radius: 6px; }
thead tr th:last-child  { border-top-right-radius: 6px; }
tr.dismissed { opacity: 0.5; }

/* the small grey id chip next to the user name */
.uid {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace;
  font-size: 11px;
  color: #888;
  font-weight: 400;
  margin-left: 4px;
}

.who { display: flex; flex-direction: column; line-height: 1.2; }
.email { color: #888; font-size: 11px; }
.score { font-weight: 700; color: #cc0000; text-align: center; }
.reason { color: #444; max-width: 380px; word-break: break-word; }

.role-pill {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  font-size: 11px; font-weight: 700; text-transform: uppercase;
}
.role-pill.admin { background: #ffe5e5; color: #cc0000; }
.role-pill.user  { background: #e8f2ff; color: #134d87; }

.btn-dismiss { padding: 4px 10px; background: #2a9d2a; color: white; border: none; border-radius: 4px; cursor: pointer; font-size: 12px; }
.btn-dismiss:hover { background: #228022; }

.logs-scroll { max-height: 50vh; overflow: auto; }

.mono { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.path { color: #555; max-width: 320px; word-break: break-all; }
.method {
  display: inline-block; padding: 2px 6px; border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; font-weight: 700;
}
.method.get    { background: #e0ecf8; color: #185FA5; }
.method.post   { background: #d0f0d0; color: #2a6a2a; }
.method.put    { background: #fff0d0; color: #8a6020; }
.method.delete { background: #ffd5d5; color: #cc0000; }

.status {
  display: inline-block; padding: 2px 6px; border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px;
}

/* count column shows ×1 normally and a yellow chip when the row has been bumped */
.count {
  display: inline-block; padding: 2px 8px; border-radius: 10px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px; font-weight: 700;
  background: #f0f0f0; color: #777;
}
.count.many { background: #fff0c0; color: #8a6020; }
.st-ok     { background: #d0f0d0; color: #2a6a2a; }
.st-redir  { background: #fff0d0; color: #8a6020; }
.st-client { background: #ffe5e5; color: #cc0000; }
.st-server { background: #cc0000; color: white; }

.empty { color: #999; text-align: center; padding: 20px; font-style: italic; }

.btn-action {
  padding: 6px 14px; background: #185FA5; color: white; border: none;
  border-radius: 6px; cursor: pointer; font-size: 12px; font-weight: 700;
}
.btn-action:hover { background: #134d87; }
.btn-action:disabled { opacity: 0.5; cursor: not-allowed; }

.perf-body { padding: 4px 0; }
.rows { display: flex; gap: 16px; font-size: 12px; color: #555; margin-bottom: 10px; }
.perf-grid {
  display: grid;
  grid-template-columns: 110px 1fr auto;
  gap: 6px 12px;
  align-items: center;
}
.perf-label { font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px; }
.perf-track {
  height: 16px; background: #f0f0f0; border-radius: 8px; overflow: hidden;
}
.perf-fill {
  height: 100%; background: #2a9d2a; transition: width 0.3s;
}
.perf-fill.slow { background: #cc0000; }
.perf-value {
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 12px;
  color: #333; min-width: 70px; text-align: right;
}
.perf-note { font-size: 12px; color: #444; margin-top: 8px; }

.score-chip {
  display: inline-block; margin: 2px 4px 0 0; padding: 1px 6px;
  background: #ffe5e5; color: #a00000; border-radius: 4px;
  font-family: ui-monospace, SFMono-Regular, Menlo, monospace; font-size: 11px;
}
</style>
