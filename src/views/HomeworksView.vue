<script setup>
import { ref, computed, onMounted, onUnmounted, watch, nextTick } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { setCookie, getCookie } from '../utils/cookies.js'
import { homeworksGql, homeworksApi, createWebSocket, offline, pendingOps } from '../api.js'
import { hasPerm } from '../utils/auth.js'

// admin can add and delete, normal user can only read
const canCreate = computed(() => hasPerm('homework_create'))
const canDelete = computed(() => hasPerm('homework_delete'))

const router = useRouter()

// gold challenge, infinite scroll
// we grab one page at a time and also prefetch the next one in the background
// so when the user scrolls to the bottom the next page is already ready
const PAGE_SIZE = 20

const homeworksList = ref([])
const nextPage      = ref(1)
const totalPages    = ref(1)
const prefetched    = ref(null)  // the page we loaded ahead of time
const loading       = ref(false)
const sentinel      = ref(null)  // the div at the bottom that triggers a new fetch
let   observer      = null
const loadedIds     = new Set()  // stops the same homework showing up twice

const showConfirm = ref(false)
const pendingDeleteId = ref(null)
const pendingDeleteTitle = ref('')
const welcomeMessage = ref('')

const today = new Date()
today.setHours(0, 0, 0, 0)

let ws = null
let afterEachUnregister = null

// grabs one page through graphql, same data the rest endpoint would return
async function fetchPage(page) {
  return await homeworksGql.page(page, PAGE_SIZE)
}

// tacks the new rows onto the list, skips duplicates
function appendPage(data) {
  totalPages.value = data.totalPages
  for (const hw of data.items) {
    if (!loadedIds.has(hw.id)) {
      loadedIds.add(hw.id)
      homeworksList.value.push(hw)
    }
  }
}

async function loadNext() {
  if (loading.value) return
  if (nextPage.value > totalPages.value) return
  loading.value = true
  try {
    // if we already prefetched this page just use it, no network needed
    if (prefetched.value && prefetched.value.page === nextPage.value) {
      appendPage(prefetched.value)
      prefetched.value = null
    } else {
      const data = await fetchPage(nextPage.value)
      appendPage(data)
    }
    nextPage.value++

    // fire off the next page in the background so it is ready for next time
    // we dont await this on purpose so the ui stays snappy
    if (nextPage.value <= totalPages.value && !prefetched.value) {
      const p = nextPage.value
      fetchPage(p).then(data => {
        // check we havent already moved past this page
        if (nextPage.value === p) prefetched.value = { page: p, ...data }
      }).catch(() => {})
    }
  } catch (e) {
    console.error('[HomeworksView] loadNext error', e)
  } finally {
    loading.value = false
  }
}

// wipes everything and starts over, used after a delete or when the websocket
// tells us new data arrived
async function reload() {
  homeworksList.value = []
  loadedIds.clear()
  nextPage.value = 1
  totalPages.value = 1
  prefetched.value = null
  await loadNext()
  // if the screen is really tall the sentinel might already be visible
  // so we keep loading untill it scrolls off screen
  await nextTick()
  await fillViewport()
}

// keeps loading pages while the sentinel is still in view
// capped at 5 extra pages so we dont accidentaly fetch the whole database
async function fillViewport() {
  let guard = 5
  while (guard-- > 0 && sentinel.value && nextPage.value <= totalPages.value) {
    const rect = sentinel.value.getBoundingClientRect()
    if (rect.top < window.innerHeight + 200) {
      await loadNext()
      await nextTick()
    } else {
      break
    }
  }
}

