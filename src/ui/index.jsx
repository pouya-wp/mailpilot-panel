/* ============================================================
   The primitive kit.

   Everything the pages are built from lives here, and every piece
   of it wears the same surface the original panel established:
   a lit glass face, a gradient ring for an edge (drawn by
   styles/surface.css, which these class names opt into), squircle
   corners where the platform supports them, and GSAP for anything
   that moves.

   Two house rules carried over from the original components:

   * `transform` belongs to whichever hook owns the motion. Nothing
     here sets it in CSS, so useTilt / usePress / useMagnetic can
     compose instead of fighting.
   * Direction comes from <html dir>. These components are written
     with logical properties, so none of them needs an RTL branch.
   ============================================================ */
import { cloneElement, forwardRef, useCallback, useEffect, useId, useLayoutEffect, useRef, useState } from 'react'
import { createPortal } from 'react-dom'
import { gsap, reduced, useGSAP } from '../anim/core'
import { usePress, useTilt } from '../anim/hooks'
import { useI18n } from '../i18n'
import { IcCheckC, IcChevron, IcChevronDown, IcCopy, IcSearch, IcX } from '../components/NavIcons'

const cx = (...a) => a.filter(Boolean).join(' ')

/* ============================================================
   useIndicator — the shared "lit thing that travels" behaviour.

   The segmented pill, the tab underline, the sidebar marker and the
   language switch all work the same way: one element is tweened to
   the bounding box of whichever child is active, so the selection
   SLIDES instead of blinking from one place to another.

   Measuring on state change alone is not enough. Collapsing the
   sidebar changes the width of everything to its inline-end over
   0.42s, and an indicator positioned from a stale rect simply stays
   where it was — which is exactly the "closing the sidebar breaks
   the panel next to it" bug. A ResizeObserver on the host re-runs
   the measurement for the whole of that transition, and covers
   window resizes and font swaps for free.
   ============================================================ */
