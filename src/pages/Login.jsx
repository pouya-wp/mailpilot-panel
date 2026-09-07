/* The sign-in screen.

   Wears the same light rig and glass surface as the panel behind it, so
   signing in reads as stepping into the product rather than as a different
   application that happens to precede it. */

import { useEffect, useRef, useState } from 'react'
import { gsap, reduced, useGSAP } from '../anim/core'
import { useI18n } from '../i18n'
import { useAuth } from '../api/auth'
import { Button, Field, Input } from '../ui'
import { Logo } from '../components/Icons'
import { useConfig } from '../api/config'
import { IcArrow, IcMoon, IcSun, IcWarn } from '../components/NavIcons'

export default function Login() {
  const { brand, agent } = useConfig()
  const { t, lang, langs, setLang, rtl, theme, toggleTheme } = useI18n()
  const { login } = useAuth()

  /* The last address that signed in on this browser, not a demo account
     from the seed data. Wrapped because storage throws in a private
     window and an unreadable convenience must not stop anyone signing in. */
  const [email, setEmail] = useState(() => {
    try {
      return window.localStorage.getItem('mailpilot:lastEmail') || ''
    } catch {
      return ''
    }
  })
  const [password, setPassword] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState(null)

  const card = useRef(null)
  const emailRef = useRef(null)

  useEffect(() => {
    // focus the first empty field, not blindly the first field
    const el = email ? document.getElementById('login-password') : emailRef.current
    el?.focus()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useGSAP(
    () => {
      if (reduced() || !card.current) return
      gsap
        .timeline()
        .from(card.current, { opacity: 0, y: 26, scale: 0.97, duration: 0.7, ease: 'glide' })
        .from(card.current.querySelectorAll('.login__row'), {
          opacity: 0,
          y: 14,
          duration: 0.5,
          stagger: 0.07,
        }, 0.15)
    },
    { scope: card }
  )

  const submit = async (e) => {
    e.preventDefault()
    if (busy) return
    setBusy(true)
    setError(null)
    try {
      await login(email.trim(), password)
      // remembered only once it is known to work, so a typo is not offered
      // back on the next visit
      try {
        window.localStorage.setItem('mailpilot:lastEmail', email.trim())
      } catch {
        /* private window; the sign-in still worked */
      }
    } catch (err) {
      setError(err)
      // shake, then put the caret back where the fix is
      if (!reduced() && card.current) {
        gsap.fromTo(card.current, { x: -8 }, { x: 0, duration: 0.5, ease: 'elastic.out(1, 0.4)' })
      }
      document.getElementById('login-password')?.focus()
    } finally {
      setBusy(false)
    }
  }

  return (
    <div className="app login" data-intro="running">
      <span className="app__orb app__orb--a" />
      <span className="app__orb app__orb--key" />
      <span className="app__orb app__orb--b" />
      <span className="app__orb app__orb--c" />

      <div className="login__corner">
        <div className="lang">
          {langs.map((l) => (
            <button
              key={l.id}
              className={`lang__btn${l.id === lang ? ' lang__btn--on' : ''}`}
              onClick={() => setLang(l.id)}
            >
              {l.short}
            </button>
          ))}
        </div>
        <button className="iconbtn" onClick={toggleTheme} aria-label={t('app.theme')}>
          {theme === 'dark' ? <IcSun size={17} /> : <IcMoon size={17} />}
        </button>
      </div>

      <form className="card login__card" ref={card} onSubmit={submit}>
        <div className="login__brand login__row">
          <span className="side__mark">
            <Logo size={34} />
          </span>
          <div>
            <div className="login__name">{brand.name}</div>
            <div className="login__tag">{brand.tagline || agent.role}</div>
          </div>
        </div>

        <h1 className="login__title login__row">{t('auth.title')}</h1>
        <p className="login__sub login__row">{t('auth.sub', { name: agent.name })}</p>

        {error && (
          <div className="login__error login__row" role="alert">
            <IcWarn size={16} />
            <span>{error.status === 401 ? t('auth.badCredentials') : error.message}</span>
          </div>
        )}

        <div className="login__row">
          <Field label={t('ct.email')}>
            <Input
              id="login-email"
              ref={emailRef}
              type="email"
              autoComplete="username"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="mono"
              /* A shape, not a suggestion. This box used to arrive with a
                 real address from the seed data already in it. */
              placeholder="name@company.com"
            />
          </Field>
        </div>

        <div className="login__row">
          <Field label={t('auth.password')}>
            <Input
              id="login-password"
              type="password"
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
            />
          </Field>
        </div>

        <div className="login__row">
          <Button
            variant="primary"
            size="lg"
            full
            type="submit"
            loading={busy}
            iconEnd={<IcArrow size={16} flip={rtl} />}
          >
            {t('auth.signIn')}
          </Button>
        </div>

        {brand.supportEmail && (
          <p className="login__hint login__row">
            {t('auth.help')} <a href={`mailto:${brand.supportEmail}`}>{brand.supportEmail}</a>
          </p>
        )}
      </form>

      <span className="grain" aria-hidden="true" />
    </div>
  )
}