onMounted(async () => {
  // show a welcome toast with the last homework the user opened
  const lastViewed = getCookie('lastViewedHomework')
  if (lastViewed) {
    welcomeMessage.value = `Bine ai revenit! Ultima temă vizualizată: "${lastViewed}"`
    setTimeout(() => { welcomeMessage.value = '' }, 4000)
  }

  // jump back to the last detail page, but only once per session
  // otherwise we would be stuck in a loop if the user tried to go back to the list
  const lastPage = getCookie('lastVisitedPage')
  const alreadyRestored = sessionStorage.getItem('homeworksRestored') === '1'
  if (lastPage && lastPage !== '/homeworks' && !alreadyRestored) {
    sessionStorage.setItem('homeworksRestored', '1')
    router.push(lastPage)
    return
  }

  await reload()

  // now that the sentinel exists in the dom, watch it with an observer
  // when it comes into view we call loadNext
  await nextTick()
  if (sentinel.value) {
    observer = new IntersectionObserver((entries) => {
      for (const entry of entries) {
        if (entry.isIntersecting) loadNext()
      }
    }, { rootMargin: '200px' })
    observer.observe(sentinel.value)
  }

  // if the user navigates back here after being on a detail page, reload
  afterEachUnregister = router.afterEach((to) => {
    if (to.path === '/homeworks') reload()
  })

  // websocket tells us when the server generator made new fake homeworks
  ws = createWebSocket((data) => {
    if (data.event === 'new_batch') reload()
  })
})

onUnmounted(() => {
  if (ws) ws.close()
  if (afterEachUnregister) afterEachUnregister()
  if (observer) observer.disconnect()
})

// when the api layer comes back online, pull fresh data from the real server
watch(offline, (now) => { if (!now) reload() })

function isOverdue(dueDate) {
  return new Date(dueDate) < today
}

function goToDetail(hw) {
  setCookie('lastViewedHomework', hw.title)
  setCookie('lastVisitedPage', `/homeworks/${hw.id}`)
  router.push(`/homeworks/${hw.id}`)
}

function promptDelete(hw) {
  pendingDeleteId.value = hw.id
  pendingDeleteTitle.value = hw.title
  showConfirm.value = true
}

async function confirmDelete() {
  try {
    await homeworksApi.delete(pendingDeleteId.value)
    const id = pendingDeleteId.value
    homeworksList.value = homeworksList.value.filter(h => h.id !== id)
    loadedIds.delete(id)
  } catch (e) {
    console.error('[HomeworksView] delete error', e)
  }
  showConfirm.value = false
  pendingDeleteId.value = null
}

const hasMore = computed(() => nextPage.value <= totalPages.value)