function useIndicator(hostRef, selector, apply, deps) {
  const applyRef = useRef(apply)
  applyRef.current = apply

  /* Deliberately a plain layout effect and NOT useGSAP.

     useGSAP with a `scope` reverts every tween created inside it when its
     dependencies change — that is the right behaviour for entrance
     choreography, and exactly wrong here. The indicator's position IS its
     state: reverting it on each change snapped the bar back to x:0, so it
     spent its life chasing a target it was reset away from before it could
     arrive. Nothing here needs the context; a manual kill on unmount is
     enough, and the position must survive between renders. */
  useLayoutEffect(() => {
    const host = hostRef.current
    if (!host) return

    const measure = () => {
      const active = host.querySelector(selector)
      if (!active) return
      const hb = host.getBoundingClientRect()
      const ab = active.getBoundingClientRect()
      // rect maths, not offsetLeft: an ancestor may still carry a transform
      // from the page-transition timeline when this first runs
      /* Rect maths, deliberately — offsetTop/offsetLeft are NOT usable here.
         `offsetParent` is the nearest POSITIONED ancestor, and any element
         carrying a transform counts as one; the entrance timeline puts a
         transform on each sidebar group, so a nav row's offsetTop is measured
         from its own group rather than from the list. Rects are absolute and
         immune to that.

         scrollTop/Left are added back because an absolutely positioned
         indicator resolves against its container's padding box, which does not
         move when the container scrolls, while the rects above do. The host
         must therefore be the indicator's containing block — see the `top: 0`
         note on .side__marker. */
      applyRef.current(host, {
        x: ab.left - hb.left + host.scrollLeft,
        y: ab.top - hb.top + host.scrollTop,
        w: ab.width,
        h: ab.height,
      })
    }

    /* One measurement per frame, at most, and only when something moved.

       An earlier version kept a rolling deadline that every observer callback
       pushed further out. Anything on the page that resizes continuously —
       and a dashboard full of counters and entrance tweens always has
       something — kept re-opening that window, so the loop never closed and
       sat re-measuring forever. It starved the compositor badly enough that
       the rail's collapse froze mid-transition.

       This version cannot run away: each notification schedules a single
       rAF, and a pending one is reused rather than stacked. When the page
       goes quiet, so does this. */
    let raf = 0
    const schedule = () => {
      if (raf) return
      raf = requestAnimationFrame(() => {
        raf = 0
        measure()
      })
    }

    /* Measured synchronously here, THEN refined on the next frame.

       The synchronous pass is what makes this correct rather than merely
       usually-correct: requestAnimationFrame is throttled to a few frames per
       second — or stopped entirely — in a background tab, so an indicator that
       only ever positions itself from a rAF callback stays wherever it was
       when the tab lost focus, and is wrong the moment the reader comes back.
       The frame-later pass then catches anything that was still settling. */
    measure()
    schedule()

    /* the rail's collapse animates `--side-w` for 0.42s, so the host's width
       changes every frame — this keeps the indicator glued to its row for the
       whole transition, and covers window resizes and the webfont swap too */
    const ro = new ResizeObserver(schedule)
    ro.observe(host)

    /* the authoritative trigger: whichever child is marked active changed.
       React's dependency array only approximates this. */
    const mo = new MutationObserver(schedule)
    mo.observe(host, { attributes: true, subtree: true, attributeFilter: ['class', 'data-on'] })

    /* the collapse finishing is the last chance to be exactly right */
    const shell = host.closest('.ash')
    const onEnd = (e) => e.propertyName === '--side-w' && schedule()
    shell?.addEventListener('transitionend', onEnd)

    return () => {
      if (raf) cancelAnimationFrame(raf)
      ro.disconnect()
      mo.disconnect()
      shell?.removeEventListener('transitionend', onEnd)
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, deps)
}

/* ============================================================
   CARD — the base surface. Everything sits on one of these.
   `tilt` opts into the lean-toward-the-pointer behaviour; it is
   off by default because a page of forty tilting cards is noise.
   ============================================================ */
export function Card({ className, children, tilt = false, pad = true, as: Tag = 'div', ...rest }) {
  const ref = useTilt({ max: 3.4, lift: 3 })
  return (
    <Tag className={cx('card', 'ucard', pad && 'ucard--pad', className)} ref={tilt ? ref : undefined} {...rest}>
      {children}
    </Tag>
  )
}

/** Card header: title, optional sub, and a slot on the far end. */
export function CardHead({ title, sub, right, icon, className }) {
  return (
    <div className={cx('ucard__head', className)}>
      {icon && <span className="ucard__headIcon">{icon}</span>}
      <div className="ucard__headText">
        <h3 className="ucard__title">{title}</h3>
        {sub && <p className="ucard__sub">{sub}</p>}
      </div>
      {right && <div className="ucard__headRight">{right}</div>}
    </div>
  )
}

/* ============================================================
   BUTTON — one component, four weights.
   `primary` is the lit CTA from the original console, scaled down
   so it can sit in a toolbar; the sheen still runs across it once
   on hover rather than looping, which would read as a spinner.
   ============================================================ */
export function Button({
  variant = 'ghost',
  size = 'md',
  icon,
  iconEnd,
  loading = false,
  full = false,
  className,
  children,
  ...rest
}) {
  const ref = usePress({ to: variant === 'primary' ? 0.975 : 0.955 })
  return (
    <button
      ref={ref}
      className={cx('btn', `btn--${variant}`, `btn--${size}`, full && 'btn--full', loading && 'btn--loading', className)}
      {...rest}
    >
      {icon && <span className="btn__icon">{icon}</span>}
      {children && <span className="btn__label">{children}</span>}
      {iconEnd && <span className="btn__icon">{iconEnd}</span>}
      {loading && <span className="btn__spin" aria-hidden="true" />}
    </button>
  )
}

/** Square icon-only button — the toolbar workhorse. */
export function IconButton({ label, className, children, active = false, ...rest }) {
  const ref = usePress({ to: 0.9 })
  return (
    <button ref={ref} className={cx('iconbtn', active && 'iconbtn--on', className)} aria-label={label} title={label} {...rest}>
      {children}
    </button>
  )
}

/* ============================================================
   BADGE / PILL — status colour is carried by a `tone`, never by a
   bespoke class per status, so a new status is one map entry away.
   ============================================================ */
export function Badge({ tone = 'neutral', dot = false, size = 'md', className, children }) {
  return (
    <span className={cx('badge', `badge--${tone}`, size === 'sm' && 'badge--sm', className)}>
      {dot && <i className="badge__dot" />}
      {children}
    </span>
  )
}

/** Maps a domain status onto a badge tone in one place. */
export const STATUS_TONE = {
  active: 'good',
  running: 'good',
  sent: 'good',
  delivered: 'good',
  verified: 'good',
  connected: 'good',
  paid: 'good',
  winner: 'good',
  sending: 'live',
  indexing: 'live',
  scheduled: 'info',
  pending: 'info',
  draft: 'neutral',
  paused: 'warn',
  stopped: 'warn',
  due: 'warn',
  unverified: 'warn',
  failed: 'bad',
  bounced: 'bad',
  unsubscribed: 'bad',
  error: 'bad',
}

export function StatusBadge({ status, children }) {
  return (
    <Badge tone={STATUS_TONE[status] || 'neutral'} dot>
      {children}
    </Badge>
  )
}

/* ============================================================
   DELTA — the ±% chip next to a KPI. Green up / red down is a
   trap for negative-good metrics (bounce rate), so `invert` flips
   which direction reads as good without flipping the arrow.
   ============================================================ */
export function Delta({ value, invert = false, suffix = '%' }) {
  const { nf } = useI18n()
  const up = value >= 0
  const good = invert ? !up : up
  return (
    <span className={cx('delta', good ? 'delta--good' : 'delta--bad')}>
      <svg viewBox="0 0 24 24" className="delta__arrow" style={{ transform: up ? 'none' : 'scaleY(-1)' }}>
        <path d="M12 5l6 8h-4v6h-4v-6H6l6-8z" fill="currentColor" />
      </svg>
      {nf(Math.abs(value), { maximumFractionDigits: 1 })}
      {suffix}
    </span>
  )
}

/* ============================================================
   KPI TILE — the square stat card from the original panel, now
   parameterised. The figure counts up on first paint through the
   shared Num component so it lands with the page rather than
   snapping in ahead of it.
   ============================================================ */
export { default as Num } from '../anim/Num'

export function Kpi({ label, value, format, delta, deltaInvert, hint, icon, spark, tone, tilt = true }) {
  const ref = useTilt({ max: 4.5, lift: 4 })
  return (
    <div className={cx('card', 'kpi', spark && 'kpi--spark', tone && `kpi--${tone}`)} ref={tilt ? ref : undefined}>
      <div className="kpi__head">
        <span className="kpi__label">{label}</span>
        {icon && <span className="kpi__icon">{icon}</span>}
      </div>
      <div className="kpi__value">{value}</div>
      <div className="kpi__foot">
        {/* `!= null` on purpose: the API sends null for "no baseline to
            compare against", and JSON null is not undefined. */}
        {delta != null && <Delta value={delta} invert={deltaInvert} />}
        {hint && <span className="kpi__hint">{hint}</span>}
      </div>
      {spark && <div className="kpi__spark">{spark}</div>}
    </div>
  )
}

/* ============================================================
   FORM CONTROLS
   ============================================================ */
export function Field({ label, hint, error, required, children, className, wide }) {
  const auto = useId()
  /* An id the caller set explicitly WINS. This used to clobber it with the
     generated one, which quietly broke anything that needed a handle on the
     control — `document.getElementById`, a test, an external <label>. The
     generated id is a fallback, not a policy. */
  const id = children?.props?.id || auto
  return (
    <div className={cx('field2', wide && 'field2--wide', className)}>
      {label && (
        <label className="field2__label" htmlFor={id}>
          {label}
          {required && <span className="field2__req">*</span>}
        </label>
      )}
      {cloneElement(children, { id })}
      {error ? <span className="field2__error">{error}</span> : hint ? <span className="field2__hint">{hint}</span> : null}
    </div>
  )
}

/* forwardRef so a caller can focus it — the sign-in screen puts the caret in
   the first empty field, which needs a handle on the actual <input>. */
export const Input = forwardRef(function Input({ className, icon, ...rest }, ref) {
  return (
    <span className={cx('input', icon && 'input--icon', className)}>
      {icon && <span className="input__icon">{icon}</span>}
      <input className="input__el" ref={ref} {...rest} />
    </span>
  )
})

export function Textarea({ className, rows = 4, ...rest }) {
  return <textarea className={cx('input', 'input--area', className)} rows={rows} {...rest} />
}

export function SearchBox({ value, onChange, placeholder, className, onClear }) {
  const { t } = useI18n()
  return (
    <span className={cx('input', 'input--icon', 'input--search', className)}>
      <span className="input__icon">
        <IcSearch size={16} />
      </span>
      <input className="input__el" value={value} onChange={(e) => onChange(e.target.value)} placeholder={placeholder} />
      {value && (
        <button className="input__clear" onClick={() => (onClear ? onClear() : onChange(''))} aria-label={t('g.clear')}>
          <IcX size={13} />
        </button>
      )}
    </span>
  )
}

/** Native select behind our own chrome — the popup is the OS one, which is
    the right call for long lists and gets keyboard and mobile behaviour free. */
export function Select({ options, value, onChange, className, ...rest }) {
  return (
    <span className={cx('uselect', className)}>
      <select className="uselect__el" value={value} onChange={(e) => onChange(e.target.value)} {...rest}>
        {options.map((o) => (
          <option key={o.value ?? o} value={o.value ?? o}>
            {o.label ?? o}
          </option>
        ))}
      </select>
      <span className="uselect__caret">
        <IcChevronDown size={14} />
      </span>
    </span>
  )
}

/* Segmented control. The lit pill behind the active item is one element that
   travels, not a background swap per button — so the selection slides. */
export function Segmented({ options, value, onChange, className, size = 'md' }) {
  const box = useRef(null)

  useIndicator(
    box,
    '[data-on="1"]',
    (host, r) => {
      const pill = host.querySelector('.seg__pill')
      if (!pill) return
      gsap.to(pill, {
        x: r.x - 4,
        width: r.w,
        duration: reduced() ? 0 : 0.42,
        ease: 'snap',
        overwrite: 'auto',
      })
    },
    [value, options.length]
  )

  return (
    <div className={cx('seg', size === 'sm' && 'seg--sm', className)} ref={box} role="tablist">
      <span className="seg__pill" aria-hidden="true" />
      {options.map((o) => {
        const v = o.value ?? o
        return (
          <button
            key={v}
            role="tab"
            aria-selected={v === value}
            data-on={v === value ? '1' : '0'}
            className={cx('seg__btn', v === value && 'seg__btn--on')}
            onClick={() => onChange(v)}
          >
            {o.icon && <span className="seg__icon">{o.icon}</span>}
            {o.label ?? o}
          </button>
        )
      })}
    </div>
  )
}

/** Toggle switch. The knob travels with `--on`, which flips sign under RTL
    through the same custom property, so the switch reads correctly mirrored. */
export function Toggle({ checked, onChange, label, hint, id: idProp, disabled }) {
  const auto = useId()
  const id = idProp || auto
  return (
    <div className={cx('toggle', disabled && 'toggle--off')}>
      <button
        id={id}
        role="switch"
        aria-checked={checked}
        disabled={disabled}
        className={cx('toggle__track', checked && 'toggle__track--on')}
        onClick={() => !disabled && onChange(!checked)}
      >
        <span className="toggle__knob" />
      </button>
      {(label || hint) && (
        <label className="toggle__text" htmlFor={id}>
          {label && <span className="toggle__label">{label}</span>}
          {hint && <span className="toggle__hint">{hint}</span>}
        </label>
      )}
    </div>
  )
}

/** The boost slider from the original console, generalised.
    `--p` (0..100) drives fill width, thumb position and both glows, so one
    number can never disagree with itself. */
export function Slider({ value, min = 0, max = 100, step = 1, onChange, ticks, format }) {
  const pct = ((value - min) / (max - min)) * 100
  return (
    <div className="slider slider--ui" style={{ '--p': pct }}>
      {ticks && (
        <div className="slider__ticks">
          {ticks.map((tk, i) => (
            <span key={i} className={i / (ticks.length - 1) <= pct / 100 + 0.001 ? 'is-lit' : ''}>
              {tk}
            </span>
          ))}
        </div>
      )}
      <div className="slider__track">
        <span className="slider__fill" />
        <span className="slider__thumb" />
      </div>
      <input
        className="slider__input"
        type="range"
        min={min}
        max={max}
        step={step}
        value={value}
        onChange={(e) => onChange(Number(e.target.value))}
        aria-valuetext={format ? format(value) : String(value)}
      />
    </div>
  )
}

/* ============================================================
   TABS — underline rides between items for the same reason the
   segmented pill does.
   ============================================================ */
export function Tabs({ tabs, value, onChange, className }) {
  const box = useRef(null)

  useIndicator(
    box,
    '[data-on="1"]',
    (host, r) => {
      const bar = host.querySelector('.tabs__bar')
      if (!bar) return
      gsap.to(bar, {
        x: r.x,
        width: r.w,
        duration: reduced() ? 0 : 0.45,
        ease: 'snap',
        overwrite: 'auto',
      })
    },
    [value, tabs.length]
  )

  return (
    <div className={cx('tabs', className)} ref={box} role="tablist">
      {tabs.map((tb) => {
        const v = tb.value ?? tb
        return (
          <button
            key={v}
            role="tab"
            aria-selected={v === value}
            data-on={v === value ? '1' : '0'}
            className={cx('tabs__btn', v === value && 'tabs__btn--on')}
            onClick={() => onChange(v)}
          >
            {tb.label ?? tb}
            {tb.count !== undefined && <span className="tabs__count">{tb.count}</span>}
          </button>
        )
      })}
      <span className="tabs__bar" aria-hidden="true" />
    </div>
  )
}

/* ============================================================
   TABLE — a thin wrapper rather than a data grid. The pages here
   have small, hand-shaped tables; a generic grid would cost more
   than it saved and would fight the surface treatment.
   ============================================================ */
export function Table({ columns, rows, keyFn, onRowClick, empty, selectable, selected, onSelect, className }) {
  const { t } = useI18n()
  const body = useRef(null)

  /* Rows arrive in a short stagger the first time a page mounts. It is the
     only motion in a table — sorting or filtering must NOT re-run it, or a
     search box turns into a slot machine, so this keys off the page mount. */
  useGSAP(
    () => {
      if (reduced() || !body.current) return
      gsap.from(body.current.querySelectorAll('.utable__row'), {
        opacity: 0,
        y: 10,
        duration: 0.5,
        stagger: 0.028,
        ease: 'glide',
        overwrite: true,
      })
    },
    { scope: body }
  )

  const allOn = selectable && rows.length > 0 && selected?.length === rows.length

  if (!rows.length) {
    return <EmptyState title={empty?.title || t('g.empty')} hint={empty?.hint || t('g.emptyHint')} icon={empty?.icon} action={empty?.action} />
  }

  return (
    <div className={cx('utable', className)}>
      <div className="utable__head" style={{ gridTemplateColumns: gridCols(columns, selectable) }}>
        {selectable && (
          <span className="utable__cell utable__cell--check">
            <Checkbox checked={allOn} onChange={() => onSelect(allOn ? [] : rows.map(keyFn))} />
          </span>
        )}
        {columns.map((c) => (
          <span key={c.key} className={cx('utable__cell', c.align && `utable__cell--${c.align}`)}>
            {c.title}
          </span>
        ))}
      </div>

      <div className="utable__body" ref={body}>
        {rows.map((row) => {
          const id = keyFn(row)
          const on = selected?.includes(id)
          return (
            <div
              key={id}
              className={cx('utable__row', on && 'utable__row--on', onRowClick && 'utable__row--click')}
              style={{ gridTemplateColumns: gridCols(columns, selectable) }}
              onClick={onRowClick ? () => onRowClick(row) : undefined}
            >
              {selectable && (
                <span className="utable__cell utable__cell--check" onClick={(e) => e.stopPropagation()}>
                  <Checkbox
                    checked={!!on}
                    onChange={() => onSelect(on ? selected.filter((s) => s !== id) : [...(selected || []), id])}
                  />
                </span>
              )}
              {columns.map((c) => (
                <span key={c.key} className={cx('utable__cell', c.align && `utable__cell--${c.align}`)}>
                  {c.render ? c.render(row) : row[c.key]}
                </span>
              ))}
            </div>
          )
        })}
      </div>
    </div>
  )
}

const gridCols = (columns, selectable) =>
  `${selectable ? '3.4rem ' : ''}${columns.map((c) => c.width || 'minmax(0,1fr)').join(' ')}`

export function Checkbox({ checked, onChange, label }) {
  return (
    <button
      role="checkbox"
      aria-checked={checked}
      className={cx('checkbox', checked && 'checkbox--on')}
      onClick={() => onChange(!checked)}
    >
      <span className="checkbox__box">
        <svg viewBox="0 0 24 24" className="checkbox__tick">
          <path d="M5 12.5l4.5 4.5L19 7" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round" />
        </svg>
      </span>
      {label && <span className="checkbox__label">{label}</span>}
    </button>
  )
}

export function Pagination({ page, pages, onChange, total }) {
  const { t, nf } = useI18n()
  const { rtl } = useI18n()
  if (pages <= 1) return null
  return (
    <div className="pager">
      <span className="pager__count">
        {nf(total)} {t('g.rows')}
      </span>
      <div className="pager__nav">
        <IconButton label={t('g.back')} disabled={page <= 1} onClick={() => onChange(page - 1)}>
          <IcChevron size={15} dir="start" flip={rtl} />
        </IconButton>
        <span className="pager__page">
          {nf(page)} {t('g.of')} {nf(pages)}
        </span>
        <IconButton label={t('g.next')} disabled={page >= pages} onClick={() => onChange(page + 1)}>
          <IcChevron size={15} dir="end" flip={rtl} />
        </IconButton>
      </div>
    </div>
  )
}

/* ============================================================
   PROGRESS + METERS
   ============================================================ */
export function Progress({ value, max = 100, tone = 'blue', label, right, height }) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100))
  const bar = useRef(null)
  useGSAP(() => {
    gsap.fromTo(bar.current, { scaleX: 0 }, { scaleX: 1, duration: reduced() ? 0 : 0.9, ease: 'glide' })
  }, [])
  return (
    <div className="prog">
      {(label || right) && (
        <div className="prog__top">
          <span className="prog__label">{label}</span>
          <span className="prog__right">{right}</span>
        </div>
      )}
      <div className="prog__track" style={height ? { height } : undefined}>
        <span className={cx('prog__fill', `prog__fill--${tone}`)} ref={bar} style={{ width: `${pct}%` }} />
      </div>
    </div>
  )
}

