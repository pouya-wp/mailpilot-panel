/* ============================================================
   THE ENTRANCE

   One master timeline for the whole panel, built in App so the
   ordering between components is written in a single place —
   twelve independent mount animations can't be tuned against each
   other, a timeline can.

   The composition assembles the way the light rig implies it was
   lit: the lights come up first, then the frame (top bar, title),
   then the glass, then what is printed on the glass, then the
   controls.

   Under `prefers-reduced-motion` the same timeline is built and
   then jumped to its end — so every element still lands in exactly
   the state the animation would have left it in, with no motion
   and no staggered popping.
   ============================================================ */
import { SplitText, gsap, reduced } from './core'

const q = (root) => gsap.utils.selector(root)

/* Where the timeline's labels actually fall, in seconds from the start.
   A component that owns a property this timeline should not touch can hang
   its own tween off the matching cue and still land in step with everything
   else. Keep in sync with the offsets below. */
export const CUE = {
  slider: 1.3, // 'controls' (1.06) + 0.24
}

export function buildIntro(root) {
  const $ = q(root)
  const splits = []
  const tl = gsap.timeline({ defaults: { ease: 'glide' } })

  /* Split the display type into masked characters. `mask: 'chars'` wraps each
     glyph in a clipping box, so the letters rise out of nothing rather than
     fading in on top of the background. */
  const split = (sel) => {
    const el = $(sel)[0]
    if (!el) return null
    const s = SplitText.create(el, { type: 'chars', mask: 'chars' })
    splits.push(s)
    return s
  }

  /* ---------- 1. the lights come up ---------- */
  tl.from($('.app__orb'), {
    opacity: 0,
    scale: 0.55,
    duration: 1.9,
    stagger: 0.16,
    ease: 'power2.out',
  }).from(root, { '--vignette': 1.8, duration: 1.7, ease: 'power2.out' }, 0)

  /* ---------- 2. the frame ---------- */
  tl.addLabel('frame', 0.18)
    .from($('.brand__mark'), { scale: 0, rotate: -160, opacity: 0, duration: 0.9, ease: 'snap' }, 'frame')
    .from($('.topbar__right > *'), { y: -14, opacity: 0, duration: 0.7, stagger: 0.08 }, 'frame+=0.1')

  const brand = split('.brand__name')
  if (brand) {
    tl.from(brand.chars, { yPercent: 110, opacity: 0, duration: 0.6, stagger: 0.028, ease: 'snap' }, 'frame+=0.06')
  }

  /* ---------- 3. the title ---------- */
  tl.addLabel('hero', 'frame+=0.16')
  const title = split('.hero__title')
  if (title) {
    tl.from(title.chars, { yPercent: 118, duration: 1.05, stagger: 0.035 }, 'hero')
      /* the blur runs on the whole headline rather than the masked chars —
         inside a clip box a blur just gets cut off. Pulling focus like this
         reads as depth of field instead of as a fade. */
      .from($('.hero__title'), { filter: 'blur(1.4rem)', opacity: 0.2, duration: 1.1 }, 'hero')
  }
  tl.from($('.hero__sub'), { y: 12, opacity: 0, duration: 0.8 }, 'hero+=0.34')

  /* ---------- 4. the glass ---------- */
  /* Reading order, not DOM order: the two stat tiles, down the left column,
     then across to the console and down it. */
  const cards = [...$('.stats .card'), ...$('.level'), ...$('.ach'), ...$('.challenge'), ...$('.console > .card')]

  tl.addLabel('glass', 'hero+=0.22')
    .from(cards, { y: 34, scale: 0.965, opacity: 0, duration: 1.0, stagger: 0.075 }, 'glass')
    .from($('.seam__btn'), { scale: 0, rotate: -180, opacity: 0, duration: 0.7, ease: 'snap' }, 'glass+=0.45')

  /* ---------- 5. what is printed on the glass ---------- */
  tl.addLabel('ink', 'glass+=0.34')

  /* the progress spline draws itself left to right */
  if ($('.level__line')[0]) {
    tl.from($('.level__line'), { drawSVG: '0% 0%', duration: 1.5, ease: 'power2.inOut' }, 'ink')
      .from($('.level__area'), { opacity: 0, duration: 1.2 }, 'ink+=0.3')
      .from($('.level__bloom'), { opacity: 0, scale: 0.6, duration: 1.3, stagger: 0.12 }, 'ink')
  }

  tl.from($('.stat__value'), { y: 18, opacity: 0, duration: 0.8, stagger: 0.1 }, 'ink')
    .from($('.stat__hint'), { opacity: 0, y: 8, duration: 0.7, stagger: 0.1 }, 'ink+=0.18')
    .from($('.badge-24h'), { scale: 0.4, opacity: 0, duration: 0.6, stagger: 0.1, ease: 'snap' }, 'ink+=0.1')
    .from($('.level__title'), { y: 16, opacity: 0, duration: 0.8 }, 'ink+=0.05')
    .from($('.level__xp'), { opacity: 0, duration: 0.7 }, 'ink+=0.5')
    .from($('.chip'), { x: 28, opacity: 0, scale: 0.94, duration: 0.75, stagger: 0.07, ease: 'snap' }, 'ink+=0.12')
    /* the envelope stack lands one sheet at a time, top first */
    .from($('.challenge__sheet'), { y: -26, opacity: 0, duration: 0.9, stagger: 0.09, ease: 'snap' }, 'ink+=0.2')
    .from($('.challenge__tag'), { scale: 0.5, opacity: 0, duration: 0.6, ease: 'snap' }, 'ink+=0.1')
    .from($('.challenge__text'), { y: 18, opacity: 0, duration: 0.85 }, 'ink+=0.24')
    .from($('.challenge__caption'), { opacity: 0, duration: 0.7 }, 'ink+=0.5')

  /* ---------- 6. the controls ---------- */
  /* `clearProps` on these two matters beyond tidiness: a leftover inline
     transform makes an element a stacking context, and .field__head is the
     ancestor the open dropdown's z-index resolves against. Left in place it
     traps the menu below the forecast badge. Handing the elements back with no
     transform at all keeps the entrance from quietly changing how the console
     stacks. */
  tl.addLabel('controls', 'ink+=0.16')
    .from(
      $('.field__head'),
      { y: -10, opacity: 0, duration: 0.7, stagger: 0.1, clearProps: 'transform,opacity' },
      'controls'
    )
    .from(
      $('.field__body'),
      { y: 14, opacity: 0, duration: 0.8, stagger: 0.1, clearProps: 'transform,opacity' },
      'controls+=0.08'
    )
    .from($('.forecast'), { scale: 0.86, opacity: 0, duration: 0.8, ease: 'snap' }, 'controls+=0.26')
    .from($('.boost__value'), { y: 14, opacity: 0, duration: 0.8 }, 'controls+=0.1')
    .from($('.slider__ticks span'), { y: -8, opacity: 0, duration: 0.5, stagger: 0.05 }, 'controls+=0.2')
    /* NOTE: the track's own fill is not driven from here. `--p` belongs to
       the slider, which already holds the live boost value; animating it
       from this timeline would mean reading a property another component
       had to have written first, and the entrance would silently fill to
       zero if that order ever changed. RunConsole runs it instead, off the
       CUE.slider cue below. */
    .from($('.info-toggle'), { y: 10, opacity: 0, duration: 0.6 }, 'controls+=0.3')
    .from($('.info__row'), { x: -16, opacity: 0, duration: 0.6, stagger: 0.06 }, 'controls+=0.36')
    .from($('.cta'), { y: 26, opacity: 0, duration: 0.9, ease: 'snap' }, 'controls+=0.42')
    /* one pass of light across the button as it settles */
    .fromTo($('.cta'), { '--sheen': -0.6 }, { '--sheen': 1.6, duration: 1.2, ease: 'power2.inOut' }, 'controls+=0.7')

  /* ---------- 7. the footer ---------- */
  tl.addLabel('foot', 'controls+=0.5')
    .from($('.footer__socials a'), { y: 14, opacity: 0, duration: 0.6, stagger: 0.07 }, 'foot')
    .from($('.footer__right > *'), { y: 14, opacity: 0, duration: 0.6, stagger: 0.07 }, 'foot+=0.08')

  /* ---------- 8. and then it never quite stops ---------- */
  let idle = []
  if (!reduced()) tl.add(() => (idle = idleLoops(root)), 'foot')
  else tl.progress(1).pause()

  return {
    timeline: tl,
    cleanup: () => {
      idle.forEach((t) => t.kill())
      splits.forEach((s) => s.revert())
      tl.kill()
    },
  }
}

