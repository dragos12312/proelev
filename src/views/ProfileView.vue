<script setup>
// Profil & setări. Three cards in one column:
// - schimbă numele
// - schimbă parola (cere parola actuală)
// - schimbă întrebarea + răspunsul de siguranță (cere parola actuală)
import { ref } from 'vue'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { profileApi } from '../api.js'
import { currentUser, setSession, authToken } from '../utils/auth.js'

const nameDraft  = ref(currentUser.value?.name || '')
const nameMsg    = ref('')
const nameErr    = ref('')

const pwOld      = ref('')
const pwNew      = ref('')
const pwNew2     = ref('')
const pwMsg      = ref('')
const pwErr      = ref('')

const secPw      = ref('')
const secQ       = ref(currentUser.value?.security_question || '')
const secA       = ref('')
const secMsg     = ref('')
const secErr     = ref('')

async function saveName() {
  nameMsg.value = ''; nameErr.value = ''
  if (!nameDraft.value.trim() || nameDraft.value.trim().length < 2) {
    nameErr.value = 'Numele trebuie să aibă cel puțin 2 caractere'; return
  }
  try {
    const r = await profileApi.updateName(nameDraft.value.trim())
    nameMsg.value = 'Salvat'
    // refresh session so the header / dashboard show the new name immediately
    const cu = { ...(currentUser.value || {}), name: r.name }
    setSession(cu, authToken.value)
    setTimeout(() => { nameMsg.value = '' }, 2500)
  } catch (e) {
    nameErr.value = e.message || 'Eroare'
  }
}

async function savePassword() {
  pwMsg.value = ''; pwErr.value = ''
  if (pwNew.value.length < 6) { pwErr.value = 'Parola nouă: minim 6 caractere'; return }
  if (pwNew.value !== pwNew2.value) { pwErr.value = 'Parolele nu coincid'; return }
  try {
    await profileApi.updatePassword(pwOld.value, pwNew.value)
    pwMsg.value = 'Parola a fost actualizată.'
    pwOld.value = ''; pwNew.value = ''; pwNew2.value = ''
    setTimeout(() => { pwMsg.value = '' }, 3000)
  } catch (e) {
    pwErr.value = e.message || 'Eroare'
  }
}

async function saveSecurity() {
  secMsg.value = ''; secErr.value = ''
  if (!secPw.value) { secErr.value = 'Introdu parola actuală'; return }
  if (secQ.value.trim().length < 4) { secErr.value = 'Întrebarea: minim 4 caractere'; return }
  if (secA.value.trim().length < 2) { secErr.value = 'Răspunsul: minim 2 caractere'; return }
  try {
    await profileApi.updateSecurity(secPw.value, secQ.value.trim(), secA.value.trim())
    secMsg.value = 'Întrebarea de siguranță a fost actualizată.'
    secPw.value = ''; secA.value = ''
    setTimeout(() => { secMsg.value = '' }, 3000)
  } catch (e) {
    secErr.value = e.message || 'Eroare'
  }
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="profil" />
      <div class="main">
        <h2 class="page-title">PROFIL ȘI SETĂRI</h2>

        <div class="card">
          <h3>Datele tale</h3>
          <p class="muted small">
            Conectat ca <b>{{ currentUser?.email }}</b> ({{ currentUser?.role }})
          </p>
          <label>Nume afișat</label>
          <input v-model="nameDraft" type="text" maxlength="150" />
          <button class="btn" @click="saveName">Salvează</button>
          <div v-if="nameMsg" class="msg ok">{{ nameMsg }}</div>
          <div v-if="nameErr" class="msg err">{{ nameErr }}</div>
        </div>

        <div class="card">
          <h3>Schimbă parola</h3>
          <label>Parola actuală</label>
          <input v-model="pwOld"  type="password" autocomplete="current-password" />
          <label>Parola nouă</label>
          <input v-model="pwNew"  type="password" autocomplete="new-password" />
          <label>Confirmă parola nouă</label>
          <input v-model="pwNew2" type="password" autocomplete="new-password" />
          <button class="btn" @click="savePassword">Salvează parola</button>
          <div v-if="pwMsg" class="msg ok">{{ pwMsg }}</div>
          <div v-if="pwErr" class="msg err">{{ pwErr }}</div>
        </div>

        <div class="card">
          <h3>Întrebarea de siguranță</h3>
          <p class="muted small">
            Folosită ca al treilea factor de autentificare.
          </p>
          <label>Parola actuală (pentru confirmare)</label>
          <input v-model="secPw" type="password" autocomplete="current-password" />
          <label>Întrebarea nouă</label>
          <input v-model="secQ" type="text" maxlength="255" />
          <label>Răspunsul nou</label>
          <input v-model="secA" type="text" maxlength="255" />
          <button class="btn" @click="saveSecurity">Salvează întrebarea</button>
          <div v-if="secMsg" class="msg ok">{{ secMsg }}</div>
          <div v-if="secErr" class="msg err">{{ secErr }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.content { display: flex; align-items: flex-start; }
.main {
  flex: 1; min-width: 0;
  padding: clamp(12px, 2.5vw, 24px); padding-right: clamp(40px, 6vw, 80px);
  font-family: 'Inter', sans-serif;
}
.page-title { font-size: clamp(18px, 3vw, 24px); color: #185FA5; font-weight: 700; margin-bottom: 16px; }

.card {
  background: white; border: 1px solid #d0d7e2; border-radius: 12px;
  padding: 18px; margin-bottom: 18px; max-width: 560px;
}
.card h3 { color: #185FA5; margin: 0 0 10px; font-size: 15px; }
.muted { color: #666; }
.muted.small { font-size: 12px; margin-top: 0; margin-bottom: 14px; }
label {
  display: block; margin-top: 8px; margin-bottom: 4px;
  color: #555; font-size: 12px; font-weight: 700;
}
input {
  width: 100%; box-sizing: border-box; padding: 9px 12px;
  border: 1px solid #d0d7e2; border-radius: 8px;
  font-family: 'Inter', sans-serif; font-size: 14px;
}
.btn {
  margin-top: 14px;
  background: #185FA5; color: white; border: none; padding: 9px 22px;
  border-radius: 8px; cursor: pointer; font-weight: 700;
  font-family: 'Inter', sans-serif;
}
.btn:hover { background: #134d87; }
.msg { margin-top: 10px; font-size: 13px; padding: 8px 12px; border-radius: 8px; }
.msg.ok  { background: #d4edda; color: #155724; }
.msg.err { background: #ffe5e5; color: #cc0000; }
</style>
