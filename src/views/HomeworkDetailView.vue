<script setup>
// detail page for one homework, shows the student list with grades and a
// comments section underneath
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { setCookie, getCookie, deleteCookie } from '../utils/cookies.js'
import { homeworksApi, fetchAllStudents, commentsApi, submissionsApi } from '../api.js'
import { hasPerm, currentUser as authUser } from '../utils/auth.js'

// only admins/teachers can edit a homework, the comment crud stays available to all logged in users
const canEdit = computed(() => hasPerm('homework_update'))

// assignment 6, role-aware UI flags
const role = computed(() => authUser.value?.role)
const isStudent = computed(() => role.value === 'student')
const isTeacher = computed(() => role.value === 'teacher')
const isParent  = computed(() => role.value === 'parent')
const canSeeStats = computed(() => role.value === 'admin' || role.value === 'teacher' || role.value === 'user')

// submission UI state (student side)
const myRow         = computed(() => studentsList.value.find(s => s.userId === authUser.value?.id) || null)
// parent side: rows for every child of the logged-in parent (backend already
// filters the response down to the parent's children only)
const childrenRows = computed(() => {
  if (!isParent.value) return []
  // dedupe by id just in case the legacy roster also seeded a row with the same id
  const seen = new Set()
  const out = []
  for (const s of studentsList.value) {
    if (seen.has(s.id)) continue
    seen.add(s.id)
    out.push(s)
  }
  return out
})
const submissionText = ref('')
const submissionFile = ref(null)
const submissionBusy = ref(false)
const submissionError = ref('')

async function loadMySubmissionDraft() {
  if (myRow.value) {
    submissionText.value = myRow.value.submissionText || ''
  }
}

async function submitMine() {
  submissionError.value = ''
  if (!submissionText.value.trim() && !submissionFile.value) {
    submissionError.value = 'Trimite text sau atașează un fișier'
    return
  }
  submissionBusy.value = true
  try {
    await submissionsApi.submit(id.value, submissionText.value.trim(), submissionFile.value)
    submissionFile.value = null
    await loadStudents()
    await loadMySubmissionDraft()
  } catch (e) {
    submissionError.value = e.message || 'Eroare la trimitere'
  } finally {
    submissionBusy.value = false
  }
}

function onFilePicked(e) {
  const f = e.target.files[0]
  submissionFile.value = f || null
}

// teacher side, edit grade + feedback per row
const editingGrade   = ref({})   // { studentId: { grade, feedback } }
function startGrade(s) {
  editingGrade.value = {
    ...editingGrade.value,
    [s.id]: { grade: s.grade ?? '', feedback: s.feedback ?? '' },
  }
}
async function saveGrade(s) {
  const draft = editingGrade.value[s.id]
  if (!draft) return
  const body = {}
  if (draft.grade !== '' && draft.grade !== null) body.grade = parseInt(draft.grade)
  if (draft.feedback !== undefined)               body.feedback = draft.feedback
  try {
    await submissionsApi.grade(id.value, s.id, body)
    delete editingGrade.value[s.id]
    editingGrade.value = { ...editingGrade.value }
    await loadStudents()
  } catch (e) {
    alert(e.message || 'Eroare la salvare notă')
  }
}
function cancelGrade(s) {
  delete editingGrade.value[s.id]
  editingGrade.value = { ...editingGrade.value }
}

async function downloadSubmission(s) {
  try {
    await submissionsApi.downloadFile(id.value, s.id, s.submissionFileName || `tema-${s.name || s.id}`)
  } catch (e) {
    alert(e.message || 'Eroare la descărcare')
  }
}

async function loadStudents() {
  try {
    studentsList.value = await fetchAllStudents(id.value)
  } catch (e) {
    console.error('[HomeworkDetailView] students error', e)
  }
}

const router = useRouter()
const route = useRoute()

// the id comes from the url, we keep it as a computed so it updates if the route changes
const id = computed(() => parseInt(route.params.id))
const homework = ref(null)
const studentsList = ref([])
const notFound = ref(false)

// paging state for the students table
const itemsPerPage = ref(10)
const currentPage = ref(1)

// comments are 1 to many per homework, served through graphql
// we grab the logged in user from sessionStorage so their name gets auto filled
const currentUser = (() => {
  try { return JSON.parse(sessionStorage.getItem('currentUser') || 'null') }
  catch { return null }
})()
const authorName = currentUser?.name || 'Utilizator'

