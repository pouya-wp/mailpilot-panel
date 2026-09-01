import { useEffect, useRef, useState } from 'react'
import { OPENERS } from '../avatar/answers'
import { gsap, reduced, useGSAP } from '../anim/core'
import { usePress } from '../anim/hooks'
import { loc, useI18n } from '../i18n'

const SUGGESTIONS = [
  { en: 'What can the agent do?', fa: 'ایجنت چه کارهایی می‌تواند بکند؟' },
  { en: 'Who will this be sent to?', fa: 'این برای چه کسانی فرستاده می‌شود؟' },
  { en: 'How do I send a campaign?', fa: 'چطور یک کمپین بفرستم؟' },
]

export default function SupportChat({ open, muted, canSpeak, onMute, onClose, onAsk, onThinking, onIdle, onSay }) {
  const { t, lang } = useI18n()
  const [log, setLog] = useState([])
  const [draft, setDraft] = useState('')
  const [busy, setBusy] = useState(false)
  const panel = useRef(null)
  const scroller = useRef(null)
  const input = useRef(null)
  const timer = useRef(null)
  const send = usePress({ to: 0.88 })

  /* greet on first open, and hand the mic back when closed */
  useEffect(() => {
    if (!open) return
    setLog((l) => (l.length ? l : [{ from: 'bot', text: OPENERS[Math.floor(Math.random() * OPENERS.length)] }]))
    onIdle?.()
    const t = setTimeout(() => input.current?.focus(), 420)
    return () => clearTimeout(t)
  }, [open, onIdle])

  useEffect(() => () => clearTimeout(timer.current), [])

  /* ---- the panel ----
     Opens from the corner the agent sits in, and the header, chips and
     composer are dealt in behind the panel itself so it reads as a thing
     unfolding rather than a rectangle fading up. */
  useGSAP(
    () => {
      const el = panel.current
      if (!el) return
      const parts = gsap.utils.toArray('.chat__head, .chat__log, .chat__chips, .chat__form', el)

      if (reduced()) {
        gsap.set(el, { opacity: open ? 1 : 0, y: 0 })
        gsap.set(parts, { opacity: 1, y: 0 })
        return
      }

      /* Rises and fades — no scale. This is the last element in the panel
         still carrying a backdrop-filter (it earns it: it sits over card text,
         where the blur is doing real work). Scaling a backdrop-filtered layer
         is what makes Chrome tear along its edges, so the panel is only ever
         translated while it is blurred. */
      const tl = gsap.timeline()
      if (open) {
        tl.fromTo(el, { opacity: 0, y: 40 }, { opacity: 1, y: 0, duration: 0.5, ease: 'snap' }).from(
          parts,
          { opacity: 0, y: 12, duration: 0.4, stagger: 0.055 },
          0.1
        )
      } else {
        tl.to(el, { opacity: 0, y: 30, duration: 0.3, ease: 'power2.in' })
      }
      /* NOTE: no manual kill. useGSAP reverts the context on cleanup, which
         is what puts these styles back; killing first strands the log at
         opacity 0 and the chat comes up empty. */
    },
    { dependencies: [open], scope: panel }
  )

  /* New bubbles arrive from the side they belong to.
     Deliberately a plain effect, not useGSAP: a scoped context would revert
     the previous bubble's tween every time the next message lands, and the
     log would flicker as it filled. These tweens are one-shot and own
     nothing that needs restoring. */
  useEffect(() => {
    const last = scroller.current?.lastElementChild
    if (!last || reduced()) return
    const mine = last.classList.contains('bubble--me')
    gsap.from(last, {
      opacity: 0,
      y: 12,
      x: mine ? 16 : -16,
      duration: 0.45,
      ease: 'snap',
    })
  }, [log.length, busy])

  useEffect(() => {
    const el = scroller.current
    if (!el) return
    if (reduced()) {
      el.scrollTop = el.scrollHeight
      return
    }
    /* `overwrite: 'auto'`, NOT `true`. Plain `true` kills every other tween
       on this element, and the element is also the one the panel's open
       timeline is fading in — so the first message to arrive would take the
       log's own reveal down with it and the chat came up empty. 'auto' only
       clears a competing scroll. */
    gsap.to(el, { scrollTo: { y: 'max' }, duration: 0.5, ease: 'glide', overwrite: 'auto' })
  }, [log, busy])

  const ask = (question) => {
    const q = question.trim()
    if (!q || busy) return
    setDraft('')
    setLog((l) => [...l, { from: 'me', text: q }])
    setBusy(true)
    onThinking?.()

    // a beat of "thinking" so the reply doesn't snap in instantly
    timer.current = setTimeout(() => {
      const answer = onAsk(q)
      setLog((l) => [...l, { from: 'bot', text: answer }])
      setBusy(false)
      onSay?.(answer)
    }, 520)
  }

  return (
    <section className={`chat${open ? ' chat--open' : ''}`} ref={panel} aria-hidden={!open}>
      <header className="chat__head">
        <div>
          <h2 className="chat__title">Onee</h2>
          <p className="chat__sub">Support agent</p>
        </div>
        <div className="chat__tools">
          {canSpeak && (
            <button
              className={`chat__icon${muted ? ' chat__icon--off' : ''}`}
              onClick={onMute}
              aria-label={muted ? 'Unmute voice' : 'Mute voice'}
            >
              {muted ? <SpeakerOff /> : <Speaker />}
            </button>
          )}
          <button className="chat__icon" onClick={onClose} aria-label={t('g.close')}>
            <Close />
          </button>
        </div>
      </header>

      <div className="chat__log" ref={scroller}>
        {log.map((m, i) => (
          <p key={i} className={`bubble bubble--${m.from}`}>
            {m.text}
          </p>
        ))}
        {busy && (
          <p className="bubble bubble--bot bubble--typing">
            <i /><i /><i />
          </p>
        )}
      </div>

      {log.length <= 1 && (
        <div className="chat__chips">
          {SUGGESTIONS.map((s) => (
            <button key={s.en} className="chat__chip" onClick={() => ask(loc(s, lang))}>
              {loc(s, lang)}
            </button>
          ))}
        </div>
      )}

      <form
        className="chat__form"
        onSubmit={(e) => {
          e.preventDefault()
          ask(draft)
        }}
      >
        <input
          ref={input}
          className="chat__input"
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          placeholder={t('chat.placeholder')}
          aria-label={t('chat.yourQuestion')}
        />
        <button className="chat__send" ref={send} type="submit" disabled={!draft.trim() || busy} aria-label={t('chat.send')}>
          <Send />
        </button>
      </form>
    </section>
  )
}

