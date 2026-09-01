/* ============================================================
   THE APP

   Composition, in order of what owns what:

   * `.app` and its orbs are the ORIGINAL light rig, untouched.
     The whole admin shell is built on top of it, which is what
     keeps the new panel recognisably the same object as the old
     one — the surfaces are lit by the same four lamps.
   * `.ash` is the new two-column shell: a fixed rail and a
     scrolling main column.
   * The router picks the page; a small timeline runs on every
     route change so a new screen arrives rather than replacing.

   Nothing is rendered until the webfonts resolve. That was true
   before (SplitText measures glyphs) and is more true now: the
   Persian face is a second webfont, and letting the panel paint in
   the fallback would show a full page of the wrong typography
   before snapping.
   ============================================================ */
import { useCallback, useEffect, useRef, useState } from 'react'
import { fontsReady, gsap, markIntroStarted, reduced, useGSAP } from './anim/core'
import { I18nProvider, useI18n } from './i18n'
import { AuthProvider, useAuth } from './api/auth'
import { ConfigProvider, useConfig } from './api/config'
import { navigate, RouterProvider, useRoute } from './router'
import Sidebar from './layout/Sidebar'
import Topbar from './layout/Topbar'
import CommandPalette from './layout/CommandPalette'
import SupportAgent from './components/SupportAgent'
import { IcCheckC } from './components/NavIcons'
import { ErrorBoundary } from './ui/ErrorBoundary'

import Home from './pages/Home'
import Campaigns from './pages/Campaigns'
import Audience from './pages/Audience'
import Designer from './pages/Designer'
import Inbox from './pages/Inbox'
import Insights from './pages/Insights'
import Guide from './pages/Guide'
import Settings from './pages/Settings'
import Setup from './pages/Setup'
import Login from './pages/Login'

/* The whole product. Everything that used to be a destination — composing,
   templates, journeys, experiments, the agent roster, six reporting screens —
   is either work the agent now does or a tab inside one of these five.

   `setup` is here but not in the navigation: it belongs to the team that
   installs the agent, and they reach it by URL. */
const PAGES = {
  home: Home,
  campaigns: Campaigns,
  audience: Audience,
  designer: Designer,
  inbox: Inbox,
  insights: Insights,
  guide: Guide,
  settings: Settings,
  setup: Setup,
}

const SIDE_KEY = 'mailpilot:side'

export default function App() {
  return (
    <I18nProvider>
      {/* The deployment is fetched before anything else and without a token:
          the sign-in screen already has to carry the customer's brand. */}
      <ConfigProvider>
        <AuthProvider>
          <RouterProvider>
            <Gate />
          </RouterProvider>
        </AuthProvider>
      </ConfigProvider>
    </I18nProvider>
  )
}

/* Three states, not two.

   The `checking` state exists because the panel reloads with a token in
   localStorage that has not been validated yet. Without it, every refresh
   would paint the sign-in screen for a frame before `/auth/me` answers —
   which reads as being logged out, and is the most common way a session
   feels broken when it is not. */
function Gate() {
  const { t } = useI18n()
  const { user, checking } = useAuth()

  if (checking) {
    return (
      <div className="boot">
        <div className="boot__inner">
          <span className="boot__spin" />
          <span className="boot__text">{t('auth.checking')}</span>
        </div>
      </div>
    )
  }
  return user ? <Shell /> : <Login />
}

