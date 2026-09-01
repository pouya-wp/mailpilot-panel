/* ============================================================
   Bilingual runtime — English (LTR) and Persian (RTL).

   Two things make this more than a string lookup:

   * `dir` is written onto <html>, not onto a wrapper. Every new
     stylesheet in this panel is authored with logical properties
     (inline-start / inline-end), so flipping that one attribute
     mirrors the whole layout — sidebar, tables, charts, drawers —
     without a single mirrored rule.

   * numbers and dates go through Intl bound to the active locale,
     so Persian gets Eastern Arabic digits and the Jalali calendar
     for free. `digits` can force Latin numerals back on, because a
     dense table of figures is easier to scan aligned.
   ============================================================ */
import { createContext, useCallback, useContext, useEffect, useMemo, useState } from 'react'
import { circularThemeSwitch } from '../anim/themeSwitch'
import en from './en'
import fa from './fa'

export const DICTS = { en, fa }
export const LANGS = ['en', 'fa']

const LANG_KEY = 'mailpilot:lang'

/** True when this browser has never had a language chosen in it. */
export const langUnset = () =>
  typeof window === 'undefined' || !window.localStorage.getItem(LANG_KEY)
const THEME_KEY = 'mailpilot:theme'
const DIGIT_KEY = 'mailpilot:digits'

const I18nCtx = createContext(null)

const readLang = () => {
  const saved = typeof window !== 'undefined' && window.localStorage.getItem(LANG_KEY)
  if (saved && DICTS[saved]) return saved
  // a Persian-speaking browser gets Persian on the first visit
  if (typeof navigator !== 'undefined' && /^fa\b/i.test(navigator.language || '')) return 'fa'
  return 'en'
}

/* The theme is remembered, and falls back to whatever the OS asks for on a
   first visit rather than assuming everyone wants the dark panel. */
const readTheme = () => {
  const saved = typeof window !== 'undefined' && window.localStorage.getItem(THEME_KEY)
  if (saved === 'light' || saved === 'dark') return saved
  if (typeof window !== 'undefined' && window.matchMedia?.('(prefers-color-scheme: light)').matches) return 'light'
  return 'dark'
}

