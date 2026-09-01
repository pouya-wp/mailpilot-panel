/* ============================================================
   Speech.

   Primary path is the server engine (Piper on the VPS): POST the
   text, get a WAV, play it through WebAudio. An AnalyserNode on the
   way to the speakers gives the real loudness envelope, which is
   what drives the talking animation — so the avatar reacts to the
   actual audio rather than to a guessed rhythm.

   If the server is unreachable or has no engine, this falls back to
   the browser's speechSynthesis so the feature still works locally.
   The fallback has no waveform, so its level is synthesised from
   word boundaries instead.
   ============================================================ */

/* `/api` now belongs to the Python backend, so the voice server has its
   own proxy prefix — pointing this at /api/tts asked the wrong server. */
const ENDPOINT = import.meta.env.VITE_TTS_URL || '/tts'
const synth = typeof window !== 'undefined' ? window.speechSynthesis : null

export const canSpeak = () => true

let ctx = null
let current = null // { source, raf } for the server path
let serverOk = null // null = unknown, true/false once probed

function audioContext() {
  if (!ctx) ctx = new (window.AudioContext || window.webkitAudioContext)()
  if (ctx.state === 'suspended') ctx.resume()
  return ctx
}

/** Probes the engine once so we do not pay a failed request per sentence. */
export async function probeEngine() {
  if (serverOk !== null) return serverOk
  try {
    const r = await fetch(`${ENDPOINT}/health`, { method: 'GET' })
    serverOk = r.ok ? !!(await r.json())?.ready : false
  } catch {
    serverOk = false
  }
  return serverOk
}

export function stopSpeaking() {
  if (current) {
    cancelAnimationFrame(current.raf)
    try {
      current.source.onended = null
      current.source.stop()
    } catch {
      /* already finished */
    }
    current = null
  }
  synth?.cancel()
}

/**
 * Speaks `text`.
 * @param onStart  called once audio begins
 * @param onLevel  0..1 loudness, every frame while speaking
 * @param onEnd    called when playback finishes, is cancelled, or fails
 */
export async function speak(text, { onStart, onEnd, onLevel } = {}) {
  stopSpeaking()
  if (!text) return onEnd?.()

  if (serverOk !== false) {
    try {
      const res = await fetch(ENDPOINT, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text }),
      })
      if (!res.ok) throw new Error(`tts ${res.status}`)
      serverOk = true
      return playBuffer(await res.arrayBuffer(), { onStart, onEnd, onLevel })
    } catch (err) {
      if (serverOk === null) console.info('[tts] server engine unavailable, using browser speech:', err.message)
      serverOk = false
    }
  }

  return browserSpeak(text, { onStart, onEnd, onLevel })
}

async function playBuffer(arrayBuffer, { onStart, onEnd, onLevel }) {
  const ac = audioContext()
  const buffer = await ac.decodeAudioData(arrayBuffer)

  const source = ac.createBufferSource()
  source.buffer = buffer

  const analyser = ac.createAnalyser()
  analyser.fftSize = 1024
  analyser.smoothingTimeConstant = 0.75
  const data = new Uint8Array(analyser.fftSize)

  source.connect(analyser)
  analyser.connect(ac.destination)

  const tick = () => {
    analyser.getByteTimeDomainData(data)
    // RMS around the 128 midpoint, scaled into a usable 0..1 range
    let sum = 0
    for (let i = 0; i < data.length; i++) {
      const v = (data[i] - 128) / 128
      sum += v * v
    }
    const rms = Math.sqrt(sum / data.length)
    onLevel?.(Math.min(1, rms * 3.2))
    current.raf = requestAnimationFrame(tick)
  }

  const done = () => {
    if (!current) return
    cancelAnimationFrame(current.raf)
    current = null
    onLevel?.(0)
    onEnd?.()
  }

  source.onended = done
  current = { source, raf: 0 }
  source.start()
  onStart?.()
  current.raf = requestAnimationFrame(tick)
}

/* ---- fallback: the browser's own voices ---- */
let voice = null
function pickVoice() {
  if (voice || !synth) return voice
  const voices = synth.getVoices()
  if (!voices.length) return null
  voice =
    voices.find((v) => /en/i.test(v.lang) && /natural|neural|google/i.test(v.name)) ??
    voices.find((v) => /^en/i.test(v.lang)) ??
    voices[0]
  return voice
}

function browserSpeak(text, { onStart, onEnd, onLevel }) {
  if (!synth) return onEnd?.()
  const u = new SpeechSynthesisUtterance(text)
  const v = pickVoice()
  if (v) {
    u.voice = v
    u.lang = v.lang
  }
  u.rate = 1.02
  u.pitch = 1.05
  u.onstart = () => onStart?.()
  // no waveform here, so fake a pulse on each word
  u.onboundary = () => {
    onLevel?.(0.85)
    setTimeout(() => onLevel?.(0.15), 90)
  }
  u.onend = () => {
    onLevel?.(0)
    onEnd?.()
  }
  u.onerror = () => {
    onLevel?.(0)
    onEnd?.()
  }
  synth.speak(u)
}
