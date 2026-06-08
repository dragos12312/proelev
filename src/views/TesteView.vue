<script setup>
// TESTE view. Two modes:
// - teacher/admin: list of their tests + "Anunță test" form + per-test
//   gradebook with one row per student
// - student/parent: list of upcoming + past tests with their grade
import { ref, computed, onMounted } from 'vue'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { testsApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const role = computed(() => currentUser.value?.role || null)
const isTeacherSide = computed(() => role.value === 'admin' || role.value === 'teacher' || role.value === 'user')

const tests       = ref([])
const picked      = ref(null)   // currently expanded test for grading
const loading     = ref(false)
const errMsg      = ref('')

// announce form state
const assignments  = ref([])
const showForm     = ref(false)
const form         = ref({ classId: null, subjectId: null, title: '', description: '', scheduledDate: new Date().toISOString().slice(0, 10) })

// grading drafts: { [studentUserId]: { grade, feedback } }
const drafts       = ref({})
const saving       = ref(false)
const flash        = ref('')

async function reload() {
  loading.value = true
  try {
    tests.value = await testsApi.list()
  } catch (e) {
    errMsg.value = e.message || 'Eroare la încărcare'
  } finally {
    loading.value = false
  }
}

async function loadAssignments() {
  if (assignments.value.length > 0) return
  try {
    assignments.value = await testsApi.myAssignments()
    if (assignments.value.length > 0) {
      form.value.classId   = assignments.value[0].classId
      form.value.subjectId = assignments.value[0].subjectId
    }
  } catch {}
}

async function announce() {
  if (!form.value.classId || !form.value.subjectId || !form.value.title.trim()) {
    flash.value = 'Completează clasa, materia și titlul'
    return
  }
  try {
    const t = await testsApi.create({
      classId:       form.value.classId,
      subjectId:     form.value.subjectId,
      title:         form.value.title.trim(),
      description:   form.value.description.trim() || null,
      scheduledDate: form.value.scheduledDate,
    })
    flash.value = `Test anunțat: ${t.title}`
    showForm.value = false
    form.value.title = ''
    form.value.description = ''
    await reload()
    await openTest(t.id)
    setTimeout(() => { flash.value = '' }, 3000)
  } catch (e) {
    flash.value = e.message || 'Eroare'
  }
}

async function openTest(id) {
  try {
    picked.value = await testsApi.detail(id)
    // seed drafts from existing grades
    const next = {}
    for (const g of picked.value.grades) {
      next[g.studentUserId] = { grade: g.grade ?? '', feedback: g.feedback ?? '' }
    }
    drafts.value = next
  } catch (e) {
    errMsg.value = e.message || 'Eroare'
  }
}

async function saveGrade(g) {
  const draft = drafts.value[g.studentUserId]
  if (!draft) return
  saving.value = true
  try {
    const payload = { studentUserId: g.studentUserId }
    if (draft.grade !== '' && draft.grade !== null) payload.grade = parseInt(draft.grade)
    else payload.grade = null
    payload.feedback = draft.feedback || null
    await testsApi.gradeOne(picked.value.id, payload)
    await openTest(picked.value.id)
  } catch (e) {
    flash.value = e.message || 'Eroare'
  } finally {
    saving.value = false
  }
}

async function saveAll() {
  if (!picked.value) return
  saving.value = true
  try {
    const list = picked.value.grades.map(g => ({
      studentUserId: g.studentUserId,
      grade:    drafts.value[g.studentUserId]?.grade === '' || drafts.value[g.studentUserId]?.grade === null
                ? null : parseInt(drafts.value[g.studentUserId].grade),
      feedback: drafts.value[g.studentUserId]?.feedback || null,
    }))
    const r = await testsApi.gradeBulk(picked.value.id, list)
    flash.value = `Salvat (${r.updated} elevi).`
    setTimeout(() => { flash.value = '' }, 3000)
    await openTest(picked.value.id)
  } catch (e) {
    flash.value = e.message || 'Eroare'
  } finally {
    saving.value = false
  }
}

function gradeClass(g) {
  if (g === null || g === undefined) return 'no-grade'
  return g >= 5 ? 'pass' : 'fail'
}

onMounted(async () => {
  await reload()
  if (isTeacherSide.value) await loadAssignments()
})
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="teste" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">TESTE</h2>
          <div v-if="isTeacherSide" class="actions">
            <button class="btn-add" @click="showForm = !showForm">
              {{ showForm ? 'Închide' : 'Anunță test' }}
            </button>
          </div>
        </div>

        <div v-if="errMsg" class="api-error">{{ errMsg }}</div>
        <div v-if="flash"  class="info">{{ flash }}</div>

        <!-- Announce form (teacher/admin) -->
        <div v-if="isTeacherSide && showForm" class="form-card">
          <h3>Anunță un test nou</h3>
          <div class="form-grid">
            <div class="field">
              <label>Clasă · materie</label>
              <select v-model="form.classId" @change="form.subjectId = assignments.find(a => a.classId === form.classId)?.subjectId">
                <option v-for="a in assignments" :key="`${a.classId}-${a.subjectId}`"
                        :value="a.classId">{{ a.className }} · {{ a.subjectName }}</option>
              </select>
            </div>
            <div class="field">
              <label>Titlu</label>
              <input v-model="form.title" type="text" placeholder="ex: Test capitolul fracții" />
            </div>
            <div class="field">
              <label>Dată (poate fi în trecut)</label>
              <input v-model="form.scheduledDate" type="date" />
            </div>
            <div class="field full">
              <label>Descriere (opțional)</label>
              <textarea v-model="form.description" rows="2" placeholder="ce intră, materiale ce trebuie aduse, etc."></textarea>
            </div>
          </div>
          <button class="btn-go" @click="announce">Anunță</button>
        </div>

        <div v-if="loading" class="muted">Se încarcă...</div>

        <!-- Test list -->
        <div v-else-if="tests.length === 0" class="muted">Niciun test încă.</div>
        <div v-else class="test-list">
          <div v-for="t in tests" :key="t.id"
               :class="['test-card', { picked: picked && picked.id === t.id }]"
               @click="openTest(t.id)">
            <div class="t-head">
              <div>
                <div class="t-title">{{ t.title }}</div>
                <div class="t-meta">{{ t.subjectName }} · {{ t.className }} · {{ t.scheduledDate }}</div>
              </div>
              <div class="t-by">de {{ t.createdByName || '—' }}</div>
            </div>
            <div v-if="t.description" class="t-desc">{{ t.description }}</div>
          </div>
        </div>

        <!-- Picked test detail -->
        <div v-if="picked" class="detail-card">
          <div class="detail-head">
            <h3>{{ picked.title }} <span class="muted">— {{ picked.subjectName }} · {{ picked.className }} · {{ picked.scheduledDate }}</span></h3>
            <button v-if="isTeacherSide" class="btn-save" :disabled="saving" @click="saveAll">
              {{ saving ? 'Se salvează...' : 'Salvează toate notele' }}
            </button>
          </div>

          <table>
            <thead>
              <tr>
                <th>Elev</th>
                <th>Notă</th>
                <th v-if="isTeacherSide">Feedback</th>
                <th v-if="isTeacherSide"></th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="g in picked.grades" :key="g.id">
                <td class="st-name">{{ g.studentName }}</td>
                <td>
                  <template v-if="isTeacherSide">
                    <input class="grade-input" type="number" min="1" max="10"
                           v-model="drafts[g.studentUserId].grade" />
                  </template>
                  <template v-else>
                    <span :class="['grade-cell', gradeClass(g.grade)]">
                      {{ g.grade === null || g.grade === undefined ? '—' : g.grade }}
                    </span>
                  </template>
                </td>
                <td v-if="isTeacherSide">
                  <textarea class="feedback-input" rows="1"
                            v-model="drafts[g.studentUserId].feedback"
                            placeholder="ex: foarte bună prezentarea"></textarea>
                </td>
                <td v-if="isTeacherSide">
                  <button class="btn-row" @click="saveGrade(g)" :disabled="saving">Salvează</button>
                </td>
              </tr>
              <tr v-if="picked.grades.length === 0">
                <td :colspan="isTeacherSide ? 4 : 2" class="muted small" style="text-align:center;">
                  Niciun elev de notat încă.
                </td>
              </tr>
            </tbody>
          </table>
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
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; flex-wrap: wrap; gap: 12px; }
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; }
.btn-add {
  background: #2a9d2a; color: white; border: none; padding: 8px 18px;
  border-radius: 8px; cursor: pointer; font-family: 'Inter', sans-serif; font-weight: 700;
}
.btn-add:hover { background: #228022; }
.muted { color: #888; padding: 12px 0; }
.muted.small { font-size: 12px; }
.info { background: #d4edda; color: #155724; padding: 8px 12px; border-radius: 8px; margin-bottom: 12px; }
.api-error { background: #ffe5e5; color: #cc0000; padding: 8px 12px; border-radius: 8px; margin-bottom: 12px; }

.form-card {
  background: white; border: 1px solid #d0d7e2; border-radius: 12px;
  padding: 16px; margin-bottom: 16px;
}
.form-card h3 { color: #185FA5; margin: 0 0 10px; font-size: 14px; }
.form-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 10px;
}
.field { display: flex; flex-direction: column; gap: 4px; }
.field.full { grid-column: 1 / -1; }
.field label { font-weight: 700; color: #185FA5; font-size: 12px; }
.field input, .field select, .field textarea {
  padding: 8px 10px; border: 1px solid #d0d7e2; border-radius: 6px;
  font-family: 'Inter', sans-serif; font-size: 13px;
}
.btn-go {
  background: #185FA5; color: white; border: none; padding: 8px 18px;
  border-radius: 8px; cursor: pointer; margin-top: 10px; font-weight: 700;
  font-family: 'Inter', sans-serif;
}
.btn-go:hover { background: #134d87; }
@media (max-width: 600px) { .form-grid { grid-template-columns: 1fr; } }

.test-list { display: grid; grid-template-columns: repeat(auto-fill, minmax(280px, 1fr)); gap: 12px; }
.test-card {
  background: white; border: 1px solid #e0e6ee; border-radius: 10px;
  padding: 12px 14px; cursor: pointer; transition: box-shadow 0.1s, border-color 0.1s;
}
.test-card:hover { box-shadow: 0 4px 12px rgba(0,0,0,0.06); }
.test-card.picked { border-color: #185FA5; background: #f5faff; }
.t-head { display: flex; justify-content: space-between; gap: 8px; }
.t-title { font-weight: 700; color: #185FA5; font-size: 14px; }
.t-meta  { font-size: 11px; color: #888; margin-top: 2px; }
.t-by    { font-size: 11px; color: #aaa; }
.t-desc  { font-size: 12px; color: #444; margin-top: 6px; white-space: pre-wrap; }

.detail-card {
  margin-top: 18px; background: white; border: 1px solid #e0e6ee; border-radius: 12px;
  padding: 16px;
}
.detail-head {
  display: flex; justify-content: space-between; align-items: center;
  gap: 10px; flex-wrap: wrap; margin-bottom: 12px;
  padding-bottom: 10px; border-bottom: 1px solid #eef2f8;
}
.detail-head h3 { margin: 0; color: #185FA5; font-size: 15px; }
.btn-save {
  background: #2a9d2a; color: white; border: none; padding: 8px 16px;
  border-radius: 8px; cursor: pointer; font-weight: 700; font-family: 'Inter', sans-serif;
}
.btn-save:disabled { opacity: 0.5; }
.btn-row {
  background: #185FA5; color: white; border: none; padding: 4px 10px;
  border-radius: 6px; cursor: pointer; font-size: 12px; font-family: 'Inter', sans-serif;
}

table { width: 100%; border-collapse: collapse; }
th { background: #185FA5; color: white; padding: 8px; text-align: left; font-size: 12px; }
td { padding: 8px; border-bottom: 1px solid #f0f3f7; font-size: 13px; }
tbody tr:last-child td { border-bottom: none; }
.st-name { font-weight: 700; color: #185FA5; width: 200px; }
.grade-input { width: 60px; padding: 4px 8px; border: 1px solid #d0d7e2; border-radius: 6px; }
.feedback-input { width: 100%; box-sizing: border-box; padding: 4px 8px; border: 1px solid #d0d7e2; border-radius: 6px; font-family: 'Inter', sans-serif; font-size: 12px; }
.grade-cell { display: inline-block; min-width: 30px; padding: 3px 10px; border-radius: 6px; font-weight: 700; }
.grade-cell.pass { background: #d4edda; color: #155724; }
.grade-cell.fail { background: #f5d6d6; color: #842029; }
.grade-cell.no-grade { background: #f0f0f0; color: #888; }
</style>
