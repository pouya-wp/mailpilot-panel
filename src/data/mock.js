/* ============================================================
   Every figure the panel shows.

   Swap this module for API calls and nothing above it changes:
   the pages import named collections and the derived helpers at
   the bottom, never a fetch.

   Two deliberate choices:

   * the series are generated from a seeded PRNG rather than typed
     out, so a chart has the texture of real data (weekday dips,
     a campaign spike) instead of the smooth curve you get from
     making numbers up by hand;
   * anything with a name carries BOTH languages (`en` / `fa`) on
     the record. Campaign names are content, not UI strings, so
     they do not belong in the i18n dictionaries — but a bilingual
     panel still has to render them in the reader's language.
   ============================================================ */

/* mulberry32 — small, fast, and stable across reloads so the panel
   looks the same every time it is opened. */
function rng(seed) {
  let a = seed >>> 0
  return () => {
    a = (a + 0x6d2b79f5) >>> 0
    let t = Math.imul(a ^ (a >>> 15), 1 | a)
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296
  }
}

/** A series with a trend, weekly seasonality and a little noise. */
export function series(n, { base = 100, trend = 0.4, noise = 0.12, weekly = 0.18, seed = 7, spikeAt } = {}) {
  const r = rng(seed)
  return Array.from({ length: n }, (_, i) => {
    const t = base * (1 + (trend * i) / n)
    const s = 1 + weekly * Math.sin((i / 7) * Math.PI * 2)
    const e = 1 + (r() - 0.5) * noise * 2
    const spike = spikeAt === i ? 1.7 : 1
    return Math.max(0, Math.round(t * s * e * spike))
  })
}

/** Labels for the last n days in the active locale. */
export function dayLabels(n, locale = 'en-US') {
  const fmt = new Intl.DateTimeFormat(locale, { day: 'numeric', month: 'short' })
  return Array.from({ length: n }, (_, i) => fmt.format(new Date(Date.now() - (n - 1 - i) * 864e5)))
}

export function weekdayLabels(locale = 'en-US') {
  const fmt = new Intl.DateTimeFormat(locale, { weekday: 'short' })
  // start on Monday — the send-time heatmap is read as a working week
  return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)))
}

const ago = (mins) => new Date(Date.now() - mins * 60000).toISOString()

/* ============================================================
   AGENTS
   ============================================================ */
export const AGENTS = [
  {
    id: 'nova',
    name: { en: 'NOVA', fa: 'نووا' },
    role: { en: 'Copywriter & send-time optimiser', fa: 'کپی‌رایتر و بهینه‌ساز زمان ارسال' },
    emoji: '🪄',
    tint: 'linear-gradient(140deg,#ff9d5c,#c2410c)',
    model: 'claude-opus-5',
    autonomy: 'approve',
    status: 'active',
    runs: 1284,
    success: 96.4,
    actionsToday: 42,
    budget: 120,
    temperature: 0.7,
    lastRun: ago(14),
    skills: ['copywriting', 'subject-lines', 'send-time', 'personalisation'],
    tools: ['contacts.read', 'campaigns.write', 'analytics.read', 'brand.read'],
    sparkline: series(14, { base: 30, trend: 0.9, seed: 11 }),
  },
  {
    id: 'atlas',
    name: { en: 'ATLAS', fa: 'اطلس' },
    role: { en: 'Deliverability & warm-up engineer', fa: 'مهندس تحویل‌پذیری و گرم‌کردن آی‌پی' },
    emoji: '🛰️',
    tint: 'linear-gradient(140deg,#57c7ff,#0b5c8f)',
    model: 'claude-sonnet-5',
    autonomy: 'full',
    status: 'active',
    runs: 3106,
    success: 99.1,
    actionsToday: 118,
    budget: 400,
    temperature: 0.2,
    lastRun: ago(3),
    skills: ['warm-up', 'bounce-triage', 'dns', 'throttling'],
    tools: ['domains.write', 'suppression.write', 'analytics.read'],
    sparkline: series(14, { base: 90, trend: 0.2, seed: 23 }),
  },
  {
    id: 'echo',
    name: { en: 'ECHO', fa: 'اکو' },
    role: { en: 'Reply triage & conversation', fa: 'دسته‌بندی و پاسخ به گفت‌وگوها' },
    emoji: '🎧',
    tint: 'linear-gradient(140deg,#b98cff,#5b21b6)',
    model: 'claude-sonnet-5',
    autonomy: 'approve',
    status: 'active',
    runs: 872,
    success: 93.8,
    actionsToday: 61,
    budget: 200,
    temperature: 0.5,
    lastRun: ago(7),
    skills: ['intent-detection', 'reply-drafting', 'escalation', 'sentiment'],
    tools: ['inbox.read', 'inbox.write', 'crm.write'],
    sparkline: series(14, { base: 45, trend: 0.6, seed: 31 }),
  },
  {
    id: 'vega',
    name: { en: 'VEGA', fa: 'وگا' },
    role: { en: 'Segmentation & audience analyst', fa: 'تحلیلگر بخش‌بندی و مخاطب' },
    emoji: '🔭',
    tint: 'linear-gradient(140deg,#4ad07d,#0f7a45)',
    model: 'claude-opus-5',
    autonomy: 'suggest',
    status: 'paused',
    runs: 412,
    success: 91.2,
    actionsToday: 0,
    budget: 80,
    temperature: 0.4,
    lastRun: ago(600),
    skills: ['segmentation', 'churn-prediction', 'lookalikes'],
    tools: ['contacts.read', 'segments.write', 'analytics.read'],
    sparkline: series(14, { base: 20, trend: -0.5, seed: 41 }),
  },
  {
    id: 'orion',
    name: { en: 'ORION', fa: 'اوریون' },
    role: { en: 'Experiment designer & referee', fa: 'طراح و داور آزمایش‌ها' },
    emoji: '⚗️',
    tint: 'linear-gradient(140deg,#5b8cff,#1b3fae)',
    model: 'claude-haiku-4-5-20251001',
    autonomy: 'full',
    status: 'active',
    runs: 640,
    success: 97.7,
    actionsToday: 9,
    budget: 60,
    temperature: 0.3,
    lastRun: ago(52),
    skills: ['ab-testing', 'stats', 'auto-promote'],
    tools: ['experiments.write', 'analytics.read'],
    sparkline: series(14, { base: 12, trend: 1.2, seed: 53 }),
  },
]

