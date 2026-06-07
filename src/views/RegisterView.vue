<script setup>
// register a new account, server hashes the password and sends back a
// session token, we drop the user straight into /main after that.
// assignment 6: an optional invite code unlocks the teacher/student/parent
// roles. without a code the new account stays plain "user".
import { ref, computed } from 'vue'
import { useRouter } from 'vue-router'
import logo from '../assets/logo.png'
import { auth, lookups } from '../api.js'
import { setSession } from '../utils/auth.js'

const router = useRouter()

const name              = ref('')
const email             = ref('')
const password          = ref('')
const confirm           = ref('')
const securityQuestion  = ref('Care este orașul tău natal?')
const securityAnswer    = ref('')
const showPassword      = ref(false)
const errors            = ref({})
const apiError          = ref('')

// assignment 6, invite code + role-specific extras
const inviteCode      = ref('')
const inviteInfo      = ref(null)   // { role, class, subject }
const inviteError     = ref('')
const classOptions    = ref([])
const subjectOptions  = ref([])
const pickedClassId   = ref(null)
const pickedSubjectId = ref(null)
const childrenEmails  = ref([''])

const needsClass = computed(() =>
  inviteInfo.value && (inviteInfo.value.role === 'student' || inviteInfo.value.role === 'teacher')
  && !inviteInfo.value.class
)
const needsSubject = computed(() =>
  inviteInfo.value && inviteInfo.value.role === 'teacher' && !inviteInfo.value.subject
)
const needsChildren = computed(() =>
  inviteInfo.value && inviteInfo.value.role === 'parent'
)

async function loadLookups() {
  if (classOptions.value.length && subjectOptions.value.length) return
  try {
    const cls = await lookups.classes()
    const sub = await lookups.subjects()
    classOptions.value   = cls
    subjectOptions.value = sub
  } catch {}
}

// debounce check of the invite code, called on blur and on Continue
async function checkInvite() {
  inviteError.value = ''
  inviteInfo.value  = null
  const code = inviteCode.value.trim()
  if (!code) return
  try {
    const info = await auth.checkInvite(code)
    inviteInfo.value = info
    await loadLookups()
  } catch (e) {
    let msg = 'Cod invalid'
    try { const p = JSON.parse(e.message); if (p.detail) msg = p.detail } catch {}
    inviteError.value = msg
  }
}

function addChildField() {
  childrenEmails.value.push('')
}
function removeChildField(i) {
  childrenEmails.value.splice(i, 1)
  if (childrenEmails.value.length === 0) childrenEmails.value.push('')
}

// client side checks, the server runs the same checks plus uniqueness
function validate() {
  errors.value = {}

  if (!name.value.trim()) {
    errors.value.name = 'Introduceți numele'
  } else if (name.value.trim().length > 150) {
    errors.value.name = 'Numele nu poate depăși 150 de caractere'
  }

  const e = email.value.trim()
  if (!e) {
    errors.value.email = 'Introduceți e-mailul'
  } else if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) {
    errors.value.email = 'Adresa de e-mail nu este validă'
  }

  if (!password.value) {
    errors.value.password = 'Introduceți parola'
  } else if (password.value.length < 6) {
    errors.value.password = 'Parola trebuie să aibă cel puțin 6 caractere'
  } else if (!/\d/.test(password.value) || !/[a-zA-Z]/.test(password.value)) {
    errors.value.password = 'Parola trebuie să conțină litere și cifre'
  }

  if (confirm.value !== password.value) {
    errors.value.confirm = 'Parolele nu coincid'
  }

  // silver, security question + answer required for the 3rd login factor
  if (!securityQuestion.value.trim() || securityQuestion.value.trim().length < 5) {
    errors.value.securityQuestion = 'Întrebarea trebuie să aibă cel puțin 5 caractere'
  }
  if (!securityAnswer.value.trim() || securityAnswer.value.trim().length < 2) {
    errors.value.securityAnswer = 'Răspunsul trebuie să aibă cel puțin 2 caractere'
  }

  // assignment 6, role-specific bits
  if (inviteInfo.value) {
    if (needsClass.value && !pickedClassId.value) {
      errors.value.classId = 'Selectează clasa'
    }
    if (needsSubject.value && !pickedSubjectId.value) {
      errors.value.subjectId = 'Selectează materia'
    }
    if (needsChildren.value) {
      const cleaned = childrenEmails.value.map(s => s.trim()).filter(s => s)
      if (cleaned.length === 0) {
        errors.value.children = 'Adaugă cel puțin un copil'
      } else {
        for (const e of cleaned) {
          if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(e)) {
            errors.value.children = 'Toate emailurile copiilor trebuie să fie valide'
            break
          }
        }
      }
    }
  }

  return Object.keys(errors.value).length === 0
}

