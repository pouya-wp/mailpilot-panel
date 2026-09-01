import { gsap, reduced, useGSAP } from '../anim/core'
import { useTilt } from '../anim/hooks'

/* The three sheets sit at fixed offsets in the stack. That offset lives on an
   OUTER <g> and the animation drives an INNER one — GSAP's y is absolute, so
   animating the element that already carries `translate(0 26)` would flatten
   the stack the first time it moved. */
const SHEETS = [0, 13, 26]

export default function ChallengeCard() {
  const card = useTilt({ max: 5, lift: 6 })

  /* The stack leans with the pointer on top of the card's own tilt, deeper
     sheets travelling further — so the artwork has parallax within a card that
     is itself already turning, and the envelopes read as objects sitting in the
     card rather than as a picture printed on it.

     Three tweens share this artwork without ever touching the same property:
     the idle hover from intro.js owns `y`, this owns `x` and `rotation`, and
     useTilt owns the card underneath. */
  useGSAP(
    () => {
      if (reduced()) return
      const el = card.current
      const sheets = gsap.utils.toArray('.challenge__sheet', el)
      if (!el || !sheets.length) return

      const to = sheets.map((s, i) => ({
        x: gsap.quickTo(s, 'x', { duration: 0.6, ease: 'power3' }),
        rot: gsap.quickTo(s, 'rotation', { duration: 0.6, ease: 'power3' }),
        depth: 1 + i * 0.7,
      }))

      const move = (e) => {
        const r = el.getBoundingClientRect()
        const nx = (e.clientX - r.left) / r.width - 0.5
        const ny = (e.clientY - r.top) / r.height - 0.5
        to.forEach((t) => {
          t.x(nx * 9 * t.depth)
          t.rot(-nx * 2.6 * t.depth + ny * 1.4)
        })
      }
      const leave = () => to.forEach((t) => (t.x(0), t.rot(0)))

      el.addEventListener('pointermove', move)
      el.addEventListener('pointerleave', leave)
      return () => {
        el.removeEventListener('pointermove', move)
        el.removeEventListener('pointerleave', leave)
      }
    },
    { scope: card }
  )

  return (
    <div className="challenge" ref={card}>
      <span className="challenge__tag">Challenges</span>
      <p className="challenge__text">
        Complete today
        <br />
        for bonus XP!
      </p>

      {/* isometric envelope stack — stands in for the 3D art of the mock */}
      <svg className="challenge__art" viewBox="0 0 140 100" aria-hidden="true">
        <defs>
          <linearGradient id="envTop" x1="0" y1="0" x2="1" y2="1">
            <stop offset="0%" stopColor="#ffffff" stopOpacity="0.95" />
            <stop offset="100%" stopColor="#c9dbff" stopOpacity="0.75" />
          </linearGradient>
          <linearGradient id="envSide" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor="#9fbcff" stopOpacity="0.85" />
            <stop offset="100%" stopColor="#4a72e0" stopOpacity="0.7" />
          </linearGradient>
        </defs>

        {SHEETS.map((offset, i) => (
          <g key={offset} transform={`translate(0 ${offset})`}>
            <g className="challenge__sheet" opacity={1 - i * 0.22}>
              <path d="M70 18 L114 40 L70 62 L26 40 Z" fill="url(#envTop)" />
              <path d="M26 40 L70 62 L70 70 L26 48 Z" fill="url(#envSide)" />
              <path d="M114 40 L70 62 L70 70 L114 48 Z" fill="#3a63d6" opacity="0.75" />
              <path d="M44 40 L70 53 L96 40" fill="none" stroke="#5b82e8" strokeWidth="1.6" opacity="0.8" />
            </g>
          </g>
        ))}
      </svg>
      <span className="challenge__caption">Campaigns</span>
    </div>
  )
}