/* ============================================================
   SEGMENTS
   ============================================================ */
export const SEGMENTS = [
  {
    id: 'vip',
    name: { en: 'VIP Customers', fa: 'مشتریان ویژه' },
    emoji: '👑',
    size: 25000,
    growth: 4.2,
    openRate: 62.6,
    tint: 'linear-gradient(140deg,#4ad07d,#0f7a45)',
    live: true,
    rules: [
      { field: 'orders', op: 'gte', value: '3' },
      { field: 'ltv', op: 'gte', value: '500' },
    ],
  },
  {
    id: 'trial',
    name: { en: 'Trial Signups', fa: 'ثبت‌نام آزمایشی' },
    emoji: '🧪',
    size: 12400,
    growth: 11.8,
    openRate: 48.1,
    tint: 'linear-gradient(140deg,#5b8cff,#1b3fae)',
    live: true,
    rules: [{ field: 'plan', op: 'eq', value: 'trial' }],
  },
  {
    id: 'churn',
    name: { en: 'Win-back', fa: 'بازگرداندنی‌ها' },
    emoji: '🎯',
    size: 8600,
    growth: -2.4,
    openRate: 21.3,
    tint: 'linear-gradient(140deg,#ff8a5b,#b8380f)',
    live: true,
    rules: [{ field: 'lastOpen', op: 'before', value: '90d' }],
  },
  {
    id: 'newsletter',
    name: { en: 'Newsletter', fa: 'خبرنامه' },
    emoji: '📰',
    size: 34100,
    growth: 6.9,
    openRate: 39.4,
    tint: 'linear-gradient(140deg,#b98cff,#5b21b6)',
    live: false,
    rules: [{ field: 'tag', op: 'has', value: 'newsletter' }],
  },
  {
    id: 'all',
    name: { en: 'All Contacts', fa: 'همهٔ مخاطبان' },
    emoji: '🌐',
    size: 48200,
    growth: 5.1,
    openRate: 34.8,
    tint: 'linear-gradient(140deg,#9b6bff,#4a1fae)',
    live: true,
    rules: [],
  },
]

/* ============================================================
   CAMPAIGNS
   ============================================================ */
const campaign = (id, en, fa, type, status, o) => ({
  id,
  name: { en, fa },
  type,
  status,
  agent: o.agent,
  segment: o.segment,
  recipients: o.recipients,
  sent: o.sent ?? o.recipients,
  delivered: Math.round((o.sent ?? o.recipients) * (o.deliv ?? 0.973)),
  opens: Math.round((o.sent ?? o.recipients) * (o.open ?? 0.4)),
  clicks: Math.round((o.sent ?? o.recipients) * (o.click ?? 0.08)),
  replies: Math.round((o.sent ?? o.recipients) * (o.reply ?? 0.012)),
  unsubs: Math.round((o.sent ?? o.recipients) * (o.unsub ?? 0.0021)),
  bounces: Math.round((o.sent ?? o.recipients) * (o.bounce ?? 0.011)),
  revenue: o.revenue ?? 0,
  updated: o.updated,
  scheduledFor: o.scheduledFor,
  subject: o.subject,
  trend: series(14, { base: o.recipients / 40, trend: 0.5, seed: o.seed ?? 7 }),
})

export const CAMPAIGNS = [
  campaign('c-401', 'Summer Drop — VIP Early Access', 'حراج تابستان — دسترسی زودهنگام ویژه', 'broadcast', 'sent', {
    agent: 'nova',
    segment: 'vip',
    recipients: 25000,
    open: 0.626,
    click: 0.184,
    reply: 0.021,
    revenue: 84200,
    updated: ago(190),
    seed: 3,
    subject: { en: 'Your early access starts now', fa: 'دسترسی زودهنگام تو از همین حالا' },
  }),
  campaign('c-398', 'Weekly Digest #42', 'خلاصهٔ هفتگی #۴۲', 'broadcast', 'sent', {
    agent: 'nova',
    segment: 'newsletter',
    recipients: 34100,
    open: 0.394,
    click: 0.061,
    revenue: 9800,
    updated: ago(1500),
    seed: 5,
    subject: { en: 'Five things worth your Tuesday', fa: 'پنج چیز که ارزش سه‌شنبه‌ات را دارد' },
  }),
  campaign('c-402', 'Trial Day 3 — Activation Nudge', 'روز سوم آزمایشی — یادآوری فعال‌سازی', 'drip', 'running', {
    agent: 'nova',
    segment: 'trial',
    recipients: 12400,
    sent: 8210,
    open: 0.481,
    click: 0.142,
    reply: 0.034,
    revenue: 21400,
    updated: ago(22),
    seed: 9,
    subject: { en: 'Two clicks from your first campaign', fa: 'دو کلیک تا اولین کمپینت' },
  }),
  campaign('c-405', 'Win-back — We miss you', 'بازگرداندن — دلمان برایت تنگ شده', 'agent', 'running', {
    agent: 'vega',
    segment: 'churn',
    recipients: 8600,
    sent: 3120,
    open: 0.213,
    click: 0.044,
    revenue: 6400,
    updated: ago(48),
    seed: 13,
    subject: { en: 'A quiet 20% while you decide', fa: 'یک ۲۰٪ بی‌سروصدا تا تصمیم بگیری' },
  }),
  campaign('c-407', 'Subject Line Test — Launch', 'تست موضوع — معرفی محصول', 'abtest', 'running', {
    agent: 'orion',
    segment: 'all',
    recipients: 48200,
    sent: 9600,
    open: 0.442,
    click: 0.101,
    revenue: 12900,
    updated: ago(9),
    seed: 17,
    subject: { en: 'Variant A vs B', fa: 'نسخهٔ الف در برابر ب' },
  }),
  campaign('c-409', 'Black Friday Warm-up', 'گرم‌کردن بلک‌فرایدی', 'broadcast', 'scheduled', {
    agent: 'nova',
    segment: 'vip',
    recipients: 25000,
    sent: 0,
    open: 0,
    click: 0,
    updated: ago(180),
    scheduledFor: new Date(Date.now() + 3 * 864e5).toISOString(),
    seed: 19,
    subject: { en: 'Something is coming on Friday', fa: 'جمعه یک اتفاقی می‌افتد' },
  }),
  campaign('c-410', 'Onboarding Sequence v3', 'مسیر آشناسازی نسخهٔ ۳', 'drip', 'draft', {
    agent: 'nova',
    segment: 'trial',
    recipients: 12400,
    sent: 0,
    open: 0,
    click: 0,
    updated: ago(70),
    seed: 23,
    subject: { en: 'Welcome aboard', fa: 'به جمع ما خوش آمدی' },
  }),
  campaign('c-393', 'Receipt & Shipping', 'رسید و ارسال', 'transactional', 'running', {
    agent: 'atlas',
    segment: 'all',
    recipients: 48200,
    sent: 14820,
    open: 0.712,
    click: 0.221,
    deliv: 0.994,
    bounce: 0.004,
    revenue: 0,
    updated: ago(2),
    seed: 29,
    subject: { en: 'Your order is on the way', fa: 'سفارشت در راه است' },
  }),
  campaign('c-388', 'Re-engagement Q2', 'بازفعال‌سازی فصل دوم', 'agent', 'paused', {
    agent: 'vega',
    segment: 'churn',
    recipients: 8600,
    sent: 2400,
    open: 0.188,
    click: 0.031,
    updated: ago(4000),
    seed: 31,
    subject: { en: 'Still interested?', fa: 'هنوز علاقه‌مندی؟' },
  }),
]

