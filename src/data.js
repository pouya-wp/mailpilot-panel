/* Static content for the panel — swap these for API data later. */

export const SEGMENTS = [
  { id: 'vip', name: 'VIP Users', emoji: '👑', size: 25000, tint: 'linear-gradient(140deg,#4ad07d,#0f7a45)' },
  { id: 'trial', name: 'Trial Signups', emoji: '🧪', size: 12400, tint: 'linear-gradient(140deg,#5b8cff,#1b3fae)' },
  { id: 'churn', name: 'Win-back', emoji: '🎯', size: 8600, tint: 'linear-gradient(140deg,#ff8a5b,#b8380f)' },
  { id: 'all', name: 'All Contacts', emoji: '🌐', size: 48200, tint: 'linear-gradient(140deg,#9b6bff,#4a1fae)' },
]

export const AGENTS = [
  { id: 'nova', name: 'NOVA', emoji: '🤖', note: 'GPT copy + send-time', tint: 'linear-gradient(140deg,#ff9d5c,#c2410c)' },
  { id: 'atlas', name: 'ATLAS', emoji: '🛰️', note: 'Warm-up & deliverability', tint: 'linear-gradient(140deg,#57c7ff,#0b5c8f)' },
  { id: 'echo', name: 'ECHO', emoji: '🎧', note: 'Reply handling', tint: 'linear-gradient(140deg,#b98cff,#5b21b6)' },
]

export const ACHIEVEMENTS = [
  { id: 1, label: 'First Campaign', icon: 'mail' },
  { id: 2, hot: true, label: ['OPEN RATE', '3', 'DAYS IN A ROW'] },
  { id: 3, label: '10K Delivered', icon: 'rocket' },
  { id: 4, label: 'Zero Bounces', icon: 'check' },
  { id: 5, label: 'Reply Streak', icon: 'flame' },
]

/* `value` is a number so the tile can count up to it — see anim/Num. */
export const STATS = [
  { label: 'Total Sent', value: 31000, unit: 'k', hint: ['8K opened', '(26%)'] },
  { label: 'Total Campaigns', value: 4200, hint: ['4,158 delivered', '(99%)'] },
]

/* boost (1..5) -> predicted rates */
export const openRate = (boost) => 0.2908 + 0.0932 * boost
export const deliverability = (boost) => 90 + boost * 1.97
export const leadsFrom = (recipients, boost) => Math.round((recipients * boost) / 1000)

export const fmt = (n) => new Intl.NumberFormat('en-US').format(Math.round(n))
