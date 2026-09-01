/* ============================================================
   THE ROOM TONE

   A slow, warm pad that plays under the panel. It is synthesised in
   the browser rather than streamed from a file, for three reasons:

   * nothing to ship — no megabyte of audio on a panel whose whole
     point is that it loads as one screen;
   * nothing to licence;
   * no loop point. The progression walks a fixed set of chords but
     the voicing, the filter movement and the shimmer are all on
     their own slow, unrelated cycles, so it never arrives back at a
     bar you recognise.

   Everything runs on the audio thread. The only main-thread work is
   one scheduling callback per chord, roughly every ten seconds.
   ============================================================ */

/* Equal temperament from A4 = 440. Notes are written "A2", "C#4". */
const SEMITONE = { C: 0, D: 2, E: 4, F: 5, G: 7, A: 9, B: 11 }
const hz = (note) => {
  const [, letter, accidental, octave] = /^([A-G])(#|b)?(-?\d)$/.exec(note)
  const n = SEMITONE[letter] + (accidental === '#' ? 1 : accidental === 'b' ? -1 : 0)
  return 440 * 2 ** ((n + (Number(octave) - 4) * 12 - 9) / 12)
}

/* Minor ninths and major sevenths, kept low and open. The bass note is
   listed first and gets its own sine an octave below the pad. */
const PROGRESSION = [
  { bass: 'A1', pad: ['A3', 'C4', 'E4', 'B4'] },
  { bass: 'F1', pad: ['F3', 'A3', 'C4', 'E4'] },
  { bass: 'D1', pad: ['D3', 'F3', 'A3', 'E4'] },
  { bass: 'E1', pad: ['E3', 'G3', 'B3', 'D4'] },
]

const CHORD = 11 // seconds per chord
const FADE = 3.5 // crossfade between chords, and the master fade in/out

/** Impulse response for the reverb: exponentially decaying stereo noise.
 *  Cheap to generate, and a long soft tail is most of what makes a pad
 *  sound like it is in a room rather than in a speaker. */
function impulse(ctx, seconds = 3.4, decay = 2.6) {
  const n = Math.floor(ctx.sampleRate * seconds)
  const buffer = ctx.createBuffer(2, n, ctx.sampleRate)
  for (let ch = 0; ch < 2; ch++) {
    const data = buffer.getChannelData(ch)
    for (let i = 0; i < n; i++) {
      data[i] = (Math.random() * 2 - 1) * (1 - i / n) ** decay
    }
  }
  return buffer
}

/* The default level is deliberately low. This plays under a working panel for
   hours at a time, not as a demo you listen to once — anything you notice on
   the second hour is too loud on the first. */
export function createAmbience({ volume = 0.085 } = {}) {
  let ctx = null
  let master = null
  let bus = null
  let timer = null
  let step = 0
  let playing = false

  /* ---- one chord ----
     Each note is two saws detuned a few cents apart: the beating between
     them is what stops a synth pad sounding like a held organ note. They
     share one lowpass whose cutoff opens and closes across the chord's
     life, so the chord breathes rather than just sounding. */
  const voice = (freq, at, length, gain) => {
    const filter = ctx.createBiquadFilter()
    filter.type = 'lowpass'
    filter.Q.value = 0.7
    filter.frequency.setValueAtTime(300, at)
    filter.frequency.linearRampToValueAtTime(760 + Math.random() * 260, at + length * 0.55)
    filter.frequency.linearRampToValueAtTime(340, at + length)

    const env = ctx.createGain()
    env.gain.setValueAtTime(0, at)
    env.gain.linearRampToValueAtTime(gain, at + FADE)
    env.gain.setValueAtTime(gain, at + length - FADE)
    env.gain.linearRampToValueAtTime(0, at + length)

    filter.connect(env).connect(bus)

    return [-6, 6].map((cents) => {
      const osc = ctx.createOscillator()
      osc.type = 'triangle'
      osc.frequency.value = freq
      osc.detune.value = cents + (Math.random() * 4 - 2)
      osc.connect(filter)
      osc.start(at)
      osc.stop(at + length + 0.1)
      osc.onended = () => {
        osc.disconnect()
        filter.disconnect()
        env.disconnect()
      }
      return osc
    })
  }

  const sub = (freq, at, length) => {
    const env = ctx.createGain()
    env.gain.setValueAtTime(0, at)
    env.gain.linearRampToValueAtTime(0.28, at + FADE)
    env.gain.setValueAtTime(0.28, at + length - FADE)
    env.gain.linearRampToValueAtTime(0, at + length)
    env.connect(bus)

    const osc = ctx.createOscillator()
    osc.type = 'sine'
    osc.frequency.value = freq
    osc.connect(env)
    osc.start(at)
    osc.stop(at + length + 0.1)
    osc.onended = () => {
      osc.disconnect()
      env.disconnect()
    }
    return [osc]
  }

  /* a high partial that wanders in and out over the top of the pad —
     the one voice that is not locked to the chord's rhythm */
  const shimmer = (freq, at, length) => {
    const env = ctx.createGain()
    env.gain.setValueAtTime(0, at)
    env.gain.linearRampToValueAtTime(0.03, at + length * 0.5)
    env.gain.linearRampToValueAtTime(0, at + length)
    env.connect(bus)

    const osc = ctx.createOscillator()
    osc.type = 'triangle'
    osc.frequency.setValueAtTime(freq, at)
    osc.frequency.linearRampToValueAtTime(freq * 1.005, at + length)
    osc.connect(env)
    osc.start(at)
    osc.stop(at + length + 0.1)
    osc.onended = () => {
      osc.disconnect()
      env.disconnect()
    }
    return [osc]
  }

  /* Schedules the NEXT chord a little before the current one ends, so the
     two overlap by the fade time and the change is a swell rather than a
     cut. Called from a timer, not from the audio thread. */
  const schedule = () => {
    if (!playing) return
    const chord = PROGRESSION[step % PROGRESSION.length]
    const at = ctx.currentTime + 0.05
    const length = CHORD + FADE

    /* Nothing is kept in a list: every node stops itself at a known time
       and disconnects in its own onended, so the graph prunes itself. */
    sub(hz(chord.bass), at, length)
    chord.pad.forEach((note, i) => voice(hz(note), at, length, 0.115 - i * 0.012))
    // every third chord, an octave up from a note that is not the root
    if (step % 3 === 1) shimmer(hz(chord.pad[2]) * 2, at, length * 1.4)

    step += 1
    timer = setTimeout(schedule, CHORD * 1000)
  }

  const build = () => {
    const AC = window.AudioContext || window.webkitAudioContext
    if (!AC) return false
    ctx = new AC()

    master = ctx.createGain()
    master.gain.value = 0
    master.connect(ctx.destination)

    /* a shelf off the top so the saws never get glassy, then the room */
    const tame = ctx.createBiquadFilter()
    tame.type = 'highshelf'
    tame.frequency.value = 2400
    tame.gain.value = -9

    const verb = ctx.createConvolver()
    verb.buffer = impulse(ctx)
    const wet = ctx.createGain()
    wet.gain.value = 0.55
    const dry = ctx.createGain()
    dry.gain.value = 0.65

    bus = ctx.createGain()
    bus.connect(tame)
    tame.connect(dry).connect(master)
    tame.connect(verb).connect(wet).connect(master)

    return true
  }

  return {
    get playing() {
      return playing
    },

    /** Must be called from a user gesture — browsers will not let an
     *  AudioContext leave the "suspended" state otherwise. */
    async start() {
      if (playing) return
      if (!ctx && !build()) return
      if (ctx.state === 'suspended') await ctx.resume()
      playing = true
      step = 0
      master.gain.cancelScheduledValues(ctx.currentTime)
      master.gain.setValueAtTime(master.gain.value, ctx.currentTime)
      master.gain.linearRampToValueAtTime(volume, ctx.currentTime + FADE * 1.6)
      schedule()
    },

    stop() {
      if (!playing || !ctx) return
      playing = false
      clearTimeout(timer)
      // ride the master down rather than cutting: a pad that stops dead
      // sounds like something broke
      master.gain.cancelScheduledValues(ctx.currentTime)
      master.gain.setValueAtTime(master.gain.value, ctx.currentTime)
      master.gain.linearRampToValueAtTime(0, ctx.currentTime + 1.4)
    },

    dispose() {
      clearTimeout(timer)
      playing = false
      ctx?.close()
      ctx = null
    },
  }
}