async function submit() {
  if (!validate()) return
  apiError.value = ''
  // build the optional payload pieces only if there's an invite code
  const extra = {}
  if (inviteCode.value.trim()) {
    extra.invite_code = inviteCode.value.trim()
    if (inviteInfo.value) {
      if (inviteInfo.value.class) {
        extra.class_id = inviteInfo.value.class.id
      } else if (pickedClassId.value) {
        extra.class_id = pickedClassId.value
      }
      if (inviteInfo.value.subject) {
        extra.subject_id = inviteInfo.value.subject.id
      } else if (pickedSubjectId.value) {
        extra.subject_id = pickedSubjectId.value
      }
      if (needsChildren.value) {
        extra.children_emails = childrenEmails.value.map(s => s.trim()).filter(s => s)
      }
    }
  }
  try {
    const res = await auth.register(
      name.value.trim(),
      email.value.trim(),
      password.value,
      securityQuestion.value.trim(),
      securityAnswer.value.trim(),
      extra,
    )
    if (res?.user && res?.access_token) setSession(res.user, res.access_token)
    router.push('/main')
  } catch (e) {
    // surface the server message, fallbacks for the common ones
    let msg = 'Înregistrarea a eșuat'
    try {
      const parsed = JSON.parse(e.message)
      if (parsed.detail) msg = parsed.detail
    } catch {
      if (e._httpStatus === 409) msg = 'Email-ul este deja folosit'
    }
    apiError.value = msg
  }
}
</script>

