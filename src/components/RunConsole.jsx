import { useEffect, useMemo, useRef, useState } from 'react'
import { AGENTS, SEGMENTS, deliverability, fmt, leadsFrom, openRate } from '../data'
import Selector from './Selector'
import { Bolt, ChevronDown, Cursor, Percent, Rocket, Switch, Users } from './Icons'
import Num from '../anim/Num'
import { gsap, introStarted, reduced, useGSAP } from '../anim/core'
import { CUE } from '../anim/intro'
import { usePress, useRipple } from '../anim/hooks'

const TICKS = ['x1', 'x2', 'x3', 'x4', 'x5']
const CAP = 999999

export default function RunConsole({ onLaunch, onState }) {
  const [segment, setSegment] = useState(SEGMENTS[0])
  const [agent, setAgent] = useState(AGENTS[0])
  const [recipients, setRecipients] = useState(25000)
  const [boost, setBoost] = useState(3.6)
  const [showInfo, setShowInfo] = useState(true)
  const [busy, setBusy] = useState(false)

  const calc = useMemo(() => {
    const rate = openRate(boost)
    return {
      opens: recipients * rate,
      rate,
      delivery: deliverability(boost),
      leads: leadsFrom(recipients, boost),
    }
  }, [recipients, boost])

  const pct = ((boost - 1) / 4) * 100

  /* keep the support agent's answers in sync with what the panel shows */
  useEffect(() => {
    onState?.({
      boost,
      segment: segment.name,
      agent: agent.name,
      recipients: fmt(recipients),
      opens: fmt(calc.opens),
      openRate: (calc.rate * 100).toFixed(1),
      delivery: calc.delivery.toFixed(1),
      leads: calc.leads,
    })
  }, [boost, segment, agent, recipients, calc, onState])

  /* ============================================================
     THE SLIDER

     `--p` (0..100) is the single source of truth for the fill width, the
     thumb position and the glow strength — CSS derives all three from it.
     Driving one custom property through quickTo means a drag produces one
     interpolated write per frame no matter how many pointermove events the
     device fires, and the entrance timeline can animate the very same
     property to fill the track on load.
     ============================================================ */
  const slider = useRef(null)
  const setP = useRef(null)
  const fill = useRef(null) // the entrance tween, killed on first real input
  const pctRef = useRef(pct)
  pctRef.current = pct

  useGSAP(
    () => {
      const el = slider.current
      if (!el) return

      if (reduced()) {
        gsap.set(el, { '--p': pctRef.current })
        setP.current = (v) => gsap.set(el, { '--p': v })
        return
      }

      setP.current = gsap.quickTo(el, '--p', { duration: 0.22, ease: 'power2.out' })

      /* The track fills as part of the entrance, on the same cue as the rest
         of the controls. It runs from here rather than from the master
         timeline because `--p` is this component's property — a `from` tween
         over there would have to read a value this effect had already
         written, and the whole fill would silently collapse to zero the day
         that ordering changed. */
      gsap.set(el, { '--p': 0 })
      let live = true
      introStarted.then(() => {
        if (!live) return
        fill.current = gsap.to(el, {
          '--p': pctRef.current,
          duration: 1.1,
          delay: CUE.slider,
          ease: 'glide',
        })
      })
      return () => {
        live = false
      }
    },
    { scope: slider }
  )

  /* Hand the track over from the entrance to the control the moment the
     reader actually touches it — compared against the opening value rather
     than a "first run" flag, which StrictMode's double mount would burn. */
  const opening = useRef(pct)
  useEffect(() => {
    if (opening.current !== null && pct === opening.current) return
    opening.current = null
    fill.current?.kill()
    setP.current?.(pct)
  }, [pct])

  /* the thumb stretches while it is being dragged, like a real fader grip */
  const grab = (on) => {
    const thumb = slider.current?.querySelector('.slider__thumb')
    if (!thumb || reduced()) return
    gsap.to(thumb, {
      scaleY: on ? 1.5 : 1,
      scaleX: on ? 1.9 : 1,
      duration: on ? 0.25 : 0.6,
      ease: on ? 'snap' : 'elastic.out(1, 0.5)',
      overwrite: 'auto',
    })
  }

  /* ============================================================
     THE AUDIENCE FIELD

     Picking a segment jumps the count by thousands. The input is
     uncontrolled so the figure can be counted straight into the DOM node
     without a React render per frame; typing writes state as before.
     ============================================================ */
  const input = useRef(null)
  const shown = useRef({ v: 25000 })

  const countTo = (target) => {
    const node = input.current
    if (!node) return
    if (reduced()) {
      shown.current.v = target
      node.value = fmt(target)
      return
    }
    /* One proxy for the life of the component, so `overwrite` actually has
       something to overwrite. A fresh object per call would leave two
       counts racing to write the same input on two picks in a row. */
    gsap.to(shown.current, {
      v: target,
      duration: 0.9,
      ease: 'soft',
      overwrite: true,
      onUpdate: () => {
        node.value = fmt(shown.current.v)
      },
    })
  }

  const onType = (e) => {
    const n = Math.min(Number(e.target.value.replace(/[^\d]/g, '')) || 0, CAP)
    e.target.value = fmt(n)
    shown.current.v = n
    setRecipients(n)
  }

  const pickSegment = (s) => {
    setSegment(s)
    setRecipients(s.size)
    countTo(s.size)
  }

  /* ============================================================
     THE INFO DRAWER

     Height-to-auto with the rows dealt out behind it. The old max-height
     trick had to guess a ceiling, and the guess is what made the close
     feel like it hesitated before moving.
     ============================================================ */
  const info = useRef(null)
  const wasOpen = useRef(showInfo)

  useGSAP(
    () => {
      const el = info.current
      // the entrance timeline owns the opening state; only a real toggle
      // animates (and this also keeps StrictMode's second mount quiet)
      if (!el || wasOpen.current === showInfo) return
      wasOpen.current = showInfo
      const rows = gsap.utils.toArray('.info__row', el)

      /* the drawer's own padding has to collapse too, or a closed drawer
         still holds a couple of rem of empty space open */
      const shut = { height: 0, opacity: 0, paddingTop: 0, paddingBottom: 0 }
      const natural = 'height,opacity,paddingTop,paddingBottom'

      if (reduced()) {
        if (showInfo) gsap.set(el, { clearProps: natural })
        else gsap.set(el, shut)
        gsap.set(rows, { clearProps: 'opacity,transform' })
        return
      }

      if (showInfo) {
        /* Measure, then animate to concrete numbers.
           The obvious version — set height to auto and `from` the closed
           state — does not work: a `from` tween initialises EAGERLY, at
           creation, so it reads its end value before the set beside it has
           rendered. Reopening therefore measured the drawer while it was
           still collapsed and dutifully animated 0 → 0. Same trap for the
           rows, whose leftover opacity: 0 would become their target. */
        gsap.set([el, ...rows], { clearProps: 'opacity,transform' })
        gsap.set(el, { clearProps: natural })
        const box = getComputedStyle(el)
        const to = {
          height: el.scrollHeight,
          paddingTop: box.paddingTop,
          paddingBottom: box.paddingBottom,
        }

        gsap
          .timeline({
            // let the drawer go back to `auto` afterwards, so it still grows
            // with its content if a row is ever added
            onComplete: () => gsap.set(el, { clearProps: natural }),
          })
          .fromTo(el, shut, { ...to, opacity: 1, duration: 0.45, ease: 'swift' })
          .fromTo(rows, { y: -10, opacity: 0 }, { y: 0, opacity: 1, duration: 0.4, stagger: 0.045 }, 0.08)
      } else {
        gsap
          .timeline()
          .to(rows, { y: -8, opacity: 0, duration: 0.25, stagger: { each: 0.03, from: 'end' } })
          .to(el, { ...shut, duration: 0.38, ease: 'swift' }, 0.1)
      }
      /* NOTE: no manual kill here. useGSAP's own cleanup reverts the context,
         which restores the inline styles these timelines wrote. Killing the
         timeline first removes it from the context before that can happen —
         and a drawer killed mid-close keeps `height: 0` forever. */
    },
    { dependencies: [showInfo], scope: info }
  )

  /* ============================================================
     LAUNCH
     ============================================================ */
  const console_ = useRef(null)
  const cta = usePress({ to: 0.985 })
  const [ctaClip, fireRipple] = useRipple('cta__ripple')

  const launch = (e) => {
    if (busy) return
    setBusy(true)
    fireRipple(e)

    const el = cta.current
    if (el && !reduced()) {
      // the fill line is the progress bar: it crosses the button once, over
      // exactly as long as the request is pretending to take
      gsap.fromTo(el, { '--load': 0 }, { '--load': 1, duration: 1.4, ease: 'power1.inOut' })
    }

    setTimeout(() => {
      setBusy(false)
      burst(cta.current)
      onLaunch?.(`Campaign queued — ${fmt(recipients)} contacts via ${agent.name}`)
    }, 1400)
  }

  /* ---- the seam button ---- */
  const seam = useRef(null)
  const cycleBoost = () => {
    setBoost((b) => (b >= 5 ? 1 : Math.min(5, b + 0.4)))
    if (seam.current && !reduced()) {
      gsap.to(seam.current, { rotate: '+=180', duration: 0.7, ease: 'snap' })
    }
    // a short shudder down the console, so the change reads as coming from here
    if (console_.current && !reduced()) {
      gsap.fromTo(
        gsap.utils.toArray('.card', console_.current),
        { y: 0 },
        { y: -3, duration: 0.18, ease: 'power2.out', stagger: 0.04, yoyo: true, repeat: 1, overwrite: 'auto' }
      )
    }
  }

  return (
    <div className="console" ref={console_}>
      {/* ------- audience ------- */}
      <div className="card field">
        <div className="field__head">
          <span className="card-label">Audience</span>
          <Selector options={SEGMENTS} value={segment} onChange={pickSegment} meta={(o) => fmt(o.size)} />
        </div>
        <div className="field__body">
          <input
            ref={input}
            className="field__input"
            defaultValue={fmt(recipients)}
            inputMode="numeric"
            onChange={onType}
          />
        </div>
      </div>

      <div className="seam">
        <button className="seam__btn" ref={seam} onClick={cycleBoost} aria-label="Cycle boost">
          <Switch size={20} />
        </button>
      </div>

      {/* ------- forecast ------- */}
      <div className="card field">
        <div className="field__head">
          <span className="card-label">Send with</span>
          <Selector options={AGENTS} value={agent} onChange={setAgent} meta={(o) => o.note} />
        </div>
        <div className="field__body">
          <Num className="field__value" value={calc.opens} format={fmt} />
        </div>

        <div className="forecast">
          <div className="forecast__label">You can gain</div>
          <div className="forecast__value">
            <Num value={calc.leads} /> <small>LEADS</small>
          </div>
        </div>
      </div>

      {/* ------- boost ------- */}
      <div className="card boost">
        <div className="boost__head">
          <span className="card-label">Boost</span>
          <Num className="boost__value" value={boost} format={(n) => n.toFixed(1)} duration={0.4} />
        </div>

        <div className="slider" ref={slider}>
          <div className="slider__ticks">
            {TICKS.map((t, i) => (
              <span key={t} className={i + 1 <= Math.round(boost) ? 'is-lit' : undefined}>
                {t}
              </span>
            ))}
          </div>
          <div className="slider__track">
            <div className="slider__fill" />
            <div className="slider__thumb" />
          </div>
          <input
            className="slider__input"
            type="range"
            min="1"
            max="5"
            step="0.1"
            value={boost}
            onChange={(e) => setBoost(Number(e.target.value))}
            onPointerDown={() => grab(true)}
            onPointerUp={() => grab(false)}
            onPointerCancel={() => grab(false)}
            aria-label="Boost multiplier"
          />
        </div>
      </div>

      {/* ------- info ------- */}
      <button
        className={`info-toggle${showInfo ? '' : ' info-toggle--closed'}`}
        onClick={() => setShowInfo((s) => !s)}
      >
        <ChevronDown size={15} />
        Info
      </button>

      <div className="info" ref={info}>
        <Row icon={<Bolt size={19} />} label="Your boost" value={<Num value={boost} format={(n) => n.toFixed(1)} duration={0.4} />} />
        <Row
          icon={<Percent size={19} />}
          label="Predicted deliverability"
          value={<Num value={calc.delivery} format={(n) => `${n.toFixed(1)}%`} />}
        />
        <Row
          icon={<Users size={19} />}
          label="You send to"
          value={<Num value={recipients} format={(n) => `${fmt(n)} contacts`} />}
        />
        <Row
          icon={<Rocket size={19} />}
          label=".. if it converts that becomes"
          value={<Num value={calc.leads} format={(n) => `${Math.round(n)} leads`} />}
        />
        <Row
          icon={<Cursor size={19} />}
          label=".. and will be opened by"
          value={<Num value={calc.opens} format={(n) => `${fmt(n)} people`} />}
          blue
        />
      </div>

      <button className={`cta${busy ? ' cta--busy' : ''}`} ref={cta} onClick={launch}>
        {/* clips the click ripple to the button's silhouette — the launch
            sparks deliberately live outside it, on the button itself */}
        <span className="cta__clip" ref={ctaClip} aria-hidden="true" />
        <span className="cta__load" aria-hidden="true" />
        <span className="cta__text">{busy ? 'Launching…' : 'Launch Campaign'}</span>
      </button>
    </div>
  )
}