/* ============================================================
   JOURNEYS / AUTOMATIONS
   ============================================================ */
export const JOURNEYS = [
  {
    id: 'j-1',
    name: { en: 'Welcome & Activation', fa: 'خوش‌آمد و فعال‌سازی' },
    trigger: { en: 'Contact created', fa: 'ساخته‌شدن مخاطب' },
    status: 'active',
    enrolled: 12480,
    completed: 8210,
    conversion: 31.4,
    agent: 'nova',
    steps: [
      { id: 's1', type: 'email', label: { en: 'Welcome email', fa: 'ایمیل خوش‌آمد' } },
      { id: 's2', type: 'wait', label: { en: 'Wait 2 days', fa: '۲ روز صبر' } },
      { id: 's3', type: 'branch', label: { en: 'Opened?', fa: 'باز کرد؟' } },
      { id: 's4', type: 'agent', label: { en: 'Agent picks follow-up', fa: 'ایجنت پیگیری را انتخاب کند' } },
      { id: 's5', type: 'email', label: { en: 'Activation nudge', fa: 'یادآوری فعال‌سازی' } },
      { id: 's6', type: 'goal', label: { en: 'First campaign sent', fa: 'اولین کمپین ارسال شد' } },
    ],
  },
  {
    id: 'j-2',
    name: { en: 'Abandoned Cart Recovery', fa: 'بازیابی سبد رهاشده' },
    trigger: { en: 'Cart abandoned 1h', fa: 'رهاشدن سبد پس از ۱ ساعت' },
    status: 'active',
    enrolled: 6420,
    completed: 2180,
    conversion: 18.9,
    agent: 'nova',
    steps: [
      { id: 's1', type: 'wait', label: { en: 'Wait 1 hour', fa: '۱ ساعت صبر' } },
      { id: 's2', type: 'email', label: { en: 'Left something behind', fa: 'چیزی جا گذاشتی' } },
      { id: 's3', type: 'branch', label: { en: 'Purchased?', fa: 'خرید کرد؟' } },
      { id: 's4', type: 'email', label: { en: 'Offer 10%', fa: 'پیشنهاد ۱۰٪' } },
      { id: 's5', type: 'goal', label: { en: 'Order placed', fa: 'سفارش ثبت شد' } },
    ],
  },
  {
    id: 'j-3',
    name: { en: 'Churn Rescue', fa: 'نجات از ریزش' },
    trigger: { en: 'Engagement score < 20', fa: 'امتیاز تعامل زیر ۲۰' },
    status: 'paused',
    enrolled: 3110,
    completed: 640,
    conversion: 9.2,
    agent: 'vega',
    steps: [
      { id: 's1', type: 'agent', label: { en: 'Diagnose why', fa: 'تشخیص علت' } },
      { id: 's2', type: 'email', label: { en: 'Personal check-in', fa: 'پیگیری شخصی' } },
      { id: 's3', type: 'wait', label: { en: 'Wait 5 days', fa: '۵ روز صبر' } },
      { id: 's4', type: 'branch', label: { en: 'Replied?', fa: 'پاسخ داد؟' } },
      { id: 's5', type: 'tag', label: { en: 'Move to dormant', fa: 'انتقال به خاموش' } },
    ],
  },
  {
    id: 'j-4',
    name: { en: 'Post-purchase Delight', fa: 'لذت پس از خرید' },
    trigger: { en: 'Order completed', fa: 'تکمیل سفارش' },
    status: 'active',
    enrolled: 21400,
    completed: 19800,
    conversion: 44.1,
    agent: 'echo',
    steps: [
      { id: 's1', type: 'email', label: { en: 'Thank you', fa: 'سپاسگزاریم' } },
      { id: 's2', type: 'wait', label: { en: 'Wait 7 days', fa: '۷ روز صبر' } },
      { id: 's3', type: 'email', label: { en: 'How did we do?', fa: 'چطور بودیم؟' } },
      { id: 's4', type: 'webhook', label: { en: 'Push review to CRM', fa: 'ارسال نظر به CRM' } },
    ],
  },
]

/* ============================================================
   CONTACTS
   ============================================================ */
const FIRST = ['Ava', 'Noah', 'Mia', 'Liam', 'Zara', 'Omid', 'Sara', 'Kian', 'Elena', 'Reza', 'Nina', 'Arash', 'Leyla', 'Marco', 'Yasmin', 'Daniel']
const FIRST_FA = ['آوا', 'نوح', 'میا', 'لیام', 'زارا', 'امید', 'سارا', 'کیان', 'الینا', 'رضا', 'نینا', 'آرش', 'لیلا', 'مارکو', 'یاسمین', 'دانیال']
const LAST = ['Reed', 'Karimi', 'Vance', 'Torres', 'Haddad', 'Novak', 'Ahmadi', 'Blake', 'Rossi', 'Sadeghi', 'Lund', 'Farhadi']
const LAST_FA = ['رید', 'کریمی', 'ونس', 'تورس', 'حداد', 'نواک', 'احمدی', 'بلیک', 'روسی', 'صادقی', 'لوند', 'فرهادی']
const SOURCES = [
  { id: 'signup', en: 'Website signup', fa: 'ثبت‌نام سایت' },
  { id: 'import', en: 'CSV import', fa: 'ورود از CSV' },
  { id: 'shopify', en: 'Shopify', fa: 'شاپیفای' },
  { id: 'api', en: 'API', fa: 'API' },
  { id: 'form', en: 'Landing form', fa: 'فرم لندینگ' },
]
const TAGS = ['vip', 'newsletter', 'trial', 'beta', 'enterprise', 'apac', 'emea']

