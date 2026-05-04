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

// reads the logged in user from sessionStorage so the audit middleware on the
// server can attribute every request to who fired it
function _userIdHeader() {
    try {
        const u = JSON.parse(sessionStorage.getItem('currentUser'))
        return u && u.id ? { 'X-User-Id': String(u.id) } : {}
    } catch {
        return {}
    }
}

// raw fetch, throws a TypeError when the server is unreachable
async function doFetch(method, path, body) {
    const res = await fetch(`${BASE}${path}`, {
        method,
        headers: { 'Content-Type': 'application/json', ..._userIdHeader() },
        body: body ? JSON.stringify(body) : undefined,
    })
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

// login endpoint
export const auth = {
    login: (email, password) =>
        request('POST', '/auth/login', { email, password }),
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
        headers: { 'Content-Type': 'application/json', ..._userIdHeader() },
        body: JSON.stringify({ query, variables }),
    })
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
    init.headers = { ...(init.headers || {}), ..._userIdHeader() }
    const r = await fetch(`${BASE}${path}`, init)
    if (!r.ok) {
        let detail = `HTTP ${r.status}`
        try { detail = (await r.json()).detail || detail } catch {}
        throw new Error(detail)
    }
    return r.json()
}

export const chatApi = {
    myRooms:    (userId) => _json(`/chat/rooms?user_id=${userId}`),
    users:      (userId) => _json(`/chat/users?user_id=${userId}`),
    openDm:     (userId, otherId) =>
        _json(`/chat/dm?user_id=${userId}&other_id=${otherId}`, { method: 'POST' }),
    createRoom: (userId, name, participants) =>
        _json(`/chat/rooms?user_id=${userId}&name=${encodeURIComponent(name)}&participants=${participants}`, { method: 'POST' }),
    history:    (roomId, userId) => _json(`/chat/rooms/${roomId}/messages?user_id=${userId}`),
}

// chat ws is a separate endpoint from the live updates ws, so the panel and the
// homeworks list dont fight over the same socket
// ─── admin (gold) ────────────────────────────────────────────────────────────
// every call passes user_id so the backend can verify the caller is admin
// the audit middleware also logs these calls for the same reason
export const adminApi = {
    logs:        (userId, page = 1, pageSize = 50, onlyUserId = null) => {
        const extra = onlyUserId !== null ? `&only_user_id=${onlyUserId}` : ''
        return _json(`/admin/logs?user_id=${userId}&page=${page}&pageSize=${pageSize}${extra}`)
    },
    observations: (userId, includeDismissed = false) =>
        _json(`/admin/observations?user_id=${userId}&include_dismissed=${includeDismissed}`),
    dismiss: (userId, flaggedUserId) =>
        _json(`/admin/observations/${flaggedUserId}/dismiss?user_id=${userId}`, { method: 'POST' }),
}


export function createChatWebSocket(onMessage) {
    const wsBase = BASE.replace(/^http/, 'ws')
    const ws = new WebSocket(`${wsBase}/chat/ws`)
    ws.onmessage = (e) => {
        try { onMessage(JSON.parse(e.data)) } catch {}
    }
    return ws
}
