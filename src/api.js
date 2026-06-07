// api.js, all the calls to the backend live here
//
// silver challenge, offline mode
// if the browser is offline or the server is down we flip to offline
// reads come from a ram cache, writes get queued
// when we come back online the queue is flushed and any temp ids get
// swapped for the real ids the server gives back

import { ref } from 'vue'

// base url, defaults to localhost for normal dev
// for the cross machine demo set VITE_API_URL in a .env.local file pointing at the server lan ip
// example: VITE_API_URL=http://192.168.1.42:8000
const BASE = import.meta.env.VITE_API_URL || 'http://localhost:8000'

// reactive flags the views can watch
export const offline     = ref(!navigator.onLine)
export const pendingOps  = ref(0)

// ram copy of the server data, keeps reads working while offline
const cache = {
    homeworks: [],
    students:  [],
}

function upsertHomeworks(items) {
    for (const hw of items) {
        const i = cache.homeworks.findIndex(h => h.id === hw.id)
        if (i >= 0) cache.homeworks[i] = hw
        else cache.homeworks.push(hw)
    }
}
function upsertStudents(items) {
    for (const s of items) {
        const i = cache.students.findIndex(x => x.id === s.id)
        if (i >= 0) cache.students[i] = s
        else cache.students.push(s)
    }
}

// queue of writes made while offline
const pendingQueue = []
let _tempIdCounter = -1               // negative ids mark stuff created offline

function enqueue(op) {
    pendingQueue.push(op)
    pendingOps.value = pendingQueue.length
}

// reads the session token from sessionStorage and turns it into the
// Authorization header. the audit middleware on the server decodes the same
// token to figure out who is calling
function _authHeader() {
    const t = sessionStorage.getItem('authToken')
    return t ? { 'Authorization': `Bearer ${t}` } : {}
}

// when the backend sits behind ngrok free, the first response would normally
// be ngrok's "Visit Site" interstitial. sending this header on every request
// bypasses that, regardless of which ngrok-like proxy is in the way
const _NGROK_BYPASS = { 'ngrok-skip-browser-warning': 'true' }

// after every response we look for X-Refresh-Token and stash it as the new
// session token, that resets the inactivity timer. on a 401 we clear the
// session entirely and bounce the user to /login
function _handleSessionHeaders(res) {
    const fresh = res.headers.get('X-Refresh-Token')
    if (fresh) sessionStorage.setItem('authToken', fresh)
    if (res.status === 401) {
        const onLogin = location.pathname === '/' || location.pathname === '/login'
        if (!onLogin) {
            sessionStorage.removeItem('authToken')
            sessionStorage.removeItem('currentUser')
            location.replace('/login')
        }
    }
}

// raw fetch, throws a TypeError when the server is unreachable
async function doFetch(method, path, body) {
    const res = await fetch(`${BASE}${path}`, {
        method,
        headers: { 'Content-Type': 'application/json', ..._authHeader(), ..._NGROK_BYPASS },
        body: body ? JSON.stringify(body) : undefined,
    })
    _handleSessionHeaders(res)
    if (!res.ok) {
        const err = await res.json().catch(() => ({ detail: res.statusText }))
        const e = new Error(JSON.stringify(err))
        e._httpStatus = res.status
        throw e
    }
    if (res.status === 204) return null
    return res.json()
}

function setOffline(v) {
    if (offline.value !== v) offline.value = v
}

// main entry point, tries the real server first and falls back to the cache
async function request(method, path, body = null, { offlineQueue = false } = {}) {
    // browser already knows the network is down, dont even try
    if (!navigator.onLine) {
        setOffline(true)
        return offlineHandle(method, path, body, offlineQueue)
    }

    try {
        const result = await doFetch(method, path, body)
        // call worked so we are online, if we were offline before flush the queue
        if (offline.value) {
            setOffline(false)
            flushQueue().catch(() => {})
        } else {
            setOffline(false)
        }
        // copy the response into the cache so future offline reads have it
        mirrorResponse(method, path, result)
        return result
    } catch (err) {
        // TypeError means the server is unreachable
        if (err instanceof TypeError) {
            setOffline(true)
            return offlineHandle(method, path, body, offlineQueue)
        }
        throw err
    }
}

