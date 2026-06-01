<script setup>
// silver, password recovery, two steps
// step 1, ask for an email and call /auth/forgot
// step 2, paste the code from the mock inbox + a new password, call /auth/reset
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import logo from '../assets/logo.png'
import { auth } from '../api.js'

const router = useRouter()

const step = ref('email')   // "email" -> "reset" -> done
const email           = ref('')
const code            = ref('')
const newPassword     = ref('')
const confirmPassword = ref('')
const showPwd         = ref(false)
const errors          = ref({})
const apiError        = ref('')
const successMsg      = ref('')


async function requestCode() {
  errors.value = {}
  apiError.value = ''
  const e = email.value.trim()
  if (!e) errors.value.email = 'Introduceți e-mailul'
  else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) errors.value.email = 'E-mail invalid'
  if (Object.keys(errors.value).length) return

  try {
    await auth.forgot(e)
    // we move to step 2 regardless of whether the email exists, the server
    // intentionally returns 200 either way so we dont leak which addresses are
    // registered
    step.value = 'reset'
    successMsg.value = 'Dacă există un cont, am trimis codul în Inbox.'
  } catch (err) {
    apiError.value = err.message || 'Eroare la trimitere'
  }
}


async function doReset() {
  errors.value = {}
  apiError.value = ''
  if (!code.value.trim()) errors.value.code = 'Introduceți codul'
  if (!newPassword.value || newPassword.value.length < 6
      || !/\d/.test(newPassword.value) || !/[a-zA-Z]/.test(newPassword.value)) {
    errors.value.newPassword = 'Min 6 caractere, cel puțin o literă și o cifră'
  }
  if (newPassword.value !== confirmPassword.value) {
    errors.value.confirmPassword = 'Parolele nu coincid'
  }
  if (Object.keys(errors.value).length) return

  try {
    await auth.reset(code.value.trim(), newPassword.value)
    // sessions from before the reset are now revoked server side
    router.push('/login')
  } catch (e) {
    let msg = 'Resetare eșuată'
    try { const p = JSON.parse(e.message); if (p.detail) msg = p.detail } catch {}
    apiError.value = msg
  }
}
</script>

<template>
  <div class="landing">
    <img :src="logo" alt="ProElev Logo" class="logo" />

    <div class="center">
      <div class="title-block">
        <h1 class="title">Recuperare parolă</h1>
        <p class="tagline">Ne ocupăm să te aducem înapoi în cont</p>
      </div>

      <div class="form">
        <div v-if="apiError" class="api-error">{{ apiError }}</div>
        <div v-if="successMsg && step === 'reset'" class="api-info">{{ successMsg }}</div>

        <!-- step 1, ask for email -->
        <template v-if="step === 'email'">
          <div class="field">
            <input v-model="email" type="text" placeholder="E-MAIL"
                   class="input" :class="{ 'input-error': errors.email }"
                   @keyup.enter="requestCode" />
            <span class="error-msg" v-if="errors.email">{{ errors.email }}</span>
          </div>
          <button class="btn-login" @click="requestCode">Trimite codul</button>
          <p class="register-link">
            <span class="link" @click="router.push('/login')">Înapoi la conectare</span>
          </p>
        </template>

        <!-- step 2, code + new password -->
        <template v-else-if="step === 'reset'">
          <p class="hint">Verifică
            <span class="link" @click="router.push('/inbox')">Inbox-ul mock</span>
            și copiază codul de mai jos.
          </p>
          <div class="field">
            <input v-model="code" type="text" placeholder="COD DE RESETARE"
                   class="input" :class="{ 'input-error': errors.code }" />
            <span class="error-msg" v-if="errors.code">{{ errors.code }}</span>
          </div>
          <div class="field">
            <input v-model="newPassword" :type="showPwd ? 'text' : 'password'"
                   placeholder="PAROLĂ NOUĂ" class="input"
                   :class="{ 'input-error': errors.newPassword }" />
            <span class="error-msg" v-if="errors.newPassword">{{ errors.newPassword }}</span>
          </div>
          <div class="field">
            <input v-model="confirmPassword" :type="showPwd ? 'text' : 'password'"
                   placeholder="CONFIRMĂ PAROLA" class="input"
                   :class="{ 'input-error': errors.confirmPassword }"
                   @keyup.enter="doReset" />
            <span class="error-msg" v-if="errors.confirmPassword">{{ errors.confirmPassword }}</span>
          </div>
          <div class="password-toggle">
            <span @click="showPwd = !showPwd">{{ showPwd ? 'Ascunde parolele' : 'Arată parolele' }}</span>
          </div>
          <button class="btn-login" @click="doReset">Schimbă parola</button>
          <p class="register-link">
            <span class="link" @click="step = 'email'">Trimite alt cod</span>
          </p>
        </template>
      </div>
    </div>
  </div>
