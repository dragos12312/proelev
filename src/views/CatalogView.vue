<script setup>
// CATALOG (gradebook) view. Backend returns a different shape per role and
// the frontend swaps in the right sub-template via viewKind.
import { ref, computed, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { gradebookApi } from '../api.js'

const router = useRouter()

const data    = ref(null)
const loading = ref(false)
const errMsg  = ref('')

async function load() {
  loading.value = true
  errMsg.value = ''
  try {
    data.value = await gradebookApi.mine()
  } catch (e) {
    errMsg.value = e.message || 'Eroare la încărcare'
  } finally {
    loading.value = false
  }
}

onMounted(load)

const kind = computed(() => data.value?.viewKind || null)

function goHomework(id) {
  if (id) router.push(`/homeworks/${id}`)
}

function gradeClass(g) {
  if (g === null || g === undefined) return 'no-grade'
  return g >= 5 ? 'pass' : 'fail'
}

function fmtGrade(g) {
  if (g === null || g === undefined) return '—'
  return g
}

const exporting = ref(false)
async function exportPdf() {
  exporting.value = true
  try {
    await gradebookApi.exportPdf()
  } catch (e) {
    errMsg.value = e.message || 'Eroare la export'
  } finally {
    exporting.value = false
  }
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="catalog" />
      <div class="main">
        <div class="title-row">
          <h2 class="page-title">CATALOG</h2>
          <button class="btn-export" :disabled="exporting" @click="exportPdf">
            {{ exporting ? 'Se exportă...' : 'Exportă PDF' }}
          </button>
        </div>

        <div v-if="loading" class="muted">Se încarcă...</div>
        <div v-else-if="errMsg" class="api-error">{{ errMsg }}</div>

        <!-- ── STUDENT view: own grades across all homeworks ─────────── -->
        <div v-else-if="kind === 'student'" class="block">
          <div class="block-header">
            <div>
              <div class="head-name">{{ data.data.name }}</div>
              <div class="head-sub">Clasa {{ data.data.class?.name || '—' }}</div>
            </div>
            <div class="avg-pill">
              Media generală:
              <b>{{ data.data.average !== null ? data.data.average : '—' }}</b>
            </div>
          </div>
          <table v-if="data.data.rows.length > 0">
            <thead>
              <tr><th>Materie</th><th>Tema</th><th>Termen</th><th>Trimisă</th><th>Notă</th><th>Feedback</th></tr>
            </thead>
            <tbody>
              <tr v-for="r in data.data.rows" :key="r.homeworkId" @click="goHomework(r.homeworkId)">
                <td>{{ r.subject }}</td>
                <td>{{ r.title }}</td>
                <td>{{ r.dueDate }}</td>
                <td>
                  <span :class="['badge', r.submitted ? 'ok' : 'no']">{{ r.submitted ? 'Da' : 'Nu' }}</span>
                </td>
                <td><span :class="['grade-cell', gradeClass(r.grade)]">{{ fmtGrade(r.grade) }}</span></td>
                <td class="feedback-cell">{{ r.feedback || '—' }}</td>
              </tr>
            </tbody>
          </table>
          <div v-else class="muted">Nu ai încă teme.</div>

          <!-- TESTE -->
          <h4 class="sect-title" v-if="data.data.tests && data.data.tests.length > 0">Teste</h4>
          <table v-if="data.data.tests && data.data.tests.length > 0">
            <thead>
              <tr><th>Materie</th><th>Test</th><th>Dată</th><th>Notă</th><th>Feedback</th></tr>
            </thead>
            <tbody>
              <tr v-for="t in data.data.tests" :key="t.testId">
                <td>{{ t.subject }}</td>
                <td>{{ t.title }}</td>
                <td>{{ t.date }}</td>
                <td><span :class="['grade-cell', gradeClass(t.grade)]">{{ fmtGrade(t.grade) }}</span></td>
                <td class="feedback-cell">{{ t.feedback || '—' }}</td>
              </tr>
            </tbody>
          </table>

          <!-- PURTARE -->
          <div v-if="data.data.behavior" class="behavior-card">
            <h4 class="sect-title">Media la purtare</h4>
            <div class="beh-row">
              <span class="beh-period">{{ data.data.behavior.period }}</span>
              <span :class="['grade-cell', gradeClass(data.data.behavior.grade)]">
                {{ data.data.behavior.grade }}
              </span>
            </div>
            <div v-if="data.data.behavior.note" class="beh-note">
              {{ data.data.behavior.note }}
            </div>
          </div>
        </div>

        <!-- ── PARENT view: one block per child ──────────────────────── -->
        <div v-else-if="kind === 'parent'">
          <div v-if="data.children.length === 0" class="muted">Nu ai copii înregistrați.</div>
          <div v-for="child in data.children" :key="child.userId" class="block">
            <div class="block-header">
              <div>
                <div class="head-name">{{ child.name }}</div>
                <div class="head-sub">Clasa {{ child.class?.name || '—' }}</div>
              </div>
              <div class="avg-pill">
                Media generală:
                <b>{{ child.average !== null ? child.average : '—' }}</b>
              </div>
            </div>
            <table v-if="child.rows && child.rows.length > 0">
              <thead>
                <tr><th>Materie</th><th>Tema</th><th>Termen</th><th>Trimisă</th><th>Notă</th><th>Feedback</th></tr>
              </thead>
              <tbody>
                <tr v-for="r in child.rows" :key="r.homeworkId" @click="goHomework(r.homeworkId)">
                  <td>{{ r.subject }}</td>
                  <td>{{ r.title }}</td>
                  <td>{{ r.dueDate }}</td>
                  <td><span :class="['badge', r.submitted ? 'ok' : 'no']">{{ r.submitted ? 'Da' : 'Nu' }}</span></td>
                  <td><span :class="['grade-cell', gradeClass(r.grade)]">{{ fmtGrade(r.grade) }}</span></td>
                  <td class="feedback-cell">{{ r.feedback || '—' }}</td>
                </tr>
              </tbody>
            </table>
            <div v-else class="muted">Niciun catalog pentru acest copil încă.</div>

            <!-- per-child tests -->
            <h4 class="sect-title" v-if="child.tests && child.tests.length > 0">Teste</h4>
            <table v-if="child.tests && child.tests.length > 0">
              <thead>
                <tr><th>Materie</th><th>Test</th><th>Dată</th><th>Notă</th><th>Feedback</th></tr>
              </thead>
              <tbody>
                <tr v-for="t in child.tests" :key="t.testId">
                  <td>{{ t.subject }}</td>
                  <td>{{ t.title }}</td>
                  <td>{{ t.date }}</td>
                  <td><span :class="['grade-cell', gradeClass(t.grade)]">{{ fmtGrade(t.grade) }}</span></td>
                  <td class="feedback-cell">{{ t.feedback || '—' }}</td>
                </tr>
              </tbody>
            </table>

            <!-- per-child behavior -->
            <div v-if="child.behavior" class="behavior-card">
              <h4 class="sect-title">Media la purtare</h4>
              <div class="beh-row">
                <span class="beh-period">{{ child.behavior.period }}</span>
                <span :class="['grade-cell', gradeClass(child.behavior.grade)]">
                  {{ child.behavior.grade }}
                </span>
              </div>
              <div v-if="child.behavior.note" class="beh-note">
                {{ child.behavior.note }}
              </div>
            </div>
          </div>
        </div>

        <!-- ── TEACHER / ADMIN view: per (class, subject) gradebook ───── -->
        <div v-else-if="kind === 'teacher' || kind === 'admin'">
          <div v-if="data.blocks.length === 0" class="muted">
            {{ kind === 'teacher' ? 'Nu ai încă materii asignate.' : 'Nu există încă teme în sistem.' }}
          </div>
          <div v-for="block in data.blocks" :key="`${block.class?.id}-${block.subject?.id}`" class="block">
            <div class="block-header">
              <div>
                <div class="head-name">{{ block.class?.name || '—' }} · {{ block.subject?.name || '—' }}</div>
                <div class="head-sub">{{ block.homeworks.length }} teme · {{ block.students.length }} elevi</div>
              </div>
              <div class="avg-pill">
                Media clasei:
                <b>{{ block.classAverage !== null ? block.classAverage : '—' }}</b>
              </div>
            </div>
            <div class="matrix-scroll" v-if="block.homeworks.length > 0">
              <table class="matrix">
                <thead>
                  <tr>
                    <th class="sticky-col">Elev</th>
                    <th v-for="hw in block.homeworks" :key="hw.id" @click="goHomework(hw.id)" class="hw-col">
                      <span class="hw-title">{{ hw.title }}</span>
                      <span class="hw-date">{{ hw.dueDate }}</span>
                    </th>
                    <th>Medie</th>
                  </tr>
                </thead>
                <tbody>
                  <tr v-for="st in block.students" :key="st.name + (st.userId || '')">
                    <td class="sticky-col st-name">{{ st.name }}</td>
                    <td v-for="hw in block.homeworks" :key="hw.id">
                      <span :class="['grade-cell', gradeClass(st.grades[hw.id]?.grade)]">
                        {{ fmtGrade(st.grades[hw.id]?.grade) }}
                      </span>
                    </td>
                    <td><b>{{ st.average !== null ? st.average : '—' }}</b></td>
                  </tr>
                </tbody>
              </table>
            </div>
            <div v-else class="muted">Nicio temă pentru această materie încă.</div>
          </div>
        </div>

        <div v-else class="muted">Rolul tău nu are catalog.</div>
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
.title-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; margin-bottom: 16px; flex-wrap: wrap; }
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; margin: 0; }
.btn-export {
  background: #185FA5; color: white; border: none; padding: 8px 18px;
  border-radius: 8px; cursor: pointer; font-family: 'Inter', sans-serif;
  font-weight: 700; font-size: 13px;
}
.btn-export:hover:not(:disabled) { background: #134d87; }
.btn-export:disabled { opacity: 0.5; cursor: not-allowed; }
.muted { color: #888; padding: 20px 0; }
.api-error { background: #ffe5e5; color: #cc0000; border: 1px solid #cc0000; border-radius: 8px; padding: 10px 16px; margin: 8px 0; }

.block {
  background: white; border: 1px solid #d0d7e2; border-radius: 12px;
  padding: clamp(10px, 2vw, 18px); margin-bottom: 20px;
}
.block-header {
  display: flex; justify-content: space-between; align-items: center;
  flex-wrap: wrap; gap: 12px; margin-bottom: 14px;
  padding-bottom: 10px; border-bottom: 1px solid #eef2f8;
}
.head-name { font-weight: 700; color: #185FA5; font-size: clamp(15px, 1.6vw, 18px); }
.head-sub  { color: #888; font-size: 12px; }
.avg-pill {
  background: #e9f1fb; color: #185FA5; padding: 6px 14px; border-radius: 999px;
  font-size: 13px;
}
.avg-pill b { font-size: 15px; margin-left: 4px; }

table { width: 100%; border-collapse: collapse; }
th {
  background: #185FA5; color: white; padding: clamp(6px, 1vw, 10px);
  text-align: center; font-size: clamp(11px, 1.2vw, 13px);
}
td {
  padding: clamp(6px, 1vw, 10px); border-bottom: 1px solid #f0f3f7;
  text-align: center; font-size: clamp(11px, 1.2vw, 13px);
}
tbody tr:hover { background: #f5faff; cursor: pointer; }
.feedback-cell {
  max-width: 240px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  text-align: left; color: #444;
}

.matrix-scroll { overflow-x: auto; }
.matrix th, .matrix td { white-space: nowrap; }
.matrix .hw-col { cursor: pointer; }
.hw-title { display: block; font-weight: 700; }
.hw-date  { display: block; font-size: 10px; color: #cfe3ff; font-weight: normal; }
.matrix .sticky-col {
  position: sticky; left: 0; background: white; text-align: left;
  font-weight: 700; color: #185FA5; z-index: 1;
}
.matrix th.sticky-col { background: #185FA5; color: white; }
.st-name { background: white; color: #185FA5; }

.grade-cell {
  display: inline-block; min-width: 30px; padding: 3px 8px; border-radius: 6px;
  font-weight: 700;
}
.grade-cell.pass     { background: #d4edda; color: #155724; }
.grade-cell.fail     { background: #f5d6d6; color: #842029; }
.grade-cell.no-grade { background: #f0f0f0; color: #888; }

.badge {
  display: inline-block; padding: 2px 10px; border-radius: 999px;
  font-size: 11px; font-weight: 700;
}
.badge.ok { background: #d4edda; color: #155724; }
.badge.no { background: #f5d6d6; color: #842029; }

.sect-title { color: #185FA5; margin: 14px 0 8px; font-size: 13px; text-transform: uppercase; }
.behavior-card {
  margin-top: 14px; background: #fff9eb; border: 1px solid #f1e3b6;
  border-radius: 10px; padding: 10px 14px;
}
.beh-row { display: flex; justify-content: space-between; align-items: center; gap: 12px; }
.beh-period { font-weight: 700; color: #7a4d00; font-size: 13px; }
.beh-note   { font-size: 12px; color: #555; margin-top: 6px; font-style: italic; }

@media (max-width: 700px) {
  .block-header { gap: 8px; }
  .avg-pill { font-size: 12px; padding: 4px 10px; }
  .head-name { font-size: 14px; }
  th, td { padding: 6px 4px; font-size: 11px; }
  /* drop feedback column on mobile, it's the widest */
  th:last-child, td:last-child { display: none; }
}
@media (max-width: 480px) {
  /* student/parent table: hide due-date column too */
  th:nth-child(3), td:nth-child(3) { display: none; }
}
</style>