/** The circular health gauge. Stroke is drawn on mount rather than snapping
    to its value, which is what makes it read as a measurement. */
export function Gauge({ value, max = 100, size = 120, label, sub, caption, tone = 'blue' }) {
  const ring = useRef(null)
  const r = 42
  const c = 2 * Math.PI * r
  const pct = Math.max(0, Math.min(1, value / max))
  // the halo has to match the arc, or a green gauge wears a blue glow
  const glow = TONE_GLOW[tone] || TONE_GLOW.blue

  useGSAP(() => {
    gsap.fromTo(
      ring.current,
      { strokeDashoffset: c },
      { strokeDashoffset: c * (1 - pct), duration: reduced() ? 0 : 1.4, ease: 'glide', delay: 0.15 }
    )
  }, [pct, c])

  return (
    <div className="gauge" style={{ width: `${size / 10}rem`, '--glow-c': glow }}>
      <div className="gauge__ring-box">
      <svg viewBox="0 0 100 100" className="gauge__svg">
        <defs>
          <linearGradient id={`gg-${tone}`} x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor={tone === 'good' ? '#8fd3a8' : tone === 'warn' ? '#e2b872' : '#cfe1f2'} />
            <stop offset="100%" stopColor={tone === 'good' ? '#3f8f66' : tone === 'warn' ? '#a8762f' : '#3f6ca9'} />
          </linearGradient>
        </defs>
        <circle cx="50" cy="50" r={r} className="gauge__track" />
        <circle
          cx="50"
          cy="50"
          r={r}
          ref={ring}
          className="gauge__ring"
          stroke={`url(#gg-${tone})`}
          strokeDasharray={c}
          strokeDashoffset={c}
        />
      </svg>
      <div className="gauge__center">
        <span className="gauge__value">{label}</span>
        {sub && <span className="gauge__sub">{sub}</span>}
      </div>
      </div>
      {caption && <span className="gauge__caption">{caption}</span>}
    </div>
  )
}

