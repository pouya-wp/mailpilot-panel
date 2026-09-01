/* ============================================================
   Reusable motion behaviours.

   Everything here is pointer/state driven — the one-shot entrance
   choreography lives in intro.js instead. All of these are
   no-ops under `prefers-reduced-motion`.
   ============================================================ */
import { useCallback, useEffect, useRef } from 'react'
import { gsap, reduced } from './core'

/* ------------------------------------------------------------
   useTilt — the card leans toward the pointer.

   Rotation and a small lift, and deliberately NO scale: a card that
   grows under the cursor reads as the panel resizing, and next to a
   fixed grid the change in size is the only thing you notice.

   The rotation goes through gsap.quickTo. pointermove fires more
   often than the display refreshes, so quickTo's single retargeted
   tween coalesces those into one interpolated write per frame,
   instead of spawning a tween per event.
   ------------------------------------------------------------ */
export function useTilt({ max = 5, lift = 5 } = {}) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el || reduced()) return

    const rx = gsap.quickTo(el, 'rotationX', { duration: 0.5, ease: 'power3' })
    const ry = gsap.quickTo(el, 'rotationY', { duration: 0.5, ease: 'power3' })
    const y = gsap.quickTo(el, 'y', { duration: 0.5, ease: 'power3' })
    gsap.set(el, { transformPerspective: 900, transformOrigin: '50% 50%' })

    /* The card does not move in layout, so its box is measured on enter
       rather than on every move — a getBoundingClientRect() per pointermove
       is a forced synchronous layout, and this panel already has the agent
       tracking the cursor too. */
    let box = null
    const enter = () => {
      box = el.getBoundingClientRect()
      y(-lift)
    }

    const move = (e) => {
      if (!box) box = el.getBoundingClientRect()
      const nx = (e.clientX - box.left) / box.width - 0.5
      const ny = (e.clientY - box.top) / box.height - 0.5
      ry(nx * 2 * max)
      rx(-ny * 2 * max)
    }

    const leave = () => {
      box = null
      rx(0)
      ry(0)
      y(0)
    }

    el.addEventListener('pointerenter', enter)
    el.addEventListener('pointermove', move)
    el.addEventListener('pointerleave', leave)
    return () => {
      el.removeEventListener('pointerenter', enter)
      el.removeEventListener('pointermove', move)
      el.removeEventListener('pointerleave', leave)
      gsap.killTweensOf(el)
    }
  }, [max, lift])

  return ref
}

/* ------------------------------------------------------------
   useMagnetic — the control leans toward the cursor while it is
   near, then springs back. Applied to the round buttons, where the
   pull reads as weight rather than as a gimmick.
   ------------------------------------------------------------ */
export function useMagnetic({ strength = 0.32, radius = 1.6, scale = 1.06 } = {}) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el || reduced()) return

    const x = gsap.quickTo(el, 'x', { duration: 0.45, ease: 'power3' })
    const y = gsap.quickTo(el, 'y', { duration: 0.45, ease: 'power3' })
    let inside = false

    /* The listener is on `window` — it has to be, or the pull could never
       begin before the pointer was already on the button. That means it runs
       for every mouse move anywhere on the page, so it must not measure:
       getBoundingClientRect() there is a forced synchronous layout on each
       event, and this panel has a pointermove handler on the agent as well.

       The button never moves in layout (only by transform, which this hook
       owns and which does not affect the box), so the centre is measured once
       and refreshed only when the page geometry can actually have changed. */
    let cx = 0
    let cy = 0
    let reach = 0
    const measure = () => {
      const r = el.getBoundingClientRect()
      // undo our own transform so the resting centre is what gets cached
      cx = r.left + r.width / 2 - gsap.getProperty(el, 'x')
      cy = r.top + r.height / 2 - gsap.getProperty(el, 'y')
      reach = Math.max(r.width, r.height) * radius
    }
    measure()

    const move = (e) => {
      const dx = e.clientX - cx
      const dy = e.clientY - cy
      // squared compare: no Math.hypot per event
      const near = dx * dx + dy * dy < reach * reach

      if (near) {
        if (!inside) {
          inside = true
          gsap.to(el, { scale, duration: 0.35, ease: 'snap' })
        }
        x(dx * strength)
        y(dy * strength)
      } else if (inside) {
        inside = false
        x(0)
        y(0)
        gsap.to(el, { scale: 1, duration: 0.55, ease: 'elastic.out(1, 0.55)' })
      }
    }

    window.addEventListener('pointermove', move, { passive: true })
    window.addEventListener('resize', measure)
    return () => {
      window.removeEventListener('pointermove', move)
      window.removeEventListener('resize', measure)
      gsap.killTweensOf(el)
    }
  }, [strength, radius, scale])

  return ref
}

/* ------------------------------------------------------------
   usePress — a physical click. Scales down on press and releases
   with a short spring, independent of any hover tween running.
   ------------------------------------------------------------ */
export function usePress({ to = 0.94 } = {}) {
  const ref = useRef(null)

  useEffect(() => {
    const el = ref.current
    if (!el || reduced()) return
    const down = () => gsap.to(el, { scale: to, duration: 0.12, ease: 'power2.out', overwrite: 'auto' })
    const up = () => gsap.to(el, { scale: 1, duration: 0.5, ease: 'elastic.out(1, 0.5)', overwrite: 'auto' })
    el.addEventListener('pointerdown', down)
    el.addEventListener('pointerup', up)
    el.addEventListener('pointercancel', up)
    el.addEventListener('pointerleave', up)
    return () => {
      el.removeEventListener('pointerdown', down)
      el.removeEventListener('pointerup', up)
      el.removeEventListener('pointercancel', up)
      el.removeEventListener('pointerleave', up)
    }
  }, [to])

  return ref
}

/* ------------------------------------------------------------
   useRipple — returns a fire(originEvent) that expands a ring from
   the click point. The ring is a throwaway element so several can
   overlap without fighting over one node.
   ------------------------------------------------------------ */
export function useRipple(className = 'ripple') {
  const ref = useRef(null)

  return [
    ref,
    useCallback(
      (e) => {
        const host = ref.current
        if (!host || reduced()) return
        const r = host.getBoundingClientRect()
        const ring = document.createElement('span')
        ring.className = className
        // fall back to the centre for keyboard activation, which has no point
        const px = e?.clientX ? e.clientX - r.left : r.width / 2
        const py = e?.clientY ? e.clientY - r.top : r.height / 2
        ring.style.left = `${px}px`
        ring.style.top = `${py}px`
        host.appendChild(ring)
        gsap.fromTo(
          ring,
          { scale: 0, opacity: 0.55 },
          {
            scale: 1,
            opacity: 0,
            duration: 0.75,
            ease: 'power2.out',
            onComplete: () => ring.remove(),
          }
        )
      },
      [className]
    ),
  ]
}