/* ============================================================
   Ambient motion — starts once the entrance is done and never
   stops. Nothing here moves far enough to notice directly; the
   point is that the composition is never completely still, which
   is what keeps a dark glass UI from reading as a screenshot.
   ============================================================ */
/* A slow there-and-back drift that only touches the DOM when the value has
   actually changed by a visible amount — half a pixel of travel, or one
   percent of brightness. See the note in idleLoops. */
function drift(el, { x = 0, y = 0, duration, delay = 0, step = 2 }) {
  const at = { x: 0, y: 0 }
  let lastX = null
  let lastY = null
  return gsap.to(at, {
    x,
    y,
    duration,
    delay,
    ease: 'sine.inOut',
    yoyo: true,
    repeat: -1,
    onUpdate: () => {
      const nx = Math.round(at.x * step) / step
      const ny = Math.round(at.y * step) / step
      if (nx === lastX && ny === lastY) return
      lastX = nx
      lastY = ny
      el.style.transform = `translate3d(${nx}px, ${ny}px, 0)`
    },
  })
}

/* The intensity ride. Deliberately on its own tween with its own period, so a
   lamp's brightest moment never lines up with the far end of its travel — that
   coincidence is what makes an animated background look like a loop. */
function breathe(el, { from, to, duration, delay = 0 }) {
  const at = { v: from }
  let last = null
  gsap.set(el, { opacity: from })
  return gsap.to(at, {
    v: to,
    duration,
    delay,
    ease: 'sine.inOut',
    yoyo: true,
    repeat: -1,
    onUpdate: () => {
      const v = Math.round(at.v * 100) / 100
      if (v === last) return
      last = v
      el.style.opacity = v
    },
  })
}