// keeps the cache in sync with whatever the server just returned
function mirrorResponse(method, path, result) {
    if (!result) return
    if (method === 'GET') {
        if (/^\/homeworks\?/.test(path) || path === '/homeworks') {
            upsertHomeworks(result.items ?? [])
        } else if (/^\/homeworks\/\d+$/.test(path)) {
            upsertHomeworks([result])
        } else if (/^\/homeworks\/\d+\/students\?/.test(path)) {
            upsertStudents(result.items ?? [])
        } else if (/^\/homeworks\/\d+\/students\/\d+$/.test(path)) {
            upsertStudents([result])
        }
    } else if (method === 'POST') {
        if (path === '/homeworks') upsertHomeworks([result])
        else if (/^\/homeworks\/\d+\/students$/.test(path)) upsertStudents([result])
    } else if (method === 'PUT') {
        if (/^\/homeworks\/\d+$/.test(path)) upsertHomeworks([result])
        else if (/^\/homeworks\/\d+\/students\/\d+$/.test(path)) upsertStudents([result])
    } else if (method === 'DELETE') {
        const mH = path.match(/^\/homeworks\/(\d+)$/)
        if (mH) {
            const id = parseInt(mH[1])
            cache.homeworks = cache.homeworks.filter(h => h.id !== id)
            cache.students  = cache.students.filter(s => s.homeworkId !== id)
        }
        const mS = path.match(/^\/homeworks\/\d+\/students\/(\d+)$/)
        if (mS) {
            const sid = parseInt(mS[1])
            cache.students = cache.students.filter(s => s.id !== sid)
        }
    }
}

// when we are offline, this decides what to do with the call
function offlineHandle(method, path, body, offlineQueue) {
    if (method === 'GET') return offlineRead(path)
    if (offlineQueue)     return offlineMutate(method, path, body)
    throw new Error('Offline')
}

// reads while offline, we basicly rebuild the server response from the cache
function offlineRead(path) {
    const mList = path.match(/^\/homeworks\?(.*)$/)
    if (mList) {
        const q = new URLSearchParams(mList[1])
        const page = parseInt(q.get('page') || '1')
        const pageSize = parseInt(q.get('pageSize') || '10')
        const subject = q.get('subject')
        const assignedClass = q.get('assignedClass')
        let items = [...cache.homeworks]
        if (subject)       items = items.filter(h => h.subject === subject)
        if (assignedClass) items = items.filter(h => h.assignedClass === assignedClass)
        const total = items.length
        const start = (page - 1) * pageSize
        return {
            items: items.slice(start, start + pageSize),
            total, page, pageSize,
            totalPages: Math.max(1, Math.ceil(total / pageSize)),
        }
    }

    const mOne = path.match(/^\/homeworks\/(-?\d+)$/)
    if (mOne) {
        const id = parseInt(mOne[1])
        const hw = cache.homeworks.find(h => h.id === id)
        if (!hw) throw new Error('Offline: tema nu este în cache')
        return hw
    }

    const mSList = path.match(/^\/homeworks\/(-?\d+)\/students\?(.*)$/)
    if (mSList) {
        const hwId = parseInt(mSList[1])
        const q = new URLSearchParams(mSList[2])
        const page = parseInt(q.get('page') || '1')
        const pageSize = parseInt(q.get('pageSize') || '10')
        const items = cache.students.filter(s => s.homeworkId === hwId)
        const total = items.length
        const start = (page - 1) * pageSize
        return {
            items: items.slice(start, start + pageSize),
            total, page, pageSize,
            totalPages: Math.max(1, Math.ceil(total / pageSize)),
        }
    }

    const mS = path.match(/^\/homeworks\/(-?\d+)\/students\/(-?\d+)$/)
    if (mS) {
        const hwId = parseInt(mS[1]), sid = parseInt(mS[2])
        const s = cache.students.find(s => s.homeworkId === hwId && s.id === sid)
        if (!s) throw new Error('Offline: elevul nu este în cache')
        return s
    }

    const mStats = path.match(/^\/homeworks\/(-?\d+)\/statistics$/)
    if (mStats) return computeStats(parseInt(mStats[1]))

    throw new Error('Offline: ruta nu este în cache')
}

