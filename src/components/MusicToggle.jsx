import { useEffect, useRef, useState } from 'react'
import { createAmbience } from '../audio/ambience'
import { gsap, reduced, useGSAP } from '../anim/core'
import { useI18n } from '../i18n'

const KEY = 'mailpilot:ambience'

/* ============================================================
   The room tone, and the switch for it.

   Browsers will not let an AudioContext start without a user
   gesture, so the pad cannot simply begin on load however much we
   would like it to. Instead the preference is remembered, and the
   very first interaction with the page — any click, any key — is
   what actually starts it. That first gesture is almost always the
   reader reaching for a control anyway, so in practice the music
   comes up a second or two in, under whatever they just touched.

   The choice is persisted, so someone who turns it off does not
   have to turn it off again on the next visit.
   ============================================================ */
export default function MusicToggle() {
  const { t } = useI18n()
  const engine = useRef(null)
  const [on, setOn] = useState(() => window.localStorage.getItem(KEY) !== 'off')
  const [live, setLive] = useState(false) // has audio actually started?
  const bars = useRef(null)

  if (!engine.current) engine.current = createAmbience()

  useEffect(() => () => engine.current?.dispose(), [])

  /* arm the first gesture */
  useEffect(() => {
    if (!on || live) return
    const wake = () => {
      engine.current?.start().then(() => setLive(true))
    }
    window.addEventListener('pointerdown', wake, { once: true })
    window.addEventListener('keydown', wake, { once: true })
    return () => {
      window.removeEventListener('pointerdown', wake)
      window.removeEventListener('keydown', wake)
    }
  }, [on, live])

  const toggle = () => {
    const next = !on
    setOn(next)
    window.localStorage.setItem(KEY, next ? 'on' : 'off')
    if (next) {
      // this click IS a gesture, so it can start straight away
      engine.current?.start().then(() => setLive(true))
    } else {
      engine.current?.stop()
      setLive(false)
    }
  }

  /* The meter only moves while sound is actually coming out — so it
     doubles as the answer to "is this thing on?" during the gap between
     switching it on and the first gesture. */
  useGSAP(
    () => {
      const el = bars.current
      if (!el) return
      const rods = gsap.utils.toArray('i', el)
      if (!live || reduced()) {
        gsap.to(rods, { scaleY: 0.28, duration: 0.4, ease: 'power2.out', overwrite: 'auto' })
        return
      }
      rods.forEach((rod, i) => {
        gsap.to(rod, {
          scaleY: gsap.utils.random(0.5, 1),
          duration: gsap.utils.random(0.7, 1.5),
          ease: 'sine.inOut',
          yoyo: true,
          repeat: -1,
          delay: i * 0.18,
          overwrite: 'auto',
        })
      })
    },
    { dependencies: [live], scope: bars }
  )

  return (
    <button
      className={`music${on ? ' music--on' : ''}`}
      onClick={toggle}
      aria-pressed={on}
      aria-label={on ? t('app.musicOff') : t('app.musicOn')}
      title={on ? 'Music on' : 'Music off'}
    >
      <span className="music__bars" ref={bars} aria-hidden="true">
        <i />
        <i />
        <i />
        <i />
      </span>
    </button>
  )
}