const comments = ref([])
const commentStats = ref(null)
const newText = ref('')
const commentError = ref('')
const editingId = ref(null)
const editText = ref('')

// fetches the comments plus the stats block on top
async function loadComments() {
  try {
    const list = await commentsApi.list(id.value)
    // newest first, the server returns them in insertion order oldest to newest
    comments.value = [...list].reverse()
    commentStats.value = await commentsApi.statistics(id.value)
  } catch (e) {
    console.error('[HomeworkDetailView] comments error', e)
  }
}

async function addComment() {
  commentError.value = ''
  try {
    await commentsApi.create(id.value, {
      author: authorName,
      text: newText.value.trim(),
    })
    newText.value = ''
    await loadComments()
  } catch (e) {
    commentError.value = e.message || 'Eroare la adăugare'
  }
}

function startEdit(c) {
  editingId.value = c.id
  editText.value = c.text
  commentError.value = ''
}

function cancelEdit() {
  editingId.value = null
  editText.value = ''
}

async function saveEdit() {
  commentError.value = ''
  try {
    await commentsApi.update(id.value, editingId.value, {
      text: editText.value.trim(),
    })
    cancelEdit()
    await loadComments()
  } catch (e) {
    commentError.value = e.message || 'Eroare la modificare'
  }
}

async function deleteComment(c) {
  if (!confirm(`Ștergi comentariul lui ${c.author}?`)) return
  try {
    await commentsApi.delete(id.value, c.id)
    await loadComments()
  } catch (e) {
    commentError.value = e.message || 'Eroare la ștergere'
  }
}

onMounted(async () => {
  // restore the last items per page setting the user picked
  const savedItemsPerPage = getCookie('itemsPerPageDetail')
  if (savedItemsPerPage) itemsPerPage.value = parseInt(savedItemsPerPage)

  const hwId = id.value
  if (!hwId || isNaN(hwId)) { notFound.value = true; return }

  // grab the homework, all its students, and all its comments
  try {
    homework.value = await homeworksApi.get(hwId)
    studentsList.value = await fetchAllStudents(hwId)
    await loadComments()
    await loadMySubmissionDraft()
  } catch (e) {
    console.error('[HomeworkDetailView] load error', e)
    notFound.value = true
  }
})

const totalPages = computed(() =>
    Math.ceil(studentsList.value.length / itemsPerPage.value)
)

const paginatedStudents = computed(() => {
  const start = (currentPage.value - 1) * itemsPerPage.value
  return studentsList.value.slice(start, start + itemsPerPage.value)
})

function setItemsPerPage(n) {
  itemsPerPage.value = n
  currentPage.value = 1
  setCookie('itemsPerPageDetail', n)
}

function goBack() {
  deleteCookie('lastVisitedPage')
  router.push('/homeworks')
}

function goToEdit() {
  router.push(`/homeworks/${id.value}/edit`)
}

