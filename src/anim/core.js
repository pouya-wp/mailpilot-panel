/* ============================================================
   GSAP setup — one place that registers plugins, names the
   eases the whole panel shares, and answers "is motion wanted?".

   Every other module in src/anim imports gsap FROM HERE so the
   registration can never be skipped by import order.
   ============================================================ */
import { gsap } from 'gsap'
import { useGSAP } from '@gsap/react'
import { CustomEase } from 'gsap/CustomEase'
import { DrawSVGPlugin } from 'gsap/DrawSVGPlugin'
import { MotionPathPlugin } from 'gsap/MotionPathPlugin'
import { ScrollToPlugin } from 'gsap/ScrollToPlugin'
import { Physics2DPlugin } from 'gsap/Physics2DPlugin'
import { SplitText } from 'gsap/SplitText'

gsap.registerPlugin(useGSAP, CustomEase, DrawSVGPlugin, MotionPathPlugin, ScrollToPlugin, Physics2DPlugin, SplitText)

/* A cubic-bezier(x1,y1,x2,y2) is literally the SVG path `M0,0 C x1,y1 x2,y2 1,1`,
   so these are the exact curves the CSS transitions used, now reusable by name. */
CustomEase.create('glide', 'M0,0 C0.16,1 0.3,1 1,1') // long, expo-ish settle — the house ease
CustomEase.create('soft', 'M0,0 C0.4,0 0.2,1 1,1') // material-ish, for value changes
CustomEase.create('snap', 'M0,0 C0.2,0.9 0.3,1.25 1,1') // slight overshoot, for pops
CustomEase.create('swift', 'M0,0 C0.62,0 0.2,1 1,1') // fast in/out, for state flips

gsap.defaults({ ease: 'glide', duration: 0.7 })

/* SVG transforms are authored around the shape's own centre everywhere here. */
gsap.config({ nullTargetWarn: false })

const QUERY = '(prefers-reduced-motion: reduce)'

/** True when the visitor asked the OS for less movement. */
export const reduced = () => typeof window !== 'undefined' && window.matchMedia(QUERY).matches

/** Wait for the webfonts before measuring text — SplitText on a fallback face
 *  splits at the wrong glyph widths and the reveal jumps when Outfit lands. */
export const fontsReady = () => {
  if (typeof document === 'undefined' || !document.fonts) return Promise.resolve()
  return Promise.race([document.fonts.ready, new Promise((r) => setTimeout(r, 1200))])
}

/* ------------------------------------------------------------
   The entrance is held back until the webfonts resolve, so it does
   not start at mount time. Anything that has to land *with* the
   choreography rather than before it — the counters, mainly — waits
   on this instead of guessing a delay.
   ------------------------------------------------------------ */
let startIntro
export const introStarted = new Promise((resolve) => {
  startIntro = resolve
})
export const markIntroStarted = () => startIntro()

export { gsap, useGSAP, SplitText }
