// reads the logged in user and the session token from sessionStorage
// the api.js login call writes both and refreshCurrentUser pulls them back in
// hasPerm and isAdmin are used by views to gate admin only ui

import { ref } from 'vue'

const TOKEN_KEY = 'authToken'
const USER_KEY  = 'currentUser'

export const currentUser = ref(_loadUser())
export const authToken   = ref(_loadToken())

function _loadUser() {
  try { return JSON.parse(sessionStorage.getItem(USER_KEY)) || null }
  catch { return null }
}

function _loadToken() {
  return sessionStorage.getItem(TOKEN_KEY) || null
}

// called after login/register, stores both pieces and updates the reactive refs
export function setSession(user, token) {
  sessionStorage.setItem(USER_KEY,  JSON.stringify(user))
  sessionStorage.setItem(TOKEN_KEY, token)
  currentUser.value = user
  authToken.value   = token
}

// called when the sliding refresh middleware ships a new token in the header
export function setToken(token) {
  if (!token) return
  sessionStorage.setItem(TOKEN_KEY, token)
  authToken.value = token
}

export function refreshCurrentUser() {
  currentUser.value = _loadUser()
  authToken.value   = _loadToken()
}

export function isAdmin() {
  return currentUser.value?.role === 'admin'
}

export function hasPerm(code) {
  return Array.isArray(currentUser.value?.permissions) && currentUser.value.permissions.includes(code)
}

// clear everything on logout or on any 401 from the server
export function logout() {
  sessionStorage.removeItem(USER_KEY)
  sessionStorage.removeItem(TOKEN_KEY)
  currentUser.value = null
  authToken.value   = null
}