/* No width/height here on purpose. Every length in this panel is a fluid rem
   that tracks the viewport, and these four were the only icons in the app
   pinned to absolute pixels — so they kept their size while the buttons around
   them grew and shrank, and ended up filling their button edge to edge. The
   viewBox carries the geometry; agent.css gives them a size that scales. */
const stroke = { fill: 'none', stroke: 'currentColor', strokeWidth: 1.7, strokeLinecap: 'round', strokeLinejoin: 'round' }

const Close = () => (
  <svg viewBox="0 0 24 24" {...stroke}>
    <path d="M6 6l12 12M18 6L6 18" />
  </svg>
)
const Send = () => (
  <svg viewBox="0 0 24 24" {...stroke}>
    <path d="M4 12l16-8-6 8 6 8-16-8z" />
  </svg>
)
const Speaker = () => (
  <svg viewBox="0 0 24 24" {...stroke}>
    <path d="M5 9.5h3l4-3.5v12l-4-3.5H5z" />
    <path d="M16 9.5a3.4 3.4 0 010 5M18.4 7a6.8 6.8 0 010 10" />
  </svg>
)
const SpeakerOff = () => (
  <svg viewBox="0 0 24 24" {...stroke}>
    <path d="M5 9.5h3l4-3.5v12l-4-3.5H5z" />
    <path d="M16 9.5l4.5 5M20.5 9.5l-4.5 5" />
  </svg>
)