// stats endpoint but ran locally against the cache
function computeStats(hwId) {
    const students = cache.students.filter(s => s.homeworkId === hwId)
    const graded   = students.filter(s => s.grade !== null && s.grade !== undefined)
    const passed   = graded.filter(s => s.grade >= 5)
    const failed   = graded.filter(s => s.grade <  5)
    const ungraded = students.filter(s => s.grade === null || s.grade === undefined)
    const avg = graded.length
        ? Math.round((graded.reduce((a, s) => a + s.grade, 0) / graded.length) * 100) / 100
        : null
    const buckets = { '10': 0, '9': 0, '8': 0, '7': 0, '6': 0, '5': 0, '<5': 0, 'FĂRĂ NOTĂ': 0 }
    for (const s of students) {
        if (s.grade === null || s.grade === undefined) buckets['FĂRĂ NOTĂ']++
        else if (s.grade < 5) buckets['<5']++
        else buckets[String(s.grade)]++
    }
    return {
        homeworkId: hwId,
        totalStudents: students.length,
        passed: passed.length,
        failed: failed.length,
        ungraded: ungraded.length,
        averageGrade: avg,
        gradeDistribution: Object.entries(buckets).map(([grade, count]) => ({ grade, count })),
    }
}

// writes while offline, we apply them to the cache and queue them for later
function offlineMutate(method, path, body) {
    // new homework
    if (method === 'POST' && path === '/homeworks') {
        const hw = {
            id: _tempIdCounter--,
            title:         body.title,
            subject:       body.subject,
            assignedClass: body.assignedClass,
            dueDate:       body.dueDate,
            description:   body.description ?? null,
            fileName:      body.fileName ?? null,
            _temp: true,
        }
        cache.homeworks.push(hw)
        enqueue({ method, path, body, kind: 'hw-create', tempId: hw.id })
        return hw
    }

    // edit a homework
    const mPut = path.match(/^\/homeworks\/(-?\d+)$/)
    if (method === 'PUT' && mPut) {
        const id = parseInt(mPut[1])
        const hw = cache.homeworks.find(h => h.id === id)
        if (hw) Object.assign(hw, body)
        enqueue({ method, path, body, kind: 'hw-update', id })
        return hw
    }

    // delete a homework
    if (method === 'DELETE' && mPut) {
        const id = parseInt(mPut[1])
        cache.homeworks = cache.homeworks.filter(h => h.id !== id)
        cache.students  = cache.students.filter(s => s.homeworkId !== id)
        enqueue({ method, path, body: null, kind: 'hw-delete', id })
        return null
    }

    // new student
    const mPostS = path.match(/^\/homeworks\/(-?\d+)\/students$/)
    if (method === 'POST' && mPostS) {
        const hwId = parseInt(mPostS[1])
        const s = {
            id: _tempIdCounter--,
            homeworkId: hwId,
            name:     body.name,
            dateTime: body.dateTime,
            grade:    body.grade ?? null,
            _temp: true,
        }
        cache.students.push(s)
        enqueue({ method, path, body, kind: 'student-create', hwId, tempId: s.id })
        return s
    }

    // edit or delete a student
    const mPutS = path.match(/^\/homeworks\/(-?\d+)\/students\/(-?\d+)$/)
    if (method === 'PUT' && mPutS) {
        const hwId = parseInt(mPutS[1]), sid = parseInt(mPutS[2])
        const s = cache.students.find(x => x.homeworkId === hwId && x.id === sid)
        if (s) Object.assign(s, body)
        enqueue({ method, path, body, kind: 'student-update', hwId, id: sid })
        return s
    }
    if (method === 'DELETE' && mPutS) {
        const hwId = parseInt(mPutS[1]), sid = parseInt(mPutS[2])
        cache.students = cache.students.filter(x => !(x.homeworkId === hwId && x.id === sid))
        enqueue({ method, path, body: null, kind: 'student-delete', hwId, id: sid })
        return null
    }

    throw new Error(`Offline: operație nesuportată ${method} ${path}`)
}

