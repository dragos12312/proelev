<script setup>
// ANUNȚURI view — MS Teams style. Left column: every (class, subject)
// channel the user has access to, sorted by most recent activity. Right
// column: the picked channel's feed (posts + resources) plus a composer.
import { ref, computed, onMounted, watch, nextTick } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { channelsApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const route  = useRoute()
const router = useRouter()

const channels   = ref([])
const picked     = ref(null)   // { classId, subjectId, className, subjectName }
const feed       = ref(null)
const loadingCh  = ref(false)
const errMsg     = ref('')

const draft      = ref('')
const filePick   = ref(null)
const fileBusy   = ref(false)
const postBusy   = ref(false)

async function loadChannels() {
  try {
    channels.value = await channelsApi.mine()
  } catch (e) {
    errMsg.value = e.message || 'Eroare la încărcarea canalelor'
  }
}

async function openChannel(ch) {
  picked.value = ch
  loadingCh.value = true
  errMsg.value = ''
  try {
    feed.value = await channelsApi.feed(ch.classId, ch.subjectId)
    // sync the URL so the picked channel is shareable / refreshable
    router.replace({ path: `/channels/${ch.classId}/${ch.subjectId}` })
  } catch (e) {
    errMsg.value = e.message || 'Eroare'
  } finally {
    loadingCh.value = false
  }
}

async function sendPost() {
  if (!picked.value || !draft.value.trim()) return
  postBusy.value = true
  try {
    await channelsApi.postText(picked.value.classId, picked.value.subjectId, draft.value.trim())
    draft.value = ''
    await openChannel(picked.value)
    await loadChannels()
  } catch (e) {
    errMsg.value = e.message || 'Eroare la trimitere'
  } finally {
    postBusy.value = false
  }
}

function onPickFile(e) {
  filePick.value = e.target.files[0] || null
}

async function uploadFile() {
  if (!picked.value || !filePick.value) return
  fileBusy.value = true
  try {
    await channelsApi.uploadFile(picked.value.classId, picked.value.subjectId, filePick.value)
    filePick.value = null
    // reset the actual file input element
    const el = document.querySelector('input[type="file"].ch-file')
    if (el) el.value = ''
    await openChannel(picked.value)
    await loadChannels()
  } catch (e) {
    errMsg.value = e.message || 'Eroare la încărcare'
  } finally {
    fileBusy.value = false
  }
}

async function downloadFile(post) {
  try {
    await channelsApi.downloadFile(post.id, post.fileName || 'fisier')
  } catch (e) {
    alert(e.message || 'Eroare la descărcare')
  }
}

async function deletePost(post) {
  if (!confirm('Sigur ștergi această postare?')) return
  try {
    await channelsApi.deletePost(post.id)
    await openChannel(picked.value)
    await loadChannels()
  } catch (e) {
    alert(e.message || 'Eroare la ștergere')
  }
}

function canDelete(post) {
  const role = currentUser.value?.role
  if (role === 'admin') return true
  if (post.authorId === currentUser.value?.id) return true
  // teacher who owns the channel sees a delete on everything; we approximate
  // by checking the feed's canPostFile flag (only teachers/admin have it)
  if (role === 'teacher' && feed.value?.canPostFile) return true
  return false
}

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

onMounted(async () => {
  await loadChannels()
  // if the URL came with /channels/:classId/:subjectId, auto-pick it
  const c = parseInt(route.params.classId)
  const s = parseInt(route.params.subjectId)
  if (!isNaN(c) && !isNaN(s)) {
    const match = channels.value.find(ch => ch.classId === c && ch.subjectId === s)
    if (match) await openChannel(match)
  } else if (channels.value.length > 0) {
    await openChannel(channels.value[0])
  }
})
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="anunturi" />
      <div class="main">
        <h2 class="page-title">ANUNȚURI</h2>
        <div v-if="errMsg" class="api-error">{{ errMsg }}</div>

        <div class="layout">
          <!-- LEFT: channel list -->
          <div class="ch-list">
            <div v-if="channels.length === 0" class="muted small">
              Niciun canal disponibil.
            </div>
            <div v-for="ch in channels" :key="`${ch.classId}-${ch.subjectId}`"
                 :class="['ch-item', { active: picked && picked.classId === ch.classId && picked.subjectId === ch.subjectId }]"
                 @click="openChannel(ch)">
              <div class="ch-title">{{ ch.subjectName }}</div>
              <div class="ch-sub">Clasa {{ ch.className }}</div>
              <div class="ch-meta">{{ ch.postCount }} postări · {{ ch.fileCount }} resurse</div>
              <div v-if="ch.lastActivity" class="ch-time">{{ fmtTime(ch.lastActivity) }}</div>
            </div>
          </div>

          <!-- RIGHT: feed -->
          <div class="ch-detail">
            <div v-if="!picked" class="muted">Alege un canal din stânga.</div>
            <div v-else-if="loadingCh" class="muted">Se încarcă...</div>
            <div v-else-if="feed">
              <div class="ch-head">
                <div>
                  <div class="ch-h-title">{{ feed.subjectName }}</div>
                  <div class="ch-h-sub">Clasa {{ feed.className }}</div>
                </div>
              </div>

              <!-- Composer for text posts -->
              <div v-if="feed.canPostText" class="composer">
                <textarea rows="3" v-model="draft"
                          placeholder="Scrie un anunț sau o întrebare..."
                          maxlength="2000"></textarea>
                <div class="composer-actions">
                  <button class="btn-post" :disabled="postBusy || !draft.trim()" @click="sendPost">
                    {{ postBusy ? 'Se trimite...' : 'Postează' }}
                  </button>
                </div>
              </div>

              <!-- Resource upload, teachers + admin only -->
              <div v-if="feed.canPostFile" class="uploader">
                <label class="upl-label">📚 Încarcă resursă (PDF, imagine, etc — max 5 MB)</label>
                <div class="upl-row">
                  <input class="ch-file" type="file" @change="onPickFile" />
                  <button class="btn-upl" :disabled="fileBusy || !filePick" @click="uploadFile">
                    {{ fileBusy ? 'Se încarcă...' : 'Încarcă' }}
                  </button>
                </div>
              </div>

              <!-- Feed -->
              <div class="feed-list">
                <div v-if="feed.posts.length === 0" class="muted">Niciun anunț încă.</div>
                <div v-for="p in feed.posts" :key="p.id"
                     :class="['feed-item', { file: p.kind === 'file' }]">
                  <div class="feed-head">
                    <span class="feed-author">{{ p.authorName }}</span>
                    <span class="feed-time">{{ fmtTime(p.createdAt) }}</span>
                  </div>
                  <div v-if="p.kind === 'post'" class="feed-text">{{ p.text }}</div>
                  <div v-else class="feed-file">
                    <span class="file-icon">📎</span>
                    <span class="file-name">{{ p.fileName }}</span>
                    <button class="btn-dl" @click="downloadFile(p)">Descarcă</button>
                  </div>
                  <div class="feed-actions">
                    <button v-if="canDelete(p)" class="btn-del-small" @click="deletePost(p)">Șterge</button>
                  </div>
                </div>
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
  padding: clamp(12px, 2.5vw, 24px);
  padding-right: clamp(40px, 6vw, 80px);
  font-family: 'Inter', sans-serif;
}
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; margin-bottom: 16px; }
.muted { color: #888; padding: 12px 0; font-size: 14px; }
.muted.small { font-size: 12px; }
.api-error { background: #ffe5e5; color: #cc0000; border: 1px solid #cc0000; border-radius: 8px; padding: 10px 16px; margin: 8px 0; }

.layout {
  display: grid;
  grid-template-columns: 280px 1fr;
  gap: 16px;
  align-items: start;
  min-height: 60vh;
}
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
}

.ch-list {
  background: white; border: 1px solid #e0e6ee; border-radius: 12px;
  padding: 8px; max-height: 70vh; overflow-y: auto;
}
.ch-item {
  padding: 10px 12px; border-radius: 8px; cursor: pointer;
  transition: background 0.1s;
  border-left: 3px solid transparent;
}
.ch-item:hover { background: #f5faff; }
.ch-item.active { background: #e9f1fb; border-left-color: #185FA5; }
.ch-title { font-weight: 700; color: #185FA5; font-size: 14px; }
.ch-sub   { font-size: 12px; color: #555; }
.ch-meta  { font-size: 11px; color: #888; margin-top: 4px; }
.ch-time  { font-size: 11px; color: #999; margin-top: 2px; }

.ch-detail {
  background: white; border: 1px solid #e0e6ee; border-radius: 12px;
  padding: clamp(12px, 2vw, 18px);
}
.ch-head { padding-bottom: 12px; border-bottom: 1px solid #eef2f8; margin-bottom: 14px; }
.ch-h-title { font-weight: 700; font-size: 18px; color: #185FA5; }
.ch-h-sub   { font-size: 12px; color: #888; }

.composer textarea {
  width: 100%; box-sizing: border-box; padding: 8px; border: 1px solid #d0d7e2;
  border-radius: 8px; font-family: 'Inter', sans-serif; font-size: 13px;
}
.composer-actions { display: flex; justify-content: flex-end; margin-top: 8px; margin-bottom: 16px; }
.btn-post {
  background: #2a9d2a; color: white; border: none; padding: 8px 18px;
  border-radius: 8px; cursor: pointer; font-weight: 700; font-family: 'Inter', sans-serif;
}
.btn-post:hover:not(:disabled) { background: #228022; }
.btn-post:disabled { opacity: 0.4; cursor: not-allowed; }

.uploader {
  background: #f7faff; border: 1px dashed #b0c4de; border-radius: 8px;
  padding: 10px 14px; margin-bottom: 16px;
}
.upl-label { font-size: 12px; color: #185FA5; font-weight: 700; display: block; margin-bottom: 6px; }
.upl-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; }
.btn-upl {
  background: #185FA5; color: white; border: none; padding: 6px 14px;
  border-radius: 6px; cursor: pointer; font-weight: 700; font-family: 'Inter', sans-serif;
  font-size: 13px;
}
.btn-upl:disabled { opacity: 0.4; cursor: not-allowed; }

.feed-list { display: flex; flex-direction: column; gap: 10px; }
.feed-item {
  border: 1px solid #eef2f8; border-radius: 10px; padding: 10px 14px;
  background: #fbfcfe; position: relative;
}
.feed-item.file { background: #fef9ec; border-color: #f1e3b6; }
.feed-head { display: flex; justify-content: space-between; align-items: center; gap: 8px; }
.feed-author { font-weight: 700; color: #185FA5; font-size: 13px; }
.feed-time   { color: #888; font-size: 11px; }
.feed-text   { font-size: 14px; color: #333; margin-top: 6px; white-space: pre-wrap; word-break: break-word; }
.feed-file   { display: flex; align-items: center; gap: 10px; margin-top: 6px; flex-wrap: wrap; }
.file-icon { font-size: 18px; }
.file-name { font-weight: 700; color: #444; flex: 1; min-width: 0; word-break: break-all; }
.btn-dl {
  background: #185FA5; color: white; border: none; padding: 6px 14px;
  border-radius: 6px; cursor: pointer; font-weight: 700; font-size: 12px;
  font-family: 'Inter', sans-serif;
}
.feed-actions { display: flex; justify-content: flex-end; margin-top: 6px; }
.btn-del-small {
  background: none; border: none; color: #cc0000; cursor: pointer; font-size: 11px;
  font-family: 'Inter', sans-serif;
}
.btn-del-small:hover { text-decoration: underline; }
</style>