export const CONTACTS = (() => {
  const r = rng(99)
  return Array.from({ length: 64 }, (_, i) => {
    const fi = Math.floor(r() * FIRST.length)
    const li = Math.floor(r() * LAST.length)
    const score = Math.round(r() * 100)
    const st = score > 70 ? 'subscribed' : score > 25 ? 'subscribed' : r() > 0.75 ? 'unsubscribed' : r() > 0.9 ? 'bounced' : 'subscribed'
    return {
      id: `p-${100 + i}`,
      name: { en: `${FIRST[fi]} ${LAST[li]}`, fa: `${FIRST_FA[fi]} ${LAST_FA[li]}` },
      email: `${FIRST[fi].toLowerCase()}.${LAST[li].toLowerCase()}@${['acme.io', 'mail.com', 'northwind.co', 'lumen.dev'][Math.floor(r() * 4)]}`,
      status: st,
      score,
      ltv: Math.round(r() * 4200),
      orders: Math.floor(r() * 9),
      tags: TAGS.filter(() => r() > 0.72).slice(0, 3),
      source: SOURCES[Math.floor(r() * SOURCES.length)],
      lastOpen: ago(Math.floor(r() * 40000)),
      created: ago(Math.floor(r() * 400000)),
      country: ['US', 'IR', 'DE', 'FR', 'AE', 'UK'][Math.floor(r() * 6)],
      device: r() > 0.55 ? 'mobile' : 'desktop',
    }
  })
})()

/* ============================================================
   SMART INBOX
   ============================================================ */
export const THREADS = [
  {
    id: 't-1',
    from: { en: 'Elena Rossi', fa: 'الینا روسی' },
    email: 'elena.rossi@northwind.co',
    subject: { en: 'Re: Your early access starts now', fa: 'پاسخ: دسترسی زودهنگام تو از همین حالا' },
    preview: {
      en: 'This looks great — can you tell me whether the enterprise tier includes the audit log?',
      fa: 'خیلی خوب به نظر می‌رسد — می‌شود بگویید پلن سازمانی گزارش ممیزی دارد یا نه؟',
    },
    intent: 'question',
    sentiment: 0.62,
    handled: false,
    at: ago(18),
    agent: 'echo',
    draft: {
      en: 'Hi Elena — yes, the audit log ships with every Enterprise workspace and retains 24 months of events by default. Happy to walk you through it on a call this week.',
      fa: 'سلام الینا — بله، گزارش ممیزی روی همهٔ فضاهای کاری سازمانی فعال است و به‌صورت پیش‌فرض ۲۴ ماه رویداد را نگه می‌دارد. اگر بخواهید همین هفته در یک تماس نشانتان می‌دهم.',
    },
  },
  {
    id: 't-2',
    from: { en: 'Marco Lund', fa: 'مارکو لوند' },
    email: 'marco@lumen.dev',
    subject: { en: 'Re: Two clicks from your first campaign', fa: 'پاسخ: دو کلیک تا اولین کمپینت' },
    preview: { en: 'Interested. What does onboarding look like for a team of 20?', fa: 'علاقه‌مندم. آشناسازی برای تیم ۲۰ نفره چطور است؟' },
    intent: 'interested',
    sentiment: 0.81,
    handled: false,
    at: ago(52),
    agent: 'echo',
    draft: {
      en: 'Hi Marco — for a team of 20 we run a 45-minute setup session, migrate your existing lists, and leave you with two agents already configured. Would Thursday suit?',
      fa: 'سلام مارکو — برای تیم ۲۰ نفره یک جلسهٔ ۴۵ دقیقه‌ای راه‌اندازی داریم، لیست‌های فعلی‌تان را منتقل می‌کنیم و دو ایجنت آماده تحویلتان می‌دهیم. پنج‌شنبه مناسب است؟',
    },
  },
  {
    id: 't-3',
    from: { en: 'Reza Sadeghi', fa: 'رضا صادقی' },
    email: 'reza.sadeghi@acme.io',
    subject: { en: 'Re: A quiet 20% while you decide', fa: 'پاسخ: یک ۲۰٪ بی‌سروصدا تا تصمیم بگیری' },
    preview: { en: 'Please remove me from this list.', fa: 'لطفاً من را از این لیست حذف کنید.' },
    intent: 'unsubscribe',
    sentiment: 0.18,
    handled: true,
    at: ago(96),
    agent: 'echo',
    draft: {
      en: 'Done — you have been removed and will not receive further campaigns. Sorry for the noise.',
      fa: 'انجام شد — حذف شدید و دیگر کمپینی دریافت نمی‌کنید. بابت مزاحمت پوزش می‌خواهیم.',
    },
  },
  {
    id: 't-4',
    from: { en: 'Yasmin Haddad', fa: 'یاسمین حداد' },
    email: 'yasmin.haddad@mail.com',
    subject: { en: 'Re: Five things worth your Tuesday', fa: 'پاسخ: پنج چیز که ارزش سه‌شنبه‌ات را دارد' },
    preview: { en: 'The pricing page 404s on mobile.', fa: 'صفحهٔ قیمت‌ها روی موبایل ۴۰۴ می‌دهد.' },
    intent: 'objection',
    sentiment: 0.34,
    handled: false,
    at: ago(140),
    agent: 'echo',
    draft: {
      en: 'Thank you for flagging it — the mobile pricing route is fixed and live. Here is the working link.',
      fa: 'ممنون که گفتید — مسیر موبایل صفحهٔ قیمت‌ها اصلاح شد و بالا آمد. این هم لینک سالم.',
    },
  },
  {
    id: 't-5',
    from: { en: 'Daniel Blake', fa: 'دانیال بلیک' },
    email: 'daniel.blake@acme.io',
    subject: { en: 'Automatic reply: Out of office', fa: 'پاسخ خودکار: خارج از دفتر' },
    preview: { en: 'I am away until the 14th with limited access to email.', fa: 'تا چهاردهم نیستم و دسترسی محدودی به ایمیل دارم.' },
    intent: 'ooo',
    sentiment: 0.5,
    handled: true,
    at: ago(220),
    agent: 'echo',
    draft: { en: 'Suppressed until the 14th, then re-enrolled automatically.', fa: 'تا چهاردهم متوقف شد و بعد خودکار دوباره وارد مسیر می‌شود.' },
  },
]

