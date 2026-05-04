<script setup>
// dashboard the user lands on after logging in, shows a grid of subject cards
// every card takes you to the homeworks page since thats where the real data is
import { useRouter } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'

const router = useRouter()

// hard coded list of school subjects for the cards
const subjects = [
  'Limba și literatura română',
  'Matematică',
  'Științele naturii',
  'Limba Engleză',
  'Istorie',
  'Geografie',
  'Educație fizică',
]

function goToSubject(subject) {
  router.push('/homeworks')
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
          <div v-for="subject in subjects"
               :key="subject"
               class="card"
               @click="goToSubject(subject)">
            {{ subject }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content {
  display: flex;
  align-items: flex-start;
}

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
  .grid {
    grid-template-columns: repeat(auto-fill, minmax(110px, 1fr));
    gap: 10px;
  }
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
  transition: background-color 0.2s;
}

.card:hover {
  background-color: #dde8f5;
}
</style>