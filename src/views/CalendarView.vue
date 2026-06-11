<script setup>
// CALENDAR view, month grid with homework due dates dropped onto the cells.
// Click a date to see the homeworks due that day; click a homework to jump
// to its detail page. Uses the existing /homeworks listing — no new backend.
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { homeworksApi, testsApi } from '../api.js'

const router = useRouter()

const today = new Date()
const cursor = ref(new Date(today.getFullYear(), today.getMonth(), 1))
const homeworks = ref([])
const tests = ref([])
const loading = ref(false)
const errMsg  = ref('')
const pickedDay = ref(null)

const MONTHS = ['Ianuarie', 'Februarie', 'Martie', 'Aprilie', 'Mai', 'Iunie',
                'Iulie', 'August', 'Septembrie', 'Octombrie', 'Noiembrie', 'Decembrie']
const DAYS_RO = ['Luni', 'Marți', 'Miercuri', 'Joi', 'Vineri', 'Sâmbătă', 'Duminică']

// fetch all homeworks + all tests so the grid shows both kinds of events
async function loadAll() {
  loading.value = true
  errMsg.value  = ''
  try {
    const page = await homeworksApi.list(1, 100)
    const items = Array.isArray(page?.items) ? page.items : (Array.isArray(page) ? page : [])
    homeworks.value = items
  } catch (e) {
    errMsg.value = e.message || 'Eroare la încărcare'
    homeworks.value = []
  }
  try {
    tests.value = await testsApi.list()
  } catch {
    tests.value = []
  }
  loading.value = false
}

onMounted(loadAll)

// monthly grid: 6 rows × 7 cols, starting from Monday of the week containing day 1
const grid = computed(() => {
  const y = cursor.value.getFullYear()
  const m = cursor.value.getMonth()
  const firstOfMonth = new Date(y, m, 1)
  // JS Sunday=0..Saturday=6, but we want Monday=0
  const startOffset = (firstOfMonth.getDay() + 6) % 7
  const start = new Date(y, m, 1 - startOffset)

  const rows = []
  let cur = new Date(start)
  for (let r = 0; r < 6; r++) {
    const row = []
    for (let c = 0; c < 7; c++) {
      row.push(new Date(cur))
      cur.setDate(cur.getDate() + 1)
    }
    rows.push(row)
  }
  return rows
})

function ymd(d) {
  return `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, '0')}-${String(d.getDate()).padStart(2, '0')}`
}

// fold homework + test events into one per-day list. each event carries a
// 'kind' so we can color/route differently.
const eventsByDay = computed(() => {
  const out = {}
  for (const hw of homeworks.value) {
    if (!hw.dueDate) continue
    if (!out[hw.dueDate]) out[hw.dueDate] = []
    out[hw.dueDate].push({
      kind: 'homework', id: hw.id, title: hw.title,
      subject: hw.subject, assignedClass: hw.assignedClass,
    })
  }
  for (const t of tests.value) {
    if (!t.scheduledDate) continue
    if (!out[t.scheduledDate]) out[t.scheduledDate] = []
    out[t.scheduledDate].push({
      kind: 'test', id: t.id, title: t.title,
      subject: t.subjectName, assignedClass: t.className,
    })
  }
  return out
})

function dayEvents(d) {
  return eventsByDay.value[ymd(d)] || []
}

function inCurrentMonth(d) {
  return d.getMonth() === cursor.value.getMonth()
}

function isToday(d) {
  return ymd(d) === ymd(today)
}

function prevMonth() {
  const d = new Date(cursor.value); d.setMonth(d.getMonth() - 1)
  cursor.value = d
  pickedDay.value = null
}
function nextMonth() {
  const d = new Date(cursor.value); d.setMonth(d.getMonth() + 1)
  cursor.value = d
  pickedDay.value = null
}
function goToday() {
  cursor.value = new Date(today.getFullYear(), today.getMonth(), 1)
  pickedDay.value = ymd(today)
}