/* ============================================================
   EXPERIMENTS
   ============================================================ */
export const EXPERIMENTS = [
  {
    id: 'x-1',
    name: { en: 'Subject: curiosity vs benefit', fa: 'موضوع: کنجکاوی در برابر منفعت' },
    status: 'running',
    metric: 'openRate',
    confidence: 87.4,
    variants: [
      { id: 'a', label: 'A', text: { en: 'Something is coming on Friday', fa: 'جمعه یک اتفاقی می‌افتد' }, split: 50, sent: 4800, rate: 44.2, winner: false },
      { id: 'b', label: 'B', text: { en: 'Save 30% this Friday', fa: 'جمعه ۳۰٪ صرفه‌جویی کن' }, split: 50, sent: 4800, rate: 48.9, winner: true },
    ],
  },
  {
    id: 'x-2',
    name: { en: 'CTA colour & copy', fa: 'رنگ و متن دکمه' },
    status: 'called',
    metric: 'clickRate',
    confidence: 99.1,
    variants: [
      { id: 'a', label: 'A', text: { en: 'Shop the drop', fa: 'دیدن محصولات' }, split: 33, sent: 8200, rate: 8.1, winner: false },
      { id: 'b', label: 'B', text: { en: 'See what is new', fa: 'ببین چه خبر است' }, split: 33, sent: 8200, rate: 11.4, winner: true },
      { id: 'c', label: 'C', text: { en: 'Take me there', fa: 'ببرم آنجا' }, split: 34, sent: 8400, rate: 9.2, winner: false },
    ],
  },
  {
    id: 'x-3',
    name: { en: 'Send time: 9am vs agent-picked', fa: 'زمان ارسال: ۹ صبح در برابر انتخاب ایجنت' },
    status: 'running',
    metric: 'openRate',
    confidence: 64.2,
    variants: [
      { id: 'a', label: 'A', text: { en: 'Fixed 09:00 local', fa: 'ثابت ۰۹:۰۰ محلی' }, split: 50, sent: 3100, rate: 37.8, winner: false },
      { id: 'b', label: 'B', text: { en: 'Agent-optimised', fa: 'بهینه‌شده توسط ایجنت' }, split: 50, sent: 3100, rate: 41.1, winner: true },
    ],
  },
]

/* ============================================================
   TEMPLATES
   ============================================================ */
export const TEMPLATES = [
  { id: 'tp-1', name: { en: 'Product Launch', fa: 'معرفی محصول' }, category: 'promo', used: 42, accent: '#7ba3cd' },
  { id: 'tp-2', name: { en: 'Weekly Digest', fa: 'خلاصهٔ هفتگی' }, category: 'newsletter', used: 118, accent: '#8fd3a8' },
  { id: 'tp-3', name: { en: 'Abandoned Cart', fa: 'سبد رهاشده' }, category: 'lifecycle', used: 67, accent: '#e2b872' },
  { id: 'tp-4', name: { en: 'Welcome Series', fa: 'مجموعهٔ خوش‌آمد' }, category: 'lifecycle', used: 91, accent: '#b98cff' },
  { id: 'tp-5', name: { en: 'Receipt', fa: 'رسید خرید' }, category: 'transactional', used: 2400, accent: '#57c7ff' },
  { id: 'tp-6', name: { en: 'Event Invite', fa: 'دعوت به رویداد' }, category: 'promo', used: 23, accent: '#ff9d5c' },
  { id: 'tp-7', name: { en: 'Win-back Offer', fa: 'پیشنهاد بازگشت' }, category: 'lifecycle', used: 38, accent: '#d68f9f' },
  { id: 'tp-8', name: { en: 'Plain Announcement', fa: 'اعلان ساده' }, category: 'newsletter', used: 14, accent: '#9fd68f' },
]

/* ============================================================
   DELIVERABILITY
   ============================================================ */
export const PROVIDERS = [
  { id: 'gmail', label: 'Gmail', inbox: 96.2, promo: 3.1, spam: 0.7, volume: 42 },
  { id: 'outlook', label: 'Outlook', inbox: 93.8, promo: 4.4, spam: 1.8, volume: 24 },
  { id: 'yahoo', label: 'Yahoo', inbox: 91.1, promo: 6.2, spam: 2.7, volume: 12 },
  { id: 'apple', label: 'iCloud', inbox: 97.4, promo: 2.2, spam: 0.4, volume: 14 },
  { id: 'other', label: 'Other', inbox: 94.6, promo: 3.8, spam: 1.6, volume: 8 },
]

export const DOMAINS = [
  {
    id: 'd-1',
    domain: 'mail.acme.io',
    status: 'verified',
    spf: true,
    dkim: true,
    dmarc: true,
    bimi: false,
    ip: '198.51.100.24',
    dedicated: true,
    reputation: 94,
    records: [
      { type: 'TXT', host: 'mail.acme.io', value: 'v=spf1 include:mailpilot.net ~all', ok: true },
      { type: 'CNAME', host: 'mp1._domainkey.mail.acme.io', value: 'mp1.dkim.mailpilot.net', ok: true },
      { type: 'TXT', host: '_dmarc.mail.acme.io', value: 'v=DMARC1; p=quarantine; rua=mailto:dmarc@acme.io', ok: true },
    ],
  },
  {
    id: 'd-2',
    domain: 'news.acme.io',
    status: 'unverified',
    spf: true,
    dkim: false,
    dmarc: false,
    bimi: false,
    ip: 'shared',
    dedicated: false,
    reputation: 71,
    records: [
      { type: 'TXT', host: 'news.acme.io', value: 'v=spf1 include:mailpilot.net ~all', ok: true },
      { type: 'CNAME', host: 'mp1._domainkey.news.acme.io', value: 'mp1.dkim.mailpilot.net', ok: false },
      { type: 'TXT', host: '_dmarc.news.acme.io', value: 'v=DMARC1; p=none', ok: false },
    ],
  },
]

