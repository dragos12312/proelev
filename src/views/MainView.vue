<script setup>
// dashboard the user lands on after logging in, a grid of subject cards.
// click a card to open that subject's channel (Teams-style hub with
// announcements, timetable, attendance, and resources inside).
import { ref, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { lookups } from '../api.js'

const router = useRouter()

const subjects = ref([])

onMounted(async () => {
  try {
    subjects.value = await lookups.subjects()
  } catch (e) {
    // fallback so the view still renders if the lookup fails
    subjects.value = [
      { id: null, name: 'Matematică' },
      { id: null, name: 'Limba Română' },
      { id: null, name: 'Științele naturii' },
      { id: null, name: 'Limba Engleză' },
      { id: null, name: 'Istorie' },
      { id: null, name: 'Geografie' },
      { id: null, name: 'Educație fizică' },
    ]
  }
})

function openSubject(s) {
  if (s.id) router.push(`/subject/${s.id}`)
  else      router.push(`/subject/0?name=${encodeURIComponent(s.name)}`)
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="" />
      <div class="main">
        <div class="grid">
          <div v-for="s in subjects"
               :key="s.id || s.name"
               class="card"
               @click="openSubject(s)">
            {{ s.name }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; }
.main {
  flex: 1;
  padding: clamp(16px, 3vw, 40px);
  padding-top: clamp(40px, 4vw, 70px);
  padding-right: clamp(40px, 6vw, 80px);
  font-family: 'Inter', sans-serif;
  min-width: 0;
}
.grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(140px, 1fr));
  gap: clamp(12px, 2vw, 24px);
}
@media (max-width: 480px) {
  .grid { grid-template-columns: repeat(auto-fill, minmax(110px, 1fr)); gap: 10px; }
}
.card {
  background-color: #f0f0f0;
  border-radius: 12px;
  padding: clamp(12px, 2vw, 24px);
  font-size: clamp(12px, 1.4vw, 16px);
  font-weight: 700;
  color: #185FA5;
  cursor: pointer;
  display: flex;
  align-items: center;
  justify-content: center;
  text-align: center;
  aspect-ratio: 1;
  transition: background-color 0.2s, transform 0.1s;
}
.card:hover { background-color: #dde8f5; transform: translateY(-2px); }
</style>
