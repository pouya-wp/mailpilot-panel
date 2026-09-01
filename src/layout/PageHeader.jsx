/* The title block every page opens with. The headline is lifted into place —
   the same reveal the original hero used, scaled down so it can run on every
   navigation without wearing out.

   Two things about splitting text that this has to respect:

   * SplitText REPLACES the element's children with its own wrapper spans, so
     the node stops being React's to manage. If React later re-renders a
     different title into it — which is exactly what switching language does —
     the two fight, and the previous language's letters survive as loose spans.
     The `key` on the heading makes React throw the whole node away and build a
     fresh one instead, so there is never a contested node.

   * Persian is CURSIVE. Splitting it per character breaks the joins between
     letters, and a row of inline-block glyphs in an RTL line is laid out
     right-to-left — which is how "Command Center" came out as "retneC dnammoC".
     So the split is per WORD in Persian, which never crosses a join, and per
     character only in Latin.
   ============================================================ */
import { useRef } from 'react'
import { SplitText, gsap, reduced, useGSAP } from '../anim/core'
import { useI18n } from '../i18n'

export default function PageHeader({ title, sub, actions, children }) {
  const box = useRef(null)
  const { lang, rtl } = useI18n()

  useGSAP(
    () => {
      const el = box.current?.querySelector('.phead__title')
      const rest = box.current?.querySelectorAll('.phead__sub, .phead__actions > *')
      if (!el || reduced()) return

      const tl = gsap.timeline()
      let split = null

      try {
        split = SplitText.create(el, { type: rtl ? 'words' : 'chars', mask: rtl ? 'words' : 'chars' })
        const parts = rtl ? split.words : split.chars
        tl.from(parts, { yPercent: 115, duration: 0.72, stagger: rtl ? 0.05 : 0.018, ease: 'glide' })
      } catch {
        // a font that has not resolved can make SplitText throw; the headline
        // simply arrives without the per-part lift rather than not at all
        tl.from(el, { yPercent: 30, opacity: 0, duration: 0.7, ease: 'glide' })
      }

      if (rest?.length) tl.from(rest, { y: 12, opacity: 0, duration: 0.6, stagger: 0.06 }, 0.14)

      return () => {
        tl.kill()
        split?.revert()
      }
    },
    { dependencies: [title, rtl], scope: box }
  )

  return (
    <div className="phead" ref={box}>
      <div className="phead__text">
        {/* keyed so a language change remounts the node instead of asking
            React to reconcile children SplitText has already replaced */}
        <h1 className="phead__title" key={`${lang}:${title}`}>
          {title}
        </h1>
        {sub && <p className="phead__sub">{sub}</p>}
        {children}
      </div>
      {actions && <div className="phead__actions">{actions}</div>}
    </div>
  )
}