/* Halo colours, keyed by tone. Exported because the radial charts need the
   same mapping — a glow that does not match the stroke it belongs to is the
   single fastest way to make a dashboard look unfinished. */
export const TONE_GLOW = {
  blue: 'rgba(150, 195, 232, 0.4)',
  good: 'rgba(127, 199, 155, 0.4)',
  warn: 'rgba(224, 180, 115, 0.4)',
  bad: 'rgba(224, 139, 139, 0.4)',
  violet: 'rgba(169, 159, 224, 0.4)',
}

/* ============================================================
   AVATAR — initials on a deterministic tint, so the same person is
   the same colour on every page without storing one.
   ============================================================ */
const TINTS = [
  'linear-gradient(140deg,#8fb4d6,#33547a)',
  'linear-gradient(140deg,#a08fd6,#43357a)',
  'linear-gradient(140deg,#8fd6c4,#2f6f63)',
  'linear-gradient(140deg,#d6b98f,#7a5a33)',
  'linear-gradient(140deg,#d68f9f,#7a3346)',
  'linear-gradient(140deg,#9fd68f,#4a7a33)',
]
export const tintFor = (seed = '') => {
  let h = 0
  for (let i = 0; i < seed.length; i++) h = (h * 31 + seed.charCodeAt(i)) >>> 0
  return TINTS[h % TINTS.length]
}