// sends every queued write to the server once we are back online
async function flushQueue() {
    if (!pendingQueue.length) return
    // maps the negative temp id we made offline to the real id from the server
    const tempToReal = new Map()

    while (pendingQueue.length > 0) {
        const op = pendingQueue[0]

        // if the path has a temp id in it, swap it for the real one we learned about
        let path = op.path.replace(/\/homeworks\/(-\d+)(\/|$)/g, (m, tid, rest) => {
            const real = tempToReal.get(parseInt(tid))
            return real != null ? `/homeworks/${real}${rest}` : m
        })
        path = path.replace(/\/students\/(-\d+)$/, (m, tid) => {
            const real = tempToReal.get(parseInt(tid))
            return real != null ? `/students/${real}` : m
        })
        // if we still have a negative id it means the parent create failed, skip
        if (path.includes('/-')) {
            console.warn('[ProElev] Dropping queued op with unresolved temp id:', op)
            pendingQueue.shift()
            pendingOps.value = pendingQueue.length
            continue
        }

        try {
            const data = await doFetch(op.method, path, op.body)
            if (op.tempId != null && data?.id != null) {
                tempToReal.set(op.tempId, data.id)
                // swap the temp row in the cache with the real one from the server
                if (op.kind === 'hw-create') {
                    cache.homeworks = cache.homeworks.filter(h => h.id !== op.tempId)
                    upsertHomeworks([data])
                    // any students that pointed at the temp homework get repointed
                    for (const s of cache.students) if (s.homeworkId === op.tempId) s.homeworkId = data.id
                } else if (op.kind === 'student-create') {
                    cache.students = cache.students.filter(s => s.id !== op.tempId)
                    upsertStudents([data])
                }
            }
            pendingQueue.shift()
            pendingOps.value = pendingQueue.length
        } catch (err) {
            if (err instanceof TypeError) {
                // server dropped again, try later
                break
            }
            // 4xx or 5xx means the op will never work, drop it so the queue moves on
            console.warn('[ProElev] Dropping failed queued op:', op.method, path, err.message)
            pendingQueue.shift()
            pendingOps.value = pendingQueue.length
        }
    }
}

// browser tells us when the network comes back, we flush the queue then
window.addEventListener('online', async () => {
    setOffline(false)
    await flushQueue()
})
window.addEventListener('offline', () => setOffline(true))

// loops through every page so views can get the whole list at once
export async function fetchAllStudents(hwId, pageSize = 100) {
    const all = []
    let page = 1
    while (true) {
        const data = await studentsApi.list(hwId, page, pageSize)
        const items = Array.isArray(data) ? data : (data.items ?? [])
        all.push(...items)
        if (items.length < pageSize) break
        page++
    }
    return all
}

export async function fetchAllHomeworks(filters = {}, pageSize = 100) {
    const all = []
    let page = 1
    while (true) {
        const data = await homeworksApi.list(page, pageSize, filters)
        const items = Array.isArray(data) ? data : (data.items ?? [])
        all.push(...items)
        if (items.length < pageSize) break
        page++
    }
    return all
}

// silver, the 3 factor login flow plus register, recovery, inbox
export const auth = {
    // factor 1, password. returns { challenge_id, next, message }
    login:           (email, password) =>
        request('POST', '/auth/login', { email, password }),
    // factor 2, email code. returns { challenge_id, security_question }
    verifyEmail:     (challenge_id, code) =>
        request('POST', '/auth/login/verify-email', { challenge_id, code }),
    // factor 3, security question. returns the final { access_token, user }
    verifyQuestion:  (challenge_id, answer) =>
        request('POST', '/auth/login/verify-question', { challenge_id, answer }),

    // assignment 6, register can take an invite code + role-specific extras.
    // `extras` is an object that may contain invite_code, class_id, subject_id,
    // children_emails. without it the new account is plain "user".
    register: (name, email, password, security_question, security_answer, extras = {}) =>
        request('POST', '/auth/register', {
            name, email, password, security_question, security_answer, ...extras,
        }),
    me:      () => request('GET',  '/auth/me'),
    logout:  () => request('POST', '/auth/logout'),
    inbox:   () => request('GET',  '/auth/inbox'),

    forgot:  (email)              => request('POST', '/auth/forgot', { email }),
    reset:   (token, new_password) => request('POST', '/auth/reset',  { token, new_password }),

    // assignment 6, pre-flight check on the invite code so the register form
    // can show which role the user is about to assume
    checkInvite: (code) => _json('/auth/invite/check?code=' + encodeURIComponent(code)),
}

