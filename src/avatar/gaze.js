/* ============================================================
   Eye tracking + blinking.

   Two runtime facts shape this file:

   1. Blinking only exists inside an animation. core's blinkOpacityAt
      reads `animation.blink` and the playback state's blinkStartedAt,
      so an avatar driven by the `expression` prop never blinks.
   2. A direct `expression` change is tweened with a hardcoded 420 ms
      "smooth" curve. Inside an animation the step carries its own
      transitionMs, so we get to pick.

   So gaze is expressed as animations, not expressions: one single-step
   animation per grid cell, each holding a pose that is a clone of
   `neutral` differing only in head yaw/pitch and eye offset. Same eye
   shape everywhere, so stepping through the grid reads as looking
   around rather than changing mood — and blinking comes for free.

   Runtime caps that bound the grid (exceeding either makes the whole
   definition invalid and the avatar silently disappears):
     expressions  max 128
     animations   max 64
   ============================================================ */

/** Artist animations kept for the chat panel. The joyful ones are deliberately
    left out: they use `joyful-wide`, whose eyes are 76 units tall against the
    neutral 40, which reads as the eyes ballooning rather than a reaction.
    Hover and speech use the synthesised `wink` / `talking` below instead. */
export const KEPT_ANIMATIONS = ['listening', 'thinking']

/** Synthesised, so they share the neutral eye shape and never balloon. */
export const WINK = 'wink'
export const TALKING = 'talking'

/** 11 x 5 = 55 cells; 55 + 2 kept + wink + talking = 59, under the cap of 64. */
const COLS = 11
const ROWS = 5

/* How far the *pose* turns at the extremes. Deliberately small: the grid is
   capped at ~55 cells by the 64-animation limit, so a wide range here would
   quantise into visible 5° jumps. The bulk of the head turn is carried by a
   continuous CSS transform instead (see .agent__tilt), which has no steps —
   this only has to move the eyes within the face. */
const YAW = 13 // left / right
const PITCH = 8 // up / down
/** extra eye travel on top of the head turn */
const EYE_X = 5
const EYE_Y = 7

/* Each grid step blends over this long. Longer than it looks like it should
   be: the CSS tilt already carries the fast motion, so a soft blend here hides
   the quantisation between cells rather than adding lag. */
const TRACK_MS = 260

const BLINK = {
  enabled: true,
  initialDelayMs: 900,
  minIntervalMs: 2400,
  maxIntervalMs: 5600,
  durationMs: 220,
}

const key = (c, r) => `look-c${c}-r${r}`

/** Clone `neutral`, overriding head rotation and per-eye height. */
function pose(base, { headX = 0, headY = 0, left = 1, right = 1 }) {
  return {
    ...base,
    head: { x: headX, y: headY, z: 0 },
    eyes: {
      ...base.eyes,
      left: { ...base.eyes.left, height: base.eyes.left.height * left },
      right: { ...base.eyes.right, height: base.eyes.right.height * right },
    },
    motion: { eyes: 'none', body: 'none' },
  }
}

/**
 * Returns a definition carrying the gaze grid as expressions + animations.
 * The source definition is not modified.
 */
export function withGazeGrid(def) {
  const base = def.expressions.neutral ?? def.expressions[def.expressionOrder[0]]
  const expressions = { ...def.expressions }
  const expressionOrder = [...def.expressionOrder]

  // only the kept moods reach the renderer
  const animations = {}
  const animationOrder = []
  for (const name of KEPT_ANIMATIONS) {
    if (def.animations[name]) {
      animations[name] = def.animations[name]
      animationOrder.push(name)
    }
  }

  for (let r = 0; r < ROWS; r++) {
    for (let c = 0; c < COLS; c++) {
      const nx = COLS === 1 ? 0 : (c / (COLS - 1)) * 2 - 1 // −1 … 1
      const ny = ROWS === 1 ? 0 : (r / (ROWS - 1)) * 2 - 1
      const k = key(c, r)

      expressions[k] = {
        ...base,
        head: { x: -ny * PITCH, y: nx * YAW, z: 0 },
        eyes: {
          ...base.eyes,
          left: { ...base.eyes.left, x: base.eyes.left.x + nx * EYE_X, y: base.eyes.left.y + ny * EYE_Y },
          right: { ...base.eyes.right, x: base.eyes.right.x + nx * EYE_X, y: base.eyes.right.y + ny * EYE_Y },
        },
        motion: { eyes: 'none', body: 'none' },
      }
      expressionOrder.push(k)

      animations[k] = {
        playbackMode: 'loop',
        // one step held for the schema maximum: the pose is static, the only
        // motion is the blink the runtime layers on top
        steps: [{ expression: k, holdMs: 60000, transitionMs: TRACK_MS, transition: 'smooth' }],
        blink: { ...BLINK },
      }
      animationOrder.push(k)
    }
  }

  /* ---- wink: one eye shut for a beat, then back ---- */
  expressions['wink-shut'] = pose(base, { headX: 3, right: 0.22 })
  expressions['wink-open'] = pose(base, { headX: 1 })
  expressionOrder.push('wink-shut', 'wink-open')
  animations[WINK] = {
    playbackMode: 'once',
    steps: [
      { expression: 'wink-shut', holdMs: 110, transitionMs: 90, transition: 'snappy' },
      { expression: 'wink-open', holdMs: 100, transitionMs: 150, transition: 'smooth' },
    ],
    blink: { ...BLINK, initialDelayMs: 4000 },
  }
  animationOrder.push(WINK)

  /* ---- talking: a small nod cycled while speech synthesis plays ---- */
  expressions['talk-up'] = pose(base, { headX: 4, headY: -2 })
  expressions['talk-down'] = pose(base, { headX: -5, headY: 2, left: 0.74, right: 0.74 })
  expressionOrder.push('talk-up', 'talk-down')
  animations[TALKING] = {
    // pingPong so the nod eases back instead of snapping to the first step
    playbackMode: 'pingPong',
    steps: [
      { expression: 'talk-up', holdMs: 100, transitionMs: 110, transition: 'snappy' },
      { expression: 'talk-down', holdMs: 100, transitionMs: 110, transition: 'snappy' },
    ],
    blink: { ...BLINK, minIntervalMs: 1600, maxIntervalMs: 3600 },
  }
  animationOrder.push(TALKING)

  return { ...def, expressions, expressionOrder, animations, animationOrder }
}

/** Nearest grid cell for a direction in −1…1 (+y is down). */
export function gazeKey(dx, dy) {
  const c = Math.round(((Math.max(-1, Math.min(1, dx)) + 1) / 2) * (COLS - 1))
  const r = Math.round(((Math.max(-1, Math.min(1, dy)) + 1) / 2) * (ROWS - 1))
  return key(c, r)
}

/** The centre cell — used before the pointer has been seen. */
export const CENTRE = key((COLS - 1) / 2, (ROWS - 1) / 2)