function idleLoops(root) {
  const $ = q(root)
  const tweens = []

  /* ---- the light rig breathes ----
     Two rides per lamp: a slow wander, and a much more noticeable swell in
     brightness. The travel stays small — a lamp you can watch sliding around
     reads as a screensaver — but the intensity is allowed to move a long way,
     because that is what actually looks like light. The key light dips to
     just over half strength and comes back, and everything lit by it (the
     glass, the ring highlights, the vignette) rides along with it.

     The orbs sit at z-index -1, BEHIND every backdrop-filtered card, so any
     pixel they change forces each card's blur to be resampled. Left as
     ordinary tweens, that is a full-screen backdrop recomputation on all
     sixty frames a second, forever. So both rides drive plain objects and
     only write to the DOM when the result has visibly changed — a few writes
     a second instead of sixty, and it looks the same.

     Periods are mutually prime-ish and none of them divides another, so the
     rig never returns to an arrangement you have already seen. */
  const RIG = [
    { travel: 14, move: 23, low: 0.55, high: 1, glow: 13 }, // --a   key spill
    { travel: 9, move: 19, low: 0.42, high: 1, glow: 8.5 }, // --key hot core
    { travel: 17, move: 31, low: 0.6, high: 1, glow: 17 }, // --b   cold fill
    { travel: 12, move: 27, low: 0.5, high: 0.95, glow: 21 }, // --c rim
    { travel: 15, move: 37, low: 0.35, high: 0.85, glow: 11 }, // --d violet
  ]

  $('.app__orb').forEach((orb, i) => {
    const rig = RIG[i] ?? RIG[0]
    tweens.push(
      drift(orb, {
        x: gsap.utils.random(-rig.travel, rig.travel),
        y: gsap.utils.random(-rig.travel * 0.65, rig.travel * 0.65),
        duration: rig.move,
      }),
      breathe(orb, { from: rig.high, to: rig.low, duration: rig.glow, delay: i * 1.7 })
    )
  })

  /* the spline's bloom drifts and swells as if the line were emitting it */
  const bloomA = $('.level__bloom--a')[0]
  const bloomB = $('.level__bloom--b')[0]
  if (bloomA && bloomB) {
    tweens.push(
      drift(bloomA, { x: 8, y: -5, duration: 15 }),
      breathe(bloomA, { from: 1, to: 0.5, duration: 9 }),
      drift(bloomB, { x: -7, y: 4, duration: 19, delay: 1.4 }),
      breathe(bloomB, { from: 0.85, to: 0.45, duration: 12, delay: 2.1 })
    )
  }

  /* the envelope stack hovers, each sheet lagging the one above it */
  $('.challenge__sheet').forEach((g, i) => {
    tweens.push(
      gsap.to(g, {
        y: -3 - i * 1.4,
        duration: 5.2 + i * 0.7,
        ease: 'sine.inOut',
        yoyo: true,
        repeat: -1,
        delay: i * 0.3,
      })
    )
  })

  /* the streak badge stays hot */
  tweens.push(gsap.to($('.chip__num'), { '--pulse': 1, duration: 2.4, ease: 'sine.inOut', yoyo: true, repeat: -1 }))

  return tweens
}