/* ============================================================
   INTEGRATIONS
   ============================================================ */
export const INTEGRATIONS = [
  { id: 'shopify', name: 'Shopify', cat: 'ecommerce', on: true, emoji: '🛍️', desc: { en: 'Orders, carts and customers', fa: 'سفارش‌ها، سبدها و مشتریان' } },
  { id: 'woo', name: 'WooCommerce', cat: 'ecommerce', on: false, emoji: '🧺', desc: { en: 'Sync your WordPress store', fa: 'همگام‌سازی فروشگاه وردپرسی' } },
  { id: 'stripe', name: 'Stripe', cat: 'ecommerce', on: true, emoji: '💳', desc: { en: 'Revenue and subscription events', fa: 'رویدادهای درآمد و اشتراک' } },
  { id: 'hubspot', name: 'HubSpot', cat: 'crm', on: true, emoji: '🧲', desc: { en: 'Two-way contact sync', fa: 'همگام‌سازی دوطرفهٔ مخاطبان' } },
  { id: 'salesforce', name: 'Salesforce', cat: 'crm', on: false, emoji: '☁️', desc: { en: 'Leads and opportunities', fa: 'سرنخ‌ها و فرصت‌ها' } },
  { id: 'segment', name: 'Segment', cat: 'data', on: true, emoji: '🔀', desc: { en: 'Event pipeline in', fa: 'خط لولهٔ رویداد ورودی' } },
  { id: 'bigquery', name: 'BigQuery', cat: 'data', on: false, emoji: '🗄️', desc: { en: 'Warehouse export', fa: 'خروجی به انبار داده' } },
  { id: 'snowflake', name: 'Snowflake', cat: 'data', on: false, emoji: '❄️', desc: { en: 'Reverse ETL audiences', fa: 'مخاطبان از طریق ETL معکوس' } },
  { id: 'slack', name: 'Slack', cat: 'messaging', on: true, emoji: '💬', desc: { en: 'Alerts and approvals', fa: 'هشدارها و تأییدها' } },
  { id: 'telegram', name: 'Telegram', cat: 'messaging', on: false, emoji: '✈️', desc: { en: 'Agent notifications', fa: 'اعلان‌های ایجنت' } },
  { id: 'meta', name: 'Meta Ads', cat: 'ads', on: false, emoji: '📣', desc: { en: 'Custom audience sync', fa: 'همگام‌سازی مخاطب سفارشی' } },
  { id: 'google', name: 'Google Ads', cat: 'ads', on: true, emoji: '🎯', desc: { en: 'Customer match lists', fa: 'لیست‌های تطبیق مشتری' } },
  { id: 'anthropic', name: 'Anthropic', cat: 'ai', on: true, emoji: '🧠', desc: { en: 'Claude models for every agent', fa: 'مدل‌های کلاد برای همهٔ ایجنت‌ها' } },
  { id: 'openai', name: 'OpenAI', cat: 'ai', on: false, emoji: '🌀', desc: { en: 'Alternate model provider', fa: 'ارائه‌دهندهٔ جایگزین مدل' } },
]

/* ============================================================
   TEAM / BILLING / DEV
   ============================================================ */
export const TEAM = [
  { id: 'u-1', name: { en: 'Pouya A.', fa: 'پویا الف.' }, email: 'pouya@acme.io', role: 'owner', active: ago(4), status: 'active' },
  { id: 'u-2', name: { en: 'Sara Ahmadi', fa: 'سارا احمدی' }, email: 'sara@acme.io', role: 'admin', active: ago(90), status: 'active' },
  { id: 'u-3', name: { en: 'Noah Vance', fa: 'نوح ونس' }, email: 'noah@acme.io', role: 'editor', active: ago(1400), status: 'active' },
  { id: 'u-4', name: { en: 'Mia Torres', fa: 'میا تورس' }, email: 'mia@acme.io', role: 'analyst', active: ago(300), status: 'active' },
  { id: 'u-5', name: { en: 'Kian Farhadi', fa: 'کیان فرهادی' }, email: 'kian@acme.io', role: 'viewer', active: null, status: 'pending' },
]

export const INVOICES = [
  { id: 'in-2044', date: ago(60 * 24 * 3), amount: 890, status: 'paid' },
  { id: 'in-2011', date: ago(60 * 24 * 33), amount: 890, status: 'paid' },
  { id: 'in-1988', date: ago(60 * 24 * 63), amount: 640, status: 'paid' },
  { id: 'in-1954', date: ago(60 * 24 * 94), amount: 640, status: 'paid' },
]

export const API_KEYS = [
  { id: 'k-1', name: { en: 'Production server', fa: 'سرور تولید' }, prefix: 'mp_live_9f2a', scopes: ['campaigns:write', 'contacts:rw'], lastUsed: ago(12) },
  { id: 'k-2', name: { en: 'Analytics reader', fa: 'خوانندهٔ تحلیل' }, prefix: 'mp_live_41cd', scopes: ['analytics:read'], lastUsed: ago(2400) },
  { id: 'k-3', name: { en: 'Staging', fa: 'محیط آزمایشی' }, prefix: 'mp_test_77be', scopes: ['*'], lastUsed: ago(60 * 24 * 12) },
]

export const WEBHOOKS = [
  { id: 'w-1', url: 'https://api.acme.io/hooks/mailpilot', events: ['email.delivered', 'email.opened', 'email.clicked'], on: true, ok: 99.8 },
  { id: 'w-2', url: 'https://ops.acme.io/agent-events', events: ['agent.action', 'agent.escalation'], on: true, ok: 100 },
  { id: 'w-3', url: 'https://legacy.acme.io/mail', events: ['email.bounced'], on: false, ok: 42.1 },
]

/* ============================================================
   SUPPRESSION
   ============================================================ */
