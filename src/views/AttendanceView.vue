<script setup>
// PREZENȚĂ view, role-aware:
// - teacher/admin: pick class + date, see roster, click status per student, save
// - student: list of own attendance rows, newest first
// - parent: same list, grouped per child
import { ref, computed, onMounted } from 'vue'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { attendanceApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const role = computed(() => currentUser.value?.role || null)
const isTeacherSide = computed(() => role.value === 'admin' || role.value === 'teacher' || role.value === 'user')

const classes      = ref([])
const pickedClass  = ref(null)
const pickedDate   = ref(new Date().toISOString().slice(0, 10))
const roster       = ref([])
const marks        = ref({})        // userId -> { status, note }
const saving       = ref(false)
const msg          = ref('')
const loadErr      = ref('')

// student / parent state
const mine         = ref(null)
const loading      = ref(false)

const STATUSES = [
  { value: 'present', label: 'Prezent',    cls: 'st-present'  },
  { value: 'absent',  label: 'Absent',     cls: 'st-absent'   },
  { value: 'late',    label: 'Întârziat',  cls: 'st-late'     },
  { value: 'excused', label: 'Motivat',    cls: 'st-excused'  },
]

async function bootTeacher() {
  try {
    classes.value = await attendanceApi.teacherClasses()
    if (classes.value.length > 0) {
      pickedClass.value = classes.value[0].id
      await loadRoster()
    }
  } catch (e) {
    loadErr.value = e.message || 'Eroare la încărcare'
  }
}

async function loadRoster() {
  if (!pickedClass.value) return
  loadErr.value = ''
  try {
    const [r, existing] = await Promise.all([
      attendanceApi.roster(pickedClass.value),
      attendanceApi.listForClass(pickedClass.value, pickedDate.value),
    ])
    roster.value = r
    // start everyone as present by default, then overlay anything stored already
    const next = {}
    for (const st of r) next[st.userId] = { status: 'present', note: '' }
    for (const row of existing) {
      if (next[row.studentUserId]) {
        next[row.studentUserId] = { status: row.status, note: row.note || '' }
      }
    }
    marks.value = next
  } catch (e) {
    loadErr.value = e.message || 'Eroare la încărcare'
  }
}

async function save() {
  if (!pickedClass.value) return
  saving.value = true
  msg.value = ''
  try {
    const payload = roster.value.map(st => ({
      studentUserId: st.userId,
      status: marks.value[st.userId]?.status || 'present',
      note:   marks.value[st.userId]?.note || null,
    }))
    const r = await attendanceApi.bulkMark(pickedClass.value, pickedDate.value, payload)
    msg.value = `Salvat (${r.affected} elevi).`
    setTimeout(() => { msg.value = '' }, 3000)
  } catch (e) {
    msg.value = e.message || 'Eroare la salvare'
  } finally {
    saving.value = false
  }
}

async function bootSelf() {
  loading.value = true
  try {
    mine.value = await attendanceApi.mine()
  } catch (e) {
    loadErr.value = e.message || 'Eroare la încărcare'
  } finally {
    loading.value = false
  }
}

onMounted(() => {
  if (isTeacherSide.value) bootTeacher()
  else                     bootSelf()
})

function statusClass(s) { return STATUSES.find(x => x.value === s)?.cls || '' }
function statusLabel(s) { return STATUSES.find(x => x.value === s)?.label || s }

// per-student counters in the self view
function counters(rows) {
  const c = { absent: 0, late: 0, excused: 0, present: 0 }
  for (const r of rows) c[r.status] = (c[r.status] || 0) + 1
  return c
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="prezenta" />
      <div class="main">
        <h2 class="page-title">PREZENȚĂ</h2>
        <div v-if="loadErr" class="api-error">{{ loadErr }}</div>

        <!-- ── teacher/admin: pick class + date, mark roster ─────────── -->
        <div v-if="isTeacherSide">
          <div class="toolbar">
            <label>Clasa</label>
            <select v-model="pickedClass" @change="loadRoster">
              <option v-for="c in classes" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <label>Data</label>
            <input type="date" v-model="pickedDate" @change="loadRoster" />
            <button class="btn-save" :disabled="saving" @click="save">
              {{ saving ? 'Se salvează...' : 'Salvează' }}
            </button>
            <span v-if="msg" class="msg">{{ msg }}</span>
          </div>

          <div v-if="classes.length === 0" class="muted">
            Nu ai încă clase asignate.
          </div>
          <div v-else-if="roster.length === 0" class="muted">
            Niciun elev înregistrat pe această clasă.
          </div>
          <table v-else class="roster">
            <thead>
              <tr><th>Elev</th><th>Status</th><th>Notă (opțional)</th></tr>
            </thead>
            <tbody>
              <tr v-for="st in roster" :key="st.userId">
                <td class="st-name">{{ st.name }}</td>
                <td>
                  <div class="pills">
                    <button v-for="s in STATUSES" :key="s.value"
                            :class="['pill', s.cls, { active: marks[st.userId]?.status === s.value }]"
                            @click="marks[st.userId] = { ...(marks[st.userId] || {}), status: s.value }">
                      {{ s.label }}
                    </button>
                  </div>
                </td>
                <td>
                  <input class="note-input" type="text" placeholder="ex: medical"
                         v-model="marks[st.userId].note" />
                </td>
              </tr>
            </tbody>
          </table>
        </div>

        <!-- ── student: own attendance rows ────────────────────────── -->
        <div v-else-if="role === 'student' && mine">
          <div v-if="mine.rows.length === 0" class="muted">Nu ai prezență înregistrată încă.</div>
          <div v-else>
            <div class="summary">
              <span v-for="s in STATUSES" :key="s.value" :class="['chip', s.cls]">
                {{ s.label }}: <b>{{ counters(mine.rows)[s.value] || 0 }}</b>
              </span>
            </div>
            <table class="self">
              <thead><tr><th>Data</th><th>Status</th><th>Notă</th></tr></thead>
              <tbody>
                <tr v-for="r in mine.rows" :key="r.id">
                  <td>{{ r.date }}</td>
                  <td><span :class="['pill', statusClass(r.status)]">{{ statusLabel(r.status) }}</span></td>
                  <td>{{ r.note || '—' }}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </div>

        <!-- ── parent: each child gets a block ─────────────────────── -->
        <div v-else-if="role === 'parent' && mine">
          <div v-if="mine.children.length === 0" class="muted">Nu ai copii înregistrați.</div>
          <div v-for="ch in mine.children" :key="ch.userId" class="child-block">
            <h3>{{ ch.name }} <span class="muted small">({{ ch.class?.name || '—' }})</span></h3>
            <div v-if="ch.rows.length === 0" class="muted">Niciun rând de prezență.</div>
            <div v-else>
              <div class="summary">
                <span v-for="s in STATUSES" :key="s.value" :class="['chip', s.cls]">
                  {{ s.label }}: <b>{{ counters(ch.rows)[s.value] || 0 }}</b>
                </span>
              </div>
              <table class="self">
                <thead><tr><th>Data</th><th>Status</th><th>Notă</th></tr></thead>
                <tbody>
                  <tr v-for="r in ch.rows" :key="r.id">
                    <td>{{ r.date }}</td>
                    <td><span :class="['pill', statusClass(r.status)]">{{ statusLabel(r.status) }}</span></td>
                    <td>{{ r.note || '—' }}</td>
                  </tr>
                </tbody>
              </table>
            </div>
          </div>
        </div>

        <div v-else-if="loading" class="muted">Se încarcă...</div>
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
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; margin-bottom: 16px; }
.muted { color: #888; padding: 20px 0; }
.muted.small { font-size: 12px; }
.api-error { background: #ffe5e5; color: #cc0000; border: 1px solid #cc0000; border-radius: 8px; padding: 10px 16px; margin: 8px 0; }

.toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 16px; }
.toolbar label { color: #185FA5; font-weight: 700; font-size: 13px; }
.toolbar select, .toolbar input[type="date"] {
  padding: 6px 10px; border: 1px solid #d0d7e2; border-radius: 6px;
  font-family: 'Inter', sans-serif; font-size: 13px; background: white;
}
.btn-save {
  background: #2a9d2a; color: white; border: none; padding: 8px 18px;
  border-radius: 8px; cursor: pointer; font-weight: 700; font-family: 'Inter', sans-serif;
}
.btn-save:hover { background: #228022; }
.btn-save:disabled { opacity: 0.5; cursor: not-allowed; }
.msg { color: #185FA5; font-size: 13px; }

table.roster, table.self {
  width: 100%; border-collapse: collapse;
  background: white; border: 1px solid #e0e6ee; border-radius: 10px; overflow: hidden;
}
th { background: #185FA5; color: white; padding: 10px; text-align: left; font-size: 13px; }
td { padding: 10px; border-bottom: 1px solid #f0f3f7; font-size: 13px; vertical-align: middle; }
tbody tr:last-child td { border-bottom: none; }
.st-name { font-weight: 700; color: #185FA5; width: 220px; }

.pills { display: flex; gap: 6px; flex-wrap: wrap; }
.pill {
  border: 1px solid #d0d7e2; background: white; padding: 4px 12px;
  border-radius: 999px; cursor: pointer; font-size: 12px; font-weight: 700;
  font-family: 'Inter', sans-serif; color: #555;
}
.pill.active { color: white; border-color: transparent; }
.pill.st-present.active { background: #2a9d2a; }
.pill.st-absent.active  { background: #cc0000; }
.pill.st-late.active    { background: #f0a020; }
.pill.st-excused.active { background: #777; }

.note-input {
  width: 100%; padding: 6px 8px; border: 1px solid #d0d7e2; border-radius: 6px;
  font-family: 'Inter', sans-serif; font-size: 13px;
}

.summary { display: flex; gap: 10px; flex-wrap: wrap; margin-bottom: 14px; }
.chip {
  padding: 6px 14px; border-radius: 999px; font-size: 12px;
  background: #f0f0f0; color: #444;
}
.chip.st-present { background: #d4edda; color: #155724; }
.chip.st-absent  { background: #f5d6d6; color: #842029; }
.chip.st-late    { background: #fde8c8; color: #7a4d00; }
.chip.st-excused { background: #e0e0e0; color: #444; }

.child-block { margin-bottom: 24px; }
.child-block h3 { color: #185FA5; margin: 0 0 10px; font-size: 15px; }

@media (max-width: 700px) {
  table.roster .st-name { width: auto; font-size: 12px; }
  /* drop the note column to free horizontal space */
  table.roster th:nth-child(3), table.roster td:nth-child(3) { display: none; }
  .pill { padding: 6px 10px; font-size: 11px; }
}
@media (max-width: 480px) {
  .pills { flex-direction: column; align-items: stretch; }
  .pill { text-align: center; }
  table.roster th, table.roster td { padding: 6px 4px; }
  table.self  th, table.self  td { padding: 6px 4px; font-size: 12px; }
  .toolbar { gap: 8px; }
  .toolbar select, .toolbar input { font-size: 13px; }
  .summary { gap: 6px; }
  .chip { padding: 4px 10px; font-size: 11px; }
}
</style>
