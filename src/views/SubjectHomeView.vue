<script setup>
// Per-subject channel hub (MS-Teams-style). User clicks a subject card on
// /main, lands here. Four tabs inside:
//   - Anunțuri  (text posts, like a Teams channel chat)
//   - Orar      (the weekly timetable for the class, this subject highlighted)
//   - Prezență  (attendance: teacher marks; student/parent reads)
//   - Resurse   (file uploads by the teacher, downloadable by everyone)
//
// The class is resolved from /channels/mine. If the user has access to more
// than one (class, subject) pair (admin/teacher with multiple classes), a
// picker shows up at the top.
import { ref, computed, onMounted, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import {
  channelsApi, timetableApi, attendanceApi, lookups,
} from '../api.js'
import { currentUser } from '../utils/auth.js'

const route  = useRoute()
const router = useRouter()

const subjectId   = computed(() => parseInt(route.params.subjectId))
const subjectName = ref(route.query.name || '')
const myChannels  = ref([])
const pickedClassId = ref(null)
const tab = ref('anunturi')  // anunturi | orar | prezenta | resurse

const role = computed(() => currentUser.value?.role || null)
const isTeacherSide = computed(() => role.value === 'admin' || role.value === 'teacher' || role.value === 'user')

const channelsForSubject = computed(() => {
  return myChannels.value.filter(c => c.subjectId === subjectId.value)
})

const currentChannel = computed(() => {
  return channelsForSubject.value.find(c => c.classId === pickedClassId.value) || null
})

// ─── Anunțuri tab state ──────────────────────────────────────────────
const feed     = ref(null)
const draft    = ref('')
const posting  = ref(false)

// ─── Orar tab state ──────────────────────────────────────────────────
const timetable = ref(null)

// ─── Prezență tab state ──────────────────────────────────────────────
const roster  = ref([])
const attDate = ref(new Date().toISOString().slice(0, 10))
const marks   = ref({})
const attSaving = ref(false)
const attMsg  = ref('')
const myAttendance = ref(null)
const STATUSES = [
  { value: 'present', label: 'Prezent',   cls: 'st-present' },
  { value: 'absent',  label: 'Absent',    cls: 'st-absent'  },
  { value: 'late',    label: 'Întârziat', cls: 'st-late'    },
  { value: 'excused', label: 'Motivat',   cls: 'st-excused' },
]

// ─── Resurse tab state ───────────────────────────────────────────────
const filePick = ref(null)
const uploading = ref(false)
const errMsg = ref('')


async function resolveChannels() {
  try {
    myChannels.value = await channelsApi.mine()
  } catch (e) {
    myChannels.value = []
  }
  // pick a class for this subject
  const list = channelsForSubject.value
  if (list.length > 0) pickedClassId.value = list[0].classId
  // best-effort fill of the subject name
  if (!subjectName.value && list.length > 0) {
    subjectName.value = list[0].subjectName
  }
  // also pull the subject name from lookups if we still don't have it
  if (!subjectName.value) {
    try {
      const all = await lookups.subjects()
      const m = all.find(s => s.id === subjectId.value)
      if (m) subjectName.value = m.name
    } catch {}
  }
  await loadTab()
}

async function loadTab() {
  errMsg.value = ''
  if (!currentChannel.value) return
  if (tab.value === 'anunturi' || tab.value === 'resurse') {
    try {
      feed.value = await channelsApi.feed(currentChannel.value.classId, currentChannel.value.subjectId)
    } catch (e) {
      errMsg.value = e.message || 'Eroare'
    }
  } else if (tab.value === 'orar') {
    try {
      timetable.value = await timetableApi.get(currentChannel.value.className)
    } catch (e) {
      errMsg.value = e.message || 'Eroare'
    }
  } else if (tab.value === 'prezenta') {
    if (isTeacherSide.value) {
      try {
        const [r, existing] = await Promise.all([
          attendanceApi.roster(currentChannel.value.classId),
          attendanceApi.listForClass(currentChannel.value.classId, attDate.value),
        ])
        roster.value = r
        const next = {}
        for (const st of r) next[st.userId] = { status: 'present', note: '' }
        for (const row of existing) {
          if (next[row.studentUserId]) {
            next[row.studentUserId] = { status: row.status, note: row.note || '' }
          }
        }
        marks.value = next
      } catch (e) {
        errMsg.value = e.message || 'Eroare'
      }
    } else {
      try {
        myAttendance.value = await attendanceApi.mine()
      } catch (e) {
        errMsg.value = e.message || 'Eroare'
      }
    }
  }
}

function switchTab(t) {
  tab.value = t
  loadTab()
}

// ─── Anunțuri actions ────────────────────────────────────────────────
async function sendPost() {
  if (!currentChannel.value || !draft.value.trim()) return
  posting.value = true
  try {
    await channelsApi.postText(currentChannel.value.classId, currentChannel.value.subjectId, draft.value.trim())
    draft.value = ''
    await loadTab()
  } catch (e) {
    errMsg.value = e.message || 'Eroare la trimitere'
  } finally {
    posting.value = false
  }
}

async function deletePost(post) {
  if (!confirm('Sigur ștergi această postare?')) return
  try { await channelsApi.deletePost(post.id); await loadTab() }
  catch (e) { alert(e.message || 'Eroare') }
}

// ─── Resurse actions ─────────────────────────────────────────────────
function onPickFile(e) { filePick.value = e.target.files[0] || null }
async function uploadResource() {
  if (!currentChannel.value || !filePick.value) return
  uploading.value = true
  try {
    await channelsApi.uploadFile(currentChannel.value.classId, currentChannel.value.subjectId, filePick.value)
    filePick.value = null
    const el = document.querySelector('input[type="file"].res-file')
    if (el) el.value = ''
    await loadTab()
  } catch (e) {
    errMsg.value = e.message || 'Eroare la încărcare'
  } finally {
    uploading.value = false
  }
}
async function downloadResource(p) {
  try { await channelsApi.downloadFile(p.id, p.fileName || 'fisier') }
  catch (e) { alert(e.message || 'Eroare') }
}

// ─── Prezență actions ────────────────────────────────────────────────
async function saveAttendance() {
  if (!currentChannel.value) return
  attSaving.value = true
  attMsg.value = ''
  try {
    const payload = roster.value.map(st => ({
      studentUserId: st.userId,
      status: marks.value[st.userId]?.status || 'present',
      note:   marks.value[st.userId]?.note || null,
    }))
    const r = await attendanceApi.bulkMark(currentChannel.value.classId, attDate.value, payload)
    attMsg.value = `Salvat (${r.affected} elevi).`
    setTimeout(() => { attMsg.value = '' }, 3000)
  } catch (e) {
    attMsg.value = e.message || 'Eroare'
  } finally {
    attSaving.value = false
  }
}

watch(() => attDate.value, () => { if (tab.value === 'prezenta') loadTab() })
watch(() => pickedClassId.value, () => loadTab())

onMounted(resolveChannels)
watch(() => route.params.subjectId, resolveChannels)

// utility filters / formatters
function fmtTime(iso) {
  if (!iso) return ''
  const d = new Date(iso); if (isNaN(d.getTime())) return iso
  const now = new Date()
  const sameDay = d.toDateString() === now.toDateString()
  const hh = String(d.getHours()).padStart(2, '0')
  const mm = String(d.getMinutes()).padStart(2, '0')
  if (sameDay) return `azi ${hh}:${mm}`
  const yyyy = d.getFullYear()
  const mo = String(d.getMonth() + 1).padStart(2, '0')
  const dd = String(d.getDate()).padStart(2, '0')
  return `${yyyy}-${mo}-${dd} ${hh}:${mm}`
}
const onlyPosts = computed(() => (feed.value?.posts || []).filter(p => p.kind === 'post'))
const onlyFiles = computed(() => (feed.value?.posts || []).filter(p => p.kind === 'file'))

function statusClass(s) { return STATUSES.find(x => x.value === s)?.cls || '' }
function statusLabel(s) { return STATUSES.find(x => x.value === s)?.label || s }
function counters(rows) {
  const c = { absent: 0, late: 0, excused: 0, present: 0 }
  for (const r of rows) c[r.status] = (c[r.status] || 0) + 1
  return c
}

const SUBJECT_COLOR = {
  'Matematică':        '#bee2ff',
  'Limba Română':      '#ffc4c4',
  'Științele naturii': '#bff0a8',
  'Limba Engleză':     '#fce58c',
  'Istorie':           '#ffc8a3',
  'Geografie':         '#a8e8f0',
  'Educație fizică':   '#d5b9f5',
}
function cellBg(s) { return s ? (SUBJECT_COLOR[s] || '#f5f5f5') : 'white' }
function highlightCell(slotSubject) {
  return slotSubject === subjectName.value && slotSubject
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="" />
      <div class="main">
        <div class="top">
          <button class="back" @click="router.push('/main')">&lt; Înapoi la materii</button>
          <div class="title-row">
            <h2>{{ subjectName || 'Materie' }}</h2>
            <div v-if="channelsForSubject.length > 1" class="class-pick">
              <label>Clasa</label>
              <select v-model.number="pickedClassId">
                <option v-for="c in channelsForSubject" :key="c.classId" :value="c.classId">
                  {{ c.className }}
                </option>
              </select>
            </div>
            <div v-else-if="currentChannel" class="class-pin">
              Clasa <b>{{ currentChannel.className }}</b>
            </div>
          </div>
        </div>

        <div v-if="!currentChannel" class="muted">
          Nu ai acces la nicio clasă pentru această materie.
        </div>

        <div v-else>
          <!-- inline tab bar -->
          <div class="tabs">
            <button :class="{ active: tab === 'anunturi' }" @click="switchTab('anunturi')">📣 ANUNȚURI</button>
            <button :class="{ active: tab === 'orar' }"     @click="switchTab('orar')">🗓️ ORAR</button>
            <button :class="{ active: tab === 'prezenta' }" @click="switchTab('prezenta')">✅ PREZENȚĂ</button>
            <button :class="{ active: tab === 'resurse' }"  @click="switchTab('resurse')">📚 RESURSE</button>
          </div>

          <div v-if="errMsg" class="api-error">{{ errMsg }}</div>

          <!-- ── ANUNȚURI tab ───────────────────────────────────────── -->
          <section v-if="tab === 'anunturi'">
            <div v-if="feed && feed.canPostText" class="composer">
              <textarea v-model="draft" rows="3"
                        placeholder="Scrie un anunț sau o întrebare..."
                        maxlength="2000"></textarea>
              <button class="btn-post" :disabled="posting || !draft.trim()" @click="sendPost">
                {{ posting ? 'Se trimite...' : 'Postează' }}
              </button>
            </div>
            <div v-if="onlyPosts.length === 0" class="muted">Niciun anunț încă.</div>
            <div v-else class="feed-list">
              <div v-for="p in onlyPosts" :key="p.id" class="feed-item">
                <div class="feed-head">
                  <span class="feed-author">{{ p.authorName }}</span>
                  <span class="feed-time">{{ fmtTime(p.createdAt) }}</span>
                </div>
                <div class="feed-text">{{ p.text }}</div>
              </div>
            </div>
          </section>

          <!-- ── ORAR tab ────────────────────────────────────────────── -->
          <section v-else-if="tab === 'orar'">
            <div v-if="!timetable" class="muted">Se încarcă orarul...</div>
            <div v-else class="grid-wrap">
              <table class="grid">
                <thead>
                  <tr>
                    <th class="time-col">Ora</th>
                    <th v-for="d in timetable.days" :key="d.day">{{ d.day }}</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="(p, pi) in timetable.periods" :key="p.period">
                    <td class="time-col">
                      <div class="p-num">{{ p.period }}</div>
                      <div class="p-time">{{ p.start }} – {{ p.end }}</div>
                    </td>
                    <td v-for="d in timetable.days" :key="d.day"
                        :class="{ highlight: highlightCell(d.slots[pi]?.subject) }"
                        :style="{ background: cellBg(d.slots[pi]?.subject) }">
                      <template v-if="d.slots[pi]?.subject">
                        <div class="subj">{{ d.slots[pi].subject }}</div>
                        <div class="teach" v-if="d.slots[pi].teachers?.length">
                          {{ d.slots[pi].teachers.join(', ') }}
                        </div>
                      </template>
                      <span v-else class="free">—</span>
                    </td>
                  </tr>
                </tbody>
              </table>
              <p class="muted small">Slot-urile evidențiate aparțin acestei materii.</p>
            </div>
          </section>

          <!-- ── PREZENȚĂ tab ────────────────────────────────────────── -->
          <section v-else-if="tab === 'prezenta'">
            <div v-if="isTeacherSide">
              <div class="att-toolbar">
                <label>Data</label>
                <input type="date" v-model="attDate" />
                <button class="btn-save" :disabled="attSaving" @click="saveAttendance">
                  {{ attSaving ? 'Se salvează...' : 'Salvează' }}
                </button>
                <span v-if="attMsg" class="msg">{{ attMsg }}</span>
              </div>
              <div v-if="roster.length === 0" class="muted">Niciun elev înregistrat pe această clasă.</div>
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

            <div v-else-if="role === 'student' && myAttendance">
              <div v-if="myAttendance.rows.length === 0" class="muted">Nu ai prezență înregistrată încă.</div>
              <div v-else>
                <div class="summary">
                  <span v-for="s in STATUSES" :key="s.value" :class="['chip', s.cls]">
                    {{ s.label }}: <b>{{ counters(myAttendance.rows)[s.value] || 0 }}</b>
                  </span>
                </div>
                <table class="self">
                  <thead><tr><th>Data</th><th>Status</th><th>Notă</th></tr></thead>
                  <tbody>
                    <tr v-for="r in myAttendance.rows" :key="r.id">
                      <td>{{ r.date }}</td>
                      <td><span :class="['pill', statusClass(r.status)]">{{ statusLabel(r.status) }}</span></td>
                      <td>{{ r.note || '—' }}</td>
                    </tr>
                  </tbody>
                </table>
              </div>
            </div>

            <div v-else-if="role === 'parent' && myAttendance">
              <div v-for="ch in myAttendance.children" :key="ch.userId" class="child-block">
                <h3>{{ ch.name }} <span class="muted small">({{ ch.class?.name || '—' }})</span></h3>
                <div v-if="ch.rows.length === 0" class="muted">Nicio prezență.</div>
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
          </section>

          <!-- ── RESURSE tab ─────────────────────────────────────────── -->
          <section v-else-if="tab === 'resurse'">
            <div v-if="feed && feed.canPostFile" class="uploader">
              <label class="upl-label">📚 Încarcă resursă (max 5 MB)</label>
              <div class="upl-row">
                <input class="res-file" type="file" @change="onPickFile" />
                <button class="btn-upl" :disabled="uploading || !filePick" @click="uploadResource">
                  {{ uploading ? 'Se încarcă...' : 'Încarcă' }}
                </button>
              </div>
            </div>
            <div v-if="onlyFiles.length === 0" class="muted">Nicio resursă încă.</div>
            <div v-else class="feed-list">
              <div v-for="p in onlyFiles" :key="p.id" class="feed-item file">
                <div class="feed-head">
                  <span class="feed-author">{{ p.authorName }}</span>
                  <span class="feed-time">{{ fmtTime(p.createdAt) }}</span>
                </div>
                <div class="feed-file">
                  <span class="file-icon">📎</span>
                  <span class="file-name">{{ p.fileName }}</span>
                  <button class="btn-dl" @click="downloadResource(p)">Descarcă</button>
                </div>
              </div>
            </div>
          </section>
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
.top { margin-bottom: 16px; }
.back {
  background: none; border: none; color: #185FA5; font-weight: 700;
  cursor: pointer; padding: 0; font-family: 'Inter', sans-serif; font-size: 13px;
  margin-bottom: 8px;
}
.back:hover { text-decoration: underline; }
.title-row { display: flex; align-items: center; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
.title-row h2 { color: #185FA5; margin: 0; font-size: clamp(20px, 3vw, 28px); }
.class-pick { display: flex; align-items: center; gap: 8px; }
.class-pick label { color: #185FA5; font-weight: 700; font-size: 13px; }
.class-pick select {
  padding: 6px 10px; border: 1px solid #d0d7e2; border-radius: 6px; background: white;
  font-family: 'Inter', sans-serif; font-size: 13px;
}
.class-pin { color: #555; font-size: 14px; }

.muted { color: #888; padding: 12px 0; }
.muted.small { font-size: 12px; }
.api-error { background: #ffe5e5; color: #cc0000; padding: 8px 12px; border-radius: 8px; margin-bottom: 12px; }

.tabs {
  display: flex; gap: 6px; margin-bottom: 16px; flex-wrap: wrap;
  border-bottom: 2px solid #e0e6ee;
}
.tabs button {
  background: none; border: none; padding: 10px 16px;
  cursor: pointer; font-family: 'Inter', sans-serif; font-weight: 700;
  font-size: 14px; color: #555;
  border-bottom: 3px solid transparent;
  margin-bottom: -2px;
}
.tabs button:hover { color: #185FA5; }
.tabs button.active { color: #185FA5; border-bottom-color: #185FA5; }

/* Anunțuri */
.composer {
  background: white; border: 1px solid #d0d7e2; border-radius: 10px;
  padding: 12px; margin-bottom: 16px;
}
.composer textarea {
  width: 100%; box-sizing: border-box; padding: 8px;
  border: 1px solid #d0d7e2; border-radius: 8px;
  font-family: 'Inter', sans-serif; font-size: 13px;
}
.btn-post {
  background: #2a9d2a; color: white; border: none; padding: 8px 18px;
  border-radius: 8px; cursor: pointer; margin-top: 8px; font-weight: 700;
  font-family: 'Inter', sans-serif;
}
.btn-post:disabled { opacity: 0.4; cursor: not-allowed; }

.feed-list { display: flex; flex-direction: column; gap: 10px; }
.feed-item {
  background: white; border: 1px solid #eef2f8; border-radius: 10px;
  padding: 10px 14px;
}
.feed-item.file { background: #fef9ec; border-color: #f1e3b6; }
.feed-head { display: flex; justify-content: space-between; }
.feed-author { font-weight: 700; color: #185FA5; font-size: 13px; }
.feed-time { color: #888; font-size: 11px; }
.feed-text { font-size: 14px; color: #333; margin-top: 6px; white-space: pre-wrap; word-break: break-word; }
.feed-file { display: flex; align-items: center; gap: 10px; margin-top: 6px; flex-wrap: wrap; }
.file-icon { font-size: 18px; }
.file-name { font-weight: 700; color: #444; flex: 1; word-break: break-all; }
.btn-dl, .btn-upl {
  background: #185FA5; color: white; border: none; padding: 6px 14px;
  border-radius: 6px; cursor: pointer; font-weight: 700; font-size: 12px;
  font-family: 'Inter', sans-serif;
}

/* Orar */
.grid-wrap { overflow-x: auto; }
table.grid { border-collapse: separate; border-spacing: 6px; width: 100%; min-width: 700px; }
table.grid th { background: #185FA5; color: white; padding: 10px 8px; border-radius: 8px; font-size: 13px; }
table.grid td {
  background: white; border: 1px solid #e0e6ee; border-radius: 8px;
  padding: 10px 8px; min-width: 110px; vertical-align: middle; text-align: center;
}
table.grid td.highlight {
  box-shadow: 0 0 0 3px #2a9d2a;
  position: relative;
}
.time-col { min-width: 80px; background: #fbfbfb !important; font-weight: 700; color: #185FA5; }
.p-num { font-size: 16px; }
.p-time { font-size: 11px; color: #888; font-weight: normal; margin-top: 2px; }
.subj { font-weight: 700; color: #333; font-size: 13px; }
.teach { font-size: 11px; color: #555; margin-top: 4px; }
.free { color: #ccc; font-size: 16px; }

/* Prezență */
.uploader {
  background: #f7faff; border: 1px dashed #b0c4de; border-radius: 8px;
  padding: 10px 14px; margin-bottom: 16px;
}
.upl-label { display: block; font-size: 12px; color: #185FA5; font-weight: 700; margin-bottom: 6px; }
.upl-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.att-toolbar { display: flex; align-items: center; gap: 12px; flex-wrap: wrap; margin-bottom: 14px; }
.att-toolbar label { color: #185FA5; font-weight: 700; font-size: 13px; }
.att-toolbar input { padding: 6px 10px; border: 1px solid #d0d7e2; border-radius: 6px; font-family: 'Inter', sans-serif; font-size: 13px; }
.btn-save { background: #2a9d2a; color: white; border: none; padding: 8px 18px; border-radius: 8px; cursor: pointer; font-weight: 700; font-family: 'Inter', sans-serif; }
.btn-save:disabled { opacity: 0.5; }
.msg { color: #185FA5; font-size: 13px; }

table.roster, table.self {
  width: 100%; border-collapse: collapse;
  background: white; border: 1px solid #e0e6ee; border-radius: 10px; overflow: hidden;
}
table.roster th, table.self th { background: #185FA5; color: white; padding: 10px; text-align: left; font-size: 13px; }
table.roster td, table.self td { padding: 10px; border-bottom: 1px solid #f0f3f7; font-size: 13px; vertical-align: middle; }
.st-name { font-weight: 700; color: #185FA5; width: 200px; }
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
.chip { padding: 6px 14px; border-radius: 999px; font-size: 12px; background: #f0f0f0; color: #444; }
.chip.st-present { background: #d4edda; color: #155724; }
.chip.st-absent  { background: #f5d6d6; color: #842029; }
.chip.st-late    { background: #fde8c8; color: #7a4d00; }
.chip.st-excused { background: #e0e0e0; color: #444; }
.child-block { margin-bottom: 24px; }
.child-block h3 { color: #185FA5; margin: 0 0 10px; font-size: 15px; }
</style>