export function Avatar({ name = '', src, size = 34, emoji, tint, ring = false }) {
  const initials = name
    .split(/\s+/)
    .filter(Boolean)
    .slice(0, 2)
    .map((w) => w[0])
    .join('')
    .toUpperCase()
  return (
    <span
      className={cx('uavatar', ring && 'uavatar--ring')}
      style={{ width: `${size / 10}rem`, height: `${size / 10}rem`, background: tint || tintFor(name), fontSize: `${size / 26}rem` }}
      title={name}
    >
      {src ? <img src={src} alt="" /> : emoji || initials}
    </span>
  )
}

export function AvatarStack({ people, max = 4, size = 28 }) {
  const shown = people.slice(0, max)
  const rest = people.length - shown.length
  return (
    <span className="stack">
      {shown.map((p, i) => (
        <span key={p.id ?? i} className="stack__item">
          <Avatar name={p.name} emoji={p.emoji} size={size} ring />
        </span>
      ))}
      {rest > 0 && (
        <span className="stack__item stack__more" style={{ width: `${size / 10}rem`, height: `${size / 10}rem` }}>
          +{rest}
        </span>
      )}
    </span>
  )
}

/* ============================================================
   EMPTY STATE
   ============================================================ */
export function EmptyState({ title, hint, icon, action }) {
  const box = useRef(null)
  useGSAP(
    () => {
      if (reduced()) return
      gsap.from(box.current.children, { opacity: 0, y: 14, duration: 0.6, stagger: 0.06, ease: 'glide' })
    },
    { scope: box }
  )
  return (
    <div className="empty" ref={box}>
      {icon && <span className="empty__icon">{icon}</span>}
      <h4 className="empty__title">{title}</h4>
      {hint && <p className="empty__hint">{hint}</p>}
      {action && <div className="empty__action">{action}</div>}
    </div>
  )
}

