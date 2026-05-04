// reads the logged in user from sessionStorage and answers role/permission questions
// the api.js login call stores the whole user object including role and permissions

import { ref } from 'vue'

// reactive snapshot of the current user, views import this to react to login or logout
export const currentUser = ref(_load())

function _load() {
  try {
    return JSON.parse(sessionStorage.getItem('currentUser')) || null
  } catch {
    return null
  }
}

// call this after a fresh login or after we manually update the user
export function refreshCurrentUser() {
  currentUser.value = _load()
}

export function isAdmin() {
  return currentUser.value?.role === 'admin'
}

// true if the logged in user has the given permission code
export function hasPerm(code) {
  return Array.isArray(currentUser.value?.permissions) && currentUser.value.permissions.includes(code)
}

export function logout() {
  sessionStorage.removeItem('currentUser')
  currentUser.value = null
}
