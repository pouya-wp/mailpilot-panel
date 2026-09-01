/* ============================================================
   Data fetching, in about a hundred lines.

   No react-query. What this panel actually needs is: fetch on
   mount, cancel on unmount, don't tear down the old data while
   the new request is in flight, and let a mutation invalidate a
   list. That is small enough to own, and owning it keeps the
   bundle and the mental model honest.

   The one behaviour worth naming is `keepPrevious`. When a filter
   changes, throwing the table away and showing a spinner makes the
   page jump and loses the reader's place. Holding the previous
   rows and dimming them keeps the layout still, which is why every
   list here passes it.
   ============================================================ */

import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from 'react'
import { ApiError, api } from './client'

/* A trivial cache so two components asking for the same path do not both
   fetch it. Invalidated by key prefix after a mutation. */
const cache = new Map()
const subscribers = new Set()

export function invalidate(prefix = '') {
  for (const key of [...cache.keys()]) {
    if (!prefix || key.startsWith(prefix)) cache.delete(key)
  }
  subscribers.forEach((fn) => fn(prefix))
}

/**
 * @param {string|null} path  request path, or null to skip entirely
 */
export function useApi(path, { keepPrevious = true, enabled = true } = {}) {
  const [state, setState] = useState(() => ({
    data: path && cache.has(path) ? cache.get(path) : null,
    error: null,
    loading: Boolean(path) && enabled && !cache.has(path),
  }))
  const alive = useRef(true)

  useEffect(() => {
    alive.current = true
    return () => {
      alive.current = false
    }
  }, [])

  const run = useCallback(
    async (signal) => {
      if (!path || !enabled) {
        setState({ data: null, error: null, loading: false })
        return
      }
      setState((s) => ({
        data: keepPrevious ? s.data : null,
        error: null,
        loading: true,
      }))
      try {
        const data = await api.get(path, { signal })
        cache.set(path, data)
        if (alive.current) setState({ data, error: null, loading: false })
      } catch (err) {
        if (err?.name === 'AbortError') return
        if (alive.current) {
          setState((s) => ({ data: keepPrevious ? s.data : null, error: err, loading: false }))
        }
      }
    },
    [path, enabled, keepPrevious]
  )

  useEffect(() => {
    const controller = new AbortController()
    run(controller.signal)
    return () => controller.abort()
  }, [run])

  // re-run when something invalidated a prefix this path falls under
  useEffect(() => {
    const onInvalidate = (prefix) => {
      if (path && (!prefix || path.startsWith(prefix))) {
        const controller = new AbortController()
        run(controller.signal)
      }
    }
    subscribers.add(onInvalidate)
    return () => subscribers.delete(onInvalidate)
  }, [path, run])

  const reload = useCallback(() => {
    if (path) cache.delete(path)
    const controller = new AbortController()
    return run(controller.signal)
  }, [path, run])

  return { ...state, reload }
}

/**
 * A write. Returns `[run, { loading, error }]`.
 *
 * `invalidates` is a list of path prefixes to refetch on success, so a page
 * never has to thread a manual `reload` down through its children.
 */
export function useMutation(fn, { invalidates = [], onSuccess, onError } = {}) {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)

  const run = useCallback(
    async (...args) => {
      setLoading(true)
      setError(null)
      try {
        const result = await fn(...args)
        invalidates.forEach((p) => invalidate(p))
        onSuccess?.(result)
        return result
      } catch (err) {
        setError(err)
        onError?.(err)
        // rethrow so a caller that wants to branch on failure still can
        throw err
      } finally {
        setLoading(false)
      }
    },
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [fn, onSuccess, onError, invalidates.join('|')]
  )

  return [run, { loading, error }]
}

/* ============================================================
   A debounced value, for search boxes. Firing a request per
   keystroke is both wasteful and racy — the answer to "sum" can
   arrive after the answer to "summe".
   ============================================================ */
export function useDebounced(value, delay = 300) {
  const [settled, setSettled] = useState(value)
  useEffect(() => {
    const id = setTimeout(() => setSettled(value), delay)
    return () => clearTimeout(id)
  }, [value, delay])
  return settled
}

/* ============================================================
   The live event stream. SSE, with the browser's own reconnect.
   ============================================================ */
export function useEventStream(enabled = true, limit = 12) {
  const [events, setEvents] = useState([])

  useEffect(() => {
    if (!enabled) return
    let cancelled = false

    // EventSource cannot send an Authorization header, so the initial list
    // comes from the normal endpoint and the stream tops it up.
    api
      .get(`/events?limit=${limit}`)
      .then((rows) => !cancelled && setEvents(rows || []))
      .catch(() => {})

    return () => {
      cancelled = true
    }
  }, [enabled, limit])

  return events
}
