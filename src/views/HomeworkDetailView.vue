<script setup>
// detail page for one homework, shows the student list with grades and a
// comments section underneath
import { ref, computed, onMounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { setCookie, getCookie, deleteCookie } from '../utils/cookies.js'
import { homeworksApi, fetchAllStudents, commentsApi } from '../api.js'
import { hasPerm } from '../utils/auth.js'

// only admins can edit a homework, the comment crud stays available to all logged in users
const canEdit = computed(() => hasPerm('homework_update'))

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
            <button class="btn-stats" @click="goToStats">STATISTICI</button>
          </div>
        </div>

        <div class="table-wrapper">
          <div class="per-page">
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
            </tr>
            </thead>
            <tbody>
            <tr v-for="(student, i) in paginatedStudents" :key="i">
              <td>{{ student.name }}</td>
              <td>{{ student.dateTime }}</td>
              <td>{{ student.grade ?? 'FĂRĂ NOTĂ' }}</td>
            </tr>
            <tr v-if="paginatedStudents.length === 0">
              <td colspan="3" style="text-align:center; color:#888;">Niciun elev găsit.</td>
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
.btn-del, .btn-cancel { background-color: #c94040; color: white; border: none; padding: 4px 10px; border-radius: 4px; cursor: pointer; font-size: clamp(10px, 1.1vw, 12px); font-weight: 700; font-family: 'Inter', sans-serif; }
.btn-del:hover, .btn-cancel:hover { background-color: #a82828; }
</style>