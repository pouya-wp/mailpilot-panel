/* Picks the TTS engine. Both adapters expose the same three functions, so
   swapping is an env var — Kokoro for quality, Piper when the VPS is small. */

const NAME = (process.env.TTS_ENGINE || 'kokoro').toLowerCase()

const engine = NAME === 'piper' ? await import('./engines/piper.mjs') : await import('./engines/kokoro.mjs')

export const { init, status, synthesise } = engine
export const engineName = NAME