function Shell() {
  const { t, rtl } = useI18n()
  const { path } = useRoute()
  const { setupComplete, has } = useConfig()
  const { can } = useAuth()

  const [ready, setReady] = useState(false)
  const [min, setMin] = useState(() => window.localStorage.getItem(SIDE_KEY) === 'min')
  const [drawer, setDrawer] = useState(false) // the mobile rail
  const [cmd, setCmd] = useState(false)
  const [toast, setToast] = useState(null)

  const root = useRef(null)
  const stage = useRef(null)
  const toastEl = useRef(null)
  const toastTimer = useRef(0)

  const Page = PAGES[path] ?? Home

  const fire = useCallback((msg) => {
    clearTimeout(toastTimer.current)
    setToast({ msg, at: Date.now() })
  }, [])

  useEffect(() => {
    window.localStorage.setItem(SIDE_KEY, min ? 'min' : 'full')
  }, [min])

  /* close the mobile rail whenever the route changes */
  useEffect(() => setDrawer(false), [path])

  /* A deployment that has never been configured opens the wizard once, and
     only for someone who can actually complete it — everyone else lands on
     home and sees a notice they can act on by asking their admin. */
  useEffect(() => {
    if (!setupComplete && path === 'home' && can('settings.write')) navigate('setup')
  }, [setupComplete, path, can])

  /* Two ways a route can fail to exist, both ending at home.

     A route belonging to a module this deployment does not include is not a
     404 to argue with — it simply does not exist here. And a route left over
     from before the pivot (`#/agents`, `#/composer`, and a dozen others) used
     to fall through to Home while the address bar still claimed otherwise,
     which left the rail highlighting nothing. */
  useEffect(() => {
    const needed = { campaigns: 'campaigns', audience: 'audience', inbox: 'inbox', insights: 'insights', designer: 'templates' }[path]
    if (needed && !has(needed)) {
      navigate('home', { replace: true })
      return
    }
    if (!PAGES[path]) navigate('home', { replace: true })
  }, [path, has])

  /* ---- Ctrl/⌘ + K ---- */
  useEffect(() => {
    const key = (e) => {
      if ((e.metaKey || e.ctrlKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        setCmd((c) => !c)
      }
    }
    window.addEventListener('keydown', key)
    return () => window.removeEventListener('keydown', key)
  }, [])

  /* ---- the entrance ---- */
  useGSAP(
    () => {
      let cancelled = false
      fontsReady().then(() => {
        if (cancelled || !root.current) return
        setReady(true)
        root.current.dataset.intro = 'running'
        markIntroStarted()

        if (reduced()) return
        gsap
          .timeline({ defaults: { ease: 'glide' } })
          .from(root.current.querySelectorAll('.app__orb'), {
            opacity: 0,
            scale: 0.55,
            duration: 1.7,
            stagger: 0.14,
            ease: 'power2.out',
          })
          .from(root.current, { '--vignette': 1.7, duration: 1.5, ease: 'power2.out' }, 0)
          /* Opacity only. The rail must never carry an inline `transform`:
             below 1080px it is an off-canvas drawer whose open/closed state IS
             its transform, and an entrance tween leaves that property set for
             good — the burger would then flip the state without the rail
             moving. Driving it through a custom property instead had its own
             failure mode (a value left mid-tween shifted the rail by 3rem and
             desynced it from its grid column), so the rail simply fades and
             its groups carry the movement. */
          .from('.side', { opacity: 0, duration: 0.8 }, 0.1)
          .from('.side__brand, .side__group, .side__foot', { opacity: 0, y: 14, duration: 0.6, stagger: 0.06 }, 0.24)
          .from('.tbar > *', { opacity: 0, y: -12, duration: 0.6, stagger: 0.05 }, 0.3)
      })
      return () => {
        cancelled = true
      }
    },
    { scope: root }
  )

  /* ---- page transition ----
     A short lift-and-settle on the stage, keyed to the route. It runs on
     `stage`, not on the page's own children, so it composes with each page's
     internal Stagger instead of overwriting the transforms that owns. */
  useGSAP(
    () => {
      if (!ready || reduced() || !stage.current) return
      gsap.fromTo(
        stage.current,
        { opacity: 0, y: 16 },
        { opacity: 1, y: 0, duration: 0.5, ease: 'glide', clearProps: 'transform' }
      )
    },
    { dependencies: [path, ready] }
  )

  /* ---- toast ---- */
  useGSAP(
    () => {
      const el = toastEl.current
      if (!toast || !el) return
      gsap.fromTo(el, { y: 40, opacity: 0, scale: 0.92 }, { y: 0, opacity: 1, scale: 1, duration: 0.55, ease: 'snap' })
      toastTimer.current = setTimeout(() => {
        gsap.to(el, {
          y: 22,
          opacity: 0,
          scale: 0.96,
          duration: 0.34,
          ease: 'power2.in',
          onComplete: () => setToast(null),
        })
      }, 2800)
      return () => clearTimeout(toastTimer.current)
    },
    { dependencies: [toast?.at] }
  )

  return (
    <div className="app" ref={root} data-intro={ready ? 'running' : 'pending'}>
      <span className="app__orb app__orb--a" />
      <span className="app__orb app__orb--key" />
      <span className="app__orb app__orb--b" />
      <span className="app__orb app__orb--c" />
      <span className="app__orb app__orb--d" />

      <div className={`ash${min ? ' ash--min' : ''}${drawer ? ' ash--open' : ''}`}>
        <Sidebar min={min} onToggle={() => setMin((m) => !m)} onNavigate={() => setDrawer(false)} />
        {drawer && <div className="ash__scrim" onClick={() => setDrawer(false)} />}

        <div className="ash__main">
          <Topbar onOpenCommand={() => setCmd(true)} onBurger={() => setDrawer((d) => !d)} onToast={fire} />
          <div className="ash__scroll">
            <div ref={stage}>
              {/* keyed by route so navigating away from a crashed page clears it */}
              <ErrorBoundary resetKey={path} title={t('err.title')} retryLabel={t('auth.retry')}>
                <Page onToast={fire} />
              </ErrorBoundary>
            </div>
          </div>
        </div>
      </div>

      <span className="grain" aria-hidden="true" />
      <SupportAgent panelState={{ segment: 'VIP Users', agent: 'NOVA', recipients: '25,000' }} />

      <CommandPalette open={cmd} onClose={() => setCmd(false)} />

      {toast && (
        <div className="toast" ref={toastEl}>
          <IcCheckC size={17} />
          {toast.msg}
        </div>
      )}
    </div>
  )
}
