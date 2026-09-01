/* ============================================================
   A scripted support bot — keyword scoring over a small set of
   answers about this panel. There is no model behind it: if
   nothing scores, it says so rather than inventing an answer.
   ============================================================ */

const TOPICS = [
  {
    id: 'greet',
    keys: ['hi', 'hello', 'hey', 'yo', 'salam', 'sup'],
    answer: () => "Hey! I'm Onee. Ask me about your audience, the boost slider, or how a campaign gets sent.",
  },
  {
    id: 'boost',
    keys: ['boost', 'slider', 'multiplier', 'x5', 'x1'],
    answer: (s) =>
      `Boost is at ${s.boost.toFixed(1)}. It models send-time optimisation: higher boost raises predicted deliverability to ${s.delivery}% and the open forecast to ${s.opens}. Above 4 the gain flattens out.`,
  },
  {
    id: 'audience',
    keys: ['audience', 'contacts', 'segment', 'list', 'recipients', 'who'],
    answer: (s) => `You're sending to ${s.recipients} contacts in the "${s.segment}" segment. Change it from the selector at the top of the console.`,
  },
  {
    id: 'leads',
    keys: ['lead', 'leads', 'gain', 'conversion', 'convert'],
    answer: (s) => `At this boost the forecast is ${s.leads} leads — roughly one per thousand contacts per boost point.`,
  },
  {
    id: 'deliverability',
    keys: ['deliver', 'deliverability', 'inbox', 'spam', 'bounce'],
    answer: (s) => `Predicted deliverability is ${s.delivery}%. Keeping the list warm and the boost above 2 is what holds that number up.`,
  },
  {
    id: 'opens',
    keys: ['open', 'opens', 'rate', 'read'],
    answer: (s) => `The open forecast is ${s.opens} people, about ${s.openRate}% of the list.`,
  },
  {
    id: 'launch',
    keys: ['launch', 'send', 'start', 'run', 'go', 'campaign'],
    answer: (s) => `Hit "Launch Campaign" at the bottom and the ${s.agent} agent queues all ${s.recipients} contacts. You can still change the segment before that.`,
  },
  {
    id: 'agent',
    keys: ['agent', 'nova', 'atlas', 'echo', 'engine'],
    answer: (s) => `You're on ${s.agent}. NOVA writes the copy and picks send times, ATLAS handles warm-up and deliverability, ECHO deals with replies.`,
  },
  {
    id: 'level',
    keys: ['level', 'xp', 'progress', 'achievement', 'challenge'],
    answer: () => "You're level 4 with 750 of 1000 XP. Finishing today's challenge is the quickest way to top that up.",
  },
  {
    id: 'stats',
    keys: ['stat', 'stats', 'sent', 'total', 'numbers', 'how many'],
    answer: () => 'So far: 31k emails sent, 8K opened — about 26% — across 4,200 campaigns, 99% of them delivered.',
  },
  {
    id: 'who',
    keys: ['you', 'name', 'onee', 'bot', 'robot'],
    answer: () => "I'm Onee, the support bot for this panel. I only know what's on this screen — I'm scripted, not a language model.",
  },
  {
    id: 'thanks',
    keys: ['thanks', 'thank', 'nice', 'cool', 'great', 'awesome'],
    answer: () => 'Any time. Ask me whenever something on the panel is unclear.',
  },
]

const FALLBACK = "I don't have an answer for that one — I only know this panel. Try asking about the audience, boost, deliverability, or launching."

/** Score by how many of a topic's keywords appear as whole words. */
export function answerFor(question, state) {
  const text = ` ${question.toLowerCase().replace(/[^a-z0-9\s]/g, ' ')} `
  let best = null
  let bestScore = 0
  for (const topic of TOPICS) {
    let score = 0
    for (const k of topic.keys) if (text.includes(` ${k} `) || text.includes(` ${k}s `)) score += 1
    if (score > bestScore) {
      bestScore = score
      best = topic
    }
  }
  return best ? best.answer(state) : FALLBACK
}

export const OPENERS = [
  'Ask me anything about this panel.',
  'What do you want to know?',
  "I'm listening.",
]
