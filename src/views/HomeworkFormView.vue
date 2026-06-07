<script setup>
// one form used for both adding and editing a homework
// which mode we are in is decided by whether the url has an id or not
import { ref, computed, onMounted, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import AppHeader from '../components/AppHeader.vue'
import AppSidebar from '../components/AppSidebar.vue'
import AppProfile from '../components/AppProfile.vue'
import { homeworksApi } from '../api.js'
import { currentUser } from '../utils/auth.js'

const router = useRouter()
const route = useRoute()

// if the route has an id then we are editing, otherwise we are adding a new one
const isEdit = computed(() => !!route.params.id)

// teachers can only post for their (class, subject) pairs, so the dropdowns
// are restricted to what they teach. admins still see everything.
const isTeacher = computed(() => currentUser.value?.role === 'teacher')
const assignments = computed(() => currentUser.value?.assignments || [])

// full lists used for admins
const allGrades   = ['1A', '1B', '2A', '2B', '3A', '3B', '4A', '4B']
const allSubjects = ['Matematică', 'Limba Română', 'Științele naturii', 'Limba Engleză', 'Istorie', 'Geografie']

// teacher-restricted lists, derived from /auth/me's assignments[] field
const teacherClasses = computed(() => {
  const names = new Set()
  for (const a of assignments.value) if (a?.class?.name) names.add(a.class.name)
  return [...names].sort()
})
const teacherSubjects = computed(() => {
  // once the teacher picks a class, only show subjects they teach for that class
  if (!form.value.assignedClass) {
    const names = new Set()
    for (const a of assignments.value) if (a?.subject?.name) names.add(a.subject.name)
    return [...names].sort()
  }
  const names = new Set()
  for (const a of assignments.value) {
    if (a?.class?.name === form.value.assignedClass && a?.subject?.name) {
      names.add(a.subject.name)
    }
  }
  return [...names].sort()
})

const grades   = computed(() => isTeacher.value ? teacherClasses.value : allGrades)
const subjects = computed(() => isTeacher.value ? teacherSubjects.value : allSubjects)

const form = ref({
  title: '',
  subject: '',
  assignedClass: '',
  dueDate: '',
  description: '',
  file: null,
  fileName: ''
})

const errors   = ref({})
const apiError = ref('')

// if a teacher switches classes and the current subject isn't on their
// new (class, subject) list, blank it out so they can't submit a combo
// the backend would 403
watch(() => form.value.assignedClass, () => {
  if (!isTeacher.value) return
  if (form.value.subject && !subjects.value.includes(form.value.subject)) {
    form.value.subject = ''
  }
})

onMounted(async () => {
  // in edit mode we prefill the form with the existing homework from the server
  if (isEdit.value) {
    try {
      const existing = await homeworksApi.get(parseInt(route.params.id))
      form.value = { ...existing, file: null }
    } catch {
      apiError.value = 'Nu s-a putut încărca tema.'
    }
  }
})

// saves the picked file so we can show its name in the ui
function handleFile(e) {
  const f = e.target.files[0]
  if (f) {
    form.value.file     = f
    form.value.fileName = f.name
  }
}

// checks the form before we send it, matches the server validation
function validate() {
  errors.value = {}

  if (!form.value.title.trim()) {
    errors.value.title = 'Titlul este obligatoriu'
  } else if (form.value.title.trim().length > 200) {
    errors.value.title = 'Titlul nu poate depăși 200 de caractere'
  }

  if (!form.value.subject)
    errors.value.subject = 'Materia este obligatorie'

  if (!form.value.assignedClass)
    errors.value.assignedClass = 'Clasa este obligatorie'

  if (!form.value.dueDate) {
    errors.value.dueDate = 'Data limită este obligatorie'
  } else {
    const today = new Date()
    today.setHours(0, 0, 0, 0)
    if (new Date(form.value.dueDate) < today)
      errors.value.dueDate = 'Data limită nu poate fi în trecut'
  }

  // at least a description or a file, otherwise the homework has no content
  if (!form.value.description.trim() && !form.value.file)
    errors.value.content = 'Adaugă o descriere sau un fișier'

  return Object.keys(errors.value).length === 0
}

// sends the form, either creates a new homework or updates an existing one
async function submit() {
  if (!validate()) return
  apiError.value = ''

  const payload = {
    title:         form.value.title.trim(),
    subject:       form.value.subject,
    assignedClass: form.value.assignedClass,
    dueDate:       form.value.dueDate,
    description:   form.value.description.trim() || null,
    fileName:      form.value.fileName || null,
  }

  try {
    if (isEdit.value) {
      await homeworksApi.update(parseInt(route.params.id), payload)
    } else {
      await homeworksApi.create(payload)
    }
    router.push('/homeworks')
  } catch (e) {
    apiError.value = e.message || 'A apărut o eroare. Încearcă din nou.'
  }
}

function cancel() {
  router.push('/homeworks')
}
</script>

<template>
  <div style="position: relative">
    <AppHeader />
    <AppProfile />
    <div class="content">
      <AppSidebar active="teme" />
      <div class="main">
        <div class="toolbar">
          <h2 class="page-title">{{ isEdit ? 'EDITEAZĂ TEMĂ' : 'ADAUGĂ TEMĂ' }}</h2>
        </div>

        <div v-if="apiError" class="api-error">{{ apiError }}</div>

        <div v-if="isTeacher" class="info-banner">
          Poți crea teme doar pentru clasele și materiile pe care le predai.
        </div>

        <div class="form">
          <div class="field">
            <label>Titlu</label>
            <input v-model="form.title" type="text" />
            <span class="error" v-if="errors.title">{{ errors.title }}</span>
          </div>

          <div class="field">
            <label>Materie</label>
            <select v-model="form.subject">
              <option value="" disabled>Selectează materia</option>
              <option v-for="s in subjects" :key="s" :value="s">{{ s }}</option>
            </select>
            <span class="error" v-if="errors.subject">{{ errors.subject }}</span>
          </div>

          <div class="field">
            <label>Clasă</label>
            <select v-model="form.assignedClass">
              <option value="" disabled>Selectează clasa</option>
              <option v-for="g in grades" :key="g" :value="g">{{ g }}</option>
            </select>
            <span class="error" v-if="errors.assignedClass">{{ errors.assignedClass }}</span>
          </div>

          <div class="field">
            <label>Dată limită</label>
            <input v-model="form.dueDate" type="date" />
            <span class="error" v-if="errors.dueDate">{{ errors.dueDate }}</span>
          </div>

          <div class="field">
            <label>Descriere</label>
            <textarea v-model="form.description" rows="4" placeholder="Descrierea temei..."></textarea>
          </div>

          <div class="field">
            <label>Fișier (opțional)</label>
            <input type="file" accept="image/*,.pdf" @change="handleFile" />
            <span class="file-name" v-if="form.fileName">📎 {{ form.fileName }}</span>
          </div>

          <span class="error" v-if="errors.content">{{ errors.content }}</span>

          <div class="actions">
            <button class="btn-cancel" @click="cancel">Anulează</button>
            <button class="btn-save" @click="submit">{{ isEdit ? 'Salvează' : 'Adaugă' }}</button>
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
  min-width: 0;
  padding: clamp(12px, 2.5vw, 24px);
  padding-right: clamp(40px, 6vw, 80px);
  font-family: 'Inter', sans-serif;
}

