<script setup>
// stats page for one specific homework, two views swapped with the buttons on top
// first view is a bar chart with how many students got each grade
// second view is a pie plus named lists of who doesnt have a grade
import { computed, ref, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { homeworksApi, fetchAllStudents, createWebSocket } from '../api.js'

const router = useRouter()
const route = useRoute()
const id = computed(() => parseInt(route.params.id))

const homework = ref(null)
const studentsList = ref([])
const activeView = ref('notes')
let ws = null

// each grade bucket has its own color, green for the top ones and red for the bad ones
const gradeColors = {
  10: '#2d6a2d', 9: '#3a8a3a', 8: '#7bc47b',
  7: '#f0c040', 6: '#e09020', 5: '#e06020',
  '<5': '#cc2000', 'FĂRĂ NOTĂ': '#cccccc',
}

// pulls the homework and all the students for it, used on mount and on every ws event
async function loadData() {
  const hwId = id.value
  if (!hwId || isNaN(hwId)) return
  try {
    homework.value = await homeworksApi.get(hwId)
    studentsList.value = await fetchAllStudents(hwId)
  } catch (e) {
    console.error('[StatisticsView] loadData error', e)
  }
}

onMounted(async () => {
  await loadData()
  ws = createWebSocket((data) => {
    if (data.event === 'new_batch') loadData()
  })
})

onUnmounted(() => {
  if (ws) ws.close()
})

// counts how many students got each grade, everyting under 5 goes in one bucket
const gradeData = computed(() => {
  const order = [10, 9, 8, 7, 6, 5, '<5', 'FĂRĂ NOTĂ']
  const counts = { 10: 0, 9: 0, 8: 0, 7: 0, 6: 0, 5: 0, '<5': 0, 'FĂRĂ NOTĂ': 0 }
  for (const student of studentsList.value) {
    if (student.grade === null) counts['FĂRĂ NOTĂ']++
    else if (student.grade < 5) counts['<5']++
    else counts[student.grade]++
  }
  return order.map(grade => ({ grade, count: counts[grade], color: gradeColors[grade] }))
})

// the tallest bar is 100 percent, everything else is scaled from it
const maxCount = computed(() => Math.max(...gradeData.value.map(d => d.count), 1))
function barHeight(count) { return (count / maxCount.value) * 100 }

// if the deadline already passed, ungraded means the student didnt hand in
const isPastDue = computed(() => {
  if (!homework.value?.dueDate) return false
  const due = new Date(homework.value.dueDate)
  due.setHours(23, 59, 59, 999)
  return due < new Date()
})

const passedStudents = computed(() =>
    studentsList.value.filter(s => s.grade !== null && s.grade >= 5)
)
const failedStudents = computed(() =>
    studentsList.value.filter(s => s.grade !== null && s.grade < 5)
)
const ungradedStudents = computed(() =>
    studentsList.value.filter(s => s.grade === null)
)

// builds the three slices for the pie, green passed, red fara nota, gray not handed in
const nogradeArcs = computed(() => {
  const total = studentsList.value.length
  if (!total) {
    return { empty: true, greenEnd: 0, redStart: 0, redEnd: 0, grayStart: 0, grayEnd: 0,
      passedCount: 0, redCount: 0, grayCount: 0 }
  }
  const passedCount = passedStudents.value.length
  const failedCount = failedStudents.value.length
  const ungradedCount = ungradedStudents.value.length
  // past deadline so ungraded students get moved to the red slice
  // otherwise they stay gray since they still have time to hand in
  const redCount = failedCount + (isPastDue.value ? ungradedCount : 0)
  const grayCount = isPastDue.value ? 0 : ungradedCount
  const pa = (passedCount / total) * 360
  const ra = (redCount / total) * 360
  const ga = (grayCount / total) * 360
  return {
    empty: false,
    greenEnd:  pa,
    redStart:  pa,
    redEnd:    pa + ra,
    grayStart: pa + ra,
    grayEnd:   pa + ra + ga,
    passedCount, redCount, grayCount,
  }
})

// names list for the red slice, bad grades always, plus the late ones if past deadline
const redNamedList = computed(() => {
  const items = failedStudents.value.map(s => ({ ...s, _reason: 'grade' }))
  if (isPastDue.value) {
    items.push(...ungradedStudents.value.map(s => ({ ...s, _reason: 'late' })))
  }
  return items
})
// gray list only shows up while we are still before the deadline
const grayNamedList = computed(() =>
    isPastDue.value ? [] : ungradedStudents.value
)

// builds the svg path d for one pie slice, same helper as in the other stats page
function describeArc(cx, cy, r, startAngle, endAngle) {
  if (endAngle - startAngle >= 360) endAngle = startAngle + 359.999
  const toRad = a => a * Math.PI / 180
  const x1 = cx + r * Math.cos(toRad(startAngle)), y1 = cy + r * Math.sin(toRad(startAngle))
  const x2 = cx + r * Math.cos(toRad(endAngle)),   y2 = cy + r * Math.sin(toRad(endAngle))
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${endAngle - startAngle > 180 ? 1 : 0} 1 ${x2} ${y2} Z`
}

function goBack() { router.push(`/homeworks/${id.value}`) }
function goToHwStatistics() { router.push(`/homeworks/${id.value}/hwstatistics`) }
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="teme" />
      <div class="main">
        <div class="toolbar">
          <span class="back" @click="goBack">&lt;</span>
          <h2 class="page-title">STATISTICI</h2>
          <div></div>
        </div>

        <div class="chart-section" v-if="homework">
          <h3 class="chart-title">
            TEME - {{ homework.subject.toUpperCase() }} - {{ homework.title.toUpperCase() }}
          </h3>

          <div class="chart-buttons">
            <button class="btn-chart btn-notes"
                    :class="{ active: activeView === 'notes' }"
                    @click="activeView = 'notes'">NOTE PER ELEV</button>
            <button class="btn-chart btn-counted"
                    @click="goToHwStatistics">CÂȚI ELEVI AU PRIMIT NOTĂ</button>
            <button class="btn-chart btn-nograde"
                    :class="{ active: activeView === 'nograde' }"
                    @click="activeView = 'nograde'">ELEVI FĂRĂ NOTĂ</button>
          </div>

          <!-- NOTE PER ELEV -->
          <div class="bar-chart" v-if="activeView === 'notes'">
            <div v-for="item in gradeData" :key="item.grade" class="bar-wrapper">
              <span class="bar-count">{{ item.count }}</span>
              <div class="bar-container">
                <div class="bar" :style="{ height: barHeight(item.count) + '%', backgroundColor: item.color }"></div>
              </div>
              <span class="bar-label">{{ item.grade }}</span>
            </div>
          </div>

          <!-- ELEVI FĂRĂ NOTĂ -->
          <div v-if="activeView === 'nograde'" class="nograde-view">
            <p class="nograde-status">
              <span v-if="isPastDue" class="badge past">Termen depășit — elevii fără notă sunt considerați nepredați.</span>
              <span v-else class="badge active-badge">Termenul nu a fost depășit — elevii pot încă preda tema.</span>
            </p>

            <div class="nograde-layout" v-if="!nogradeArcs.empty">
              <div class="pie-wrapper">
                <svg class="nograde-svg" viewBox="0 0 200 200">
                  <path v-if="nogradeArcs.greenEnd > 0"
                        :d="describeArc(100,100,90,0,nogradeArcs.greenEnd)" fill="#2a9d2a" />
                  <path v-if="nogradeArcs.redEnd > nogradeArcs.redStart"
                        :d="describeArc(100,100,90,nogradeArcs.redStart,nogradeArcs.redEnd)" fill="#cc0000" />
                  <path v-if="nogradeArcs.grayEnd > nogradeArcs.grayStart"
                        :d="describeArc(100,100,90,nogradeArcs.grayStart,nogradeArcs.grayEnd)" fill="#cccccc" />
                </svg>
                <div class="legend-group">
                  <div class="legend"><span class="legend-dot" style="background:#2a9d2a"></span> CU NOTĂ ≥ 5 - {{ nogradeArcs.passedCount }}</div>
                  <div class="legend" v-if="nogradeArcs.redCount > 0">
                    <span class="legend-dot" style="background:#cc0000"></span> FĂRĂ NOTĂ - {{ nogradeArcs.redCount }}
                  </div>
                  <div class="legend" v-if="nogradeArcs.grayCount > 0">
                    <span class="legend-dot" style="background:#cccccc"></span> NEPREDAT - {{ nogradeArcs.grayCount }}
                  </div>
                </div>
              </div>

              <div class="names-lists">
                <div class="names-block red" v-if="redNamedList.length">
                  <h4 class="names-title">FĂRĂ NOTĂ</h4>
                  <ul>
                    <li v-for="s in redNamedList" :key="s.id ?? s.name">
                      {{ s.name }}
                      <span class="reason" v-if="s._reason === 'late'">(nepredat)</span>
                      <span class="reason" v-else>(nota {{ s.grade }})</span>
                    </li>
                  </ul>
                </div>
                <div class="names-block gray" v-if="grayNamedList.length">
                  <h4 class="names-title">NEPREDAT</h4>
                  <ul>
                    <li v-for="s in grayNamedList" :key="s.id ?? s.name">{{ s.name }}</li>
                  </ul>
                </div>
                <p v-if="!redNamedList.length && !grayNamedList.length" class="empty-note">
                  Toți elevii au notă ≥ 5.
                </p>
              </div>
            </div>

            <p v-else class="empty-note">Niciun elev asociat acestei teme.</p>
          </div>

        </div>

        <div v-else><p>Se încarcă...</p></div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; padding-top: clamp(10px, 2vw, 25px); }
.main { flex: 1; min-width: 0; padding: clamp(12px, 2.5vw, 24px); padding-right: clamp(40px, 6vw, 80px); font-family: 'Inter', sans-serif; display: flex; flex-direction: column; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: clamp(16px, 2.5vw, 24px); border-bottom: 1px solid #ccc; padding-bottom: clamp(10px, 1.5vw, 16px); gap: 12px; flex-wrap: wrap; }
.back { font-size: clamp(18px, 2.4vw, 24px); cursor: pointer; color: #333; font-weight: 700; width: 40px; }
.back:hover { color: #185FA5; }
.page-title { font-size: clamp(18px, 3vw, 24px); color: #333; font-weight: 700; }
.chart-section { display: flex; flex-direction: column; flex: 1; }
.chart-title { font-size: clamp(14px, 1.8vw, 18px); font-weight: 700; color: #333; margin-bottom: 16px; }
.chart-buttons { display: grid; grid-template-columns: repeat(2, minmax(0, 220px)); gap: 12px; margin-bottom: clamp(16px, 2.5vw, 24px); }
.btn-chart { background-color: #185FA5; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: clamp(11px, 1.1vw, 12px); font-weight: 700; font-family: 'Inter', sans-serif; opacity: 0.5; text-align: center; }
.btn-chart.btn-notes    { grid-column: 1; grid-row: 1; }
.btn-chart.btn-counted  { grid-column: 2; grid-row: 1; }
.btn-chart.btn-nograde  { grid-column: 1; grid-row: 2; }
.btn-chart.active { opacity: 1; }
.btn-chart:hover { opacity: 1; }
.bar-chart { display: flex; align-items: flex-end; gap: clamp(8px, 2vw, 24px); height: clamp(240px, 42vw, 400px); overflow-x: auto; -webkit-overflow-scrolling: touch; }
.bar-wrapper { display: flex; flex-direction: column; align-items: center; flex: 1 0 40px; height: 100%; min-width: 40px; }
.bar-count { font-size: clamp(11px, 1.2vw, 13px); font-weight: 700; color: #333; margin-bottom: 4px; height: 20px; }
.bar-container { flex: 1; width: 100%; display: flex; align-items: flex-end; }
.bar { width: 100%; border-radius: 4px 4px 0 0; transition: height 0.5s ease; }
.bar-label { font-size: clamp(11px, 1.2vw, 13px); font-weight: 700; color: #333; margin-top: 8px; text-align: center; }

.nograde-view { display: flex; flex-direction: column; gap: 16px; }
.nograde-status .badge { display: inline-block; padding: 6px 12px; border-radius: 6px; font-size: clamp(11px, 1.2vw, 13px); font-weight: 700; }
.nograde-status .badge.past { background: #ffe5e5; color: #a00000; border: 1px solid #cc0000; }
.nograde-status .badge.active-badge { background: #e8f2ff; color: #134d87; border: 1px solid #185FA5; }
.nograde-layout { display: flex; gap: clamp(20px, 4vw, 48px); align-items: flex-start; flex-wrap: wrap; }
.pie-wrapper { display: flex; flex-direction: column; align-items: center; gap: 12px; flex: 1 1 240px; max-width: 320px; }
.nograde-svg { width: 100%; max-width: 280px; height: auto; }
.legend-group { display: flex; flex-direction: column; gap: 6px; }
.legend { display: flex; align-items: center; gap: 8px; font-size: clamp(11px, 1.2vw, 13px); font-weight: 700; }
.legend-dot { width: 14px; height: 14px; border-radius: 3px; display: inline-block; flex-shrink: 0; }

.names-lists { display: flex; flex-direction: column; gap: 16px; flex: 1 1 240px; min-width: 0; }
.names-block { border-radius: 8px; padding: 12px 16px; border: 1px solid transparent; }
.names-block.red { background: #fff5f5; border-color: #f0b0b0; }
.names-block.gray { background: #f5f5f5; border-color: #cccccc; }
.names-title { font-size: clamp(12px, 1.3vw, 14px); font-weight: 700; margin-bottom: 8px; }
.names-block.red .names-title { color: #a00000; }
.names-block.gray .names-title { color: #555; }
.names-block ul { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
.names-block li { font-size: clamp(11px, 1.2vw, 13px); color: #333; word-break: break-word; }
.reason { color: #888; font-size: clamp(10px, 1.1vw, 12px); margin-left: 6px; }
.empty-note { color: #666; font-size: clamp(12px, 1.3vw, 14px); font-style: italic; margin-top: 8px; }
</style>