function openDay(d) { pickedDay.value = ymd(d) }
function goEvent(ev) {
  if (ev.kind === 'test') router.push(`/tests`)
  else                    router.push(`/homeworks/${ev.id}`)
}

const pickedDayEvents = computed(() => {
  if (!pickedDay.value) return []
  return eventsByDay.value[pickedDay.value] || []
})

// pastel color per subject so cells are easy to scan
const SUBJECT_COLOR = {
  'Matematică':        '#bee2ff',
  'Limba Română':      '#ffc4c4',
  'Științele naturii': '#bff0a8',
  'Limba Engleză':     '#fce58c',
  'Istorie':           '#ffc8a3',
  'Geografie':         '#a8e8f0',
  'Educație fizică':   '#d5b9f5',
}
function subjColor(s) { return SUBJECT_COLOR[s] || '#cfd8e3' }
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="calendar" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">CALENDAR</h2>
          <div class="nav">
            <button @click="prevMonth">‹</button>
            <span class="title">{{ MONTHS[cursor.getMonth()] }} {{ cursor.getFullYear() }}</span>
            <button @click="nextMonth">›</button>
            <button class="today-btn" @click="goToday">Azi</button>
          </div>
        </div>

        <div v-if="errMsg" class="api-error">{{ errMsg }}</div>
        <div v-if="loading" class="muted">Se încarcă...</div>

        <div v-else class="cal-wrap">
          <div class="cal">
            <div class="cal-row head">
              <div v-for="d in DAYS_RO" :key="d" class="cal-cell head">{{ d }}</div>
            </div>
            <div v-for="(row, ri) in grid" :key="ri" class="cal-row">
              <div v-for="(d, di) in row" :key="di"
                   :class="['cal-cell', { other: !inCurrentMonth(d), today: isToday(d), picked: pickedDay === ymd(d) }]"
                   @click="openDay(d)">
                <div class="cell-num">{{ d.getDate() }}</div>
                <div class="cell-events">
                  <div v-for="ev in dayEvents(d).slice(0, 3)" :key="ev.kind + '-' + ev.id"
                       :class="['ev-dot', { 'ev-test': ev.kind === 'test' }]"
                       :style="{ background: subjColor(ev.subject) }"
                       :title="`${ev.kind === 'test' ? 'Test: ' : ''}${ev.subject} - ${ev.title}`">
                    {{ ev.kind === 'test' ? 'TEST · ' : '' }}{{ ev.title }}
                  </div>
                  <div v-if="dayEvents(d).length > 3" class="ev-more">
                    +{{ dayEvents(d).length - 3 }} mai multe
                  </div>
                </div>
              </div>
            </div>
          </div>

          <div class="day-panel">
            <div v-if="!pickedDay" class="muted small">
              Selectează o zi pentru detalii.
            </div>
            <div v-else>
              <div class="panel-head">Ziua {{ pickedDay }}</div>
              <div v-if="pickedDayEvents.length === 0" class="muted small">
                Niciun eveniment în această zi.
              </div>
              <div v-else class="day-list">
                <div v-for="ev in pickedDayEvents" :key="ev.kind + '-' + ev.id"
                     :class="['day-item', { 'day-test': ev.kind === 'test' }]"
                     @click="goEvent(ev)">
                  <div class="day-bar" :style="{ background: subjColor(ev.subject) }"></div>
                  <div class="day-main">
                    <div class="day-title">
                      <span v-if="ev.kind === 'test'" class="day-tag">TEST</span>
                      {{ ev.title }}
                    </div>
                    <div class="day-meta">{{ ev.subject }} · {{ ev.assignedClass }}</div>
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
.toolbar {
  display: flex; justify-content: space-between; align-items: center;
  margin-bottom: 16px; flex-wrap: wrap; gap: 12px;
}
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; }
.nav { display: flex; align-items: center; gap: 10px; }
.nav button {
  background: white; border: 1px solid #d0d7e2; padding: 6px 12px;
  border-radius: 8px; cursor: pointer; font-family: 'Inter', sans-serif;
  color: #185FA5; font-weight: 700; font-size: 14px;
}
.nav button:hover { background: #f0f5fb; }
.nav .title { font-weight: 700; color: #185FA5; min-width: 160px; text-align: center; }
.today-btn { background: #185FA5 !important; color: white !important; }
.today-btn:hover { background: #134d87 !important; }
.api-error { background: #ffe5e5; color: #cc0000; border: 1px solid #cc0000; border-radius: 8px; padding: 10px 16px; margin: 8px 0; }
.muted { color: #888; padding: 12px 0; }
.muted.small { font-size: 12px; }

.cal-wrap {
  display: grid;
  grid-template-columns: 1fr 280px;
  gap: 16px;
  align-items: start;
}
@media (max-width: 900px) {
  .cal-wrap { grid-template-columns: 1fr; }
}

.cal {
  background: white; border: 1px solid #e0e6ee; border-radius: 12px;
  overflow: hidden;
}
.cal-row { display: grid; grid-template-columns: repeat(7, 1fr); }
.cal-row.head { background: #185FA5; }
.cal-cell {
  background: white; padding: 6px; min-height: 96px; cursor: pointer;
  border-right: 1px solid #eef2f8; border-bottom: 1px solid #eef2f8;
  transition: background 0.1s; position: relative;
  overflow: hidden;
}
.cal-cell:hover { background: #f5faff; }
.cal-cell.head { background: transparent; color: white; font-weight: 700; padding: 8px; text-align: center; min-height: 0; cursor: default; }
.cal-cell.other { background: #fafbfd; color: #aaa; }
.cal-cell.today { background: #e9f7e9; }
.cal-cell.picked { box-shadow: inset 0 0 0 2px #185FA5; }
.cell-num { font-weight: 700; font-size: 13px; color: #185FA5; }
.cal-cell.other .cell-num { color: #aaa; }
.cell-events { display: flex; flex-direction: column; gap: 2px; margin-top: 4px; }
.ev-dot {
  font-size: 10px; padding: 2px 6px; border-radius: 4px;
  color: #333; font-weight: 700;
  white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
}
.ev-dot.ev-test {
  border: 1.5px solid #cc0000;
  color: #cc0000;
}
.day-test .day-bar { background: #cc0000 !important; }
.day-tag {
  background: #cc0000; color: white; padding: 1px 6px; border-radius: 4px;
  font-size: 10px; margin-right: 6px;
}
.ev-more { font-size: 10px; color: #888; }

.day-panel {
  background: white; border: 1px solid #e0e6ee; border-radius: 12px;
  padding: 14px; position: sticky; top: 16px;
}
.panel-head { font-weight: 700; color: #185FA5; margin-bottom: 10px; font-size: 14px; }
.day-list { display: flex; flex-direction: column; gap: 8px; }
.day-item {
  display: flex; gap: 10px; align-items: stretch; cursor: pointer;
  padding: 8px 10px; border: 1px solid #eef2f8; border-radius: 8px;
  transition: background 0.1s;
}
.day-item:hover { background: #f5faff; }
.day-bar { width: 4px; border-radius: 3px; flex-shrink: 0; }
.day-main { flex: 1; min-width: 0; }
.day-title { font-weight: 700; color: #185FA5; font-size: 13px; }
.day-meta  { font-size: 11px; color: #888; margin-top: 2px; }

@media (max-width: 700px) {
  .cal-cell { padding: 4px; min-height: 64px; }
  .cell-num { font-size: 11px; }
  .ev-dot { font-size: 9px; padding: 1px 4px; }
  .nav .title { min-width: 110px; font-size: 13px; }
  .nav button { padding: 4px 10px; font-size: 13px; }
}
@media (max-width: 480px) {
  .cal-row.head .cal-cell.head { padding: 6px 2px; font-size: 10px; }
  /* only show one event chip per cell, plus "+N" if more */
  .cal-cell { min-height: 52px; }
  .ev-dot:nth-child(n+2) { display: none; }
  .ev-more { font-size: 9px; }
  /* day panel is below the grid (already via 900px breakpoint) — tighten it */
  .day-panel { padding: 10px; }
}
</style>