</template>

<style scoped>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;700;900&display=swap');

.landing { min-height: 100vh; padding: clamp(20px, 4vw, 40px) clamp(20px, 5vw, 60px); background-color: white; font-family: 'Inter', sans-serif; position: relative; }
.logo { position: absolute; top: 30px; left: 20px; width: clamp(60px, 11vw, 224px); height: auto; border-radius: 20px; }
.center { display: flex; flex-direction: column; align-items: center; padding-top: clamp(20px, 5vw, 40px); }
.title-block { text-align: center; margin-bottom: clamp(24px, 5vw, 60px); }
.title { font-size: clamp(28px, 5vw, 60px); color: #185FA5; font-weight: 900; line-height: 1; }
.tagline { font-size: clamp(13px, 1.7vw, 18px); color: #185FA5; margin-top: 4px; text-align: center; }
.form { width: clamp(280px, 50vw, 420px); display: flex; flex-direction: column; gap: clamp(8px, 1.5vw, 12px); }
.field { display: flex; flex-direction: column; gap: 4px; }
.input { padding: clamp(10px, 1.6vw, 14px) clamp(12px, 1.8vw, 16px); border: 1px solid #ccc; border-radius: 10px; font-size: clamp(13px, 1.5vw, 16px); font-family: 'Inter', sans-serif; outline: none; }
.input:focus { border-color: #185FA5; }
.input-error { border-color: #cc0000; }
.error-msg { color: #cc0000; font-size: clamp(11px, 1.2vw, 13px); }
.api-error { background: #ffe5e5; color: #cc0000; border: 1px solid #cc0000; border-radius: 8px; padding: 10px 16px; font-size: clamp(12px, 1.3vw, 14px); }
.api-info  { background: #e8f2ff; color: #134d87; border: 1px solid #185FA5; border-radius: 8px; padding: 10px 16px; font-size: clamp(12px, 1.3vw, 14px); }
.password-toggle { font-size: clamp(11px, 1.2vw, 13px); color: #555; cursor: pointer; align-self: flex-end; }
.btn-login { background-color: #185FA5; color: white; border: none; border-radius: 10px; padding: clamp(10px, 1.6vw, 14px); cursor: pointer; font-weight: 700; font-size: clamp(14px, 1.5vw, 18px); font-family: 'Inter', sans-serif; width: 100%; margin-top: 8px; }
.btn-login:hover { background-color: #134d87; }
.register-link { margin-top: 16px; text-align: center; font-size: clamp(13px, 1.3vw, 15px); color: #555; }
.register-link .link, .hint .link { color: #185FA5; font-weight: 700; cursor: pointer; }
.register-link .link:hover, .hint .link:hover { text-decoration: underline; }
.hint { font-size: clamp(12px, 1.3vw, 14px); color: #444; text-align: center; margin: 0; }

@media (max-width: 700px) {
  .tagline { padding-left: 0; text-align: center; white-space: normal; }
  .form { width: 100%; max-width: 360px; }
  .logo { top: 16px; left: 12px; width: clamp(48px, 14vw, 90px); }
  .center { padding-top: clamp(80px, 18vw, 120px); }
}
</style>
