/* ============================================================
   The HTTP client.

   One place that knows about tokens, errors and refresh, so no
   component ever touches `fetch` directly.

   The part worth reading is `refresh()`. An access token expires
   while the panel is open, and a dashboard fires half a dozen
   parallel requests — so several of them will get a 401 at the
   same instant. Without care that means several parallel refresh
   calls, and since refresh tokens are single-use on the server,
   the first one to land invalidates the rest and signs the user
   out mid-session.

   So a refresh is a SINGLE shared promise: the first 401 starts
   it, every other request awaits the same one, and they all retry
   once with the new token.
   ============================================================ */

const BASE = '/api'

const ACCESS_KEY = 'mailpilot:access'
const REFRESH_KEY = 'mailpilot:refresh'

/* ---------------------------------------------------------------- tokens */

export const tokens = {
  get access() {
    return localStorage.getItem(ACCESS_KEY) || ''
  },
  get refresh() {
    return localStorage.getItem(REFRESH_KEY) || ''
  },
  set({ access_token, refresh_token }) {
    if (access_token) localStorage.setItem(ACCESS_KEY, access_token)
    if (refresh_token) localStorage.setItem(REFRESH_KEY, refresh_token)
  },
  clear() {
    localStorage.removeItem(ACCESS_KEY)
    localStorage.removeItem(REFRESH_KEY)
  },
}

/* Anything that needs to know the session ended — the auth provider
   subscribes so it can drop the user back to the sign-in screen. */
const listeners = new Set()
export const onSignedOut = (fn) => {
  listeners.add(fn)
  return () => listeners.delete(fn)
}
const signOut = () => {
  tokens.clear()
  listeners.forEach((fn) => fn())
}

/* ---------------------------------------------------------------- errors */

export class ApiError extends Error {
  constructor(status, body, requestId) {
    // `problems` comes from the server's validation handler and names the
    // offending field, which is far more useful than "422".
    const detail =
      body?.problems?.map((p) => `${p.field}: ${p.message}`).join(', ') ||
      body?.detail ||
      `Request failed (${status})`
    super(detail)
    this.name = 'ApiError'
    this.status = status
    this.body = body
    this.requestId = requestId
    this.problems = body?.problems || []
  }

  /** 401/403 are the reader's problem to fix; 5xx are ours. */
  get isAuth() {
    return this.status === 401 || this.status === 403
  }
}

/* ---------------------------------------------------------------- refresh */

let refreshing = null

async function refresh() {
  if (refreshing) return refreshing // everyone waits on the same attempt
  const token = tokens.refresh
  if (!token) return Promise.resolve(false)

  refreshing = (async () => {
    try {
      const res = await fetch(`${BASE}/auth/refresh`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ refresh_token: token }),
      })
      if (!res.ok) {
        signOut()
        return false
      }
      tokens.set(await res.json())
      return true
    } catch {
      return false
    } finally {
      // cleared in a microtask so concurrent callers still see this attempt
      setTimeout(() => {
        refreshing = null
      }, 0)
    }
  })()

  return refreshing
}

/* ---------------------------------------------------------------- language

   The server writes its refusals in English and translates them on the way
   out, which it can only do if it knows what the reader is reading. This is
   pushed in by the i18n provider rather than read from storage here, so the
   storage key stays in one place.

   It defaults to English: an unset language is exactly the behaviour this
   API had before, so nothing regresses while the provider is mounting. */
let language = 'en'
export function setLanguage(next) {
  if (next) language = next
}

/* ---------------------------------------------------------------- request */

/* How long to wait before giving up.
 *
 * There was no timeout at all: a wedged server or a dropped connection left
 * every request pending forever, and the panel span a loader with no error and
 * no way to know it should be retried. A spinner that never resolves is worse
 * than a failure, because nobody reaches for the reload button.
 *
 * The AI calls are genuinely slow — research reads several web pages, a
 * template is a whole HTML document — so a blanket short limit would fail the
 * requests most worth waiting for. Two numbers rather than one. */
const TIMEOUT_MS = 30_000
const SLOW_TIMEOUT_MS = 180_000
const SLOW_PATHS = ['/ai/', '/research/', '/google/sync', '/contacts/import']

function budgetFor(path) {
  return SLOW_PATHS.some((p) => path.startsWith(p)) ? SLOW_TIMEOUT_MS : TIMEOUT_MS
}

