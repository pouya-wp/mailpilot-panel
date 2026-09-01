import Num from '../anim/Num'
import { gsap, introStarted, reduced, useGSAP } from '../anim/core'
import { useTilt } from '../anim/hooks'

/* Agent progress card with the glowing spline, like the reference mock. */
const PATH =
  'M-6,86 C34,80 44,14 78,17 C112,20 118,77 148,92 C182,109 196,71 226,53 C258,34 286,44 330,24'

export default function LevelCard({ level = 4, xp = 750, xpMax = 1000 }) {
  const card = useTilt({ max: 4, lift: 5 })

  /* ---- the read-head ----
     Once the spline has drawn itself, a small light runs the curve on a loop.
     It is the same geometry the line uses (MotionPath reads the `d` attribute
     off the path element), so the two can never drift apart if the curve is
     ever re-authored. */
  useGSAP(
    () => {
      if (reduced()) return
      const head = card.current?.querySelector('.level__head')
      const line = card.current?.querySelector('.level__line')
      if (!head || !line) return

      let tl = null
      let live = true
      introStarted.then(() => {
        if (!live) return
        /* a long rest between passes: while the head is travelling the card
           repaints every frame, so this is an occasional flourish rather
           than something running the whole time the panel is open */
        tl = gsap.timeline({ repeat: -1, repeatDelay: 9, delay: 2.2 })
        tl.set(head, { opacity: 0 })
          .to(head, { opacity: 1, duration: 0.35 })
          .to(
            head,
            {
              motionPath: { path: line, align: line, alignOrigin: [0.5, 0.5] },
              duration: 3.6,
              ease: 'sine.inOut',
            },
            0
          )
          .to(head, { opacity: 0, duration: 0.5 }, '-=0.5')
      })
      return () => {
        live = false
        tl?.kill()
      }
    },
    { scope: card }
  )

  return (
    <div className="card level" ref={card}>
      <span className="card-label">Your Progress</span>
      <div className="level__title">
        Level <em>{level}</em>
      </div>

      <div className="level__chart">
        <span className="level__bloom level__bloom--a" />
        <span className="level__bloom level__bloom--b" />
        <svg viewBox="0 0 320 140" preserveAspectRatio="none" aria-hidden="true">
          <defs>
            <linearGradient id="lineGrad" x1="0" y1="0" x2="1" y2="0">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="0" />
              <stop offset="18%" stopColor="#d6e6f4" stopOpacity="0.5" />
              <stop offset="58%" stopColor="#ffffff" stopOpacity="0.95" />
              <stop offset="100%" stopColor="#9dc0dd" stopOpacity="0.22" />
            </linearGradient>
            <linearGradient id="areaGrad" x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor="#9cc3e4" stopOpacity="0.16" />
              <stop offset="100%" stopColor="#9cc3e4" stopOpacity="0" />
            </linearGradient>
            <filter id="lineGlow" x="-30%" y="-90%" width="160%" height="320%">
              <feGaussianBlur stdDeviation="6" result="b" />
              <feMerge>
                <feMergeNode in="b" />
                <feMergeNode in="SourceGraphic" />
              </feMerge>
            </filter>
            <radialGradient id="headGrad">
              <stop offset="0%" stopColor="#ffffff" stopOpacity="1" />
              <stop offset="45%" stopColor="#dcecfb" stopOpacity="0.7" />
              <stop offset="100%" stopColor="#9dc0dd" stopOpacity="0" />
            </radialGradient>
          </defs>

          <path className="level__area" d={`${PATH} L330,140 L-6,140 Z`} fill="url(#areaGrad)" />
          <path
            className="level__line"
            d={PATH}
            fill="none"
            stroke="url(#lineGrad)"
            strokeWidth="2"
            filter="url(#lineGlow)"
          />
          <circle className="level__head" r="5" fill="url(#headGrad)" opacity="0" />
        </svg>
      </div>

      <div className="level__xp">
        <Num tag="b" value={xp} from={0} delay={0.35} flash={false} /> / {xpMax} xp
      </div>
    </div>
  )
}
