<script setup>
// reset password screen, just validates and sends the user back to login
// the actual reset flow is not implemented for this assignment
import { ref } from 'vue'
import { useRouter } from 'vue-router'
import logo from '../assets/logo.png'

const router = useRouter()

const newPassword = ref('')
const confirmPassword = ref('')
const showPassword1 = ref(false)
const showPassword2 = ref(false)
const errors = ref({})

// must be 8 chars, have a capital letter and a digit, and match the confirm box
function validate() {
  errors.value = {}
  if (!newPassword.value || newPassword.value.length < 8 || !/[A-Z]/.test(newPassword.value) || !/[0-9]/.test(newPassword.value)) {
    errors.value.newPassword = 'Parola are nevoie de minim 8 caractere, o majusculă și o cifră!'
  }
  if (newPassword.value !== confirmPassword.value) {
    errors.value.confirmPassword = 'Parolele trebuie să fie identice!'
  }
  return Object.keys(errors.value).length === 0
}

function save() {
  if (!validate()) return
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

      <div class="form">
        <div class="field">
          <div class="password-toggle">
            👁 <span @click="showPassword1 = !showPassword1">{{ showPassword1 ? 'Ascunde parola' : 'Arată parola' }}</span>
          </div>
          <input v-model="newPassword"
                 :type="showPassword1 ? 'text' : 'password'"
                 placeholder="PAROLA NOUĂ"
                 class="input"
                 :class="{ 'input-error': errors.newPassword }" />
          <span class="error-msg" v-if="errors.newPassword">{{ errors.newPassword }}</span>
        </div>

        <div class="field">
          <div class="password-toggle">
            👁 <span @click="showPassword2 = !showPassword2">{{ showPassword2 ? 'Ascunde parola' : 'Arată parola' }}</span>
          </div>
          <input v-model="confirmPassword"
                 :type="showPassword2 ? 'text' : 'password'"
                 placeholder="REINTRODUCEȚI PAROLA NOUĂ"
                 class="input"
                 :class="{ 'input-error': errors.confirmPassword }" />
          <span class="error-msg" v-if="errors.confirmPassword">{{ errors.confirmPassword }}</span>
        </div>

        <button class="btn-save" @click="save">Salvare</button>
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
  margin-bottom: clamp(24px, 5vw, 60px);
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

.form {
  display: flex;
  flex-direction: column;
  gap: clamp(12px, 1.5vw, 20px);
  width: clamp(260px, 35vw, 400px);
}

.field {
  display: flex;
  flex-direction: column;
  gap: 4px;
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
  box-shadow: none;
}

.input:focus {
  background-color: #e8e8e8;
}

.input-error {
  outline: 1px solid #cc0000;
}

.error-msg {
  color: #cc0000;
  font-size: clamp(10px, 1vw, 13px);
  font-family: 'Courier New', monospace;
}

.password-toggle {
  text-align: right;
  font-size: clamp(11px, 1.1vw, 14px);
  color: #555;
  cursor: pointer;
}

.password-toggle span:hover {
  color: #185FA5;
}

.btn-save {
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

.btn-save:hover {
  background-color: #134d87;
}

@media (max-width: 700px) {
  .tagline {
    padding-left: 0;
    text-align: center;
    white-space: normal;
  }

  .form {
    width: 100%;
    max-width: 360px;
  }

  .logo {
    top: 16px;
    left: 12px;
    width: clamp(48px, 14vw, 90px);
  }

  .center {
    padding-top: clamp(80px, 18vw, 120px);
  }
}
</style>