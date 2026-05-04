<script setup>
// stats page that shows one big pie and six smaller pies, one per subject
// each pie compares graded vs ungraded students for the most recent homework
// in that subject
import { computed, ref, watch, onMounted, onUnmounted } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { fetchAllHomeworks, fetchAllStudents, createWebSocket } from '../api.js'

// angles that the animation eases towards, drives the big pie
const animatedGraded   = ref(0)
const animatedUngraded = ref(0)

const router = useRouter()
const route  = useRoute()
const id     = computed(() => parseInt(route.params.id))

const subjectList = ['Matematică', 'Limba Română', 'Științele naturii', 'Limba Engleză', 'Istorie', 'Geografie']
const classList   = ['Toate clasele', '1A', '1B', '2A', '2B', '3A', '3B', '4A', '4B']

const selectedSubject = ref(subjectList[0])
const selectedClass   = ref('Toate clasele')
const animating       = ref(false)
const dataLoaded      = ref(false)

// stats keyed by subject, each entry has counts and the homework title
const subjectStats = ref({})
let ws = null
let animationInterval = null

// loops over every subject and builds the stats object
async function loadAllStats() {
  const results = {}
  for (const subject of subjectList) {
    try {
      const filters = { subject }
      if (selectedClass.value !== 'Toate clasele') filters.assignedClass = selectedClass.value

      const homeworks = await fetchAllHomeworks(filters)
      if (!homeworks.length) {
        results[subject] = { hwTitle: null, total: 0, graded: 0, ungraded: 0, noHomework: true }
        continue
      }
      // pick the homework with the latest due date, that is the one we show
      const hw = homeworks.reduce((a, b) =>
          new Date(a.dueDate) >= new Date(b.dueDate) ? a : b
      )
      const students = await fetchAllStudents(hw.id)
      const total    = students.length
      const graded   = students.filter(s => s.grade !== null).length
      const ungraded = students.filter(s => s.grade === null).length
      results[subject] = { hwTitle: hw.title, total, graded, ungraded, noHomework: false }
    } catch (e) {
      console.error(`[HomeworkStatistics] Error loading subject "${subject}":`, e)
      results[subject] = { hwTitle: null, total: 0, graded: 0, ungraded: 0, noHomework: true }
    }
  }
  subjectStats.value = results
  dataLoaded.value = true
  animateTo(selectedSubject.value)
}

onMounted(async () => {
  await loadAllStats()
  ws = createWebSocket((data) => {
    if (data.event === 'new_batch') loadAllStats()
  })
})

onUnmounted(() => {
  if (ws) ws.close()
  if (animationInterval) clearInterval(animationInterval)
})

watch(selectedClass, () => {
  dataLoaded.value = false
  loadAllStats()
})

watch(selectedSubject, (subject) => {
  if (dataLoaded.value) animateTo(subject)
})

// eases the pie slices from the old angles to the new ones over about 400ms
// we run a setInterval at 60fps and linearly step the values each frame
function animateTo(subject) {
  if (animationInterval) clearInterval(animationInterval)
  const stats = subjectStats.value[subject]
  if (!stats || !stats.total) {
    animatedGraded.value = 0
    animatedUngraded.value = 0
    return
  }
  const { total, graded, ungraded } = stats
  const targetGraded   = (graded / total) * 360
  const targetUngraded = (ungraded / total) * 360
  const totalFrames = (400 / 1000) * 60
  let frame = 0
  const sg = animatedGraded.value,   su = animatedUngraded.value
  const dg = targetGraded - sg,      du = targetUngraded - su
  animating.value = true
  animationInterval = setInterval(() => {
    frame++
    animatedGraded.value   = sg + dg * frame / totalFrames
    animatedUngraded.value = su + du * frame / totalFrames
    if (frame >= totalFrames) {
      clearInterval(animationInterval)
      animationInterval = null
      animating.value = false
    }
  }, 1000 / 60)
}

// turns the raw counts into the arc angles the small pies use
function getArcs(subject) {
  const stats = subjectStats.value[subject]
  if (!stats || stats.noHomework || !stats.total) {
    return { greenEnd: 0, redStart: 0, redEnd: 0, graded: 0, ungraded: 0, noHomework: true }
  }
  const total = stats.total
  const pa = (stats.graded   / total) * 360
  const ra = (stats.ungraded / total) * 360
  return {
    greenEnd: pa,
    redStart: pa,
    redEnd:   pa + ra,
    graded:   stats.graded,
    ungraded: stats.ungraded,
    noHomework: false,
  }
}

