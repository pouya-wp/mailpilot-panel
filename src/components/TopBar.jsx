import { Logo } from './Icons'
import MusicToggle from './MusicToggle'
import { gsap, reduced, useGSAP } from '../anim/core'
import { usePress } from '../anim/hooks'
import { useRef } from 'react'

export default function TopBar() {
  const bar = useRef(null)
  const account = usePress({ to: 0.97 })

  /* The mark is the only lit object in the top bar, so it gets the only
     ambient motion up here: a slow counter-rotation of the second spark plus
     a glow that drifts, as if the light rig were passing across it. */
  useGSAP(
    () => {
      if (reduced()) return
      const mark = bar.current?.querySelector('.brand__mark')
      if (!mark) return
      const spin = gsap.to(mark.querySelectorAll('path')[1], {
        rotation: 360,
        transformOrigin: '50% 50%',
        duration: 14,
        ease: 'none',
        repeat: -1,
      })
      const glow = gsap.to(mark, {
        '--lit': 1,
        duration: 2.6,
        ease: 'sine.inOut',
        yoyo: true,
        repeat: -1,
      })

      const hover = () =>
        gsap.to(mark, { rotate: '+=180', scale: 1.12, duration: 0.8, ease: 'snap', overwrite: 'auto' })
      const off = () => gsap.to(mark, { scale: 1, duration: 0.5, ease: 'power3.out', overwrite: 'auto' })
      const brand = bar.current.querySelector('.brand')
      brand.addEventListener('pointerenter', hover)
      brand.addEventListener('pointerleave', off)

      return () => {
        spin.kill()
        glow.kill()
        brand.removeEventListener('pointerenter', hover)
        brand.removeEventListener('pointerleave', off)
      }
    },
    { scope: bar }
  )

  return (
    <header className="topbar" ref={bar}>
      <div className="brand">
        <span className="brand__mark">
          <Logo size={28} />
        </span>
        <span className="brand__name">Campaigns</span>
      </div>

      <div className="topbar__right">
        <MusicToggle />
        <button className="linkbtn">Campaign History</button>
        <button className="account" ref={account}>
          <span className="account__dot" />
          <span>Acme Inc … Pro</span>
        </button>
      </div>
    </header>
  )
}
