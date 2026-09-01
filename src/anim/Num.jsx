import { useEffect, useRef } from 'react'
import { gsap, introStarted, reduced } from './core'
import { useI18n } from '../i18n'

/* ============================================================
   A number that travels to its new value instead of cutting to it.

   Every figure in the panel is derived from the same two inputs
   (audience size and boost), so one slider drag changes five of
   them at once. Counting makes the relationship between the control
   and the forecast legible — you can see which figures move a lot.

   Two things keep that cheap enough to run five at a time while a
   slider is being dragged:

   * the tween drives a plain object and writes textContent, rather
     than putting a React state update on every frame;
   * retargeting goes through quickTo, which re-points ONE tween at
     the new value. Creating a fresh tween per change would mean
     building and killing five tweens per frame for the length of
     the drag.
   ============================================================ */
export default function Num({
  value,
  format = (n) => String(Math.round(n)),
  duration = 0.85,
  from, // count up from here on first paint
  delay = 0,
  flash = true, // brighten briefly when the value changes
  tag: Tag = 'span',
  className,
  ...rest
}) {
  const { lang } = useI18n()
  const el = useRef(null)
  const at = useRef({ v: from ?? value })
  // the one and only string React will ever put in this node
  const seed = useRef(null)
  if (seed.current === null) seed.current = format(from ?? value)
  const to = useRef(null)
  const lit = useRef(0)
  const fmt = useRef(format)
  fmt.current = format

  /* one tween, retargeted for the life of the component */
  useEffect(() => {
    const node = el.current
    if (!node || reduced()) return
    const write = () => {
      node.textContent = fmt.current(at.current.v)
    }
    to.current = gsap.quickTo(at.current, 'v', { duration, ease: 'soft', onUpdate: write })
    return () => {
      gsap.killTweensOf(at.current)
      to.current = null
    }
  }, [duration])

  /* the opening count, run with the entrance rather than ahead of it */
  useEffect(() => {
    const node = el.current
    if (!node || from === undefined) return
    if (reduced()) {
      at.current.v = value
      node.textContent = fmt.current(value)
      return
    }
    let live = true
    let tween = null
    introStarted.then(() => {
      if (!live) return
      tween = gsap.to(at.current, {
        v: value,
        // slower than a correction: this is part of the reveal, not a
        // number the reader has already read changing under them
        duration: duration * 1.7,
        delay,
        ease: 'glide',
        onUpdate: () => {
          node.textContent = fmt.current(at.current.v)
        },
      })
    })
    return () => {
      live = false
      tween?.kill()
    }
    // only ever runs for the opening value
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [])

  useEffect(() => {
    const node = el.current
    if (!node) return

    /* Jump straight to the value when there is no point animating to it.

       `document.hidden` matters as much as `prefers-reduced-motion` here.
       GSAP's ticker runs on requestAnimationFrame, which a browser throttles
       to a crawl — or suspends outright — in a background tab. Now that the
       figures arrive asynchronously, a dashboard left open in another tab
       would receive its data, start a count-up that never advances, and still
       be showing zeros when the reader came back. */
    if (reduced() || document.hidden || !to.current) {
      at.current.v = value
      node.textContent = fmt.current(value)
      return
    }
    if (at.current.v === value) return

    to.current(value)

    /* The flash marks a figure that just moved. During a drag the value
       changes every frame, so it is rate-limited — otherwise the glow is
       restarted before it can decay and simply reads as "always lit". */
    if (flash) {
      const now = performance.now()
      if (now - lit.current > 400) {
        lit.current = now
        gsap.fromTo(node, { '--lit': 1 }, { '--lit': 0, duration: 0.9, ease: 'power2.out', overwrite: 'auto' })
      }
    }
    // `format` is usually an inline arrow; depending on it would restart this
    // on every render, so the value alone drives it
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value])

  /* Coming back to a backgrounded tab must show the truth, not wherever a
     suspended tween happened to stop. `value` is the authority; the animation
     is only ever a way of arriving at it. */
  useEffect(() => {
    const sync = () => {
      const node = el.current
      if (!node || document.hidden) return
      if (at.current.v !== value) {
        at.current.v = value
        node.textContent = fmt.current(value)
      }
    }
    document.addEventListener('visibilitychange', sync)
    return () => document.removeEventListener('visibilitychange', sync)
  }, [value])

  /* Re-format in place when the LOCALE changes.

     Nothing else here reacts to that: the counting tween is keyed to the
     value, and the value does not change when someone switches language. The
     figure would otherwise stay in the previous locale's digits until the
     next time it happened to move. */
  useEffect(() => {
    const node = el.current
    if (node) node.textContent = fmt.current(at.current.v)
  }, [lang])

  /* `num` carries the --lit glow the flash tween drives, so every counter in
     the panel reacts the same way without each caller opting in.

     The children are FROZEN at their first render. GSAP owns this text node —
     it writes into it every frame while counting — and React must never think
     it owns it too. Rendering `format(from)` live meant that any re-render
     which changed the formatter's output (switching to Persian digits changes
     "0" to "۰") made React reconcile the text node back to the OPENING value,
     wiping whatever the counter had reached. That is why every figure on the
     dashboard reset to zero the moment the language was switched. */
  return (
    <Tag ref={el} className={className ? `num ${className}` : 'num'} {...rest}>
      {seed.current}
    </Tag>
  )
}