/* ============================================================
   MODAL + DRAWER
   Both portal to <body> so no card's `overflow: hidden` can clip
   them, and both trap Escape. The drawer opens from the inline-end
   edge, which is the right edge in English and the left in Persian
   — one `inset-inline-end: 0` covers both.
   ============================================================ */
function useEscape(on, close) {
  useEffect(() => {
    if (!on) return
    const key = (e) => e.key === 'Escape' && close()
    document.addEventListener('keydown', key)
    return () => document.removeEventListener('keydown', key)
  }, [on, close])
}

export function Modal({ open, onClose, title, sub, children, footer, width = 60 }) {
  const scrim = useRef(null)
  const panel = useRef(null)
  useEscape(open, onClose)

  useGSAP(
    () => {
      if (!open || !panel.current) return
      if (reduced()) return
      gsap
        .timeline()
        .fromTo(scrim.current, { opacity: 0 }, { opacity: 1, duration: 0.28, ease: 'swift' })
        .fromTo(panel.current, { opacity: 0, y: 26, scale: 0.97 }, { opacity: 1, y: 0, scale: 1, duration: 0.5, ease: 'snap' }, 0.04)
    },
    { dependencies: [open] }
  )

  if (!open) return null
  return createPortal(
    <div className="modal">
      <div className="modal__scrim" ref={scrim} onClick={onClose} />
      <div className="modal__panel card" ref={panel} style={{ width: `${width}rem` }} role="dialog" aria-modal="true">
        <div className="modal__head">
          <div>
            <h3 className="modal__title">{title}</h3>
            {sub && <p className="modal__sub">{sub}</p>}
          </div>
          <IconButton label="close" onClick={onClose}>
            <IcX size={15} />
          </IconButton>
        </div>
        <div className="modal__body">{children}</div>
        {footer && <div className="modal__foot">{footer}</div>}
      </div>
    </div>,
    document.body
  )
}