export const SUPPRESSED = (() => {
  const r = rng(2024)
  const reasons = ['unsub', 'bounce', 'complaint', 'manual']
  return Array.from({ length: 22 }, (_, i) => ({
    id: `s-${i}`,
    email: `${['old', 'test', 'noreply', 'info', 'admin', 'hello'][Math.floor(r() * 6)]}${Math.floor(r() * 900)}@${['mail.com', 'acme.io', 'example.org'][Math.floor(r() * 3)]}`,
    reason: reasons[Math.floor(r() * reasons.length)],
    at: ago(Math.floor(r() * 200000)),
  }))
})()

/* ============================================================
   ACTIVITY / AUDIT / FEED
   ============================================================ */
export const ACTIVITY = [
  { id: 'a-1', kind: 'agent', actor: 'nova', action: { en: 'rewrote 1,240 subject lines', fa: '۱٬۲۴۰ موضوع را بازنویسی کرد' }, target: 'c-402', at: ago(4), tone: 'info' },
  { id: 'a-2', kind: 'agent', actor: 'atlas', action: { en: 'throttled sending to Yahoo', fa: 'سرعت ارسال به یاهو را کم کرد' }, target: 'news.acme.io', at: ago(11), tone: 'warn' },
  { id: 'a-3', kind: 'human', actor: 'u-2', action: { en: 'approved the win-back draft', fa: 'پیش‌نویس بازگرداندن را تأیید کرد' }, target: 'c-405', at: ago(26), tone: 'good' },
  { id: 'a-4', kind: 'agent', actor: 'orion', action: { en: 'called variant B the winner', fa: 'نسخهٔ ب را برنده اعلام کرد' }, target: 'x-2', at: ago(41), tone: 'good' },
  { id: 'a-5', kind: 'agent', actor: 'echo', action: { en: 'answered 18 replies autonomously', fa: '۱۸ پاسخ را خودکار جواب داد' }, target: 'inbox', at: ago(58), tone: 'info' },
  { id: 'a-6', kind: 'system', actor: 'system', action: { en: 'DKIM verified', fa: 'DKIM تأیید شد' }, target: 'mail.acme.io', at: ago(120), tone: 'good' },
  { id: 'a-7', kind: 'agent', actor: 'vega', action: { en: 'flagged 640 contacts as churn risk', fa: '۶۴۰ مخاطب را در خطر ریزش علامت زد' }, target: 'churn', at: ago(190), tone: 'warn' },
  { id: 'a-8', kind: 'human', actor: 'u-1', action: { en: 'rotated the production API key', fa: 'کلید API تولید را چرخاند' }, target: 'k-1', at: ago(320), tone: 'info' },
  { id: 'a-9', kind: 'system', actor: 'system', action: { en: 'nightly list hygiene removed 84 addresses', fa: 'پاک‌سازی شبانه ۸۴ آدرس را حذف کرد' }, target: 'suppression', at: ago(500), tone: 'info' },
  { id: 'a-10', kind: 'agent', actor: 'nova', action: { en: 'scheduled Black Friday warm-up', fa: 'گرم‌کردن بلک‌فرایدی را زمان‌بندی کرد' }, target: 'c-409', at: ago(700), tone: 'info' },
]

/* The stream on the dashboard — short, high-frequency, and always
   "just now" relative to when the panel is opened. */
export const LIVE_EVENTS = [
  { id: 'e1', type: 'opened', who: 'ava.reed@acme.io', at: ago(0.2) },
  { id: 'e2', type: 'clicked', who: 'marco@lumen.dev', at: ago(0.6) },
  { id: 'e3', type: 'delivered', who: 'nina.rossi@mail.com', at: ago(1.1) },
  { id: 'e4', type: 'replied', who: 'elena.rossi@northwind.co', at: ago(1.8) },
  { id: 'e5', type: 'opened', who: 'kian.sadeghi@acme.io', at: ago(2.4) },
  { id: 'e6', type: 'bounced', who: 'old441@example.org', at: ago(3.2) },
  { id: 'e7', type: 'converted', who: 'yasmin.haddad@mail.com', at: ago(4.0) },
  { id: 'e8', type: 'unsubscribed', who: 'test902@mail.com', at: ago(5.1) },
]

/* ============================================================
   AGENT RECOMMENDATIONS
   ============================================================ */
export const RECOMMENDATIONS = [
  {
    id: 'r-1',
    agent: 'nova',
    lift: 12.4,
    effort: 'low',
    title: { en: 'Move the VIP send to 08:40 local', fa: 'ارسال ویژه را به ۰۸:۴۰ محلی ببر' },
    body: {
      en: 'Opens for this segment peak 40 minutes earlier than the fixed 09:20 slot you are using.',
      fa: 'اوج بازشدن این بخش ۴۰ دقیقه زودتر از ساعت ثابت ۰۹:۲۰ فعلی است.',
    },
  },
  {
    id: 'r-2',
    agent: 'atlas',
    lift: 8.1,
    effort: 'low',
    title: { en: 'Finish DKIM on news.acme.io', fa: 'DKIM دامنهٔ news.acme.io را کامل کن' },
    body: {
      en: 'One CNAME is missing. Until it resolves, Outlook is filing 6% of that domain in Promotions.',
      fa: 'یک رکورد CNAME کم است. تا وقتی حل نشود، اوت‌لوک ۶٪ از این دامنه را در تبلیغات می‌گذارد.',
    },
  },
  {
    id: 'r-3',
    agent: 'vega',
    lift: 6.8,
    effort: 'medium',
    title: { en: 'Split "All Contacts" by engagement', fa: '«همهٔ مخاطبان» را بر اساس تعامل تقسیم کن' },
    body: {
      en: '18,400 addresses have not opened in 120 days and are dragging the whole domain reputation down.',
      fa: '۱۸٬۴۰۰ آدرس ۱۲۰ روز است چیزی باز نکرده‌اند و اعتبار کل دامنه را پایین می‌کشند.',
    },
  },
  {
    id: 'r-4',
    agent: 'orion',
    lift: 4.2,
    effort: 'low',
    title: { en: 'Promote variant B on the launch test', fa: 'نسخهٔ ب را در تست معرفی ارتقا بده' },
    body: {
      en: 'Confidence crossed 95% two hours ago. The remaining 38,600 recipients should get B.',
      fa: 'اطمینان دو ساعت پیش از ۹۵٪ رد شد. ۳۸٬۶۰۰ گیرندهٔ باقی‌مانده باید نسخهٔ ب را بگیرند.',
    },
  },
]

