/* ============================================================
   A hash router in ~70 lines.

   The panel is a single static bundle with no server in front of
   it, so history routing would 404 on a refresh. Hash routing has
   no such problem and needs no dependency: `#/campaigns/c-204`
   parses to `{ path: 'campaigns', params: ['c-204'] }`.

   `navigate` is exported as a plain function as well as a hook, so
   non-React code (the command palette's keyboard handler, the
   agent) can move the panel without threading a callback through.
   ============================================================ */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'

const RouteCtx = createContext(null)

const read = () => {
  const raw = window.location.hash.replace(/^#\/?/, '')
  const [pathPart, queryPart] = raw.split('?')
  const parts = pathPart.split('/').filter(Boolean)
  return {
    path: parts[0] || 'home',
    params: parts.slice(1),
    query: Object.fromEntries(new URLSearchParams(queryPart || '')),
    raw,
  }
}

export const navigate = (to, { replace = false } = {}) => {
  const next = `#/${String(to).replace(/^#?\/?/, '')}`
  if (window.location.hash === next) return
  if (replace) window.history.replaceState(null, '', next)
  else window.location.hash = next
  // replaceState does not fire hashchange, so tell the app ourselves
  if (replace) window.dispatchEvent(new HashChangeEvent('hashchange'))
}

export function RouterProvider({ children }) {
  const [route, setRoute] = useState(read)

  useEffect(() => {
    const sync = () => setRoute(read())
    window.addEventListener('hashchange', sync)
    if (!window.location.hash) navigate('home', { replace: true })
    return () => window.removeEventListener('hashchange', sync)
  }, [])

  /* Each navigation starts at the top of the page — an admin panel where the
     next screen opens half-scrolled reads as broken. */
  useEffect(() => {
    document.querySelector('.ash__scroll')?.scrollTo({ top: 0 })
  }, [route.raw])

  const value = useMemo(() => ({ ...route, navigate }), [route])
  return <RouteCtx.Provider value={value}>{children}</RouteCtx.Provider>
}

export function useRoute() {
  const ctx = useContext(RouteCtx)
  if (!ctx) throw new Error('useRoute must be used inside <RouterProvider>')
  return ctx
}

export function useNavigate() {
  return useCallback(navigate, [])
}

/** An anchor that keeps middle-click and "open in new tab" working. */
export function Link({ to, className, children, ...rest }) {
  return (
    <a href={`#/${String(to).replace(/^#?\/?/, '')}`} className={className} {...rest}>
      {children}
    </a>
  )
}
