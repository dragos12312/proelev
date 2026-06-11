<script setup>
// ORAR (timetable) view. Backend returns a 5-day × 5-period grid for one
// class; admin/teacher get a dropdown to switch classes.
import { ref, computed, onMounted } from 'vue'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { timetableApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const data    = ref(null)
const loading = ref(false)
const errMsg  = ref('')
const picked  = ref('')   // class the admin/teacher selected

const canSwitch = computed(() => {
  const role = currentUser.value?.role
  return role === 'admin' || role === 'teacher' || role === 'user'
})

async function load(cls) {
  loading.value = true
  errMsg.value = ''
  try {
    data.value = await timetableApi.get(cls || undefined)
    picked.value = data.value?.class?.name || ''
  } catch (e) {
    errMsg.value = e.message || 'Eroare la încărcare'
  } finally {
    loading.value = false
  }
}

function onSwitch() {
  load(picked.value)
}

onMounted(() => load())

// the current weekday so we can highlight today's column. Monday=0..Sunday=6
const todayIdx = computed(() => {
  const js = new Date().getDay()   // Sunday=0..Saturday=6 in JS
  return (js + 6) % 7              // shift so Monday=0
})

// only highlight if today is a weekday (0..4)
function isToday(dayIdx) {
  return dayIdx === todayIdx.value && todayIdx.value <= 4
}

// short subject color so cells are easier to scan
const SUBJECT_COLOR = {
  'Matematică':         '#e3f1ff',
  'Limba Română':       '#fde8e8',
  'Științele naturii':  '#e6f7e1',
  'Limba Engleză':      '#fef5d0',
  'Istorie':            '#fde3d0',
  'Geografie':          '#e5f6f8',
  'Educație fizică':    '#f0e3fa',
}
function cellBg(subject) { return subject ? (SUBJECT_COLOR[subject] || '#f5f5f5') : 'white' }
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="orar" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">ORAR</h2>
          <div class="switcher" v-if="canSwitch && data?.available_classes">
            <label>Clasa</label>
            <select v-model="picked" @change="onSwitch">
              <option v-for="c in data.available_classes" :key="c" :value="c">{{ c }}</option>
            </select>
          </div>
          <div class="class-label" v-else-if="data?.class">
            Clasa <b>{{ data.class.name }}</b>
          </div>
        </div>

        <div v-if="loading" class="muted">Se încarcă...</div>
        <div v-else-if="errMsg" class="api-error">{{ errMsg }}</div>

        <div v-else-if="data" class="grid-wrap">
          <table class="grid">
            <thead>
              <tr>
                <th class="time-col">Ora</th>
                <th v-for="(d, i) in data.days" :key="d.day" :class="{ today: isToday(i) }">
                  {{ d.day }}
                </th>
              </tr>
            </thead>
            <tbody>
              <tr v-for="(p, pi) in data.periods" :key="p.period">
                <td class="time-col">
                  <div class="p-num">{{ p.period }}</div>
                  <div class="p-time">{{ p.start }} – {{ p.end }}</div>
                </td>
                <td v-for="(d, di) in data.days" :key="d.day"
                    :class="{ today: isToday(di) }"
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
.muted { color: #888; padding: 20px 0; }
.api-error { background: #ffe5e5; color: #cc0000; border: 1px solid #cc0000; border-radius: 8px; padding: 10px 16px; margin: 8px 0; }
.switcher { display: flex; align-items: center; gap: 8px; font-size: 14px; }
.switcher label { color: #185FA5; font-weight: 700; }
.switcher select {
  padding: 6px 10px; border: 1px solid #d0d7e2; border-radius: 6px;
  font-family: 'Inter', sans-serif; font-size: 13px; background: white;
}
.class-label { font-size: 14px; color: #185FA5; }

.grid-wrap { overflow-x: auto; }
table.grid { border-collapse: separate; border-spacing: 6px; width: 100%; min-width: 700px; }
th {
  background: #185FA5; color: white; padding: 10px 8px;
  border-radius: 8px; font-size: 13px; text-align: center;
}
th.today { background: #2a9d2a; }
td {
  background: white; border: 1px solid #e0e6ee; border-radius: 8px;
  padding: 10px 8px; min-width: 120px; vertical-align: middle; text-align: center;
}
td.today { box-shadow: 0 0 0 2px #2a9d2a40; }
.time-col {
  min-width: 80px; background: #fbfbfb; font-weight: 700; color: #185FA5;
}
.p-num { font-size: 18px; }
.p-time { font-size: 11px; color: #888; font-weight: normal; margin-top: 2px; }
.subj { font-weight: 700; color: #333; font-size: 13px; }
.teach { font-size: 11px; color: #555; margin-top: 4px; }
.free { color: #ccc; font-size: 18px; }

@media (max-width: 700px) {
  .switcher { font-size: 13px; }
  table.grid { border-spacing: 4px; }
  th { padding: 6px 4px; font-size: 11px; }
  td { padding: 6px 4px; min-width: 90px; }
  .subj { font-size: 11px; }
  .teach { font-size: 10px; }
  .time-col { min-width: 60px; }
  .p-num { font-size: 14px; }
  .p-time { font-size: 9px; }
}
</style>