export function I18nProvider({ children }) {
  const [lang, setLang] = useState(readLang)
  const [theme, setTheme] = useState(readTheme)
  const [latinDigits, setLatinDigits] = useState(
    () => typeof window !== 'undefined' && window.localStorage.getItem(DIGIT_KEY) === 'latin'
  )

  const dict = DICTS[lang]
  const dir = dict.dir

  /* The document element is the single source of truth for direction, so
     third-party bits (the avatar, native scrollbars, form controls) flip too. */
  useEffect(() => {
    const root = document.documentElement
    root.lang = lang
    root.dir = dir
    root.dataset.lang = lang
    window.localStorage.setItem(LANG_KEY, lang)
  }, [lang, dir])

  useEffect(() => {
    window.localStorage.setItem(DIGIT_KEY, latinDigits ? 'latin' : 'native')
  }, [latinDigits])

  /* `data-theme` on <html> is the single switch: tokens.css keys both palettes
     off it, so nothing below has to know which theme is active. */
  useEffect(() => {
    document.documentElement.dataset.theme = theme
    window.localStorage.setItem(THEME_KEY, theme)
  }, [theme])

  /* Persian numerals unless the reader asked for Latin ones. `-u-nu-latn`
     keeps the locale (grouping, calendar) and swaps only the digit set. */
  const numLocale = lang === 'fa' && latinDigits ? 'fa-IR-u-nu-latn' : dict.locale

  const api = useMemo(() => {
    const t = (key, vars) => {
      let s = dict[key] ?? en[key] ?? key
      if (vars) for (const k in vars) s = s.replaceAll(`{${k}}`, vars[k])
      return s
    }

    const nf = (n, opts) => new Intl.NumberFormat(numLocale, opts).format(n ?? 0)
    const sign = lang === 'fa' ? '٪' : '%'
    const pct = (n, digits = 1) =>
      new Intl.NumberFormat(numLocale, {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
      }).format(n ?? 0) + sign
    const money = (n, currency = 'USD') =>
      new Intl.NumberFormat(numLocale, { style: 'currency', currency, maximumFractionDigits: 0 }).format(n ?? 0)
    /* 31,000 -> 31k / ۳۱هزار. Charts and tiles need the short form or the
       figures start colliding with their own labels. */
    const compact = (n) => {
      const abs = Math.abs(n ?? 0)
      if (abs >= 1_000_000) return nf(Math.round((n / 1_000_000) * 10) / 10) + (lang === 'fa' ? 'م' : 'M')
      if (abs >= 1000) return nf(Math.round((n / 1000) * 10) / 10) + (lang === 'fa' ? 'ه' : 'k')
      return nf(Math.round(n ?? 0))
    }
    /* Every date helper below refuses a value it cannot read.
       `new Date(null)` is not an error — it is the Unix epoch, so a contact who
       has never opened anything was being shown as "57 years ago" rather than
       as never. `new Date(undefined)` is worse: an Invalid Date that formats as
       literal junk. Both reach these helpers constantly, because "no date yet"
       is the normal state of a fresh install. */
    const readable = (d) => {
      if (d === null || d === undefined || d === '') return null
      const parsed = d instanceof Date ? d : new Date(d)
      return Number.isNaN(parsed.getTime()) ? null : parsed
    }
    const date = (d, opts = { day: 'numeric', month: 'short' }) => {
      const when = readable(d)
      return when ? new Intl.DateTimeFormat(numLocale, opts).format(when) : '—'
    }
    const time = (d) => {
      const when = readable(d)
      return when
        ? new Intl.DateTimeFormat(numLocale, { hour: '2-digit', minute: '2-digit' }).format(when)
        : '—'
    }
    /* "3 h ago" — used all over the activity feeds. Intl.RelativeTimeFormat
       gives the right Persian wording without a table of plural rules here. */
    const ago = (d) => {
      const when = readable(d)
      if (!when) return t('g.never')
      const rtf = new Intl.RelativeTimeFormat(numLocale, { numeric: 'auto' })
      const diff = (when - Date.now()) / 1000
      const steps = [
        [60, 'second', 1],
        [3600, 'minute', 60],
        [86400, 'hour', 3600],
        [604800, 'day', 86400],
        [2592000, 'week', 604800],
        [31536000, 'month', 2592000],
        [Infinity, 'year', 31536000],
      ]
      for (const [limit, unit, div] of steps) {
        if (Math.abs(diff) < limit) return rtf.format(Math.round(diff / div), unit)
      }
      return ''
    }

    return { t, nf, pct, money, compact, date, time, ago }
  }, [dict, numLocale, lang])

  const value = useMemo(
    () => ({
      lang,
      dir,
      rtl: dir === 'rtl',
      setLang,
      latinDigits,
      setLatinDigits,
      langs: LANGS.map((id) => ({ id, label: DICTS[id].label, short: DICTS[id].short })),
      theme,
      setTheme,
      /* `origin` is the element the reader clicked. The circular reveal
         opens from there, so the animation belongs to the control rather
         than to the page. Callers that have no element still work. */
      toggleTheme: (origin) => {
        const next = theme === 'dark' ? 'light' : 'dark'
        circularThemeSwitch(next, () => setTheme(next), origin)
      },
      ...api,
    }),
    [lang, dir, latinDigits, theme, api]
  )

  return <I18nCtx.Provider value={value}>{children}</I18nCtx.Provider>
}

export function useI18n() {
  const ctx = useContext(I18nCtx)
  if (!ctx) throw new Error('useI18n must be used inside <I18nProvider>')
  return ctx
}

/* Handy for components that only need the string function. */
export function useT() {
  return useI18n().t
}

/* ============================================================
   CONTENT localisation, as opposed to interface localisation.

   Campaign names, agent roles and contact names come from the API
   as `{en, fa}` — they are data, not UI strings, so they are not
   in the dictionaries above. `loc()` picks the reader's language
   out of such a value and falls back to English when a translation
   is missing, which is the same rule the server applies.

   It tolerates a plain string too, so a field that has not been
   made bilingual yet still renders instead of printing "[object
   Object]".
   ============================================================ */
export const loc = (value, lang) => {
  if (value === null || value === undefined) return ''
  if (typeof value === 'string' || typeof value === 'number') return String(value)
  return value[lang] ?? value.en ?? value.fa ?? ''
}

/** `const L = useLoc()` then `L(campaign.name)` — language already bound. */
export function useLoc() {
  const { lang } = useI18n()
  return useCallback((value) => loc(value, lang), [lang])
}

/** Find a record by id in a list the API returned. Replaces the mock's
    `agentById` / `segmentById` helpers, which indexed module constants. */
export const byId = (list, id) => (Array.isArray(list) ? list.find((r) => r.id === id) : undefined)

/* Direction-aware sign: multiply any x-offset by this and a tween written
   for LTR reads correctly in RTL. Used by the page-transition timeline. */
export const useFlip = () => (useI18n().rtl ? -1 : 1)

export { useCallback }
