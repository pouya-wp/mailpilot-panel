import { useRef } from 'react'
import { Discord, Headset, Telegram, XSocial } from './Icons'
import { gsap, reduced, useGSAP } from '../anim/core'
import { useMagnetic } from '../anim/hooks'

export default function Footer() {
  const socials = useRef(null)
  const fab = useMagnetic({ strength: 0.28, radius: 2, scale: 1.1 })

  /* Social marks pop on hover with a little overshoot, and the icon inside
     rolls — the whole target moves as one object rather than the colour
     changing under a static shape. */
  useGSAP(
    () => {
      if (reduced()) return
      const links = gsap.utils.toArray('a', socials.current)
      const kill = links.map((a) => {
        const enter = () =>
          gsap.to(a, { y: -5, scale: 1.18, rotate: -8, duration: 0.45, ease: 'snap', overwrite: 'auto' })
        const leave = () =>
          gsap.to(a, { y: 0, scale: 1, rotate: 0, duration: 0.6, ease: 'elastic.out(1, 0.6)', overwrite: 'auto' })
        a.addEventListener('pointerenter', enter)
        a.addEventListener('pointerleave', leave)
        return () => {
          a.removeEventListener('pointerenter', enter)
          a.removeEventListener('pointerleave', leave)
        }
      })
      return () => kill.forEach((fn) => fn())
    },
    { scope: socials }
  )

  return (
    <footer className="footer">
      <div className="footer__socials" ref={socials}>
        <a href="#x" aria-label="X">
          <XSocial size={20} />
        </a>
        <a href="#discord" aria-label="Discord">
          <Discord size={22} />
        </a>
        <a href="#telegram" aria-label="Telegram">
          <Telegram size={22} />
        </a>
      </div>

      <div className="footer__right">
        <button className="linkbtn">About</button>
        <button className="linkbtn">Contact</button>
        <button className="footer__fab" ref={fab} aria-label="Support">
          <Headset size={24} />
        </button>
      </div>
    </footer>
  )
}
