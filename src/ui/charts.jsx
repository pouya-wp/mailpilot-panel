/* ============================================================
   Charts, drawn by hand in SVG.

   No charting library: the panel's whole identity is a specific
   quality of light — the glow filter on a stroke, the bloom the
   line throws onto the glass behind it, the read-head that runs
   the curve — and every library would have to be fought to give
   that back. These are small enough to own.

   Shared conventions:
   * geometry is authored in a 0..100 viewBox and stretched, so a
     chart is laid out by its container, not by a pixel width;
   * every series enters with DrawSVG on the stroke, which is the
     same reveal the original level card used;
   * nothing here reads `dir`. An RTL chart still runs time left to
     right — that is the convention for time series in Persian
     dashboards too — but axis labels flip with the flexbox that
     holds them, which is what actually needs mirroring.
   ============================================================ */
import { useMemo, useRef, useState } from 'react'
import { gsap, introStarted, reduced, useGSAP } from '../anim/core'
import { useI18n } from '../i18n'

let uid = 0
const nextId = () => `ch${++uid}`

/* Catmull-Rom to cubic Bézier. A polyline through noisy daily data reads as
   jagged and draws the eye to the sampling rather than the trend; this keeps
   the curve through every real point while smoothing the joins. */
function spline(points, tension = 0.42) {
  if (points.length < 2) return ''
  let d = `M${points[0][0]},${points[0][1]}`
  for (let i = 0; i < points.length - 1; i++) {
    const p0 = points[i - 1] || points[i]
    const p1 = points[i]
    const p2 = points[i + 1]
    const p3 = points[i + 2] || p2
    const c1x = p1[0] + ((p2[0] - p0[0]) / 6) * tension * 2
    const c1y = p1[1] + ((p2[1] - p0[1]) / 6) * tension * 2
    const c2x = p2[0] - ((p3[0] - p1[0]) / 6) * tension * 2
    const c2y = p2[1] - ((p3[1] - p1[1]) / 6) * tension * 2
    d += ` C${c1x},${c1y} ${c2x},${c2y} ${p2[0]},${p2[1]}`
  }
  return d
}

/** Up to `max` evenly spaced ticks, always including the first and the last. */
function axisTicks(labels, max = 6) {
  if (labels.length <= max) return labels.map((label, i) => ({ label, i }))
  const step = (labels.length - 1) / (max - 1)
  const out = []
  for (let k = 0; k < max; k++) {
    const i = Math.round(k * step)
    if (!out.length || out[out.length - 1].i !== i) out.push({ label: labels[i], i })
  }
  return out
}

const scale = (values, h, pad = 12) => {
  const max = Math.max(...values, 1)
  const min = Math.min(...values, 0)
  const span = max - min || 1
  return values.map((v) => h - pad - ((v - min) / span) * (h - pad * 2))
}

/* ============================================================
   AREA / LINE CHART — the dashboard's main pulse.
   Up to three series; the first one carries the glow and the fill,
   the others are drawn thinner so the primary reading stays clear.
   ============================================================ */