/* ============================================================
   KNOWLEDGE SOURCES
   ============================================================ */
export const KB_SOURCES = [
  { id: 'kb-1', name: { en: 'acme.io — full site', fa: 'acme.io — کل سایت' }, type: 'web', chunks: 1840, status: 'indexed', at: ago(2400) },
  { id: 'kb-2', name: { en: 'Product catalogue.csv', fa: 'کاتالوگ محصولات.csv' }, type: 'file', chunks: 620, status: 'indexed', at: ago(6000) },
  { id: 'kb-3', name: { en: 'Brand guidelines.pdf', fa: 'راهنمای برند.pdf' }, type: 'file', chunks: 88, status: 'indexed', at: ago(9000) },
  { id: 'kb-4', name: { en: 'Support macros (Zendesk)', fa: 'ماکروهای پشتیبانی (زندسک)' }, type: 'app', chunks: 240, status: 'indexing', at: ago(12) },
  { id: 'kb-5', name: { en: 'Past campaigns (2023–2025)', fa: 'کمپین‌های گذشته (۲۰۲۳–۲۰۲۵)' }, type: 'internal', chunks: 3120, status: 'indexed', at: ago(40000) },
]

/* ============================================================
   NOTIFICATIONS
   ============================================================ */
export const NOTIFICATIONS = [
  { id: 'n-1', tone: 'warn', title: { en: 'ATLAS wants approval', fa: 'اطلس منتظر تأیید است' }, body: { en: 'Reduce Yahoo volume by 40% for 24h', fa: 'کاهش ۴۰٪ حجم یاهو برای ۲۴ ساعت' }, at: ago(9), unread: true },
  { id: 'n-2', tone: 'good', title: { en: 'Experiment called', fa: 'آزمایش داوری شد' }, body: { en: 'CTA colour & copy — variant B wins', fa: 'رنگ و متن دکمه — نسخهٔ ب برنده شد' }, at: ago(41), unread: true },
  { id: 'n-3', tone: 'info', title: { en: 'Summer Drop finished sending', fa: 'ارسال حراج تابستان تمام شد' }, body: { en: '25,000 delivered · 62.6% open', fa: '۲۵٬۰۰۰ تحویل · ۶۲٫۶٪ بازشدن' }, at: ago(190), unread: false },
  { id: 'n-4', tone: 'bad', title: { en: 'DKIM missing', fa: 'DKIM ناقص است' }, body: { en: 'news.acme.io is sending unsigned', fa: 'news.acme.io بدون امضا ارسال می‌کند' }, at: ago(600), unread: false },
]

/* ============================================================
   DERIVED — the numbers the dashboard opens with.
   ============================================================ */
export const totals = () => {
  const live = CAMPAIGNS.filter((c) => c.sent > 0)
  const sum = (k) => live.reduce((s, c) => s + c[k], 0)
  const sent = sum('sent')
  return {
    sent,
    delivered: sum('delivered'),
    opens: sum('opens'),
    clicks: sum('clicks'),
    replies: sum('replies'),
    bounces: sum('bounces'),
    unsubs: sum('unsubs'),
    revenue: sum('revenue'),
    openRate: (sum('opens') / sent) * 100,
    clickRate: (sum('clicks') / sent) * 100,
    bounceRate: (sum('bounces') / sent) * 100,
    unsubRate: (sum('unsubs') / sent) * 100,
    deliveryRate: (sum('delivered') / sent) * 100,
    contacts: 48200,
  }
}

/* Open rate by weekday × 12 two-hour buckets — the send-time heatmap.
   Built from a plausible model (a morning peak, a smaller evening one,
   the weekend flatter) so the picture actually carries a lesson. */
export const sendHeatmap = () => {
  const r = rng(1234)
  return Array.from({ length: 7 }, (_, d) =>
    Array.from({ length: 12 }, (_, h) => {
      const hour = h * 2
      const morning = Math.exp(-Math.pow(hour - 9, 2) / 12) * 1.0
      const evening = Math.exp(-Math.pow(hour - 20, 2) / 18) * 0.55
      const weekend = d >= 5 ? 0.62 : 1
      return Math.round((morning + evening) * weekend * (0.85 + r() * 0.3) * 62 * 10) / 10
    })
  )
}

export const cohortData = () => {
  const r = rng(555)
  const months = 6
  return Array.from({ length: months }, (_, i) => ({
    label: new Intl.DateTimeFormat('en-US', { month: 'short' }).format(new Date(2025, 2 + i, 1)),
    values: Array.from({ length: months }, (_, p) =>
      p > months - 1 - i ? 0 : Math.round(100 * Math.exp(-p * 0.28) * (0.85 + r() * 0.25))
    ),
  }))
}

export const DEVICES = [
  { id: 'mobile', label: { en: 'Mobile', fa: 'موبایل' }, value: 58, color: '#7ba3cd' },
  { id: 'desktop', label: { en: 'Desktop', fa: 'دسکتاپ' }, value: 33, color: '#8fd3a8' },
  { id: 'tablet', label: { en: 'Tablet', fa: 'تبلت' }, value: 9, color: '#b98cff' },
]

export const PLAN = {
  name: { en: 'Scale', fa: 'اسکیل' },
  price: 890,
  emails: { used: 184200, limit: 500000 },
  credits: { used: 41200, limit: 120000 },
  contacts: { used: 48200, limit: 100000 },
  renews: new Date(Date.now() + 12 * 864e5).toISOString(),
}

export const MODELS = [
  { value: 'claude-opus-5', label: 'Claude Opus 5' },
  { value: 'claude-sonnet-5', label: 'Claude Sonnet 5' },
  { value: 'claude-haiku-4-5-20251001', label: 'Claude Haiku 4.5' },
]

/** Pick the language-appropriate string off a bilingual record. */
export const loc = (v, lang) => (v && typeof v === 'object' ? v[lang] ?? v.en : v)

export const agentById = (id) => AGENTS.find((a) => a.id === id)
export const segmentById = (id) => SEGMENTS.find((s) => s.id === id)
export const campaignById = (id) => CAMPAIGNS.find((c) => c.id === id)
export const memberById = (id) => TEAM.find((m) => m.id === id)
