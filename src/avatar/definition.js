import raw from './onee.avatar.json'

/* ============================================================
   The exported Onee file carries `tipRoundness: 2` and
   `baseRoundness: 2`, but @bible-strong/avatar-core@0.1.0
   validates every roundness as 0…1 and rejects the whole
   definition. Rather than editing the artist's file we clamp on
   load, and say so once in the console — if the cone's tip/base
   looks wrong, re-export with in-range values.
   ============================================================ */

const ROUNDNESS = new Set(['roundness', 'morphRoundness', 'tipRoundness', 'baseRoundness'])
const clamped = []

function normalise(node, path = '') {
  if (Array.isArray(node)) return node.map((v, i) => normalise(v, `${path}/${i}`))
  if (node && typeof node === 'object') {
    const out = {}
    for (const [k, v] of Object.entries(node)) {
      const p = `${path}/${k}`
      if (ROUNDNESS.has(k) && typeof v === 'number' && (v < 0 || v > 1)) {
        clamped.push(`${p}: ${v} → ${Math.min(1, Math.max(0, v))}`)
        out[k] = Math.min(1, Math.max(0, v))
      } else {
        out[k] = normalise(v, p)
      }
    }
    return out
  }
  return node
}

const definition = normalise(raw)

if (clamped.length) {
  console.info(`[avatar] clamped ${clamped.length} out-of-range roundness value(s):\n  ${clamped.join('\n  ')}`)
}

export default definition
