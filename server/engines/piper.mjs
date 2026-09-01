import { spawn } from 'node:child_process'
import { readFile, rm } from 'node:fs/promises'
import { existsSync } from 'node:fs'
import readline from 'node:readline'
import path from 'node:path'
import os from 'node:os'
import crypto from 'node:crypto'
import { mkdirSync } from 'node:fs'

/* ============================================================
   Piper adapter — persistent workers.

   Piper spends ~1.8 s loading a 120 MB voice, so spawning one
   process per request made a two second sentence cost 2.4 s. In
   `--json-input` mode the process stays alive with the model
   resident and accepts one JSON line per sentence, which drops the
   same request to ~0.7 s.

   Each worker prints the output path on stdout when a line is
   finished; that is the completion signal. Jobs are handed to a
   worker one at a time, so stdout lines map to submissions in order.
   ============================================================ */

const BIN = process.env.PIPER_BIN || 'piper'
const MODEL = process.env.PIPER_MODEL || ''
const WORKERS = Number(process.env.PIPER_CONCURRENCY || 2)
const TMP = process.env.PIPER_TMP || path.join(os.tmpdir(), 'piper-out')
mkdirSync(TMP, { recursive: true })

let sampleRate = 22050
let ready = false
let reason = 'not initialised'

const workers = []
const queue = []

export async function init() {
  if (!MODEL) {
    reason = 'PIPER_MODEL is not set'
    return (ready = false)
  }
  if (!existsSync(MODEL)) {
    reason = `model not found at ${MODEL}`
    return (ready = false)
  }
  const cfgPath = MODEL.endsWith('.json') ? MODEL : `${MODEL}.json`
  if (existsSync(cfgPath)) {
    try {
      sampleRate = JSON.parse(await readFile(cfgPath, 'utf8'))?.audio?.sample_rate ?? sampleRate
    } catch {
      /* keep the default */
    }
  }

  try {
    for (let i = 0; i < WORKERS; i++) workers.push(spawnWorker())
  } catch (err) {
    reason = `cannot start ${BIN}: ${err.message}`
    return (ready = false)
  }

  // one throwaway render proves the binary, the voice and the pipe all work
  try {
    await synthesise('Ready.')
    ready = true
    reason = 'ok'
  } catch (err) {
    ready = false
    reason = err.message
  }
  return ready
}

export const status = () => ({
  ready,
  reason,
  engine: 'piper',
  model: MODEL ? path.basename(MODEL) : null,
  workers: WORKERS,
  sampleRate,
})

function spawnWorker() {
  const child = spawn(BIN, ['--model', MODEL, '--json-input'], { stdio: ['pipe', 'pipe', 'pipe'] })
  const w = { child, busy: false, job: null }

  // piper echoes the finished output path, one line per submitted sentence
  readline.createInterface({ input: child.stdout }).on('line', () => {
    const job = w.job
    w.job = null
    w.busy = false
    job?.done()
    pump()
  })

  let err = ''
  child.stderr.on('data', (c) => {
    err += c.toString()
    if (err.length > 4000) err = err.slice(-2000)
  })

  const die = (why) => {
    const job = w.job
    w.job = null
    w.busy = false
    job?.fail(new Error(`${why}: ${err.slice(-300)}`))
    // a dead worker is replaced so one bad line cannot take the service down
    const i = workers.indexOf(w)
    if (i !== -1) {
      workers.splice(i, 1)
      try {
        workers.push(spawnWorker())
      } catch {
        /* the next request reports it */
      }
    }
    pump()
  }
  child.on('error', () => die('piper failed to start'))
  child.on('close', (code) => die(`piper exited (${code})`))

  return w
}

function pump() {
  if (!queue.length) return
  const w = workers.find((x) => !x.busy && x.child.stdin.writable)
  if (!w) return
  const job = queue.shift()
  w.busy = true
  w.job = job
  clearTimeout(job.timer)
  job.timer = setTimeout(() => job.fail(new Error('piper timed out')), 30000)
  w.child.stdin.write(`${JSON.stringify({ text: job.text, output_file: job.file })}\n`)
}

/** Renders `text` to a WAV buffer. */
export function synthesise(text) {
  if (!workers.length) return Promise.reject(new Error(`piper unavailable: ${reason}`))

  const file = path.join(TMP, `${crypto.randomBytes(8).toString('hex')}.wav`)
  return new Promise((resolve, reject) => {
    const job = {
      text: text.replace(/\s+/g, ' ').trim(),
      file,
      timer: null,
      settled: false,
      done: async () => {
        if (job.settled) return
        job.settled = true
        clearTimeout(job.timer)
        try {
          const wav = await readFile(file)
          rm(file, { force: true }).catch(() => {})
          resolve(wav)
        } catch (e) {
          reject(new Error(`piper wrote no file: ${e.message}`))
        }
      },
      fail: (e) => {
        if (job.settled) return
        job.settled = true
        clearTimeout(job.timer)
        rm(file, { force: true }).catch(() => {})
        reject(e)
      },
    }
    queue.push(job)
    pump()
  })
}