export function AreaChart({ series, labels = [], height = 220, showGrid = true, fill = true, formatValue }) {
  const id = useMemo(nextId, [])
  const box = useRef(null)
  const [hover, setHover] = useState(null)
  const { nf } = useI18n()

  const W = 100
  const H = 100
  /* Data arrives asynchronously, so "no points yet" is a normal state rather
     than a bug. Without this guard `spline([])` returns an empty string and
     the browser rejects the path outright — the console fills with "Expected
     moveto" and the card renders blank with no explanation. */
  const usable = (series || []).filter((s) => Array.isArray(s.data) && s.data.length > 1)
  const first = usable[0]?.data || []
  const step = first.length > 1 ? W / (first.length - 1) : W

  /* All series share one scale, or a small second series would draw itself
     across the same band as the big one and imply a comparison that is false */
  const flat = usable.flatMap((s) => s.data)
  const maxAll = Math.max(...flat, 1)

  const paths = usable.map((s) => {
    const ys = s.data.map((v) => H - 10 - (v / maxAll) * (H - 22))
    const pts = s.data.map((_, i) => [i * step, ys[i]])
    return { ...s, d: spline(pts), pts }
  })

  useGSAP(
    () => {
      if (reduced() || !box.current) return
      const lines = box.current.querySelectorAll('.ch__line')
      const areas = box.current.querySelectorAll('.ch__area')
      let tl = null
      let live = true
      introStarted.then(() => {
        if (!live) return
        tl = gsap.timeline()
        tl.fromTo(lines, { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.5, stagger: 0.12, ease: 'glide' })
          .fromTo(areas, { opacity: 0 }, { opacity: 1, duration: 0.9 }, 0.5)
      })
      return () => {
        live = false
        tl?.kill()
      }
    },
    { dependencies: [series.map((s) => s.data.join()).join('|')], scope: box }
  )

  if (!usable.length) {
    return <div className="ch ch--empty" style={{ height: `${height / 10}rem` }} aria-hidden="true" />
  }

  return (
    <div className="ch" ref={box} style={{ height: `${height / 10}rem` }}>
      {/* The plot is its own positioned box: the markers and the read-out
          are placed in per-cent of the VIEWBOX, so the element they are
          positioned against has to be the one the viewBox fills. */}
      <div className="ch__plot">
      <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="ch__svg">
        <defs>
          {paths.map((s, i) => (
            <linearGradient key={s.id ?? i} id={`${id}-fill-${i}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={s.color || '#9cc3e4'} stopOpacity={i === 0 ? 0.28 : 0.12} />
              <stop offset="100%" stopColor={s.color || '#9cc3e4'} stopOpacity="0" />
            </linearGradient>
          ))}
          {/* The blur is in USER units, and this viewBox is stretched wide —
              so a deviation that looks right vertically blooms enormously
              across. Kept small; the line reads lit, not blown out. */}
          <filter id={`${id}-glow`} x="-20%" y="-60%" width="140%" height="260%">
            <feGaussianBlur stdDeviation="0.7" result="b" />
            <feMerge>
              <feMergeNode in="b" />
              <feMergeNode in="SourceGraphic" />
            </feMerge>
          </filter>
        </defs>

        {showGrid &&
          [0.25, 0.5, 0.75].map((g) => (
            <line key={g} x1="0" x2={W} y1={H * g} y2={H * g} className="ch__grid" vectorEffect="non-scaling-stroke" />
          ))}

        {/* Only the PRIMARY series is filled. Three stacked translucent
            washes turned into one muddy blanket that hid the very shape the
            lines were there to show — and a fill under a secondary series
            implies an area comparison that these numbers do not support. */}
        {fill && paths[0] && (
          <path className="ch__area" d={`${paths[0].d} L${W},${H} L0,${H} Z`} fill={`url(#${id}-fill-0)`} />
        )}

        {paths.map((s, i) => (
          <path
            key={`l${i}`}
            className="ch__line"
            d={s.d}
            fill="none"
            stroke={s.color || '#cfe1f2'}
            strokeWidth={i === 0 ? 2.2 : 1.6}
            strokeOpacity={i === 0 ? 1 : 0.85}
            strokeDasharray={s.dashed ? '4 3' : undefined}
            vectorEffect="non-scaling-stroke"
            filter={i === 0 ? `url(#${id}-glow)` : undefined}
          />
        ))}

        {/* one transparent band per sample: the hover target has to be the
            full column height, not the 1px the line occupies there */}
        {first.map((_, i) => (
          <rect
            key={`h${i}`}
            x={i * step - step / 2}
            y="0"
            width={step}
            height={H}
            fill="transparent"
            onMouseEnter={() => setHover(i)}
            onMouseLeave={() => setHover(null)}
          />
        ))}

        {hover !== null && (
          <line x1={hover * step} x2={hover * step} y1="0" y2={H} className="ch__cursor" vectorEffect="non-scaling-stroke" />
        )}
      </svg>

      {/* The marker is an HTML dot, not an SVG <circle>. This viewBox is drawn
          with preserveAspectRatio="none", so every circle in it renders as a
          wide flat ellipse — that is what the scattered pills across the chart
          were. Strokes escape it through vector-effect; shapes cannot. An
          absolutely positioned div is immune to the stretch. */}
      {hover !== null &&
        paths.map((s, i) => (
          <span
            key={`m${i}`}
            className="ch__marker"
            style={{
              // physical: the series runs left-to-right in both directions
              left: `${(s.pts[hover][0] / W) * 100}%`,
              top: `${(s.pts[hover][1] / H) * 100}%`,
              background: s.color || '#cfe1f2',
              zIndex: paths.length - i,
            }}
          />
        ))}

      {hover !== null && (
        <div
          className="ch__tip"
          style={{ left: `${(hover * step) / W * 100}%`, '--side': hover / (first.length - 1) > 0.5 ? -1 : 0 }}
        >
          <span className="ch__tipLabel">{labels[hover]}</span>
          {series.map((s, i) => (
            <span key={i} className="ch__tipRow">
              <i style={{ background: s.color || '#cfe1f2' }} />
              {s.name}
              <b>{formatValue ? formatValue(s.data[hover]) : nf(s.data[hover])}</b>
            </span>
          ))}
        </div>
      )}

      </div>

      {/* Only a handful of ticks are printed. A 30-day series has 30 labels and
          `white-space: nowrap` on each of them; laying all of them out is what
          made the page scroll sideways on a phone, because flex will not shrink
          a nowrap item below its text. Six evenly spaced ticks give the axis its
          scale, and the exact date for any sample is in the hover read-out. */}
      {labels.length > 0 && (
        <div className="ch__axis">
          {axisTicks(labels, 6).map(({ label, i }) => (
            <span key={i} className={i === hover ? 'is-on' : ''}>
              {label}
            </span>
          ))}
        </div>
      )}

      {usable.length > 1 && (
        <div className="ch__legend">
          {usable.map((s, i) => (
            <span key={i}>
              <i style={{ background: s.color || '#cfe1f2' }} />
              {s.name}
            </span>
          ))}
        </div>
      )}
    </div>
  )
}

/* ============================================================
   SPARKLINE — the tiny trace inside a KPI tile. No axes, no
   interaction; its only job is the shape of the last two weeks.
   ============================================================ */
export function Sparkline({ data, color = '#9dc0dd', height = 40, fill = true }) {
  const id = useMemo(nextId, [])
  const ref = useRef(null)
  const W = 100
  const H = 34
  const points = Array.isArray(data) ? data : []
  const max = Math.max(...points, 1)
  const min = Math.min(...points, 0)
  const span = max - min || 1
  const pts = points.map((v, i) => [(i / (points.length - 1)) * W, H - 3 - ((v - min) / span) * (H - 8)])
  const d = spline(pts)

  useGSAP(
    () => {
      if (reduced() || !ref.current) return
      let live = true
      let tw = null
      introStarted.then(() => {
        if (!live) return
        tw = gsap.fromTo(ref.current, { drawSVG: '0%' }, { drawSVG: '100%', duration: 1.2, ease: 'glide' })
      })
      return () => {
        live = false
        tw?.kill()
      }
    },
    { dependencies: [points.join()] }
  )

  if (points.length < 2) return null

  return (
    <svg viewBox={`0 0 ${W} ${H}`} preserveAspectRatio="none" className="spark" style={{ height: `${height / 10}rem` }}>
      <defs>
        <linearGradient id={`${id}-sf`} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%" stopColor={color} stopOpacity="0.3" />
          <stop offset="100%" stopColor={color} stopOpacity="0" />
        </linearGradient>
      </defs>
      {fill && <path d={`${d} L${W},${H} L0,${H} Z`} fill={`url(#${id}-sf)`} />}
      <path ref={ref} d={d} fill="none" stroke={color} strokeWidth="1.8" vectorEffect="non-scaling-stroke" strokeLinecap="round" />
    </svg>
  )
}

/* ============================================================
   BARS — horizontal, because the labels are campaign and segment
   names. Vertical bars would either truncate them or rotate them.
   ============================================================ */
export function BarList({ items, format, tone = 'blue', max: maxProp }) {
  const box = useRef(null)
  const { nf } = useI18n()
  const rows = Array.isArray(items) ? items : []
  const max = maxProp ?? Math.max(...rows.map((i) => i.value), 1)

  useGSAP(
    () => {
      if (reduced() || !box.current) return
      gsap.from(box.current.querySelectorAll('.barl__fill'), {
        scaleX: 0,
        transformOrigin: 'inset-inline-start center',
        duration: 1,
        stagger: 0.07,
        ease: 'glide',
      })
    },
    { dependencies: [rows.map((i) => i.value).join()], scope: box }
  )

  return (
    <div className="barl" ref={box}>
      {rows.map((it) => (
        <div className="barl__row" key={it.id ?? it.label}>
          <div className="barl__top">
            <span className="barl__label">
              {it.icon && <i className="barl__ico">{it.icon}</i>}
              {it.label}
            </span>
            <span className="barl__value">{format ? format(it.value) : nf(it.value)}</span>
          </div>
          <div className="barl__track">
            <span
              className={`barl__fill barl__fill--${it.tone || tone}`}
              style={{ width: `${(it.value / max) * 100}%` }}
            />
          </div>
        </div>
      ))}
    </div>
  )
}

/* ============================================================
   DONUT — device split, plan usage. Segments are drawn as stroked
   arcs on one circle so the gaps stay even at any ratio.
   ============================================================ */
export function Donut({ data, size = 150, thickness = 13, center, sub }) {
  const ref = useRef(null)
  const r = 42
  const c = 2 * Math.PI * r
  const slices = Array.isArray(data) ? data : []
  const total = slices.reduce((s, d) => s + d.value, 0) || 1

  let acc = 0
  const arcs = slices.map((d) => {
    const len = (d.value / total) * c
    const arc = { ...d, len, offset: -acc }
    acc += len
    return arc
  })

  useGSAP(
    () => {
      if (reduced() || !ref.current) return
      gsap.from(ref.current.querySelectorAll('.donut__arc'), {
        strokeDasharray: `0 ${c}`,
        duration: 1.1,
        stagger: 0.09,
        ease: 'glide',
      })
    },
    { dependencies: [slices.map((d) => d.value).join()] }
  )

  return (
    <div className="donut" ref={ref} style={{ width: `${size / 10}rem` }}>
      <svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} className="donut__track" strokeWidth={thickness} />
        {arcs.map((a, i) => (
          <circle
            key={i}
            cx="50"
            cy="50"
            r={r}
            className="donut__arc"
            stroke={a.color}
            strokeWidth={thickness}
            strokeDasharray={`${Math.max(a.len - 1.6, 0)} ${c}`}
            strokeDashoffset={a.offset}
            strokeLinecap="round"
          />
        ))}
      </svg>
      {(center || sub) && (
        <div className="donut__center">
          <span className="donut__value">{center}</span>
          {sub && <span className="donut__sub">{sub}</span>}
        </div>
      )}
    </div>
  )
}

/* ============================================================
   FUNNEL — sent → delivered → opened → clicked → converted.
   Each stage is a trapezoid so the drop between stages is a shape,
   not a number you have to subtract yourself.
   ============================================================ */
export function Funnel({ stages, format }) {
  const box = useRef(null)
  const { nf, pct } = useI18n()
  const steps = Array.isArray(stages) ? stages : []
  const top = steps[0]?.value || 1

  useGSAP(
    () => {
      if (reduced() || !box.current) return
      gsap.from(box.current.querySelectorAll('.fun__row'), {
        opacity: 0,
        x: 24,
        duration: 0.6,
        stagger: 0.08,
        ease: 'glide',
      })
    },
    { dependencies: [steps.map((s) => s.value).join()], scope: box }
  )

  return (
    <div className="fun" ref={box}>
      {steps.map((s, i) => {
        const w = (s.value / top) * 100
        const prev = i === 0 ? s.value : steps[i - 1].value
        const drop = i === 0 ? null : ((prev - s.value) / prev) * 100
        return (
          <div className="fun__row" key={s.key}>
            <div className="fun__meta">
              <span className="fun__label">{s.label}</span>
              <span className="fun__value">{format ? format(s.value) : nf(s.value)}</span>
            </div>
            <div className="fun__barbox">
              <span className="fun__bar" style={{ width: `${w}%`, background: s.color }} />
              <span className="fun__pct">{pct((s.value / top) * 100, 1)}</span>
              {drop !== null && drop > 0.05 && <span className="fun__drop">−{pct(drop, 1)}</span>}
            </div>
          </div>
        )
      })}
    </div>
  )
}

/* ============================================================
   HEATMAP — weekday × hour open rate. The cell's alpha is the
   value, which is the only encoding that survives 168 cells in a
   card this size; the top cell gets a ring so the answer to
   "when should I send?" is findable without reading them all.
   ============================================================ */
export function Heatmap({ rows, cols, values, rowLabels, colLabels, onPick, format }) {
  const box = useRef(null)
  const { pct } = useI18n()
  const grid = Array.isArray(values) ? values : []
  const flat = grid.flat()
  const max = Math.max(...flat, 0.0001)
  const bestIdx = flat.indexOf(max)

  useGSAP(
    () => {
      if (reduced() || !box.current) return
      gsap.from(box.current.querySelectorAll('.heat__cell'), {
        opacity: 0,
        scale: 0.5,
        transformOrigin: '50% 50%',
        duration: 0.5,
        stagger: { each: 0.004, from: 'start' },
        ease: 'snap',
      })
    },
    { dependencies: [rows, cols], scope: box }
  )

  return (
    <div className="heat" ref={box}>
      <div className="heat__grid" style={{ gridTemplateColumns: `auto repeat(${cols}, minmax(0,1fr))` }}>
        <span />
        {colLabels.map((c, i) => (
          <span key={i} className="heat__col">
            {c}
          </span>
        ))}
        {/* `display: contents` keeps each row's cells as direct children of the
            grid — a real wrapper element would break the column tracks. */}
        {rowLabels.map((r, ri) => (
          <div key={`row-${ri}`} style={{ display: 'contents' }}>
            <span className="heat__row">{r}</span>
            {(grid[ri] || []).map((v, ci) => {
              const idx = ri * cols + ci
              return (
                <button
                  key={`${ri}-${ci}`}
                  className={`heat__cell${idx === bestIdx ? ' heat__cell--best' : ''}`}
                  style={{ '--a': (v / max).toFixed(3) }}
                  title={`${r} ${colLabels[ci]} — ${format ? format(v) : pct(v, 1)}`}
                  onClick={() => onPick?.(ri, ci, v)}
                />
              )
            })}
          </div>
        ))}
      </div>
      <div className="heat__scale">
        <span className="heat__scaleBar" />
      </div>
    </div>
  )
}

/* ============================================================
   COHORT GRID — retention by signup month. Same alpha encoding as
   the heatmap, but the numbers stay printed: a cohort table is
   read cell by cell, not scanned for a maximum.
   ============================================================ */
export function CohortGrid({ cohorts, periods }) {
  const { pct } = useI18n()
  const rows = Array.isArray(cohorts) ? cohorts : []
  const cols = Array.isArray(periods) ? periods : []
  return (
    <div className="cohort">
      <div className="cohort__grid" style={{ gridTemplateColumns: `10rem repeat(${periods.length}, minmax(0,1fr))` }}>
        <span className="cohort__corner" />
        {cols.map((p) => (
          <span key={p} className="cohort__head">
            {p}
          </span>
        ))}
        {rows.map((c) => (
          <div key={c.label} style={{ display: 'contents' }}>
            <span className="cohort__label">{c.label}</span>
            {(c.values || []).map((v, i) => (
              <span key={`${c.label}-${i}`} className="cohort__cell" style={{ '--a': (v / 100).toFixed(3) }}>
                {v > 0 ? pct(v, 0) : '—'}
              </span>
            ))}
          </div>
        ))}
      </div>
    </div>
  )
}

/* ============================================================
   RADIAL BARS — the agent-vs-agent comparison on the analytics
   page. Small multiples of one arc read faster than a grouped bar
   chart when every series has exactly one number.
   ============================================================ */
/* A translucent version of whatever colour the ring is drawn in, so the halo
   belongs to the arc rather than to the inherited text colour. */
const glowFor = (c) => {
  const m = /^#([0-9a-f]{6})$/i.exec(c || '')
  if (!m) return 'rgba(150, 195, 232, 0.5)'
  const n = parseInt(m[1], 16)
  return `rgba(${(n >> 16) & 255}, ${(n >> 8) & 255}, ${n & 255}, 0.5)`
}

export function RadialStat({ value, max = 100, size = 84, color = '#7ba3cd', label, center }) {
  const ref = useRef(null)
  const r = 40
  const c = 2 * Math.PI * r
  const pctv = Math.min(1, value / max)

  useGSAP(() => {
    gsap.fromTo(
      ref.current,
      { strokeDashoffset: c },
      { strokeDashoffset: c * (1 - pctv), duration: reduced() ? 0 : 1.2, ease: 'glide' }
    )
  }, [pctv, c])

  return (
    <div className="radial" style={{ width: `${size / 10}rem`, '--glow-c': glowFor(color) }}>
      <svg viewBox="0 0 100 100">
        <circle cx="50" cy="50" r={r} className="radial__track" />
        <circle
          cx="50"
          cy="50"
          r={r}
          ref={ref}
          className="radial__ring"
          stroke={color}
          strokeDasharray={c}
          strokeDashoffset={c}
        />
      </svg>
      <span className="radial__center">{center}</span>
      {label && <span className="radial__label">{label}</span>}
    </div>
  )
}

export { spline, scale }