// public lookups used by the register form before the user has a token
export const lookups = {
    classes:  () => _json('/lookups/classes'),
    subjects: () => _json('/lookups/subjects'),
}

// assignment 6, admin invite code management
export const invitesApi = {
    list:    (includeExpired = false, includeUsed = false) =>
        _json(`/admin/invites?include_expired=${includeExpired}&include_used=${includeUsed}`),
    create:  (payload) => _json('/admin/invites', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(payload),
    }),
    revoke:  (id) => _json(`/admin/invites/${id}/revoke`, { method: 'POST' }),
}


// assignment 6, student submissions + teacher grading
export const submissionsApi = {
    // student uploads, multipart so we can attach a file
    submit: async (homeworkId, text, file) => {
        const fd = new FormData()
        if (text) fd.append('text', text)
        if (file) fd.append('file', file)
        const t = sessionStorage.getItem('authToken')
        const res = await fetch(`${BASE}/homeworks/${homeworkId}/submit`, {
            method: 'POST',
            headers: {
                ...(t ? { 'Authorization': `Bearer ${t}` } : {}),
                'ngrok-skip-browser-warning': 'true',
            },
            body: fd,
        })
        _handleSessionHeaders(res)
        if (!res.ok) {
            let detail = `HTTP ${res.status}`
            try { detail = (await res.json()).detail || detail } catch {}
            throw new Error(detail)
        }
        return res.json()
    },
    grade:  (homeworkId, studentId, payload) =>
        _json(`/homeworks/${homeworkId}/students/${studentId}/grade`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload),
        }),
    list:   (homeworkId, page = 1, pageSize = 100) =>
        _json(`/homeworks/${homeworkId}/students?page=${page}&pageSize=${pageSize}`),
    fileUrl: (homeworkId, studentId) =>
        `${BASE}/homeworks/${homeworkId}/students/${studentId}/file`,
    // streams the file with the auth header, pops a download in the browser
    // can't use a plain <a href> because the server needs the bearer token
    downloadFile: async (homeworkId, studentId, suggestedName = 'submission') => {
        const t = sessionStorage.getItem('authToken')
        const res = await fetch(`${BASE}/homeworks/${homeworkId}/students/${studentId}/file`, {
            headers: {
                ...(t ? { 'Authorization': `Bearer ${t}` } : {}),
                'ngrok-skip-browser-warning': 'true',
            },
        })
        _handleSessionHeaders(res)
        if (!res.ok) {
            let detail = `HTTP ${res.status}`
            try { detail = (await res.json()).detail || detail } catch {}
            throw new Error(detail)
        }
        // try to read the server-supplied filename, fall back to the caller's hint
        let filename = suggestedName
        const cd = res.headers.get('Content-Disposition') || ''
        const m = cd.match(/filename="?([^"]+)"?/)
        if (m) filename = m[1]
        const blob = await res.blob()
        const url = URL.createObjectURL(blob)
        const a = document.createElement('a')
        a.href = url
        a.download = filename
        document.body.appendChild(a)
        a.click()
        a.remove()
        // free the blob after the click registered
        setTimeout(() => URL.revokeObjectURL(url), 1000)
    },
}

// all the homework routes, used by pretty much every view
export const homeworksApi = {
    list: (page = 1, pageSize = 100, filters = {}) => {
        const params = new URLSearchParams({ page, pageSize, ...filters })
        return request('GET', `/homeworks?${params}`)
    },

    get: (id) => request('GET', `/homeworks/${id}`),

    create: (data) =>
        request('POST', '/homeworks', data, { offlineQueue: true }),

    update: (id, data) =>
        request('PUT', `/homeworks/${id}`, data, { offlineQueue: true }),

    delete: (id) =>
        request('DELETE', `/homeworks/${id}`, null, { offlineQueue: true }),
}

