import { useCallback, useEffect, useRef, useState } from 'react'
import { createAvatar } from '@bible-strong/avatar-react'
import { validateAvatarDefinition } from '@bible-strong/avatar-core'
import '@bible-strong/avatar-react/styles.css'
import baseDefinition from '../avatar/definition'
import { CENTRE, TALKING, WINK, gazeKey, withGazeGrid } from '../avatar/gaze'
import { answerFor } from '../avatar/answers'
import { canSpeak, probeEngine, speak, stopSpeaking } from '../avatar/speech'
import SupportChat from './SupportChat'
import { useI18n } from '../i18n'
import { useConfig } from '../api/config'
import { gsap, introStarted, reduced, useGSAP } from '../anim/core'

const definition = withGazeGrid(baseDefinition)
let Onee = null
try {
  Onee = createAvatar(definition)
} catch (err) {
  // createAvatar throws on the first issue only; print them all, otherwise the
  // agent just silently vanishes from the corner
  console.error('[avatar] definition rejected:', validateAvatarDefinition(definition)?.issues ?? err)
}

/* Reference distance for a full deflection, as a fraction of the longer
   viewport axis. Normalising per side instead — by the room available left vs
   right — collapses on whichever side the agent is jammed against: with the
   agent near the right edge the gaze jumped from 0 to full within ~60px. A
   single radius keeps the mapping symmetric and continuous everywhere; the
   cramped side simply never reaches full deflection, which is what actually
   looking at a nearby point does. */
const REACH = 0.55

