/* ============================================================
   COMMAND PALETTE  ·  Ctrl/⌘ + K

   Searches three things at once: the nav map, a small set of verbs,
   and the campaign and agent records — so "nova" jumps to the agent
   and "summer" jumps to the campaign, without the reader having to
   know which page either lives on.

   Matching is a plain substring test over BOTH language strings,
   deliberately: someone running the Persian interface still types
   `campaigns` half the time, and someone on English still has
   Persian campaign names in front of them.
   ============================================================ */
import { useEffect, useMemo, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { gsap, reduced, useGSAP } from '../anim/core'
import { loc, useI18n } from '../i18n'
import { navigate } from '../router'
import { useApi } from '../api/hooks'
import { IcAgent, IcCampaign, IcCompose, IcPlus, IcSearch, IcUpload } from '../components/NavIcons'
import { NAV_FLAT } from './nav'

export default function CommandPalette({ open, onClose }) {
  const { t, lang } = useI18n()
  const campaignsQ = useApi(open ? '/campaigns?size=50' : null)
  const agentsQ = useApi(open ? '/agents' : null)
  const [q, setQ] = useState('')
  const [cursor, setCursor] = useState(0)
  const input = useRef(null)
  const panel = useRef(null)
  const scrim = useRef(null)
  const list = useRef(null)

  const groups = useMemo(() => {
    const needle = q.trim().toLowerCase()
    const hit = (...vals) => !needle || vals.some((v) => String(v ?? '').toLowerCase().includes(needle))

    const pages = NAV_FLAT.filter((i) => hit(t(i.labelKey), i.id)).map((i) => ({
      id: `p-${i.id}`,
      label: t(i.labelKey),
      icon: <i.icon size={16} />,
      hint: t(i.group),
      run: () => navigate(i.id),
    }))

    const actions = [
      { id: 'a-new', label: t('camp.new'), icon: <IcPlus size={16} />, run: () => navigate('campaigns') },
      /* These three used to be screens. The composer is now the ask box on
         Home, the agent is a tab in Settings, and contacts live under
         Audience. The routes went away; these callers did not, so each one
         hit the router's unknown-path guard and bounced the reader to Home
         with no explanation. */
      { id: 'a-comp', label: t('comp.generate'), icon: <IcCompose size={16} />, run: () => navigate('home') },
      { id: 'a-agent', label: t('ag.new'), icon: <IcAgent size={16} />, run: () => navigate('settings?tab=agent') },
      { id: 'a-import', label: t('ct.importCsv'), icon: <IcUpload size={16} />, run: () => navigate('audience') },
    ].filter((a) => hit(a.label))

    const records = [
      ...(campaignsQ.data?.items || []).filter((c) => hit(c.name.en, c.name.fa, c.id)).map((c) => ({
        id: `c-${c.id}`,
        label: loc(c.name, lang),
        icon: <IcCampaign size={16} />,
        hint: t('nav.campaigns'),
        run: () => navigate(`campaigns/${c.id}`),
      })),
      ...(agentsQ.data || []).filter((a) => hit(a.name.en, a.name.fa, a.id)).map((a) => ({
        id: `ag-${a.id}`,
        label: loc(a.name, lang),
        icon: <IcAgent size={16} />,
        hint: t('nav.agents'),
        run: () => navigate(`agents/${a.id}`),
      })),
    ].slice(0, 6)

    return [
      { key: 'goto', label: t('app.commandGoto'), items: pages },
      { key: 'actions', label: t('app.commandActions'), items: actions },
      { key: 'records', label: t('g.search'), items: records },
    ].filter((g) => g.items.length)
  }, [q, t, lang, campaignsQ.data, agentsQ.data])

  const flat = useMemo(() => groups.flatMap((g) => g.items), [groups])

  useEffect(() => setCursor(0), [q])

  useEffect(() => {
    if (!open) return
    setQ('')
    setCursor(0)
    // focus after the entrance has committed, or the caret lands mid-tween
    const id = requestAnimationFrame(() => input.current?.focus())
    return () => cancelAnimationFrame(id)
  }, [open])

  useEffect(() => {
    if (!open) return
    const key = (e) => {
      if (e.key === 'Escape') return onClose()
      if (e.key === 'ArrowDown') {
        e.preventDefault()
        setCursor((c) => (c + 1) % Math.max(flat.length, 1))
      }
      if (e.key === 'ArrowUp') {
        e.preventDefault()
        setCursor((c) => (c - 1 + flat.length) % Math.max(flat.length, 1))
      }
      if (e.key === 'Enter') {
        e.preventDefault()
        flat[cursor]?.run()
        onClose()
      }
    }
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [open, flat, cursor, onClose])

  /* keep the highlighted row in view while arrowing through a long list */
  useEffect(() => {
    list.current?.querySelector('.cmdk__item--on')?.scrollIntoView({ block: 'nearest' })
  }, [cursor])

  useGSAP(
    () => {
      if (!open || !panel.current || reduced()) return
      gsap
        .timeline()
        .fromTo(scrim.current, { opacity: 0 }, { opacity: 1, duration: 0.24, ease: 'swift' })
        .fromTo(
          panel.current,
          { opacity: 0, y: -22, scale: 0.97 },
          { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'snap' },
          0.02
        )
    },
    { dependencies: [open] }
  )

  if (!open) return null

  let idx = -1
  return createPortal(
    <div className="cmdk">
      <div className="cmdk__scrim" ref={scrim} onClick={onClose} />
      <div className="cmdk__panel" ref={panel} role="dialog" aria-modal="true">
        <div className="cmdk__input">
          <IcSearch size={19} />
          <input
            ref={input}
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder={t('app.commandPlaceholder')}
            aria-label={t('app.commandTitle')}
          />
          <kbd className="kbd">esc</kbd>
        </div>

        <div className="cmdk__list" ref={list}>
          {flat.length === 0 && <div className="cmdk__empty">{t('app.commandNoResult')}</div>}
          {groups.map((g) => (
            <div key={g.key}>
              <div className="cmdk__group">{g.label}</div>
              {g.items.map((it) => {
                idx++
                const on = idx === cursor
                const myIdx = idx
                return (
                  <button
                    key={it.id}
                    className={`cmdk__item${on ? ' cmdk__item--on' : ''}`}
                    onMouseEnter={() => setCursor(myIdx)}
                    onClick={() => {
                      it.run()
                      onClose()
                    }}
                  >
                    <span className="cmdk__icon">{it.icon}</span>
                    <span className="ellip">{it.label}</span>
                    {it.hint && <span className="cmdk__hint">{it.hint}</span>}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      </div>
    </div>,
    document.body
  )
}
