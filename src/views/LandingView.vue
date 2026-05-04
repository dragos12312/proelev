<script setup>
// first page the user sees, just has a login button and a contact dropdown
import { useRouter } from 'vue-router'
import { ref } from 'vue'
import logo from '../assets/logo.png'

const router = useRouter()
const showContactMenu = ref(false)

function goToLogin() {
  router.push('/login')
}
</script>

<template>
  <div class="landing">
    <img :src="logo" alt="ProElev Logo" class="logo" />

    <div class="center">
      <div class="title-block">
        <h1 class="title">ProElev</h1>
        <p class="tagline">Perseverența duce la reușite!</p>
      </div>

      <p class="description">
        Un website care facilitează gestionarea cursurilor pentru învățare remedială
        și măsurarea progresului elevului.
      </p>

      <div class="actions">
        <button class="btn-primary" @click="goToLogin">Conectare</button>

        <div class="contact-wrapper">
          <button class="btn-primary" @click="showContactMenu = !showContactMenu">
            Contactează-ne!
          </button>
          <div v-if="showContactMenu" class="contact-dropdown">
            <p>Înscrie-ți școala</p>
            <p>Suport tehnic</p>
            <p>Oferă feedback</p>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');

.landing {
  min-height: 100vh;
  padding: clamp(20px, 4vw, 40px) clamp(20px, 5vw, 60px);
  background-color: white;
  font-family: 'Inter', sans-serif;
  position: relative;
}

.logo {
  position: absolute;
  top: 30px;
  left: 20px;
  width: clamp(60px, 11vw, 224px);
  height: auto;
  border-radius: 20px;
}

.center {
  display: flex;
  flex-direction: column;
  align-items: center;
  padding-top: clamp(20px, 5vw, 40px);
}

.title-block {
  text-align: center;
  margin-bottom: clamp(16px, 3vw, 30px);
}

.title {
  font-size: clamp(36px, 7vw, 80px);
  color: #185FA5;
  font-weight: 900;
  line-height: 1;
}

.tagline {
  font-size: clamp(14px, 2.5vw, 32px);
  color: #185FA5;
  margin-top: 4px;
  padding-left: 40%;
  text-align: left;
  white-space: nowrap;
}

.description {
  font-size: clamp(14px, 2vw, 26px);
  color: #333;
  text-align: center;
  margin: clamp(12px, 2vw, 20px) auto clamp(24px, 5vw, 60px);
  max-width: min(1000px, 90vw);
  line-height: 1.6;
}

.actions {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  width: 100%;
  max-width: min(900px, 90vw);
  margin-top: clamp(32px, 8vw, 120px);
  flex-wrap: wrap;
  gap: clamp(12px, 2vw, 24px);
}

.btn-primary {
  background-color: #185FA5;
  color: white;
  border: none;
  padding: clamp(10px, 1.2vw, 14px) 0;
  border-radius: 8px;
  cursor: pointer;
  font-size: clamp(14px, 1.6vw, 20px);
  font-family: 'Inter', sans-serif;
  width: clamp(140px, 28vw, 300px);
}

.btn-primary:hover {
  background-color: #134d87;
}

.contact-wrapper {
  position: relative;
  width: clamp(140px, 28vw, 300px);
}

.contact-dropdown {
  background-color: #4a7fd4;
  border-radius: 8px;
  padding: 6px 0;
  width: 100%;
  margin-top: 0px;
}

.contact-dropdown p {
  color: white;
  padding: clamp(6px, 0.8vw, 8px) 20px;
  cursor: pointer;
  margin: 0;
  font-family: 'Inter', sans-serif;
  font-size: clamp(12px, 1.4vw, 16px);
}

.contact-dropdown p:hover {
  background-color: #3a6fc4;
}

@media (max-width: 700px) {
  .tagline {
    padding-left: 0;
    text-align: center;
    white-space: normal;
  }

  .logo {
    top: 16px;
    left: 12px;
    width: clamp(48px, 14vw, 90px);
  }

  .center {
    padding-top: clamp(70px, 16vw, 120px);
  }

  .actions {
    flex-direction: column;
    align-items: center;
    margin-top: clamp(20px, 6vw, 60px);
  }

  .btn-primary,
  .contact-wrapper {
    width: 100%;
    max-width: 360px;
  }
}
</style>