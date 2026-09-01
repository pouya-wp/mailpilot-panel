/* ============================================================
   Who is signed in.

   The provider starts in a `checking` state and stays there until
   `/auth/me` has answered. That third state matters: without it the
   panel renders the sign-in screen for a frame on every reload,
   which reads as being logged out and is the single most common
   way a session feels broken when it is not.
   ============================================================ */

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api, onSignedOut, tokens } from './client'
import { invalidate } from './hooks'

const AuthCtx = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [checking, setChecking] = useState(true)

  /* ---- bootstrap ---- */
  useEffect(() => {
    let alive = true
    if (!tokens.access) {
      setChecking(false)
      return
    }
    api
      .get('/auth/me')
      .then((me) => alive && setUser(me))
      .catch(() => alive && setUser(null))
      .finally(() => alive && setChecking(false))
    return () => {
      alive = false
    }
  }, [])

  /* the client signs us out when a refresh fails — follow it */
  useEffect(() => onSignedOut(() => setUser(null)), [])

  const login = useCallback(async (email, password) => {
    await api.login(email, password)
    const me = await api.get('/auth/me')
    invalidate() // nothing cached under the previous session survives
    setUser(me)
    return me
  }, [])

  const logout = useCallback(async () => {
    await api.logout()
    invalidate()
    setUser(null)
  }, [])

  const value = useMemo(
    () => ({
      user,
      checking,
      login,
      logout,
      /** Role gate for the UI. The API enforces this too — this only
          decides whether to show a control the caller could not use. */
      can: (permission) => Boolean(user?.permissions?.includes(permission)),
    }),
    [user, checking, login, logout]
  )

  return <AuthCtx.Provider value={value}>{children}</AuthCtx.Provider>
}

export function useAuth() {
  const ctx = useContext(AuthCtx)
  if (!ctx) throw new Error('useAuth must be used inside <AuthProvider>')
  return ctx
}
