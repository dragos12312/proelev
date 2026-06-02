<script setup>
// silver, 3 factor login wizard
// step 1, password.   factor 1, the user types email + password
// step 2, email code. factor 2, the user reads the 6 digit code from the mock
//                     inbox and types it back
// step 3, question.   factor 3, the user answers their security question
// each step swaps the visible fields but keeps the same panel layout
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import logo from '../assets/logo.png'
import { auth } from '../api.js'
import { setSession } from '../utils/auth.js'

const router = useRouter()

// state machine, "password" -> "email_code" -> "security_question" -> done
const step = ref('password')

// form state, kept across the wizard
const email        = ref('')
const password     = ref('')
const showPassword = ref(false)
const code         = ref('')
const question     = ref('')
const answer       = ref('')
const challengeId  = ref('')

const errors   = ref({})
const apiError = ref('')

// step 1
async function submitPassword() {
  errors.value = {}
  apiError.value = ''
  if (!email.value.trim()) errors.value.email = 'Introduceți e-mailul'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email.value.trim()))
    errors.value.email = 'Adresa de e-mail nu este validă'
  if (!password.value.trim()) errors.value.password = 'Introduceți parola'
  if (Object.keys(errors.value).length) return

  try {
    const res = await auth.login(email.value.trim(), password.value)
    challengeId.value = res.challenge_id
    step.value = 'email_code'
  } catch (e) {
    apiError.value = e.message || 'Email sau parolă incorecte'
  }
}

// step 2
async function submitCode() {
  errors.value = {}
  apiError.value = ''
  if (!code.value.trim()) {
    errors.value.code = 'Introduceți codul'
    return
  }
  try {
    const res = await auth.verifyEmail(challengeId.value, code.value.trim())
    question.value = res.security_question
    step.value = 'security_question'
  } catch (e) {
    apiError.value = e.message || 'Cod incorect'
  }
}

// auto fill the code by fetching the latest email for this address from the
// public mock inbox endpoint, so the user doesnt have to navigate away and
// lose the wizard state
async function autofillCode() {
  apiError.value = ''
  errors.value = {}
  try {
    const base = import.meta.env.VITE_API_URL || 'http://localhost:8000'
    const res = await fetch(
      `${base}/auth/inbox/last?to=${encodeURIComponent(email.value.trim())}`,
      { headers: { 'ngrok-skip-browser-warning': 'true' } },
    )
    if (!res.ok) {
      apiError.value = res.status === 404 ? 'Inbox-ul este gol încă, mai încearcă' : 'Eroare la inbox'
      return
    }
    const msg = await res.json()
    if (msg && msg.code) code.value = String(msg.code)
  } catch (e) {
    apiError.value = e.message || 'Eroare la inbox'
  }
}

// step 3
async function submitAnswer() {
  errors.value = {}
  apiError.value = ''
  if (!answer.value.trim()) {
    errors.value.answer = 'Răspunsul nu poate fi gol'
    return
  }
  try {
    const res = await auth.verifyQuestion(challengeId.value, answer.value.trim())
    if (res?.user && res?.access_token) setSession(res.user, res.access_token)
    router.push('/main')
  } catch (e) {
    apiError.value = e.message || 'Răspuns incorect'
  }
}