// overdue homeworks come first, then the rest sorted by due date
// we sort whatever pages are loaded so far, new pages get re sorted on every change
const sortedHomeworks = computed(() => {
  return [...homeworksList.value].sort((a, b) => {
    const aDate = new Date(a.dueDate)
    const bDate = new Date(b.dueDate)
    const aOverdue = aDate < today
    const bOverdue = bDate < today
    if (aOverdue && !bOverdue) return -1
    if (!aOverdue && bOverdue) return 1
    return aDate - bDate
  })
})
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />

    <div v-if="offline" class="offline-banner">
      ⚠️ Ești offline (rețea sau server indisponibil).
      <span v-if="pendingOps > 0"> {{ pendingOps }} modificări în așteptare — se vor sincroniza automat.</span>
      <span v-else> Modificările vor fi sincronizate când conexiunea revine.</span>
    </div>

    <div v-if="welcomeMessage" class="welcome-toast">
      {{ welcomeMessage }}
    </div>

    <div class="content">
      <AppSidebar active="teme" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">TEME</h2>
          <button v-if="canCreate" class="btn-add" @click="router.push('/homeworks/add')">ADAUGĂ TEMĂ</button>
        </div>

        <div class="table-scroll">
          <table>
            <thead>
            <tr>
              <th>MATERIE</th>
              <th>TITLU</th>
              <th>CLASĂ</th>
              <th>DATĂ LIMITĂ</th>
              <th>ACȚIUNI</th>
            </tr>
            </thead>
            <tbody>
            <tr v-for="hw in sortedHomeworks" :key="hw.id" @click="goToDetail(hw)" :class="{ overdue: isOverdue(hw.dueDate) }">
              <td>{{ hw.subject }}</td>
              <td>{{ hw.title }}</td>
              <td>{{ hw.assignedClass }}</td>
              <td>{{ hw.dueDate }}</td>
              <td @click.stop>
                <button v-if="canDelete" class="btn-delete" @click="promptDelete(hw)">Șterge</button>
                <span v-else class="muted">—</span>
              </td>
            </tr>
            <tr v-if="homeworksList.length === 0 && !loading">
              <td colspan="5" style="text-align:center; color:#888; padding:20px;">Nicio temă găsită.</td>
            </tr>
            </tbody>
          </table>
        </div>

        <div class="scroll-sentinel" ref="sentinel">
          <span v-if="loading">Se încarcă...</span>
          <span v-else-if="!hasMore && homeworksList.length > 0" class="end-marker">— toate temele au fost încărcate —</span>
        </div>
      </div>
    </div>

    <div v-if="showConfirm" class="overlay">
      <div class="confirm-box">
        <p>Sunteți sigur/ă că vreți să ștergeți tema "{{ pendingDeleteTitle }}"?</p>
        <div class="confirm-actions">
          <button class="btn-delete" @click="confirmDelete">Șterge</button>
          <button class="btn-cancel" @click="showConfirm = false">Anulează</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.offline-banner { background-color: #cc0000; color: white; text-align: center; padding: 10px; font-family: 'Inter', sans-serif; font-size: clamp(12px, 1.4vw, 14px); font-weight: 700; }
.content { display: flex; align-items: flex-start; }
.main { flex: 1; min-width: 0; padding: clamp(12px, 2.5vw, 24px); font-family: 'Inter', sans-serif; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: 16px; padding-right: clamp(40px, 6vw, 80px); gap: 12px; flex-wrap: wrap; }
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; }
.btn-add { background-color: #2a9d2a; color: white; border: none; padding: clamp(8px, 1.2vw, 10px) clamp(14px, 2.5vw, 24px); border-radius: 8px; cursor: pointer; font-size: clamp(13px, 1.4vw, 16px); font-family: 'Inter', sans-serif; }
.btn-add:hover { background-color: #228022; }
.btn-delete { background-color: #cc0000; color: white; border: none; padding: clamp(5px, 0.8vw, 6px) clamp(10px, 1.5vw, 14px); border-radius: 6px; cursor: pointer; font-family: 'Inter', sans-serif; font-size: clamp(12px, 1.2vw, 14px); }
.btn-delete:hover { background-color: #a00000; }
.table-scroll { overflow-x: auto; -webkit-overflow-scrolling: touch; }
table { width: 100%; border-collapse: collapse; min-width: 520px; }
th { background-color: #185FA5; color: white; padding: clamp(6px, 1vw, 10px); text-align: center; font-size: clamp(11px, 1.2vw, 14px); }
td { padding: clamp(6px, 1vw, 10px); border-bottom: 1px solid #ccc; text-align: center; font-size: clamp(11px, 1.2vw, 14px); }
tr:hover { background-color: #f0f0f0; cursor: pointer; }
tr.overdue td { color: #cc0000; font-weight: 700; }
.scroll-sentinel { height: 40px; display: flex; align-items: center; justify-content: center; color: #888; font-size: 13px; margin-top: 8px; }
.end-marker { color: #aaa; font-style: italic; }
.overlay { position: fixed; top: 0; left: 0; width: 100vw; height: 100vh; background: rgba(0,0,0,0.4); display: flex; align-items: center; justify-content: center; z-index: 1000; padding: 16px; }
.confirm-box { background: white; padding: clamp(20px, 4vw, 32px); border-radius: 12px; text-align: center; font-family: 'Inter', sans-serif; font-size: clamp(14px, 1.8vw, 18px); max-width: 420px; width: 100%; }
.confirm-actions { display: flex; justify-content: center; gap: 12px; margin-top: 20px; flex-wrap: wrap; }
.btn-cancel { background-color: #888; color: white; border: none; padding: clamp(8px, 1.2vw, 10px) clamp(14px, 2.5vw, 24px); border-radius: 8px; cursor: pointer; font-size: clamp(13px, 1.4vw, 16px); font-family: 'Inter', sans-serif; }
.btn-cancel:hover { background-color: #666; }
.welcome-toast { position: fixed; bottom: clamp(12px, 2vw, 24px); right: clamp(12px, 2vw, 24px); left: clamp(12px, 2vw, 24px); max-width: 360px; margin-left: auto; background-color: #185FA5; color: white; padding: clamp(10px, 1.5vw, 14px) clamp(16px, 2vw, 24px); border-radius: 10px; font-family: 'Inter', sans-serif; font-size: clamp(13px, 1.4vw, 15px); z-index: 999; box-shadow: 0 4px 12px rgba(0,0,0,0.2); }
</style>
