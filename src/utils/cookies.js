// tiny helper for reading and writing browser cookies
// we use this to remember which page the user was on, so after a refresh we send them back

// writes a cookie that lasts for some number of days, default is 30
export function setCookie(name, value, days = 30) {
  const expires = new Date()
  expires.setTime(expires.getTime() + days * 24 * 60 * 60 * 1000)
  document.cookie = `${name}=${encodeURIComponent(value)};expires=${expires.toUTCString()};path=/`
}

// splits the whole cookie string and finds the one with the given name
export function getCookie(name) {
  const cookies = document.cookie.split(';')
  for (let cookie of cookies) {
    const [key, val] = cookie.trim().split('=')
    if (key === name) return decodeURIComponent(val)
  }
  return null
}

// trick to delete a cookie, just set it to expire in the past
export function deleteCookie(name) {
  document.cookie = `${name}=;expires=Thu, 01 Jan 1970 00:00:00 UTC;path=/`
}