export default function SupportAgent() {
  const { lang, t } = useI18n()
  const { agent, has } = useConfig()
  const [open, setOpen] = useState(false)
  const [gaze, setGaze] = useState(CENTRE)
  const [mood, setMood] = useState(null) // an animation, overrides gaze
  const [muted, setMuted] = useState(false)
  const [speaking, setSpeaking] = useState(false)

  /* Read through a ref so `ask` never changes identity as the panel
     updates. What goes in is deliberately small: the language, the agent's
     name and the module gate. The script is not allowed to quote the
     customer's figures, because it cannot see them — it used to be handed
     a hardcoded "25,000 contacts in VIP Users" and repeat it to everyone. */
  const askStateRef = useRef(null)
  askStateRef.current = { lang, agent: agent?.name, has }

  const box = useRef(null)
  const tilt = useRef(null)
  const frame = useRef(0)
  const point = useRef(null)
  const moodTimer = useRef(null)
  const level = useRef(null) // element carrying the loudness custom property
  // mirrored so the chat callbacks below can stay referentially stable
  const speakingRef = useRef(false)

  /* ---- follow the cursor ---- */
  useEffect(() => {
    const apply = () => {
      frame.current = 0
      const el = box.current
      const p = point.current
      if (!el || !p) return
      const r = el.getBoundingClientRect()
      const cx = r.left + r.width / 2
      const cy = r.top + r.height / 2
      // measured on the longer axis so a wide screen keeps responding across
      // more of the page instead of saturating a third of the way out
      const radius = Math.max(1, Math.max(window.innerWidth, window.innerHeight) * REACH)
      const clamp = (v) => Math.max(-1, Math.min(1, v))
      const nx = clamp((p.x - cx) / radius)
      const ny = clamp((p.y - cy) / radius)

      // The head turn is continuous and written straight to CSS custom
      // properties — going through React state would re-render on every frame,
      // and the pose grid it feeds is too coarse to look smooth on its own.
      const tiltEl = tilt.current
      if (tiltEl) {
        tiltEl.style.setProperty('--gx', nx.toFixed(3))
        tiltEl.style.setProperty('--gy', ny.toFixed(3))
      }

      setGaze(gazeKey(nx, ny)) // only changes when the cell changes
    }

    const onMove = (e) => {
      // keep only the latest position; reading the event inside the frame
      // callback instead would drop the final move
      point.current = { x: e.clientX, y: e.clientY }
      if (!frame.current) frame.current = requestAnimationFrame(apply)
    }

    window.addEventListener('pointermove', onMove, { passive: true })
    return () => {
      window.removeEventListener('pointermove', onMove)
      if (frame.current) cancelAnimationFrame(frame.current)
    }
  }, [])

  /** Play one of the kept animations for a moment, then fall back to tracking. */
  const playMood = useCallback((name, holdMs = 2200) => {
    clearTimeout(moodTimer.current)
    setMood(name)
    if (holdMs > 0) moodTimer.current = setTimeout(() => setMood(null), holdMs)
  }, [])

  useEffect(() => () => clearTimeout(moodTimer.current), [])

  /* ask the server engine once, up front, so the first answer does not pay
     for a round trip that is going to fail */
  useEffect(() => {
    probeEngine()
  }, [])

  const say = useCallback(
    (text) => {
      const stop = () => {
        speakingRef.current = false
        setSpeaking(false)
        setMood(null)
      }
      if (muted || !canSpeak()) {
        // no audio, but the agent should still look like it is delivering
        speakingRef.current = true
        setSpeaking(true)
        playMood(TALKING, 0)
        clearTimeout(moodTimer.current)
        moodTimer.current = setTimeout(stop, Math.min(6000, 400 + text.length * 45))
        return
      }
      speak(text, {
        onStart: () => {
          speakingRef.current = true
          setSpeaking(true)
          playMood(TALKING, 0)
        },
        onLevel: (v) => {
          // written straight to CSS: this runs every frame, and a re-render
          // per frame would be far more work than the effect is worth
          level.current?.style.setProperty('--level', v.toFixed(3))
        },
        onEnd: stop,
      })
    },
    [muted, playMood]
  )

  const ask = useCallback((q) => answerFor(q, askStateRef.current), [])
  const think = useCallback(() => playMood('thinking', 0), [playMood])
  /* never interrupt speech with the idle pose */
  const listen = useCallback(() => {
    if (!speakingRef.current) playMood('listening', 0)
  }, [playMood])

  const close = useCallback(() => {
    setOpen(false)
    stopSpeaking()
    clearTimeout(moodTimer.current)
    setMood(null)
    speakingRef.current = false
    setSpeaking(false)
  }, [])

  useEffect(() => {
    if (!open) return
    const onKey = (e) => e.key === 'Escape' && close()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, close])

  /* ---- arrival, then a permanent hover ----
     The agent is the last thing to appear: it drops into the corner once the
     panel behind it has finished assembling, then never quite settles. The
     float runs on `.agent` itself so it composes with the CSS transition that
     moves the corner position when the chat docks — two different properties,
     no fight over the transform. */
  useGSAP(
    () => {
      const el = box.current
      if (!el || reduced()) return
      let tl = null
      let live = true
      introStarted.then(() => {
        if (!live) return
        tl = gsap.timeline({ delay: 2.6 })
        tl.from(el, { y: 60, scale: 0.7, opacity: 0, duration: 0.95, ease: 'snap' })
          .fromTo(
            el,
            { y: 0 },
            { y: -9, duration: 3.6, ease: 'sine.inOut', yoyo: true, repeat: -1 },
            '>-0.2'
          )
      })
      return () => {
        live = false
        tl?.kill()
      }
    },
    { scope: box }
  )

  if (!Onee) return null

  return (
    <>
      <div
        className={`agent${open ? ' agent--docked' : ''}${speaking ? ' agent--speaking' : ''}`}
        ref={box}
        data-mood={mood ?? gaze}
      >
        <span className="agent__bloom" />
        <span className="agent__wave" ref={level} aria-hidden="true">
          <i />
          <i />
        </span>
        <button
          className="agent__hit"
          onMouseEnter={() => !open && !speaking && playMood(WINK, 900)}
          onClick={() => {
            if (open) close()
            else {
              setOpen(true)
              playMood(WINK, 900)
            }
          }}
          aria-label={open ? t('chat.closeAria') : t('chat.open')}
          aria-expanded={open}
        >
          <span className="agent__tilt" ref={tilt}>
            <Onee
              animation={mood ?? gaze}
              size="100%"
              className="agent__avatar"
              ariaLabel={t('chat.role')}
            />
          </span>
        </button>
      </div>

      <SupportChat
        open={open}
        muted={muted}
        canSpeak={canSpeak()}
        onMute={() => {
          setMuted((m) => {
            if (!m) stopSpeaking()
            return !m
          })
        }}
        onClose={close}
        onAsk={ask}
        onThinking={think}
        onIdle={listen}
        onSay={say}
      />
    </>
  )
}
