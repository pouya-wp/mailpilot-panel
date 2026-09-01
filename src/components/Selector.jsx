import { useEffect, useRef, useState } from 'react'
import { ChevronDown } from './Icons'
import { gsap, reduced, useGSAP } from '../anim/core'

export default function Selector({ options, value, onChange, onOpen, meta }) {
  const [open, setOpen] = useState(false)
  const box = useRef(null)
  const menu = useRef(null)
  const caret = useRef(null)
  const avatar = useRef(null)
  const picked = useRef(value.id)

  useEffect(() => {
    if (!open) return
    const away = (e) => {
      if (!box.current?.contains(e.target)) setOpen(false)
    }
    document.addEventListener('mousedown', away)
    return () => document.removeEventListener('mousedown', away)
  }, [open])

  /* the token spins in when the choice actually changes, so the swap is
     visible even though the button never moves */
  useGSAP(
    () => {
      if (picked.current === value.id || reduced()) return
      picked.current = value.id
      gsap.fromTo(
        avatar.current,
        { scale: 0.35, rotate: -140, opacity: 0 },
        { scale: 1, rotate: 0, opacity: 1, duration: 0.7, ease: 'snap' }
      )
      gsap.fromTo(avatar.current.nextSibling, { opacity: 0, x: -8 }, { opacity: 1, x: 0, duration: 0.45, ease: 'glide' })
    },
    { dependencies: [value.id], scope: box }
  )

  /* ---- open / close ----
     The menu is always in the DOM and hidden with `autoAlpha` (opacity plus
     visibility, so it is neither seen nor focusable when shut).

     It used to be mounted and unmounted around the animation, which is where
     the dropdown bug lived: the exit timeline's onComplete unmounted the menu,
     and a click that reopened it mid-exit still got that callback afterwards.
     The menu then vanished while `open` was true — and since the state that
     re-mounted it only reacted to `open` CHANGING, it never came back. There
     is no unmount to race with now. */
  useGSAP(
    () => {
      const el = menu.current
      gsap.to(caret.current, {
        rotate: open ? 180 : 0,
        duration: reduced() ? 0 : 0.35,
        ease: 'snap',
        overwrite: 'auto',
      })

      if (reduced()) {
        gsap.set(el, { autoAlpha: open ? 1 : 0, y: 0 })
        return
      }

      /* The menu slides and fades; it does NOT scale. A scaled dropdown drags
         its own type through a size change on every open, and next to the card
         behind it the whole panel looks like it is resizing. */
      const items = gsap.utils.toArray('.selector__item', el)
      if (open) {
        gsap
          .timeline()
          .fromTo(el, { autoAlpha: 0, y: -8 }, { autoAlpha: 1, y: 0, duration: 0.28, ease: 'swift' })
          .fromTo(items, { opacity: 0, y: -6 }, { opacity: 1, y: 0, duration: 0.26, stagger: 0.035 }, 0.04)
      } else {
        gsap.to(el, { autoAlpha: 0, y: -6, duration: 0.18, ease: 'power2.in', overwrite: 'auto' })
      }
    },
    { dependencies: [open], scope: box }
  )

  return (
    <div className={`selector${open ? ' selector--open' : ''}`} ref={box}>
      <button
        className="selector__btn"
        onClick={() =>
          setOpen((o) => {
            if (!o) onOpen?.()
            return !o
          })
        }
        aria-expanded={open}
      >
        <span className="selector__avatar" ref={avatar} style={{ background: value.tint }}>
          {value.emoji}
        </span>
        <span className="selector__name">{value.name}</span>
        <span className="selector__caret" ref={caret}>
          <ChevronDown size={17} />
        </span>
      </button>

      <div className="selector__menu" ref={menu} aria-hidden={!open}>
        {options.map((o) => (
          <button
            key={o.id}
            className="selector__item"
            tabIndex={open ? 0 : -1}
            onClick={() => {
              onChange(o)
              setOpen(false)
            }}
          >
            <span className="selector__avatar" style={{ background: o.tint }}>
              {o.emoji}
            </span>
            <span>{o.name}</span>
            <small>{meta ? meta(o) : ''}</small>
          </button>
        ))}
      </div>
    </div>
  )
}