export function Drawer({ open, onClose, title, sub, children, footer, width = 56 }) {
  const scrim = useRef(null)
  const panel = useRef(null)
  const { rtl } = useI18n()
  useEscape(open, onClose)

  useGSAP(
    () => {
      if (!open || !panel.current || reduced()) return
      gsap
        .timeline()
        .fromTo(scrim.current, { opacity: 0 }, { opacity: 1, duration: 0.3, ease: 'swift' })
        // slides in from whichever edge is "end" in the active direction
        .fromTo(panel.current, { xPercent: rtl ? -100 : 100 }, { xPercent: 0, duration: 0.55, ease: 'glide' }, 0)
        .from(panel.current.querySelectorAll('.drawer__stagger > *'), {
          opacity: 0,
          y: 16,
          duration: 0.5,
          stagger: 0.045,
        }, 0.18)
    },
    { dependencies: [open, rtl] }
  )

  if (!open) return null
  return createPortal(
    <div className="drawer">
      <div className="drawer__scrim" ref={scrim} onClick={onClose} />
      <aside className="drawer__panel" ref={panel} style={{ width: `${width}rem` }} role="dialog" aria-modal="true">
        <header className="drawer__head">
          <div>
            <h3 className="drawer__title">{title}</h3>
            {sub && <p className="drawer__sub">{sub}</p>}
          </div>
          <IconButton label="close" onClick={onClose}>
            <IcX size={15} />
          </IconButton>
        </header>
        <div className="drawer__body drawer__stagger">{children}</div>
        {footer && <div className="drawer__foot">{footer}</div>}
      </aside>
    </div>,
    document.body
  )
}

/* ============================================================
   MENU — a small popover anchored to its trigger. Closes on any
   outside pointerdown and on Escape, like the original Selector.
   ============================================================ */