function Row({ icon, label, value, blue }) {
  return (
    <div className="info__row">
      <span className="info__icon">{icon}</span>
      <span className="info__label">{label}</span>
      <span className={`info__val${blue ? ' info__val--blue' : ''}`}>{value}</span>
    </div>
  )
}

/* ============================================================
   The launch burst.

   A shockwave ring plus a handful of sparks thrown on ballistic arcs
   (Physics2DPlugin does the integration). The nodes are created on the
   fly and removed when they land, so nothing is left in the DOM between
   launches and overlapping launches can't fight over one element.
   ============================================================ */
function burst(host) {
  if (!host || reduced()) return

  const ring = document.createElement('span')
  ring.className = 'cta__shock'
  host.appendChild(ring)
  gsap.fromTo(
    ring,
    { scale: 0.2, opacity: 0.9 },
    { scale: 1, opacity: 0, duration: 0.9, ease: 'power2.out', onComplete: () => ring.remove() }
  )

  const sparks = Array.from({ length: 18 }, () => {
    const s = document.createElement('i')
    s.className = 'cta__spark'
    host.appendChild(s)
    return s
  })

  gsap.to(sparks, {
    physics2D: {
      velocity: () => gsap.utils.random(140, 320),
      angle: () => gsap.utils.random(-155, -25),
      gravity: 620,
    },
    scale: () => gsap.utils.random(0.4, 1.1),
    opacity: 0,
    duration: 1.1,
    ease: 'power1.out',
    stagger: 0.012,
    onComplete: () => sparks.forEach((s) => s.remove()),
  })
}
