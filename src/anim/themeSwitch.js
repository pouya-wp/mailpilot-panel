/* ============================================================
   THE THEME SWITCH — a circle that opens from the button.

   The whole page is snapshotted, the new palette is painted
   underneath, and a growing circle wipes the old one away from
   wherever the reader clicked. Because the browser does the
   snapshotting, every part of the panel changes together — the
   rail, the charts, the orbs — instead of a hundred separate CSS
   transitions arriving at slightly different times, which is what
   makes a theme toggle look cheap.

   Three details this depends on and one thing to know:

   * THE DOM MUST CHANGE SYNCHRONOUSLY inside the callback. The
     browser takes the "before" snapshot, runs the callback, then
     takes the "after" one. React's `useEffect` runs too late for
     that, so the attribute is written by hand here rather than
     waiting for the effect that normally owns it. Setting the
     same value twice is harmless.

   * THE RADIUS IS THE DISTANCE TO THE FURTHEST CORNER. Anything
     smaller leaves a wedge of the old theme in a corner at the
     end of the animation.

   * THE ANIMATION IS ON `::view-transition-new(root)`, so the
     circle reveals the NEW theme over the old. Animating the old
     one instead would shrink the previous palette away, which
     reads as leaving rather than arriving.

   Support: `startViewTransition` exists in Chromium and Safari
   and not yet in Firefox. Where it is missing, and for anyone who
   asked for less motion, the theme just changes. That is the
   correct fallback — the feature is the theme, not the circle.
   ============================================================ */
import { reduced } from './core'

const DURATION = 560

/**
 * Swap the theme with a circular reveal.
 *
 * @param {'dark'|'light'} next   the theme to move to
 * @param {() => void} commit     tell React about it
 * @param {Element|null} origin   the control that was clicked
 */
export function circularThemeSwitch(next, commit, origin) {
  const apply = () => {
    /* By hand, not via the effect: the snapshot is taken the moment this
       callback returns, and a passive effect has not run by then. */
    document.documentElement.dataset.theme = next
    commit()
  }

  if (typeof document === 'undefined' || !document.startViewTransition || reduced()) {
    apply()
    return
  }

  const { x, y } = centreOf(origin)
  const radius = Math.hypot(
    Math.max(x, window.innerWidth - x),
    Math.max(y, window.innerHeight - y)
  )

  /* A transition already running means the reader is clicking faster than the
     animation; skipping straight to the value beats queueing circles. */
  document.documentElement.classList.add('theme-switching')

  const transition = document.startViewTransition(apply)

  transition.ready
    .then(() => {
      document.documentElement.animate(
        {
          clipPath: [
            `circle(0px at ${x}px ${y}px)`,
            `circle(${radius}px at ${x}px ${y}px)`,
          ],
        },
        {
          duration: DURATION,
          easing: 'cubic-bezier(0.22, 1, 0.36, 1)',
          pseudoElement: '::view-transition-new(root)',
        }
      )
    })
    .catch(() => {
      /* A transition can be abandoned — another one starting, the tab hiding.
         The theme has already been applied by then, so there is nothing to
         recover, only the class to clear below. */
    })

  transition.finished
    .finally(() => {
      document.documentElement.classList.remove('theme-switching')
    })
    /* `finished` REJECTS on a skipped or abandoned transition — a hidden tab
       is the common one, since the browser refuses to run a transition it
       cannot paint. `.finally()` forwards that rejection, so without this the
       console fills with unhandled rejections every time someone toggles the
       theme in a background tab. */
    .catch(() => {})
}

/** Where the circle starts. Falls back to the top edge if there is no origin. */
function centreOf(origin) {
  const rect = origin?.getBoundingClientRect?.()
  if (!rect || (!rect.width && !rect.height)) {
    return { x: window.innerWidth / 2, y: 0 }
  }
  return { x: rect.left + rect.width / 2, y: rect.top + rect.height / 2 }
}