.toolbar {
  margin-bottom: clamp(16px, 2vw, 24px);
}

.page-title {
  font-size: clamp(18px, 3vw, 24px);
  color: #185FA5;
  font-weight: 700;
}

.api-error {
  background: #ffe5e5;
  color: #cc0000;
  border: 1px solid #cc0000;
  border-radius: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  font-size: clamp(12px, 1.3vw, 14px);
}

.info-banner {
  background: #eef5ff;
  color: #185FA5;
  border: 1px solid #b5d0f0;
  border-radius: 8px;
  padding: 10px 16px;
  margin-bottom: 16px;
  font-size: clamp(12px, 1.3vw, 14px);
}

.form {
  display: flex;
  flex-direction: column;
  gap: clamp(14px, 2vw, 20px);
  max-width: 1200px;
}

.field {
  display: flex;
  flex-direction: column;
  gap: 6px;
}

label {
  font-weight: 700;
  color: #333;
  font-size: clamp(13px, 1.3vw, 15px);
}

input[type="text"],
input[type="date"],
select,
textarea {
  padding: clamp(9px, 1.2vw, 10px) clamp(10px, 1.4vw, 14px);
  border: 1px solid #ccc;
  border-radius: 8px;
  font-size: clamp(13px, 1.3vw, 15px);
  font-family: 'Inter', sans-serif;
  outline: none;
  width: 100%;
}

input[type="text"]:focus,
input[type="date"]:focus,
select:focus,
textarea:focus {
  border-color: #185FA5;
}

.error {
  color: #cc0000;
  font-size: clamp(11px, 1.2vw, 13px);
}

.file-name {
  font-size: clamp(11px, 1.2vw, 13px);
  color: #555;
  word-break: break-all;
}

.actions {
  display: flex;
  gap: 12px;
  margin-top: 8px;
  flex-wrap: wrap;
}

.btn-save,
.btn-cancel {
  color: white;
  border: none;
  padding: clamp(10px, 1.4vw, 12px) clamp(20px, 3vw, 32px);
  border-radius: 8px;
  cursor: pointer;
  font-size: clamp(13px, 1.4vw, 16px);
  font-family: 'Inter', sans-serif;
  flex: 1 1 140px;
}

.btn-save { background-color: #2a9d2a; }
.btn-save:hover { background-color: #228022; }
.btn-cancel { background-color: #888; }
.btn-cancel:hover { background-color: #666; }

@media (max-width: 600px) {
  .actions { flex-direction: column-reverse; }
  .btn-save, .btn-cancel { flex: 0 0 auto; width: 100%; }
}
</style>