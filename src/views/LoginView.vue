<script setup>
// login page, the user enters email and password and we call the auth api
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import logo from '../assets/logo.png'
import { auth } from '../api.js'
import { refreshCurrentUser } from '../utils/auth.js'

const router = useRouter()

// form state and error messages
const email       = ref('')
const password    = ref('')
const showPassword = ref(false)
const errors      = ref({})
const apiError    = ref('')

// basic client side checks, the server does the real validation too
function validate() {
  errors.value = {}

  if (!email.value.trim()) {
    errors.value.email = 'Introduceți e-mailul sau numărul de telefon'
  } else if (email.value.includes('@') && !/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value)) {
    errors.value.email = 'Adresa de e-mail nu este validă'
  }

  if (!password.value.trim()) {
    errors.value.password = 'Introduceți parola'
  } else if (password.value.length < 6) {
    errors.value.password = 'Parola trebuie să aibă cel puțin 6 caractere'
  }

  return Object.keys(errors.value).length === 0
}

async function login() {
  if (!validate()) return
  apiError.value = ''
  try {
    const res = await auth.login(email.value.trim(), password.value)
    // save the user so the comments page knows who is writing
    if (res?.user) sessionStorage.setItem('currentUser', JSON.stringify(res.user))
    refreshCurrentUser()  // make role and perms available to the rest of the app right away
    router.push('/main')
  } catch (e) {
    apiError.value = e.message || 'Email sau parolă incorecte'
  }
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

      <div class="form">
        <div v-if="apiError" class="api-error">{{ apiError }}</div>

        <div class="field">
          <input v-model="email"
                 type="text"
                 placeholder="E-MAIL/NR. TELEFON"
                 class="input"
                 :class="{ 'input-error': errors.email }" />
          <span class="error-msg" v-if="errors.email">{{ errors.email }}</span>
        </div>

        <div class="field">
          <div class="password-toggle">
            👁 <span @click="showPassword = !showPassword">{{ showPassword ? 'Ascunde parola' : 'Arată parola' }}</span>
          </div>
          <input v-model="password"
                 :type="showPassword ? 'text' : 'password'"
                 placeholder="PAROLĂ"
                 class="input"
                 :class="{ 'input-error': errors.password }" />
          <span class="error-msg" v-if="errors.password">{{ errors.password }}</span>
        </div>

        <p class="forgot" @click="router.push('/reset-password')">Am uitat parola</p>

        <button class="btn-login" @click="login">Conectare</button>
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
  top: 30px; left: 20px;
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

.title-block { text-align: center; margin-bottom: clamp(24px, 5vw, 60px); }

.title { font-size: clamp(36px, 7vw, 80px); color: #185FA5; font-weight: 900; line-height: 1; }

.tagline {
  font-size: clamp(14px, 2.5vw, 32px);
  color: #185FA5;
  margin-top: 4px;
  padding-left: 40%;
  text-align: left;
  white-space: nowrap;
}

.form {
  display: flex;
  flex-direction: column;
  gap: clamp(12px, 1.5vw, 20px);
  width: clamp(260px, 35vw, 400px);
}

.field { display: flex; flex-direction: column; gap: 4px; }

.api-error {
  background: #ffe5e5;
  color: #cc0000;
  border: 1px solid #cc0000;
  border-radius: 8px;
  padding: 10px 16px;
  font-size: 14px;
}

.input {
  padding: clamp(10px, 1.2vw, 14px) 16px;
  border: none;
  background-color: #f0f0f0;
  font-size: clamp(12px, 1.2vw, 15px);
  font-family: 'Inter', sans-serif;
  outline: none;
  color: #555;
  letter-spacing: 0.5px;
}

.input:focus { background-color: #e8e8e8; }

.input-error { outline: 1px solid #cc0000; }

.error-msg { color: #cc0000; font-size: clamp(10px, 1vw, 12px); }

.password-toggle { text-align: right; font-size: clamp(11px, 1.1vw, 14px); color: #555; cursor: pointer; }

.password-toggle span:hover { color: #185FA5; }

.forgot {
  color: #185FA5;
  font-size: clamp(13px, 1.4vw, 18px);
  font-weight: 700;
  cursor: pointer;
  text-align: center;
  font-family: 'Courier New', monospace;
}

.forgot:hover { text-decoration: underline; }

.btn-login {
  background-color: #185FA5;
  color: white;
  border: none;
  padding: clamp(10px, 1.4vw, 16px);
  border-radius: 8px;
  cursor: pointer;
  font-size: clamp(14px, 1.5vw, 18px);
  font-family: 'Inter', sans-serif;
  width: 100%;
  margin-top: 8px;
}

.btn-login:hover { background-color: #134d87; }

@media (max-width: 700px) {
  .tagline { padding-left: 0; text-align: center; white-space: normal; }
  .form { width: 100%; max-width: 360px; }
  .logo { top: 16px; left: 12px; width: clamp(48px, 14vw, 90px); }
  .center { padding-top: clamp(80px, 18vw, 120px); }
}
</style>