// student routes, each homework has its own list of students
export const studentsApi = {
    list: (hwId, page = 1, pageSize = 100) =>
        request('GET', `/homeworks/${hwId}/students?page=${page}&pageSize=${pageSize}`),

    get: (hwId, studentId) =>
        request('GET', `/homeworks/${hwId}/students/${studentId}`),

    create: (hwId, data) =>
        request('POST', `/homeworks/${hwId}/students`, data, { offlineQueue: true }),

    update: (hwId, studentId, data) =>
        request('PUT', `/homeworks/${hwId}/students/${studentId}`, data, { offlineQueue: true }),

    delete: (hwId, studentId) =>
        request('DELETE', `/homeworks/${hwId}/students/${studentId}`, null, { offlineQueue: true }),
}

// server computes the grade stats for a homework and sends them over
export const statisticsApi = {
    get: (hwId) => request('GET', `/homeworks/${hwId}/statistics`),
}

// controls the fake data generator on the server side
export const generatorApi = {
    start:  () => request('POST', '/generator/start'),
    stop:   () => request('POST', '/generator/stop'),
    status: () => request('GET',  '/generator/status'),
}

// gold challenge, small graphql client, same data just a different shape
async function gql(query, variables = {}) {
    const res = await fetch(`${BASE}/graphql`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json', ..._authHeader(), ..._NGROK_BYPASS },
        body: JSON.stringify({ query, variables }),
    })
    _handleSessionHeaders(res)
    if (!res.ok) throw new Error(`GraphQL ${res.status}`)
    const json = await res.json()
    if (json.errors && json.errors.length) {
        throw new Error(json.errors[0].message || 'GraphQL error')
    }
    return json.data
}

// comments belong to a homework, the graphql queries and mutations live here
const Q_COMMENTS = `
  query Comments($hwId: Int!) {
    comments(homeworkId: $hwId) { id homeworkId author text createdAt }
  }`
const Q_COMMENT_STATS = `
  query CommentStats($hwId: Int!) {
    commentStatistics(homeworkId: $hwId) {
      homeworkId totalComments uniqueAuthors averageTextLength topAuthor
    }
  }`
const M_CREATE_COMMENT = `
  mutation CreateComment($hwId: Int!, $input: CommentInput!) {
    createComment(homeworkId: $hwId, input: $input) {
      id homeworkId author text createdAt
    }
  }`
const M_UPDATE_COMMENT = `
  mutation UpdateComment($hwId: Int!, $id: Int!, $patch: CommentPatch!) {
    updateComment(homeworkId: $hwId, id: $id, patch: $patch) {
      id homeworkId author text createdAt
    }
  }`
const M_DELETE_COMMENT = `
  mutation DeleteComment($hwId: Int!, $id: Int!) {
    deleteComment(homeworkId: $hwId, id: $id)
  }`

export const commentsApi = {
    list:       (hwId)          => gql(Q_COMMENTS,        { hwId }).then(d => d.comments),
    statistics: (hwId)          => gql(Q_COMMENT_STATS,   { hwId }).then(d => d.commentStatistics),
    create:     (hwId, input)   => gql(M_CREATE_COMMENT,  { hwId, input }).then(d => d.createComment),
    update:     (hwId, id, p)   => gql(M_UPDATE_COMMENT,  { hwId, id, patch: p }).then(d => d.updateComment),
    delete:     (hwId, id)      => gql(M_DELETE_COMMENT,  { hwId, id }).then(d => d.deleteComment),
}

// the homeworks list view uses graphql for paging, its what the sentinel hits
const Q_HOMEWORKS_PAGE = `
  query HwPage($page: Int!, $pageSize: Int!, $subject: String, $assignedClass: String) {
    homeworks(page: $page, pageSize: $pageSize, subject: $subject, assignedClass: $assignedClass) {
      total page pageSize totalPages
      items { id title subject assignedClass dueDate description fileName }
    }
  }`

export const homeworksGql = {
    page: (page, pageSize, filters = {}) =>
        gql(Q_HOMEWORKS_PAGE, {
            page, pageSize,
            subject:       filters.subject       || null,
            assignedClass: filters.assignedClass || null,
        }).then(d => d.homeworks),
}