function goToStats() {
  router.push(`/homeworks/${id.value}/statistics`)
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="teme" />
      <div class="main" v-if="homework">
        <div class="toolbar">
          <div class="left">
            <span class="back" @click="goBack">&lt; TEME</span>
            <span class="hw-title">{{ homework.subject.toUpperCase() }} - {{ homework.title.toUpperCase() }}</span>
          </div>
          <div class="right">
            <button v-if="canEdit" class="btn-edit" @click="goToEdit">MODIFICĂ</button>
            <button v-if="canSeeStats" class="btn-stats" @click="goToStats">STATISTICI</button>
          </div>
        </div>

        <!-- homework brief, visible to every role so they know what was assigned -->
        <div class="hw-brief">
          <div class="hw-meta">
            <span><b>Clasă:</b> {{ homework.assignedClass }}</span>
            <span><b>Materie:</b> {{ homework.subject }}</span>
            <span><b>Termen:</b> {{ homework.dueDate }}</span>
          </div>
          <div v-if="homework.description" class="hw-desc">{{ homework.description }}</div>
        </div>

        <!-- parent view, read-only per-child status, grade, feedback -->
        <div v-if="isParent" class="parent-card">
          <h3>Situația copiilor mei</h3>
          <div v-if="childrenRows.length === 0" class="muted small">
            Niciunul dintre copiii tăi nu este înscris pentru această temă.
          </div>
          <div v-for="row in childrenRows" :key="row.id" class="child-row">
            <div class="child-name">{{ row.name }}</div>
            <div class="child-stat">
              <span v-if="row.submittedAt" class="badge ok">
                Trimis pe {{ row.submittedAt.replace('T', ' ').slice(0, 16) }}
              </span>
              <span v-else class="badge no">Netrimis</span>
            </div>
            <div class="child-stat">
              Notă:
              <b v-if="row.grade !== null && row.grade !== undefined" class="grade-val">{{ row.grade }}</b>
              <span v-else class="muted">FĂRĂ NOTĂ</span>
            </div>
            <div v-if="row.feedback" class="feedback-box">
              <b>Feedback profesor:</b> {{ row.feedback }}
            </div>
          </div>
        </div>

        <!-- assignment 6: student-only submission card -->
        <div v-if="isStudent" class="submit-card">
          <h3>Tema mea</h3>
          <div v-if="myRow && myRow.submittedAt" class="muted small">
            Trimis ultima dată: {{ myRow.submittedAt.replace('T', ' ').slice(0, 16) }}
          </div>
          <div v-if="myRow && myRow.grade !== null && myRow.grade !== undefined" class="my-grade">
            Nota ta: <b>{{ myRow.grade }}</b>
          </div>
          <div v-if="myRow && myRow.feedback" class="feedback-box">
            <b>Feedback profesor:</b> {{ myRow.feedback }}
          </div>
          <textarea v-model="submissionText" rows="3" placeholder="Scrie răspunsul aici (text)"></textarea>
          <label class="file-pick">
            Atașează un fișier (opțional, max 1 MB)
            <input type="file" @change="onFilePicked" />
          </label>
          <div v-if="submissionFile" class="muted small">📎 {{ submissionFile.name }}</div>
          <p class="muted small">Trebuie să trimiți text, un fișier, sau ambele.</p>
          <div v-if="submissionError" class="api-error">{{ submissionError }}</div>
          <button class="btn-submit" :disabled="submissionBusy" @click="submitMine">
            {{ submissionBusy ? 'Se trimite...' : 'Trimite tema' }}
          </button>
        </div>

        <div v-if="!isParent" class="table-wrapper">
          <div class="per-page" v-if="!isStudent">
            Articole per pagină:
            <span v-for="n in [5, 10, 15, 20]"
                  :key="n"
                  :class="{ active: itemsPerPage === n }"
                  @click="setItemsPerPage(n)">{{ n }}</span>
          </div>

          <table>
            <thead>
            <tr>
              <th>NUME</th>
              <th>DATA/ORA</th>
              <th>NOTĂ</th>
              <th v-if="isTeacher">FEEDBACK</th>
              <th v-if="isTeacher">SUBMISIE</th>
              <th v-if="isTeacher"></th>
            </tr>
            </thead>
            <tbody>
            <tr v-for="(student, i) in paginatedStudents" :key="i">
              <td>{{ student.name }}</td>
              <td>{{ student.dateTime }}</td>
              <td>
                <template v-if="isTeacher && editingGrade[student.id]">
                  <input class="grade-input" type="number" min="1" max="10"
                         v-model="editingGrade[student.id].grade" />
                </template>
                <template v-else>
                  {{ student.grade ?? 'FĂRĂ NOTĂ' }}
                </template>
              </td>
              <td v-if="isTeacher">
                <template v-if="editingGrade[student.id]">
                  <textarea class="feedback-input" rows="2"
                            v-model="editingGrade[student.id].feedback"></textarea>
                </template>
                <template v-else>
                  <span class="muted small">{{ student.feedback || '-' }}</span>
                </template>
              </td>
              <td v-if="isTeacher">
                <div v-if="student.submittedAt">
                  <span class="muted small">{{ student.submittedAt.replace('T', ' ').slice(0, 16) }}</span>
                  <div v-if="student.submissionText" class="sub-text">{{ student.submissionText }}</div>
                  <button v-if="student.hasFile" class="btn-link"
                          @click="downloadSubmission(student)">descarcă fișier</button>
                </div>
                <span v-else class="muted small">netrimis</span>
              </td>
              <td v-if="isTeacher">
                <template v-if="editingGrade[student.id]">
                  <button class="btn-edit-small" @click="saveGrade(student)">Salvează</button>
                  <button class="btn-cancel-small" @click="cancelGrade(student)">Anulează</button>
                </template>
                <template v-else>
                  <button class="btn-edit-small" @click="startGrade(student)">Notează</button>
                </template>
              </td>
            </tr>
            <tr v-if="paginatedStudents.length === 0">
              <td :colspan="isTeacher ? 6 : 3" style="text-align:center; color:#888;">
                {{ isStudent ? 'Niciun elev de afișat aici, doar tu poți vedea propria submisie mai sus.' : 'Niciun elev găsit.' }}
              </td>
            </tr>
            </tbody>
          </table>

          <div class="pagination" v-if="totalPages > 1">
            <button @click="currentPage = 1" :disabled="currentPage === 1">&lt;&lt;</button>
            <button @click="currentPage--" :disabled="currentPage === 1">&lt;</button>
            <button v-for="p in totalPages" :key="p" :class="{ active: currentPage === p }" @click="currentPage = p">{{ p }}</button>
            <button @click="currentPage++" :disabled="currentPage === totalPages">&gt;</button>
            <button @click="currentPage = totalPages" :disabled="currentPage === totalPages">&gt;&gt;</button>
          </div>
        </div>

        <!-- ── Comments (1-to-many via GraphQL) ─────────────────────────── -->
        <div class="comments-wrapper">
          <div class="comments-header">COMENTARII</div>

          <div class="comment-stats" v-if="commentStats">
            <span>Total: <b>{{ commentStats.totalComments }}</b></span>
            <span>Autori unici: <b>{{ commentStats.uniqueAuthors }}</b></span>
            <span v-if="commentStats.topAuthor">
              Cel mai activ: <b>{{ commentStats.topAuthor }}</b>
            </span>
          </div>

          <div class="comment-form">
            <div class="comment-as">Scrii ca <b>{{ authorName }}</b></div>
            <textarea v-model="newText" placeholder="Scrie un comentariu..." maxlength="1000" rows="2"></textarea>
            <button class="btn-add" @click="addComment"
                    :disabled="!newText.trim()">
              ADAUGĂ
            </button>
          </div>
          <div class="comment-error" v-if="commentError">{{ commentError }}</div>

          <div class="comment-list">
            <div v-if="comments.length === 0" class="no-comments">Niciun comentariu încă.</div>
            <div v-for="c in comments" :key="c.id" class="comment-item">
              <template v-if="editingId === c.id">
                <textarea v-model="editText" maxlength="1000" rows="2"></textarea>
                <div class="comment-actions">
                  <button class="btn-save"   @click="saveEdit">SALVEAZĂ</button>
                  <button class="btn-cancel" @click="cancelEdit">ANULEAZĂ</button>
                </div>
              </template>
              <template v-else>
                <div class="comment-head">
                  <span class="comment-author">{{ c.author }}</span>
                  <span class="comment-date">{{ c.createdAt }}</span>
                </div>
                <div class="comment-text">{{ c.text }}</div>
                <div class="comment-actions">
                  <button class="btn-edit-small" @click="startEdit(c)">MODIFICĂ</button>
                  <button class="btn-del"        @click="deleteComment(c)">ȘTERGE</button>
                </div>
              </template>
            </div>
          </div>
        </div>
      </div>

      <div class="main" v-else-if="notFound">
        <p>Tema nu a fost găsită.</p>
      </div>

      <div class="main" v-else>
        <p>Se încarcă...</p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; }