async function request(method, path, { body, signal, retry = true, auth = true } = {}) {
  const headers = { Accept: 'application/json', 'Accept-Language': language }
  if (body !== undefined) headers['Content-Type'] = 'application/json'
  if (auth && tokens.access) headers.Authorization = `Bearer ${tokens.access}`

  /* The caller's own signal still works and still wins — this only adds a
     ceiling for the callers that pass none, which is all of them. */
  const clock = new AbortController()
  const timer = setTimeout(() => clock.abort(new DOMException('timeout', 'TimeoutError')),
                           budgetFor(path))
  const onCallerAbort = () => clock.abort(signal.reason)
  if (signal) {
    if (signal.aborted) clock.abort(signal.reason)
    else signal.addEventListener('abort', onCallerAbort, { once: true })
  }

  let res
  try {
    res = await fetch(`${BASE}${path}`, {
      method,
      headers,
      signal: clock.signal,
      body: body === undefined ? undefined : JSON.stringify(body),
    })
  } catch (err) {
    // the caller aborted on purpose — theirs to handle, not ours to relabel
    if (signal?.aborted) throw err
    if (clock.signal.aborted) {
      const seconds = Math.round(budgetFor(path) / 1000)
      throw new ApiError(0, {
        detail: `The server did not answer within ${seconds} seconds. It may still be working — check before trying again.`,
      }, '')
    }
    if (err?.name === 'AbortError') throw err
    // a network failure is not a 500 — say so, or the reader goes looking
    // for a server problem that does not exist
    throw new ApiError(0, { detail: 'Could not reach the server' }, '')
  } finally {
    clearTimeout(timer)
    signal?.removeEventListener?.('abort', onCallerAbort)
  }

  if (res.status === 401 && retry && auth && tokens.refresh) {
    const ok = await refresh()
    if (ok) return request(method, path, { body, signal, retry: false, auth })
  }

  const requestId = res.headers.get('X-Request-Id') || ''
  if (res.status === 204) return null

  const text = await res.text()
  let payload = null
  if (text) {
    try {
      payload = JSON.parse(text)
    } catch {
      payload = { detail: text.slice(0, 300) }
    }
  }

  if (!res.ok) {
    if (res.status === 401) signOut()
    throw new ApiError(res.status, payload, requestId)
  }
  return payload
}

export const api = {
  get: (path, opts) => request('GET', path, opts),
  post: (path, body, opts) => request('POST', path, { ...opts, body }),
  patch: (path, body, opts) => request('PATCH', path, { ...opts, body }),
  put: (path, body, opts) => request('PUT', path, { ...opts, body }),
  del: (path, opts) => request('DELETE', path, opts),

  /** Fetch a file and save it, with the bearer token attached.
   *
   * A plain <a href> cannot do this: the export endpoints are authenticated
   * and an anchor sends no Authorization header, so the browser would follow
   * the link and land on a 401 page. So the file is fetched like any other
   * request, turned into a blob, and handed to a synthetic link.
   *
   * The object URL is revoked afterwards — without it every export leaks the
   * whole file into memory for the lifetime of the tab, which for a contact
   * list is not a rounding error.
   */
  async download(path, fallbackName = 'export.csv') {
    const res = await fetch(BASE + path, {
      headers: {
        'Accept-Language': language,
        ...(tokens.access ? { Authorization: `Bearer ${tokens.access}` } : {}),
      },
    })
    if (!res.ok) {
      let detail = ''
      try {
        detail = (await res.json()).detail
      } catch {
        /* an error page rather than JSON; the status is what matters */
      }
      throw new Error(detail || `Download failed (${res.status})`)
    }

    // the server names the file; the caller's name is only a fallback
    const disposition = res.headers.get('content-disposition') || ''
    const named = /filename="?([^"';]+)"?/i.exec(disposition)
    const blob = await res.blob()
    const url = URL.createObjectURL(blob)
    const a = document.createElement('a')
    a.href = url
    a.download = named ? named[1] : fallbackName
    document.body.appendChild(a)
    a.click()
    a.remove()
    URL.revokeObjectURL(url)
    return blob.size
  },

  /** Login is the one call that must NOT carry a stale token. */
  async login(email, password) {
    const data = await request('POST', '/auth/login', {
      body: { email, password },
      auth: false,
      retry: false,
    })
    tokens.set(data)
    return data
  },

  async logout() {
    try {
      await request('POST', '/auth/logout', { retry: false })
    } catch {
      // signing out locally matters more than the server acknowledging it
    }
    signOut()
  },
}

/** Build a query string, dropping empties so `?q=&status=all` never happens. */
export function qs(params = {}) {
  const out = new URLSearchParams()
  for (const [k, v] of Object.entries(params)) {
    if (v === undefined || v === null || v === '' || v === 'all') continue
    out.set(k, String(v))
  }
  const s = out.toString()
  return s ? `?${s}` : ''
}