export function Menu({ trigger, items, align = 'end', width }) {
  const [open, setOpen] = useState(false)
  const box = useRef(null)
  const panel = useRef(null)

  useEffect(() => {
    if (!open) return
    const away = (e) => !box.current?.contains(e.target) && setOpen(false)
    const key = (e) => e.key === 'Escape' && setOpen(false)
    document.addEventListener('mousedown', away)
    document.addEventListener('keydown', key)
    return () => {
      document.removeEventListener('mousedown', away)
      document.removeEventListener('keydown', key)
    }
  }, [open])

  useGSAP(
    () => {
      const el = panel.current
      if (!el) return
      if (reduced()) return gsap.set(el, { autoAlpha: open ? 1 : 0 })
      if (open) {
        gsap
          .timeline()
          .fromTo(el, { autoAlpha: 0, y: -8 }, { autoAlpha: 1, y: 0, duration: 0.26, ease: 'swift' })
          .fromTo(el.children, { opacity: 0, y: -6 }, { opacity: 1, y: 0, duration: 0.24, stagger: 0.03 }, 0.03)
      } else {
        gsap.to(el, { autoAlpha: 0, y: -6, duration: 0.16, ease: 'power2.in', overwrite: 'auto' })
      }
    },
    { dependencies: [open], scope: box }
  )

  return (
    <div className={cx('menu', open && 'menu--open')} ref={box}>
      <span onClick={() => setOpen((o) => !o)}>{trigger}</span>
      <div
        className={cx('menu__panel', `menu__panel--${align}`)}
        ref={panel}
        style={width ? { minWidth: `${width}rem` } : undefined}
        aria-hidden={!open}
      >
        {items.map((it, i) =>
          it.divider ? (
            <span key={`d${i}`} className="menu__divider" />
          ) : (
            <button
              key={it.id ?? it.label}
              className={cx('menu__item', it.tone && `menu__item--${it.tone}`, it.active && 'menu__item--on')}
              tabIndex={open ? 0 : -1}
              onClick={() => {
                it.onClick?.()
                setOpen(false)
              }}
            >
              {it.icon && <span className="menu__icon">{it.icon}</span>}
              <span className="menu__label">{it.label}</span>
              {it.active && (
                <span className="menu__check">
                  <IcCheckC size={14} />
                </span>
              )}
              {it.right && <span className="menu__right">{it.right}</span>}
            </button>
          )
        )}
      </div>
    </div>
  )
}

/* ============================================================
   TOOLTIP — CSS-driven, no portal. Deliberately simple: these
   never carry interactive content, so they do not need focus
   management or collision detection.
   ============================================================ */
export function Tooltip({ label, children, side = 'top' }) {
  return (
    <span className={cx('tip', `tip--${side}`)} data-tip={label}>
      {children}
    </span>
  )
}

/* ============================================================
   MISC LAYOUT HELPERS
   ============================================================ */
export function Row({ gap = 1.2, wrap = false, align = 'center', justify, className, children, style }) {
  return (
    <div
      className={cx('row', wrap && 'row--wrap', className)}
      style={{ gap: `${gap}rem`, alignItems: align, justifyContent: justify, ...style }}
    >
      {children}
    </div>
  )
}

export function Grid({ cols = 2, gap = 1.5, min, className, children, style }) {
  return (
    <div
      className={cx('ugrid', className)}
      style={{
        gap: `${gap}rem`,
        gridTemplateColumns: min ? `repeat(auto-fit, minmax(${min}rem, 1fr))` : `repeat(${cols}, minmax(0,1fr))`,
        ...style,
      }}
    >
      {children}
    </div>
  )
}

export function Divider({ label }) {
  return label ? (
    <div className="hr hr--label">
      <span>{label}</span>
    </div>
  ) : (
    <div className="hr" />
  )
}

/** The stagger wrapper every page body uses, so a new screen assembles in
    reading order instead of appearing all at once. */
export function Stagger({ children, className, delay = 0, y = 18 }) {
  const box = useRef(null)
  useGSAP(
    () => {
      if (reduced() || !box.current) return
      gsap.from(box.current.children, {
        opacity: 0,
        y,
        duration: 0.7,
        stagger: 0.06,
        delay,
        ease: 'glide',
        overwrite: true,
        clearProps: 'opacity,transform',
      })
    },
    { scope: box }
  )
  return (
    <div className={className} ref={box}>
      {children}
    </div>
  )
}

/** Copy-to-clipboard chip used by the DNS records and API keys screens. */
export function CopyField({ value, mono = true }) {
  const { t } = useI18n()
  const [hit, setHit] = useState(false)
  return (
    <button
      className={cx('copyf', mono && 'copyf--mono')}
      onClick={() => {
        navigator.clipboard?.writeText(value)
        setHit(true)
        setTimeout(() => setHit(false), 1400)
      }}
      title={t('g.copy')}
    >
      <span className="copyf__val">{value}</span>
      <span className="copyf__icon">{hit ? <IcCheckC size={14} /> : <IcCopy size={14} />}</span>
    </button>
  )
}

export { cx, useCallback, useIndicator }
