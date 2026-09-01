/* ============================================================
   THE DEPLOYMENT.

   One installation of this agent is sold to one customer, and the
   implementation team decides beforehand what that customer gets:
   the name on the door, the accent colour, which sections exist,
   who the agent is.

   This provider holds that answer. It is fetched BEFORE anything
   else and without a token, because the sign-in screen already
   has to carry the customer's brand — a login page reading
   "MailPilot" to someone who bought "Northwind" is the first
   thing they would notice and the last thing we want them to.

   `has(module)` is the only way the UI should ask whether a
   section exists. The server enforces the same list, so this is a
   presentation concern and never a security one.
   ============================================================ */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { api } from './client'
import { langUnset, useI18n } from '../i18n'

const ConfigCtx = createContext(null)

/* Enough to render a coherent panel if the config request fails outright —
   the alternative is a blank screen when one endpoint is slow. */
const FALLBACK = {
  brand: { name: 'MailPilot', tagline: '', accent: '#7ba3cd', supportEmail: '' },
  lang: { default: 'en', locked: false },
  modules: ['campaigns', 'audience'],
  agent: { name: 'Agent', role: '' },
  ai: { configured: false, search: false },
  setupComplete: true,
}

export function ConfigProvider({ children }) {
  const { setLang } = useI18n()
  const [config, setConfig] = useState(null)
  const [failed, setFailed] = useState(false)

  const load = useCallback(async () => {
    try {
      setConfig(await api.get('/config'))
      setFailed(false)
    } catch {
      // A deployment that cannot describe itself is still worth showing; the
      // customer sees a working panel with default branding rather than a wall.
      setConfig(FALLBACK)
      setFailed(true)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  /* The accent is the one brand token that reaches CSS. Everything else in the
     palette is derived from it in tokens.css, so a deployment recolours by
     writing a single custom property rather than by shipping a stylesheet. */
  useEffect(() => {
    const accent = config?.brand?.accent
    if (accent) document.documentElement.style.setProperty('--brand', accent)
  }, [config?.brand?.accent])

  useEffect(() => {
    if (config?.brand?.name) document.title = config.brand.name
  }, [config?.brand?.name])

  /* The deployment's default language applies to a browser that has never
     chosen one — a reader's own choice is never overridden. A LOCKED
     deployment is different: it is not a default, it is the only option, so it
     wins over whatever was stored. */
  useEffect(() => {
    const wanted = config?.lang?.default
    if (!wanted) return
    if (config.lang.locked || langUnset()) setLang(wanted)
  }, [config?.lang?.default, config?.lang?.locked, setLang])

  const value = useMemo(() => {
    const modules = config?.modules || []
    return {
      config,
      failed,
      ready: config !== null,
      reload: load,
      brand: config?.brand || FALLBACK.brand,
      agent: config?.agent || FALLBACK.agent,
      ai: config?.ai || FALLBACK.ai,
      setupComplete: config?.setupComplete ?? true,
      langLocked: Boolean(config?.lang?.locked),
      has: (module) => modules.includes(module),
    }
  }, [config, failed, load])

  return <ConfigCtx.Provider value={value}>{children}</ConfigCtx.Provider>
}

export function useConfig() {
  const ctx = useContext(ConfigCtx)
  if (!ctx) throw new Error('useConfig must be used inside <ConfigProvider>')
  return ctx
}