<template>
  <div class="landing">
    <img :src="logo" alt="ProElev Logo" class="logo" />

    <div class="center">
      <div class="title-block">
        <h1 class="title">Cont nou</h1>
        <p class="tagline">Înregistrează-te pentru a accesa ProElev</p>
      </div>

      <div class="form">
        <div v-if="apiError" class="api-error">{{ apiError }}</div>

        <!-- assignment 6, optional invite code at the top -->
        <p class="section-label">Cod de invitație (opțional)</p>
        <div class="field">
          <input v-model="inviteCode" type="text" placeholder="EX. ABCD1234EF5678" class="input"
                 :class="{ 'input-error': inviteError }"
                 @blur="checkInvite" />
          <span class="error-msg" v-if="inviteError">{{ inviteError }}</span>
          <span class="hint-msg" v-else-if="inviteInfo">
            Cont nou ca <b>{{ inviteInfo.role }}</b>
            <template v-if="inviteInfo.class"> · clasă {{ inviteInfo.class.name }}</template>
            <template v-if="inviteInfo.subject"> · materie {{ inviteInfo.subject.name }}</template>
          </span>
          <span class="hint-msg" v-else>
            Lasă gol pentru cont standard. Cere admin-ului un cod pentru profesor / elev / părinte.
          </span>
        </div>

        <!-- role-specific extras (visible only when an invite code is verified) -->
        <template v-if="needsClass">
          <div class="field">
            <select v-model="pickedClassId" class="input"
                    :class="{ 'input-error': errors.classId }">
              <option :value="null" disabled>SELECTEAZĂ CLASA</option>
              <option v-for="c in classOptions" :key="c.id" :value="c.id">{{ c.name }}</option>
            </select>
            <span class="error-msg" v-if="errors.classId">{{ errors.classId }}</span>
          </div>
        </template>
        <template v-if="needsSubject">
          <div class="field">
            <select v-model="pickedSubjectId" class="input"
                    :class="{ 'input-error': errors.subjectId }">
              <option :value="null" disabled>SELECTEAZĂ MATERIA</option>
              <option v-for="s in subjectOptions" :key="s.id" :value="s.id">{{ s.name }}</option>
            </select>
            <span class="error-msg" v-if="errors.subjectId">{{ errors.subjectId }}</span>
          </div>
        </template>
        <template v-if="needsChildren">
          <p class="section-label">Copiii tăi (email-ul de elev)</p>
          <div v-for="(em, idx) in childrenEmails" :key="idx" class="field child-row">
            <input v-model="childrenEmails[idx]" type="text" placeholder="EMAIL COPIL"
                   class="input" />
            <button class="btn-mini" @click="removeChildField(idx)" v-if="childrenEmails.length > 1">×</button>
          </div>
          <button class="btn-mini-wide" @click="addChildField">+ Mai adaugă un copil</button>
          <span class="error-msg" v-if="errors.children">{{ errors.children }}</span>
        </template>

        <p class="section-label">Datele tale</p>
        <div class="field">
          <input v-model="name" type="text" placeholder="NUME COMPLET"
                 class="input" :class="{ 'input-error': errors.name }" />
          <span class="error-msg" v-if="errors.name">{{ errors.name }}</span>
        </div>

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
                 :class="{ 'input-error': errors.password }" />
          <span class="error-msg" v-if="errors.password">{{ errors.password }}</span>
        </div>

        <div class="field">
          <input v-model="confirm" :type="showPassword ? 'text' : 'password'"
                 placeholder="CONFIRMĂ PAROLA" class="input"
                 :class="{ 'input-error': errors.confirm }" />
          <span class="error-msg" v-if="errors.confirm">{{ errors.confirm }}</span>
        </div>

        <!-- silver, 3rd factor for login and password recovery -->
        <p class="section-label">Întrebare de securitate</p>
        <div class="field">
          <select v-model="securityQuestion" class="input"
                  :class="{ 'input-error': errors.securityQuestion }">
            <option>Care este orașul tău natal?</option>
            <option>Care este numele primului tău profesor?</option>
            <option>Care era numele primului tău animal de companie?</option>
            <option>Care este materia ta preferată?</option>
          </select>
          <span class="error-msg" v-if="errors.securityQuestion">{{ errors.securityQuestion }}</span>
        </div>
        <div class="field">
          <input v-model="securityAnswer" type="text"
                 placeholder="RĂSPUNS" class="input"
                 :class="{ 'input-error': errors.securityAnswer }" />
          <span class="error-msg" v-if="errors.securityAnswer">{{ errors.securityAnswer }}</span>
        </div>

        <button class="btn-login" @click="submit">Înregistrare</button>

        <p class="register-link">
          Ai deja cont?
          <span class="link" @click="router.push('/login')">Conectează-te</span>
        </p>
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
.tagline { font-size: clamp(14px, 2.5vw, 28px); color: #185FA5; margin-top: 4px; text-align: center; }
.form { width: clamp(280px, 50vw, 420px); display: flex; flex-direction: column; gap: clamp(8px, 1.5vw, 12px); }
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
.register-link .link { color: #185FA5; font-weight: 700; cursor: pointer; margin-left: 4px; }
.register-link .link:hover { text-decoration: underline; }
.section-label {
  margin: 8px 0 2px; font-size: clamp(11px, 1.2vw, 13px);
  text-transform: uppercase; color: #888; letter-spacing: 0.05em;
}
.hint-msg {
  font-size: clamp(11px, 1.2vw, 13px); color: #134d87;
}
.child-row {
  flex-direction: row !important; align-items: center; gap: 6px !important;
}
.child-row .input { flex: 1; }
.btn-mini {
  background: transparent; border: 1px solid #cc0000; color: #cc0000;
  width: 30px; height: 30px; border-radius: 50%; cursor: pointer;
  font-size: 16px; line-height: 1;
}
.btn-mini-wide {
  background: #e0ecf8; color: #185FA5; border: none; padding: 6px 12px;
  border-radius: 8px; cursor: pointer; font-size: 12px; font-weight: 700;
  align-self: flex-start; margin-top: 4px;
}

@media (max-width: 700px) {
  .tagline { padding-left: 0; text-align: center; white-space: normal; }
  .form { width: 100%; max-width: 360px; }
  .logo { top: 16px; left: 12px; width: clamp(48px, 14vw, 90px); }
  .center { padding-top: clamp(80px, 18vw, 120px); }
}
</style>