// builds the svg path d for one pie slice between two angles
function describeArc(cx, cy, r, startAngle, endAngle) {
  if (endAngle - startAngle >= 360) endAngle = startAngle + 359.999
  const toRad = a => a * Math.PI / 180
  const x1 = cx + r * Math.cos(toRad(startAngle)), y1 = cy + r * Math.sin(toRad(startAngle))
  const x2 = cx + r * Math.cos(toRad(endAngle)),   y2 = cy + r * Math.sin(toRad(endAngle))
  return `M ${cx} ${cy} L ${x1} ${y1} A ${r} ${r} 0 ${endAngle - startAngle > 180 ? 1 : 0} 1 ${x2} ${y2} Z`
}

// the five subjects shown in the small grid are everyting except the selected one
const otherSubjects = computed(() => subjectList.filter(s => s !== selectedSubject.value))
const selectedStats = computed(() => subjectStats.value[selectedSubject.value])

function goBack()        { router.push(`/homeworks/${id.value}/statistics`) }
function goToNotePerElev() { router.push(`/homeworks/${id.value}/statistics`) }
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="teme" />
      <div class="main">
        <div class="toolbar">
          <span class="back" @click="goBack">&lt; TEME</span>
          <h2 class="page-title">STATISTICI</h2>
          <div></div>
        </div>

        <div class="chart-section">
          <div class="chart-buttons">
            <button class="btn-chart btn-notes" @click="goToNotePerElev">NOTE PER ELEV</button>
            <button class="btn-chart btn-counted active">CÂȚI ELEVI AU PRIMIT NOTĂ</button>
          </div>

          <div class="controls">
            <select v-model="selectedSubject" class="subject-select">
              <option v-for="s in subjectList" :key="s" :value="s">{{ s.toUpperCase() }}</option>
            </select>
            <select v-model="selectedClass" class="subject-select">
              <option v-for="c in classList" :key="c" :value="c">{{ c.toUpperCase() }}</option>
            </select>
            <div class="legend-top">
              <div class="legend"><span class="legend-dot" style="background:#2a9d2a"></span> CU NOTĂ</div>
              <div class="legend"><span class="legend-dot" style="background:#cc0000"></span> FĂRĂ NOTĂ</div>
              <div class="legend"><span class="legend-dot" style="background:#cccccc"></span> FĂRĂ TEMĂ</div>
            </div>
          </div>

          <div v-if="!dataLoaded" class="loading">Se încarcă statisticile...</div>

          <div class="charts-layout" v-else>
            <!-- BIG: selected subject -->
            <div class="big-chart">
              <svg class="big-svg" viewBox="0 0 200 200" :class="{ 'chart-animate': animating }">
                <circle v-if="getArcs(selectedSubject).noHomework" cx="100" cy="100" r="90" fill="#cccccc" />
                <path v-if="!getArcs(selectedSubject).noHomework && animatedGraded > 0"
                      :d="describeArc(100,100,90,0,animatedGraded)" fill="#2a9d2a" />
                <path v-if="!getArcs(selectedSubject).noHomework && animatedUngraded > 0"
                      :d="describeArc(100,100,90,animatedGraded,animatedGraded+animatedUngraded)" fill="#cc0000" />
              </svg>
              <p class="pie-label big-label" :class="{ 'label-fade': animating }">
                {{ selectedSubject.toUpperCase() }}
              </p>
              <p class="pie-sub" v-if="selectedStats?.hwTitle">{{ selectedStats.hwTitle }}</p>
              <p class="pie-sub empty" v-else-if="selectedStats?.noHomework">Nicio temă înregistrată</p>
            </div>

            <!-- SMALL: other subjects -->
            <div class="small-charts">
              <div v-for="subject in otherSubjects" :key="subject" class="pie-item"
                   @click="selectedSubject = subject">
                <svg class="small-svg" viewBox="0 0 200 200">
                  <circle v-if="getArcs(subject).noHomework" cx="100" cy="100" r="90" fill="#cccccc" />
                  <path v-if="!getArcs(subject).noHomework && getArcs(subject).graded > 0"
                        :d="describeArc(100,100,90,0,getArcs(subject).greenEnd)" fill="#2a9d2a" />
                  <path v-if="!getArcs(subject).noHomework && getArcs(subject).ungraded > 0"
                        :d="describeArc(100,100,90,getArcs(subject).redStart,getArcs(subject).redEnd)" fill="#cc0000" />
                </svg>
                <p class="pie-label">{{ subject.toUpperCase() }}</p>
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
.main { flex: 1; min-width: 0; padding: clamp(12px, 2.5vw, 24px); padding-right: clamp(40px, 6vw, 80px); font-family: 'Inter', sans-serif; display: flex; flex-direction: column; }
.toolbar { display: flex; justify-content: space-between; align-items: center; margin-bottom: clamp(16px, 2.5vw, 24px); border-bottom: 1px solid #ccc; padding-bottom: clamp(10px, 1.5vw, 16px); gap: 12px; flex-wrap: wrap; }
.back { font-size: clamp(13px, 1.4vw, 16px); cursor: pointer; color: #333; font-weight: 700; }
.back:hover { color: #185FA5; }
.page-title { font-size: clamp(18px, 3vw, 24px); color: #333; font-weight: 700; }
.chart-section { display: flex; flex-direction: column; flex: 1; }

.chart-buttons { display: grid; grid-template-columns: repeat(2, minmax(0, 220px)); gap: 12px; margin-bottom: clamp(16px, 2.5vw, 24px); }
.btn-chart { background-color: #185FA5; color: white; border: none; padding: 8px 14px; border-radius: 6px; cursor: pointer; font-size: clamp(11px, 1.1vw, 12px); font-weight: 700; font-family: 'Inter', sans-serif; opacity: 0.5; text-align: center; }
.btn-chart.btn-notes   { grid-column: 1; grid-row: 1; }
.btn-chart.btn-counted { grid-column: 2; grid-row: 1; }
.btn-chart.active { opacity: 1; }
.btn-chart:hover { opacity: 1; }

.controls { display: flex; align-items: center; gap: 12px; margin-bottom: clamp(20px, 3vw, 32px); flex-wrap: wrap; }
.subject-select { padding: 8px 12px; border-radius: 8px; border: 1px solid #ccc; font-size: clamp(12px, 1.2vw, 13px); font-family: 'Inter', sans-serif; cursor: pointer; max-width: 100%; }
.legend-top { display: flex; gap: 12px; margin-left: auto; flex-wrap: wrap; }
.legend { display: flex; align-items: center; gap: 6px; font-size: clamp(11px, 1.2vw, 13px); font-weight: 700; }
.legend-dot { width: 14px; height: 14px; border-radius: 3px; display: inline-block; }
.loading { color: #666; font-size: 15px; font-weight: 600; margin-top: 40px; }
.charts-layout { display: flex; gap: clamp(20px, 4vw, 48px); align-items: flex-start; flex-wrap: wrap; justify-content: center; }
.big-chart { display: flex; flex-direction: column; align-items: center; gap: 8px; flex: 1 1 260px; max-width: 420px; }
.big-svg { width: 100%; max-width: 400px; height: auto; }
.big-label { font-size: clamp(13px, 1.5vw, 16px); font-weight: 700; color: #333; text-align: center; }
.pie-sub { font-size: clamp(11px, 1.2vw, 12px); color: #666; text-align: center; max-width: 240px; }
.pie-sub.empty { color: #999; font-style: italic; }
.small-charts { display: grid; grid-template-columns: repeat(auto-fit, minmax(140px, 180px)); grid-auto-rows: auto; gap: clamp(16px, 3vw, 32px); justify-items: center; align-items: start; flex: 1 1 300px; }
.small-svg { width: 100%; max-width: 180px; height: auto; }
.pie-item { display: flex; flex-direction: column; align-items: center; gap: 4px; cursor: pointer; width: 100%; max-width: 180px; }
.pie-item:hover svg { opacity: 0.8; }
.pie-label { font-size: clamp(11px, 1.2vw, 13px); font-weight: 700; color: #333; text-align: center; max-width: 180px; word-break: break-word; white-space: normal; }

@media (max-width: 480px) {
  .legend-top { margin-left: 0; width: 100%; }
}
@keyframes fadeIn { from { opacity: 0; transform: scale(0.92); } to { opacity: 1; transform: scale(1); } }
.chart-animate { animation: fadeIn 0.4s ease; }
.label-fade { animation: fadeIn 0.4s ease; }
</style>
