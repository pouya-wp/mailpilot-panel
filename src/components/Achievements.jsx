import { useRef } from 'react'
import { ACHIEVEMENTS } from '../data'
import { ChevronLeft, ChevronRight, Mail, Rocket, Check, Flame } from './Icons'
import { gsap, reduced, useGSAP } from '../anim/core'
import { usePress, useTilt } from '../anim/hooks'

const ICONS = { mail: Mail, rocket: Rocket, check: Check, flame: Flame }

export default function Achievements() {
  const card = useTilt({ max: 3.5, lift: 4 })
  const row = useRef(null)
  const back = usePress()
  const fwd = usePress()

  /* `scroll-behavior: smooth` gives a fixed, linear-ish glide the rest of the
     panel does not share. Tweening scrollLeft instead puts the rail on the
     same ease as everything else, and lets a second click retarget mid-flight
     rather than queueing behind the first. */
  const scroll = (dir) => {
    const el = row.current
    if (!el) return
    const step = el.clientWidth * 0.62
    const to = gsap.utils.clamp(0, el.scrollWidth - el.clientWidth, el.scrollLeft + dir * step)
    if (reduced()) {
      el.scrollLeft = to
      return
    }
    gsap.to(el, { scrollTo: { x: to }, duration: 0.7, ease: 'glide', overwrite: 'auto' })
  }

  /* The hovered chip lifts and the ones beside it lean away — a shelf being
     pushed apart rather than one card ignoring its neighbours.

     The whole rail is one delegated listener driving ONE tween whose values
     are functions of each chip's index. Per-chip enter/leave handlers do not
     work here: moving the pointer from one chip to the next fires the old
     chip's `leave` and the new chip's `enter` in the same breath, and the
     leave handler — which has to reset every chip, since it cannot know which
     one is next — kept wiping the lift the enter had just applied. That fight
     is what made the row twitch, and it meant up to five tweens were being
     built and thrown away on every crossing. */
  useGSAP(
    () => {
      if (reduced()) return
      const rail = row.current
      const chips = gsap.utils.toArray('.chip', rail)

      const focus = (idx) =>
        gsap.to(chips, {
          y: (i) => (i === idx ? -6 : 0),
          x: (i) => {
            if (idx < 0 || i === idx) return 0
            const d = i - idx
            return Math.abs(d) > 2 ? 0 : Math.sign(d) * (7 - Math.abs(d) * 2.5)
          },
          duration: 0.45,
          ease: 'power3.out',
          overwrite: 'auto',
        })

      // pointerover bubbles, so crossing between chips reports once, already
      // carrying the chip being entered
      const over = (e) => {
        const chip = e.target.closest?.('.chip')
        focus(chip ? chips.indexOf(chip) : -1)
      }
      const out = () => focus(-1)

      rail.addEventListener('pointerover', over)
      rail.addEventListener('pointerleave', out)
      return () => {
        rail.removeEventListener('pointerover', over)
        rail.removeEventListener('pointerleave', out)
      }
    },
    { scope: card }
  )

  return (
    <div className="card ach" ref={card}>
      <div className="ach__head">
        <span className="card-label">Achievements</span>
        <div className="ach__nav">
          <button ref={back} onClick={() => scroll(-1)} aria-label="Previous">
            <ChevronLeft size={16} />
          </button>
          <button ref={fwd} onClick={() => scroll(1)} aria-label="Next">
            <ChevronRight size={16} />
          </button>
        </div>
      </div>

      <div className="ach__row" ref={row}>
        {ACHIEVEMENTS.map((a) => {
          if (a.hot) {
            const [before, num, after] = a.label
            return (
              <div className="chip chip--hot" key={a.id}>
                <span className="chip__text">
                  {before}
                  <span className="chip__num">{num}</span>
                  {after}
                </span>
              </div>
            )
          }
          const Icon = ICONS[a.icon] ?? Mail
          return (
            <div className="chip" key={a.id}>
              <span className="chip__icon">
                <Icon size={22} />
              </span>
              <span className="chip__text">{a.label}</span>
            </div>
          )
        })}
      </div>
    </div>
  )
}
