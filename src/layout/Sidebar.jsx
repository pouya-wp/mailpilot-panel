/* ============================================================
   THE RAIL

   The one piece of choreography worth pointing at is the active
   marker. It is a SINGLE element that is tweened to the active
   row's position, not a pseudo-element on each item — which means
   the selection travels down the rail when you change page instead
   of blinking off one row and on at another. Exactly the same
   trick as the segmented control and the tabs; three different
   components, one gesture, so the panel feels like one object.

   Position is measured with getBoundingClientRect rather than
   offsetTop because the rail is inside the page-transition
   timeline, which may still have a transform on an ancestor when
   this first runs.
   ============================================================ */
import { useRef } from 'react'
import { gsap, reduced, useGSAP } from '../anim/core'
import { useI18n } from '../i18n'
import { navigate, useRoute } from '../router'
import { Logo } from '../components/Icons'
import { IcChevron } from '../components/NavIcons'
import { Progress, useIndicator } from '../ui'
import { useApi } from '../api/hooks'
import { useConfig } from '../api/config'
import { navFor } from './nav'

export default function Sidebar({ min, onToggle, onNavigate }) {
  const { t, nf, rtl } = useI18n()
  const { brand, has, agent } = useConfig()
  const { path } = useRoute()
  const rail = useRef(null)
  const nav = useRef(null)
  const marker = useRef(null)

  /* ---- the travelling marker ----
     Re-measured through a ResizeObserver as well as on route change: the rail
     is 0.42s mid-transition while it collapses, and a marker placed from the
     rect it had before the collapse ends up floating off the row. */
  useIndicator(
    nav,
    '.navi--on',
    (host, r) => {
      const mk = marker.current
      if (!mk) return
      gsap.to(mk, {
        y: r.y + (r.h - mk.offsetHeight) / 2,
        opacity: 1,
        duration: reduced() ? 0 : 0.5,
        ease: 'snap',
        overwrite: 'auto',
      })
    },
    [path, min]
  )

  /* nothing active (an unknown route) — retract it rather than leaving it lit */
  useGSAP(
    () => {
      if (!rail.current?.querySelector('.navi--on')) gsap.to(marker.current, { opacity: 0, duration: 0.2 })
    },
    { dependencies: [path], scope: rail }
  )

  /* ---- the mark breathes, as it did in the original top bar ---- */
  useGSAP(
    () => {
      if (reduced()) return
      const mark = rail.current?.querySelector('.side__mark')
      if (!mark) return
      const spin = gsap.to(mark.querySelectorAll('path')[1], {
        rotation: 360,
        transformOrigin: '50% 50%',
        duration: 16,
        ease: 'none',
        repeat: -1,
      })
      const glow = gsap.to(mark, { '--lit': 1, duration: 2.8, ease: 'sine.inOut', yoyo: true, repeat: -1 })
      return () => {
        spin.kill()
        glow.kill()
      }
    },
    { scope: rail }
  )

  const go = (id) => {
    navigate(id)
    onNavigate?.()
  }

  /* The rail's credit meter is the same counter Billing shows, so it moves the
     moment the agent spends — every AI call invalidates /billing. Skipped
     entirely where billing was not part of the deployment. */
  const billing = useApi(has('billing') ? '/billing' : null)
  const credits = has('billing') ? billing.data?.usage?.credits : null

  return (
    <aside className="side" ref={rail}>
      <div className="side__brand">
        <span className="side__mark">
          <Logo size={30} />
        </span>
        <span className="side__names">
          <span className="side__name">{brand.name}</span>
          <span className="side__tag">{brand.tagline || agent.name}</span>
        </span>
      </div>

      <nav className="side__scroll" ref={nav}>
        <span className="side__marker" ref={marker} aria-hidden="true" />

        {navFor(has).map((item) => {
          const Icon = item.icon
          const on = path === item.id
          return (
            <a
              key={item.id}
              href={`#/${item.id}`}
              className={`navi${on ? ' navi--on' : ''}`}
              title={min ? t(item.labelKey) : undefined}
              onClick={(e) => {
                e.preventDefault()
                go(item.id)
              }}
            >
              <span className="navi__icon">
                <Icon size={18} />
              </span>
              <span className="navi__label">{t(item.labelKey)}</span>
            </a>
          )
        })}
      </nav>

      <div className="side__foot">
        {has('billing') && (
        <div className="credits">
          <div className="credits__top">
            <span>{t('m.credits')}</span>
            <b>{nf(credits ? credits.limit - credits.used : 0)}</b>
          </div>
          <Progress value={credits ? credits.limit - credits.used : 0} max={credits?.limit || 1} tone="blue" />
        </div>
        )}

        <button className="side__collapse" onClick={onToggle}>
          <IcChevron size={16} dir={min ? 'end' : 'start'} flip={rtl} />
          <span>{min ? t('app.expand') : t('app.collapse')}</span>
        </button>
      </div>
    </aside>
  )
}