function resetWizard() {
  step.value = 'password'
  code.value = ''
  question.value = ''
  answer.value = ''
  challengeId.value = ''
  errors.value = {}
  apiError.value = ''
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

        <!-- progress dots -->
        <div class="dots">
          <span class="dot" :class="{ active: step === 'password',          done: step !== 'password' }">1</span>
          <span class="dot" :class="{ active: step === 'email_code',        done: step === 'security_question' }">2</span>
          <span class="dot" :class="{ active: step === 'security_question' }">3</span>
        </div>

        <!-- step 1, password -->
        <template v-if="step === 'password'">
          <div class="field">
            <input v-model="email" type="text" placeholder="E-MAIL"
                   class="input" :class="{ 'input-error': errors.email }" />
            <span class="error-msg" v-if="errors.email">{{ errors.email }}</span>
          </div>
          <div class="field">
            <div class="password-toggle">
              👁 <span @click="showPassword = !showPassword">{{ showPassword ? 'Ascunde parola' : 'Arată parola' }}</span>
            </div>
            <input v-model="password" :type="showPassword ? 'text' : 'password'"
                   placeholder="PAROLĂ" class="input"
                   :class="{ 'input-error': errors.password }"
                   @keyup.enter="submitPassword" />
            <span class="error-msg" v-if="errors.password">{{ errors.password }}</span>
          </div>
          <p class="forgot" @click="router.push('/reset-password')">Am uitat parola</p>
          <button class="btn-login" @click="submitPassword">Continuă</button>
          <p class="register-link">
            Nu ai cont?
            <span class="link" @click="router.push('/register')">Creează unul aici</span>
          </p>
        </template>

        <!-- step 2, email code -->
        <template v-else-if="step === 'email_code'">
          <p class="hint">Ți-am trimis un cod de 6 cifre la <b>{{ email }}</b>.</p>
          <p class="hint subtle">
            Demo:
            <span class="link" @click="autofillCode">completează codul automat</span>
            sau deschide
            <a class="link" href="/inbox" target="_blank" rel="noopener">Inbox-ul mock</a>
            într-un tab nou.
          </p>
          <div class="field">
            <input v-model="code" type="text" inputmode="numeric" maxlength="6"
                   placeholder="COD DIN EMAIL" class="input"
                   :class="{ 'input-error': errors.code }"
                   @keyup.enter="submitCode" />
            <span class="error-msg" v-if="errors.code">{{ errors.code }}</span>
          </div>
          <button class="btn-login" @click="submitCode">Verifică codul</button>
          <p class="register-link">
            <span class="link" @click="resetWizard">Înapoi la pasul 1</span>
          </p>
        </template>

        <!-- step 3, security question -->
        <template v-else-if="step === 'security_question'">
          <p class="hint">Răspunde la întrebarea ta de securitate:</p>
          <p class="question">{{ question }}</p>
          <div class="field">
            <input v-model="answer" type="text" placeholder="RĂSPUNS"
                   class="input" :class="{ 'input-error': errors.answer }"
                   @keyup.enter="submitAnswer" />
            <span class="error-msg" v-if="errors.answer">{{ errors.answer }}</span>
          </div>
          <button class="btn-login" @click="submitAnswer">Conectare</button>
          <p class="register-link">
            <span class="link" @click="resetWizard">Reîncepe</span>
          </p>
        </template>
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
.center { display: flex; flex-direction: column; align-items: center; padding-top: clamp(20px, 5vw, 40px); }
.title-block { text-align: center; margin-bottom: clamp(24px, 5vw, 60px); }
.title { font-size: clamp(36px, 7vw, 80px); color: #185FA5; font-weight: 900; line-height: 1; }
.tagline { font-size: clamp(14px, 2.5vw, 32px); color: #185FA5; margin-top: 4px; text-align: center; }

.form {
  width: clamp(280px, 50vw, 420px);
  display: flex; flex-direction: column;
  gap: clamp(8px, 1.5vw, 12px);
}

/* progress dots at the top of the form */
.dots {
  display: flex; gap: 8px; justify-content: center; margin-bottom: 8px;
}
.dot {
  width: 28px; height: 28px; border-radius: 50%;
  display: flex; align-items: center; justify-content: center;
  background: #e0e0e0; color: #777; font-weight: 700; font-size: 13px;
}
.dot.active { background: #185FA5; color: white; }
.dot.done   { background: #2a9d2a; color: white; }

.field { display: flex; flex-direction: column; gap: 4px; }
.input {
  padding: clamp(10px, 1.6vw, 14px) clamp(12px, 1.8vw, 16px);
  border: 1px solid #ccc; border-radius: 10px;
  font-size: clamp(13px, 1.5vw, 16px);
  font-family: 'Inter', sans-serif; outline: none;
}
.input:focus { border-color: #185FA5; }
.input-error { border-color: #cc0000; }
.error-msg { color: #cc0000; font-size: clamp(11px, 1.2vw, 13px); }
.api-error {
  background: #ffe5e5; color: #cc0000; border: 1px solid #cc0000;
  border-radius: 8px; padding: 10px 16px; font-size: clamp(12px, 1.3vw, 14px);
}
.password-toggle {
  font-size: clamp(11px, 1.2vw, 13px); color: #555; cursor: pointer; align-self: flex-end;
}
.forgot {
  margin: 0; align-self: flex-end; font-size: clamp(11px, 1.2vw, 13px);
  color: #185FA5; cursor: pointer;
}
.forgot:hover { text-decoration: underline; }

.btn-login {
  background-color: #185FA5; color: white; border: none;
  border-radius: 10px; padding: clamp(10px, 1.6vw, 14px);
  cursor: pointer; font-weight: 700; font-size: clamp(14px, 1.5vw, 18px);
  font-family: 'Inter', sans-serif; width: 100%; margin-top: 8px;
}
.btn-login:hover { background-color: #134d87; }

.register-link {
  margin-top: 16px; text-align: center;
  font-size: clamp(13px, 1.3vw, 15px); color: #555;
}
.register-link .link, .hint .link {
  color: #185FA5; font-weight: 700; cursor: pointer; margin-left: 4px;
  text-decoration: none;
}
.register-link .link:hover, .hint .link:hover { text-decoration: underline; }

.hint {
  font-size: clamp(12px, 1.3vw, 14px);
  color: #444;
  text-align: center;
  margin: 0;
}
.hint.subtle { color: #888; font-size: clamp(11px, 1.2vw, 13px); }
.question {
  background: #e0ecf8; color: #134d87;
  padding: 10px 14px; border-radius: 8px;
  font-size: clamp(13px, 1.4vw, 16px);
  text-align: center; margin: 4px 0;
}

@media (max-width: 700px) {
  .tagline { padding-left: 0; text-align: center; white-space: normal; }
  .form { width: 100%; max-width: 360px; }
  .logo { top: 16px; left: 12px; width: clamp(48px, 14vw, 90px); }
  .center { padding-top: clamp(80px, 18vw, 120px); }
}
</style>