.main { flex: 1; min-width: 0; padding: clamp(12px, 2vw, 24px); padding-right: clamp(40px, 6vw, 80px); margin-right: clamp(0px, 2vw, 20px); }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; border-bottom: 1px solid #ccc; padding-bottom: 16px; flex-wrap: wrap; gap: 12px; }
.left { display: flex; align-items: center; gap: clamp(8px, 2vw, 24px); flex-wrap: wrap; min-width: 0; }
.back { font-size: clamp(12px, 1.4vw, 16px); cursor: pointer; color: #333; font-weight: 700; }
.back:hover { color: #185FA5; }
.hw-title { font-size: clamp(13px, 1.6vw, 20px); font-weight: 700; color: #333; word-break: break-word; }
.right { display: flex; align-items: center; gap: clamp(8px, 1.5vw, 16px); flex-wrap: wrap; }
.btn-edit { background-color: #2a9d2a; color: white; border: none; padding: clamp(6px, 1vw, 10px) clamp(12px, 2vw, 24px); border-radius: 8px; cursor: pointer; font-size: clamp(12px, 1.4vw, 16px); font-weight: 700; font-family: 'Inter', sans-serif; }
.btn-edit:hover { background-color: #228022; }
.table-wrapper { border: 2px solid #185FA5; border-radius: 12px; padding: clamp(8px, 1.5vw, 16px); overflow-x: auto; }
.per-page { margin-bottom: 12px; font-size: clamp(11px, 1.2vw, 14px); color: #333; }
.per-page span { margin-left: 8px; cursor: pointer; color: #185FA5; font-weight: 700; }
.per-page span.active { text-decoration: underline; }
table { width: 100%; border-collapse: collapse; min-width: 320px; }
th { background-color: #185FA5; color: white; padding: clamp(6px, 1vw, 10px); text-align: center; font-size: clamp(11px, 1.2vw, 14px); }
td { padding: clamp(6px, 1vw, 10px); border-bottom: 1px solid #ccc; text-align: center; font-size: clamp(11px, 1.2vw, 14px); }
tr:hover { background-color: #f0f0f0; cursor: pointer; }
.pagination { display: flex; gap: 6px; margin-top: 16px; align-items: center; justify-content: center; flex-wrap: wrap; overflow-x: auto; }
.pagination button { padding: clamp(4px, 0.8vw, 6px) clamp(8px, 1vw, 12px); border: 1px solid #ccc; background: white; cursor: pointer; border-radius: 4px; font-family: 'Inter', sans-serif; font-size: clamp(11px, 1.2vw, 14px); }
.pagination button.active { background-color: #185FA5; color: white; border-color: #185FA5; }
.pagination button:disabled { opacity: 0.4; cursor: default; }
.btn-stats { background-color: #185FA5; color: white; border: none; padding: clamp(6px, 1vw, 10px) clamp(12px, 2vw, 24px); border-radius: 8px; cursor: pointer; font-size: clamp(12px, 1.4vw, 16px); font-weight: 700; font-family: 'Inter', sans-serif; }
.btn-stats:hover { background-color: #134d87; }

/* Comments section */
.comments-wrapper { border: 2px solid #185FA5; border-radius: 12px; padding: clamp(8px, 1.5vw, 16px); margin-top: 24px; }
.comments-header { font-size: clamp(13px, 1.4vw, 16px); font-weight: 700; color: #185FA5; margin-bottom: 12px; }
.comment-stats { display: flex; flex-wrap: wrap; gap: 16px; font-size: clamp(11px, 1.2vw, 14px); color: #333; margin-bottom: 14px; padding-bottom: 10px; border-bottom: 1px dashed #ccc; }
.comment-form { display: grid; grid-template-columns: 1fr; gap: 8px; margin-bottom: 10px; }
.comment-form input, .comment-form textarea,
.comment-item input, .comment-item textarea {
  padding: 8px; border: 1px solid #ccc; border-radius: 6px; font-family: 'Inter', sans-serif; font-size: clamp(11px, 1.2vw, 14px); resize: vertical;
}
.btn-add { background-color: #2a9d2a; color: white; border: none; padding: 8px 16px; border-radius: 6px; cursor: pointer; font-weight: 700; justify-self: end; font-family: 'Inter', sans-serif; }
.btn-add:disabled { background-color: #aaa; cursor: not-allowed; }
.btn-add:hover:not(:disabled) { background-color: #228022; }
.comment-error { color: #c00; font-size: clamp(11px, 1.2vw, 14px); margin-bottom: 10px; }
.comment-list { display: flex; flex-direction: column; gap: 10px; }
.no-comments { color: #888; font-size: clamp(11px, 1.2vw, 14px); text-align: center; padding: 12px; }
.comment-item { border: 1px solid #e0e0e0; border-radius: 8px; padding: 10px; background: #fafafa; display: flex; flex-direction: column; gap: 6px; }
.comment-head { display: flex; justify-content: space-between; align-items: center; font-size: clamp(11px, 1.2vw, 14px); }
.comment-author { font-weight: 700; color: #185FA5; }
.comment-date { color: #888; font-size: clamp(10px, 1.1vw, 12px); }
.comment-text { font-size: clamp(11px, 1.2vw, 14px); color: #333; white-space: pre-wrap; word-break: break-word; }
.comment-actions { display: flex; gap: 8px; justify-content: flex-end; }
.btn-edit-small, .btn-save { background-color: #185FA5; color: white; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: clamp(10px, 1.1vw, 12px); font-weight: 700; font-family: 'Inter', sans-serif; }
.btn-edit-small:hover, .btn-save:hover { background-color: #134d87; }
.btn-cancel-small {
  background: #888; color: white; border: none; padding: 4px 10px;
  border-radius: 4px; cursor: pointer; font-size: clamp(10px, 1.1vw, 12px);
  font-weight: 700; margin-left: 4px;
}
.btn-cancel-small:hover { background: #666; }

/* assignment 6, student submission card */
.submit-card {
  background: #f5faff; border: 1px solid #b0c4de; border-radius: 10px;
  padding: 16px; margin-bottom: 20px;
}
.submit-card h3 { margin: 0 0 8px; color: #185FA5; }
.submit-card textarea {
  width: 100%; box-sizing: border-box; padding: 8px;
  border: 1px solid #ccc; border-radius: 6px;
  font-family: 'Inter', sans-serif; font-size: 13px; margin: 8px 0;
}
.submit-card input[type="file"] { font-size: 12px; margin-bottom: 8px; }
.file-pick { display: block; font-size: 12px; color: #555; margin: 8px 0; }
.file-pick input[type="file"] { display: block; margin-top: 4px; }

/* homework brief shown to every role */
.hw-brief {
  background: #fbfbfb; border: 1px solid #e0e0e0; border-radius: 10px;
  padding: clamp(10px, 1.5vw, 16px); margin-bottom: 16px;
}
.hw-meta { display: flex; flex-wrap: wrap; gap: 16px; font-size: 13px; color: #333; }
.hw-desc {
  margin-top: 8px; padding-top: 8px; border-top: 1px dashed #ccc;
  font-size: 13px; color: #444; white-space: pre-wrap;
}

/* parent view card */
.parent-card {
  background: #f5faff; border: 1px solid #b0c4de; border-radius: 10px;
  padding: 16px; margin-bottom: 20px;
}
.parent-card h3 { margin: 0 0 10px; color: #185FA5; }
.child-row {
  background: white; border: 1px solid #ddd; border-radius: 8px;
  padding: 10px 14px; margin-bottom: 10px;
  display: flex; flex-wrap: wrap; align-items: center; gap: 12px;
}
.child-row:last-child { margin-bottom: 0; }
.child-name { font-weight: 700; color: #185FA5; min-width: 140px; }
.child-stat { font-size: 13px; }
.badge {
  display: inline-block; padding: 3px 10px; border-radius: 999px;
  font-size: 12px; font-weight: 700;
}
.badge.ok { background: #d4edda; color: #155724; }
.badge.no { background: #f5d6d6; color: #842029; }
.grade-val { color: #2a9d2a; font-size: 16px; }
.btn-submit {
  background: #2a9d2a; color: white; border: none;
  padding: 8px 20px; border-radius: 6px; cursor: pointer;
  font-weight: 700; font-family: 'Inter', sans-serif;
}
.btn-submit:hover { background: #228022; }
.btn-submit:disabled { opacity: 0.4; cursor: not-allowed; }
.my-grade { font-size: 18px; color: #2a9d2a; margin: 4px 0; }
.feedback-box {
  background: white; border: 1px solid #ccc; padding: 8px;
  border-radius: 6px; margin: 8px 0; font-size: 13px;
}
.muted { color: #777; }
.small { font-size: 11px; }
.grade-input {
  width: 50px; padding: 4px; border: 1px solid #ccc; border-radius: 4px;
  font-family: 'Inter', sans-serif;
}
.feedback-input {
  width: 100%; box-sizing: border-box; padding: 4px;
  border: 1px solid #ccc; border-radius: 4px; font-size: 12px;
}
.sub-text {
  font-size: 12px; color: #444; margin-top: 4px;
  background: #f7f7f7; padding: 4px 6px; border-radius: 4px;
  max-height: 60px; overflow-y: auto;
}
.btn-link {
  background: none; border: none; color: #185FA5; text-decoration: underline;
  cursor: pointer; padding: 0; margin-top: 4px; font-size: 12px;
  font-family: 'Inter', sans-serif;
}
.btn-link:hover { color: #134d87; }
.btn-del, .btn-cancel { background-color: #c94040; color: white; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: clamp(10px, 1.1vw, 12px); font-weight: 700; font-family: 'Inter', sans-serif; }
.btn-del:hover, .btn-cancel:hover { background-color: #a82828; }
</style>