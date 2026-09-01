import http from 'node:http'
import crypto from 'node:crypto'
import { mkdir, readFile, writeFile } from 'node:fs/promises'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import * as engine from './engine.mjs'

/* ============================================================
   Server-side TTS.

   POST /api/tts   { "text": "..." }  -> audio/wav
   GET  /api/tts/health               -> { ready, engine, ... }

   Answers repeat constantly (the same handful of sentences with a
   few numbers swapped), so every render is cached on disk by a hash
   of the text. On a VPS that turns most requests into a file read.
   ============================================================ */

const HERE = path.dirname(fileURLToPath(import.meta.url))
const CACHE = process.env.TTS_CACHE || path.join(HERE, '.cache')
const PORT = Number(process.env.TTS_PORT || 8787)
const HOST = process.env.TTS_HOST || '127.0.0.1'
/** Cap the work a single request can ask for. */
const MAX_CHARS = 600
/** Simple per-IP rate limit: requests per minute. */
const RATE = Number(process.env.TTS_RATE || 60)

const hits = new Map()
function allowed(ip) {
  const now = Date.now()
  const win = hits.get(ip)
  if (!win || now - win.start > 60000) {
    hits.set(ip, { start: now, n: 1 })
    return true
  }
  win.n++
  return win.n <= RATE
}

const keyFor = (text) => crypto.createHash('sha256').update(`v1|${text}`).digest('hex').slice(0, 32)

function send(res, code, body, headers = {}) {
  res.writeHead(code, { 'Cache-Control': 'no-store', ...headers })
  res.end(body)
}

function json(res, code, obj) {
  send(res, code, JSON.stringify(obj), { 'Content-Type': 'application/json' })
}

async function readBody(req) {
  const chunks = []
  let size = 0
  for await (const c of req) {
    size += c.length
    if (size > 64 * 1024) throw new Error('payload too large')
    chunks.push(c)
  }
  return Buffer.concat(chunks).toString('utf8')
}

const server = http.createServer(async (req, res) => {
  // CORS: the built site may be served from a different origin than this API
  res.setHeader('Access-Control-Allow-Origin', process.env.TTS_ORIGIN || '*')
  res.setHeader('Access-Control-Allow-Headers', 'Content-Type')
  res.setHeader('Access-Control-Allow-Methods', 'POST, GET, OPTIONS')
  if (req.method === 'OPTIONS') return send(res, 204, '')

  const url = new URL(req.url, `http://${req.headers.host}`)

  if (url.pathname === '/api/tts/health') {
    return json(res, 200, engine.status())
  }

  if (url.pathname !== '/api/tts' || req.method !== 'POST') {
    return json(res, 404, { error: 'not found' })
  }

  const ip = req.headers['x-forwarded-for']?.split(',')[0]?.trim() || req.socket.remoteAddress || 'unknown'
  if (!allowed(ip)) return json(res, 429, { error: 'rate limited' })

  let text
  try {
    text = JSON.parse(await readBody(req))?.text
  } catch {
    return json(res, 400, { error: 'invalid json' })
  }
  if (typeof text !== 'string' || !text.trim()) return json(res, 400, { error: 'text required' })
  text = text.trim().slice(0, MAX_CHARS)

  const file = path.join(CACHE, `${keyFor(text)}.wav`)
  try {
    const cached = await readFile(file)
    return send(res, 200, cached, { 'Content-Type': 'audio/wav', 'X-TTS-Cache': 'hit' })
  } catch {
    /* miss — render it */
  }

  try {
    const wav = await engine.synthesise(text)
    // best effort: a failed cache write must not fail the response
    writeFile(file, wav).catch(() => {})
    return send(res, 200, wav, { 'Content-Type': 'audio/wav', 'X-TTS-Cache': 'miss' })
  } catch (err) {
    console.error('[tts]', err.message)
    // 503 rather than 500: the client falls back to browser speech on this
    return json(res, 503, { error: 'engine unavailable', detail: err.message })
  }
})

await mkdir(CACHE, { recursive: true })
console.log('[tts] loading engine (first run downloads model weights)...')
const ok = await engine.init()
server.listen(PORT, HOST, () => {
  const s = engine.status()
  console.log(`[tts] listening on http://${HOST}:${PORT}`)
  console.log(`[tts] engine: ${s.engine} — ${ok ? `ready (${s.model}${s.voice ? `, voice ${s.voice}` : ''})` : `UNAVAILABLE: ${s.reason}`}`)
  if (!ok) console.log('[tts] the panel will fall back to browser speech until this is fixed')
})