// opens a WebSocket to the server so views get live updates when new data comes in
// derives the ws url from the http BASE so the cross machine demo just works
export function createWebSocket(onMessage) {
    const wsBase = BASE.replace(/^http/, 'ws')
    const ws = new WebSocket(`${wsBase}/ws`)

    ws.onopen    = () => console.log('[ProElev] WebSocket connected')
    ws.onmessage = (e) => {
        try {
            const data = JSON.parse(e.data)
            onMessage(data)
        } catch {
            console.warn('[ProElev] Invalid WS message', e.data)
        }
    }
    ws.onerror = () => console.warn('[ProElev] WebSocket error')
    ws.onclose = () => console.log('[ProElev] WebSocket disconnected')

    return ws
}

// old helper, some views still import this so we keep it around
export function useOfflineStatus() {
    return { offline, pendingCount: pendingOps }
}


// ─── chat (silver) ───────────────────────────────────────────────────────────
// rest helpers, plus a websocket factory that returns the raw ws so the panel
// can also send messages (subscribe, post) not just receive
async function _json(path, init = {}) {
    init.headers = { ...(init.headers || {}), ..._authHeader(), ..._NGROK_BYPASS }
    const r = await fetch(`${BASE}${path}`, init)
    _handleSessionHeaders(r)
    if (!r.ok) {
        let detail = `HTTP ${r.status}`
        try { detail = (await r.json()).detail || detail } catch {}
        throw new Error(detail)
    }
    return r.json()
}

// chat helpers, all of them carry the bearer token via _json, so they no
// longer need a user_id parameter
export const chatApi = {
    myRooms:    ()                        => _json('/chat/rooms'),
    users:      ()                        => _json('/chat/users'),
    openDm:     (otherId)                 => _json(`/chat/dm?other_id=${otherId}`, { method: 'POST' }),
    createRoom: (name, participants = '') =>
        _json(`/chat/rooms?name=${encodeURIComponent(name)}&participants=${participants}`, { method: 'POST' }),
    history:    (roomId)                  => _json(`/chat/rooms/${roomId}/messages`),
}

// ─── admin (gold) ────────────────────────────────────────────────────────────
// auth is the bearer token now, no more user_id query parameter
export const adminApi = {
    logs: (page = 1, pageSize = 50, onlyUserId = null) => {
        const extra = onlyUserId !== null ? `&only_user_id=${onlyUserId}` : ''
        return _json(`/admin/logs?page=${page}&pageSize=${pageSize}${extra}`)
    },
    observations: (includeDismissed = false) =>
        _json(`/admin/observations?include_dismissed=${includeDismissed}`),
    dismiss: (flaggedUserId) =>
        _json(`/admin/observations/${flaggedUserId}/dismiss`, { method: 'POST' }),
    runAi: () => _json('/admin/ai/run', { method: 'POST' }),
}

// assignment 6, notification feed (newest first, red unread badge)
export const notificationsApi = {
    list:        (unreadOnly = false, limit = 50) =>
        _json(`/notifications?unread_only=${unreadOnly}&limit=${limit}`),
    unreadCount: () =>
        _json('/notifications/unread_count'),
    markRead:    (id) =>
        _json(`/notifications/${id}/read`, { method: 'POST' }),
    markAllRead: () =>
        _json('/notifications/read_all', { method: 'POST' }),
}

// assignment 5 gold, heavy compute stat + perf demo
export const statsApi = {
    byTag:    (mode = 'naive') => _json(`/stats/by-tag?mode=${mode}`),
    perfDemo: ()                => _json('/stats/perf-demo'),
}


// chat ws is a separate endpoint, the hello message carries the bearer token
// since browsers can't attach custom headers on the websocket handshake
export function createChatWebSocket(onMessage) {
    const wsBase = BASE.replace(/^http/, 'ws')
    const ws = new WebSocket(`${wsBase}/chat/ws`)
    ws.onmessage = (e) => {
        try { onMessage(JSON.parse(e.data)) } catch {}
    }
    return ws
}
