// legacy in memory store left over from before the backend was wired up
// the unit tests still poke at these helpers so i kept them around
// real data comes from api.js now, nothing in the views reads from here anymore
import { ref } from 'vue'

export const students = ref([
  { name: 'LATIȘ MIRUNA', dateTime: '03-03 16:25', grade: null },
  { name: 'LATIȘ ALEXANDRA', dateTime: '03-03 16:22', grade: null },
  { name: 'MOLDOVEANU BIANCA', dateTime: '03-03 16:18', grade: null },
  { name: 'LUPAȘCU LUCA', dateTime: '03-03 16:03', grade: 8 },
  { name: 'BUCUR DELIA', dateTime: '03-03 15:58', grade: 10 },
  { name: 'HOTEA NICUȘOR', dateTime: '03-03 15:54', grade: 5 },
  { name: 'BUCUR ALEXANDRU', dateTime: '03-03 15:50', grade: 10 },
  { name: 'ALBESCU MATEI', dateTime: '03-03 15:49', grade: 9 },
  { name: 'POPA GEORGE', dateTime: '03-03 15:42', grade: 7 },
  { name: 'POPA ANDREI', dateTime: '03-03 15:38', grade: 8 },
  { name: 'IONESCU MARIA', dateTime: '03-03 15:30', grade: 6 },
  { name: 'STAN ELENA', dateTime: '03-03 15:20', grade: 2 },
])

export const homeworks = ref([
  { id: 1, title: 'Înmulțiri', subject: 'Matematică', assignedClass: '4A', dueDate: '2026-03-25', submitted: 5, total: 20, description: 'Din culegere:\n• pag. 91, problema 4\n• pag. 92, problemele 5, 6, 7', file: null, fileName: '' },
  { id: 2, title: 'Substantivul', subject: 'Limba Română', assignedClass: '4A', dueDate: '2026-03-26', submitted: 12, total: 20, description: 'Exercițiile 1-5 de la pagina 45', file: null, fileName: '' },
  { id: 3, title: 'Sistemul solar', subject: 'Științele naturii', assignedClass: '4B', dueDate: '2026-03-27', submitted: 3, total: 18, description: 'Referat despre planetele sistemului solar', file: null, fileName: '' },
  { id: 4, title: 'Verbul', subject: 'Limba Română', assignedClass: '4B', dueDate: '2026-03-28', submitted: 18, total: 18, description: 'Exercițiile 3-8 de la pagina 60', file: null, fileName: '' },
  { id: 5, title: 'Fracții', subject: 'Matematică', assignedClass: '4A', dueDate: '2026-03-29', submitted: 0, total: 20, description: 'Pag. 102, exercițiile 1-10', file: null, fileName: '' },
  { id: 6, title: 'Adjectivul', subject: 'Limba Română', assignedClass: '4A', dueDate: '2026-03-30', submitted: 7, total: 20, description: 'Fișa de lucru nr. 3', file: null, fileName: '' },
  { id: 7, title: 'Plantele', subject: 'Științele naturii', assignedClass: '4B', dueDate: '2026-03-31', submitted: 10, total: 18, description: 'Desenați și etichetați părțile unei plante', file: null, fileName: '' },
  { id: 8, title: 'Ecuații', subject: 'Matematică', assignedClass: '4B', dueDate: '2026-04-01', submitted: 14, total: 18, description: 'Rezolvați ecuațiile de la pagina 78', file: null, fileName: '' },
  { id: 9, title: 'Pronumele', subject: 'Limba Română', assignedClass: '4A', dueDate: '2026-04-02', submitted: 2, total: 20, description: 'Exercițiile 1-6 de la pagina 55', file: null, fileName: '' },
  { id: 10, title: 'Atomul', subject: 'Științele naturii', assignedClass: '4A', dueDate: '2026-04-03', submitted: 9, total: 20, description: 'Referat despre structura atomului', file: null, fileName: '' },
  { id: 11, title: 'Triunghiuri', subject: 'Matematică', assignedClass: '4A', dueDate: '2026-04-04', submitted: 6, total: 20, description: 'Pag. 88, exercițiile 5-12', file: null, fileName: '' },
  { id: 12, title: 'Poezia', subject: 'Limba Română', assignedClass: '4B', dueDate: '2026-04-05', submitted: 11, total: 18, description: 'Analizați poezia de la pagina 70', file: null, fileName: '' },
])

// the next id is one bigger than the biggest existing one
export function addHomework(homework) {
  const newId = homeworks.value.length
    ? Math.max(...homeworks.value.map(h => h.id)) + 1
    : 1
  homeworks.value.push({ id: newId, submitted: 0, total: 20, ...homework })
}

// merges new fields into the existing row, leaves the rest alone
export function updateHomework(id, updated) {
  const index = homeworks.value.findIndex(h => h.id === id)
  if (index !== -1) {
    homeworks.value[index] = { ...homeworks.value[index], ...updated }
  }
}

export function deleteHomework(id) {
  const index = homeworks.value.findIndex(h => h.id === id)
  if (index !== -1) homeworks.value.splice(index, 1)
}