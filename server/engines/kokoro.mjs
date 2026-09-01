import { KokoroTTS } from 'kokoro-js'
import { AutoTokenizer, StyleTextToSpeech2Model } from '@huggingface/transformers'
import os from 'node:os'

/* ============================================================
   Kokoro adapter.

   An 82M-parameter model run through onnxruntime. Noticeably more
   natural than Piper, at the cost of RAM and CPU time — on a VPS
   without a GPU budget roughly 1–3 s per sentence at q8.

   Weights are pulled from HuggingFace on first use and cached on
   disk, so the first request after a cold start is slow. `warm()`
   below loads the model at boot to keep that out of the request path.
   ============================================================ */

const MODEL = process.env.KOKORO_MODEL || 'onnx-community/Kokoro-82M-v1.0-ONNX'
/** q8 keeps the download near 90 MB and runs well on CPU; fp32 is ~326 MB. */
const DTYPE = process.env.KOKORO_DTYPE || 'q8'
const DEVICE = process.env.KOKORO_DEVICE || 'cpu'
/** Kokoro ships its own voice set — `ryan` and friends are Piper names. */
const VOICE = process.env.KOKORO_VOICE || 'am_michael'
const CONCURRENCY = Number(process.env.KOKORO_CONCURRENCY || 1)
/* onnxruntime defaults to roughly one thread here, which measured at ~1.5 of
   12 cores busy and ~6.5x realtime. kokoro-js's from_pretrained does not
   forward session_options, so the model is built directly — it only wraps
   StyleTextToSpeech2Model + AutoTokenizer — and the thread count is set. */
const THREADS = Number(process.env.KOKORO_THREADS || Math.max(1, Math.min(8, os.cpus().length - 2)))

let tts = null
let ready = false
let reason = 'not initialised'
let sampleRate = 24000

export async function init() {
  try {
    const session_options = {
      intraOpNumThreads: THREADS,
      interOpNumThreads: 1,
      executionMode: 'sequential',
      graphOptimizationLevel: 'all',
    }
    const [model, tokenizer] = await Promise.all([
      StyleTextToSpeech2Model.from_pretrained(MODEL, { dtype: DTYPE, device: DEVICE, session_options }),
      AutoTokenizer.from_pretrained(MODEL),
    ])
    tts = new KokoroTTS(model, tokenizer)
    const voices = Object.keys(tts.voices ?? {})
    if (voices.length && !voices.includes(VOICE)) {
      reason = `unknown voice "${VOICE}" — available: ${voices.slice(0, 12).join(', ')}`
      return (ready = false)
    }
    ready = true
    reason = 'ok'
    return true
  } catch (err) {
    reason = err.message
    return (ready = false)
  }
}

export const status = () => ({
  ready,
  reason,
  engine: 'kokoro',
  model: MODEL,
  dtype: DTYPE,
  voice: VOICE,
  threads: THREADS,
  sampleRate,
  voices: tts ? Object.keys(tts.voices ?? {}) : [],
})

let running = 0
const queue = []
const slot = () =>
  new Promise((resolve) => {
    if (running < CONCURRENCY) {
      running++
      resolve()
    } else queue.push(resolve)
  })
function release() {
  running--
  const next = queue.shift()
  if (next) {
    running++
    next()
  }
}

/** Renders `text` to a WAV buffer. */
export async function synthesise(text, voice = VOICE) {
  if (!ready) throw new Error(`kokoro unavailable: ${reason}`)
  await slot()
  try {
    const audio = await tts.generate(text, { voice })
    sampleRate = audio.sampling_rate ?? sampleRate
    // RawAudio.toWav() returns an ArrayBuffer with the header already in place
    return Buffer.from(await audio.toWav())
  } finally {
    release()
  }
}
