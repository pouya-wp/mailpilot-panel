/* ============================================================
   A scripted helper — keyword scoring over a small set of
   answers about this panel. There is no model behind it: if
   nothing scores, it says so rather than inventing an answer.

   WHAT IT MUST NOT DO. The previous version of this file told
   every customer they were "sending to 25,000 contacts in the
   VIP Users segment", that they were "level 4 with 750 XP", and
   that "31k emails" had been sent — none of it read from
   anything. A helper that states figures it cannot see is worse
   than no helper, because the figures look authoritative and a
   customer has no way to tell they are furniture.

   So this script explains HOW THE PANEL WORKS and never reports
   WHAT IS IN IT. Real numbers live on the screens that actually
   query them. The only state it uses is the agent's name, the
   language, and which modules the deployment bought.

   BOTH LANGUAGES. The panel ships in English and Persian, and
   the old matcher stripped every non-latin character before
   scoring — which turned any Persian question into an empty
   string, so a Persian customer got the fallback every single
   time, in English. Persian is a first-class input here.
   ============================================================ */

/* Persian arrives spelled several ways: Arabic yeh/kaf from one
   keyboard, Persian yeh/kaf from another, and ZWNJ inside almost
   every compound ("کمپین‌ها"). Fold those together and treat ZWNJ
   as a space, so "کمپين‌ها" and "کمپین ها" both reach "کمپین". */
const fold = (s) =>
  s
    .toLowerCase()
    /* CAREFUL: the third range is invisible in an editor — it is
       U+200B..U+200F, the zero-width and direction marks. A well-meaning
       "tidy up the whitespace" pass deletes it and the matcher silently
       stops folding compounds. The fourth is U+064B..U+0652, the harakat. */
    .replace(/[يى]/g, 'ی') // Arabic yeh -> Persian yeh
    .replace(/ك/g, 'ک') // Arabic kaf -> Persian kaf
    .replace(/[​-‏]/g, ' ') // ZWNJ and friends -> space
    .replace(/[ً-ْ]/g, '') // harakat, which nobody types twice
    .replace(/[^\p{L}\p{N}]+/gu, ' ') // keep LETTERS in any script
    .trim()

/* Each topic answers in the reader's language. `s` carries only
   what this file is allowed to know: the agent's name, and `has`
   for module gating — describing the email designer to a customer
   whose deployment does not include it is its own small lie. */
const TOPICS = [
  {
    id: 'greet',
    keys: {
      en: ['hi', 'hello', 'hey', 'yo', 'sup', 'salam'],
      fa: ['سلام', 'درود', 'وقت بخیر', 'خسته نباشید'],
    },
    en: (s) =>
      `Hello — I'm ${s.agent}. Ask me how anything in this panel works: contacts, campaigns, sending, or getting Gmail connected.`,
    fa: (s) =>
      `سلام — من ${s.agent} هستم. هر چیزی دربارهٔ کار کردن با این پنل بپرسید: مخاطبان، کمپین‌ها، ارسال، یا وصل کردن جیمیل.`,
  },
  {
    id: 'self',
    /* Phrases, not bare pronouns. "who" and "you" on their own swallowed
       "Who will this be sent to?" — a question about the audience — and
       answered it with a self-introduction. */
    keys: {
      en: ['who are you', 'what are you', 'your name', 'bot', 'robot', 'assistant', 'chatbot'],
      fa: ['کی هستی', 'چی هستی', 'کی هستید', 'اسمت', 'نام تو', 'ربات', 'دستیار', 'خودت را معرفی'],
    },
    en: (s) =>
      `I'm ${s.agent}. In this corner I answer questions about the panel from a short script — I'm not the part that writes your emails. That's on the Campaigns screen, and it does use a language model.`,
    fa: (s) =>
      `من ${s.agent} هستم. در این گوشه، بر اساس یک راهنمای کوتاه به سؤال‌های شما دربارهٔ پنل جواب می‌دهم — نوشتن ایمیل‌ها کار من در اینجا نیست؛ آن در صفحهٔ کمپین‌ها انجام می‌شود و از مدل زبانی استفاده می‌کند.`,
  },
  {
    id: 'audience',
    keys: {
      en: ['audience', 'contact', 'contacts', 'group', 'groups', 'segment', 'list', 'import', 'csv',
           'recipient', 'recipients', 'subscribers', 'sent to', 'send to', 'go to', 'who will'],
      fa: ['مخاطب', 'مخاطبان', 'گروه', 'گروه‌بندی', 'لیست', 'فهرست', 'ایمپورت', 'وارد کردن',
           'گیرنده', 'گیرندگان', 'چه کسانی', 'کسانی', 'برای کی', 'فرستاده می‌شود', 'وارد'],
    },
    en: () =>
      'The Audience screen holds every contact, the groups you sort them into, and the do-not-contact list. You can import a CSV there, and a campaign sends to one group — so a contact has to be in a group before it can be mailed.',
    fa: () =>
      'صفحهٔ مخاطبان همهٔ مخاطبان، گروه‌هایی که در آن‌ها دسته‌بندی می‌شوند و فهرست تماس‌ممنوع را نگه می‌دارد. آنجا می‌توانید فایل CSV وارد کنید. هر کمپین به یک گروه ارسال می‌شود، پس مخاطب باید در گروهی باشد تا ایمیلی به او برود.',
  },
  {
    id: 'campaign',
    keys: {
      en: ['campaign', 'send', 'sending', 'launch', 'schedule', 'later', 'queue', 'draft'],
      fa: ['کمپین', 'ارسال', 'فرستادن', 'بفرست', 'زمان‌بندی', 'بعدا', 'صف', 'پیش‌نویس'],
    },
    en: (s) =>
      `A campaign needs three things before it will send: a subject, a body, and a group to send to. Once it has them, ${s.agent} queues the recipients and works through them one at a time — you can send now or pick a time, and the Campaigns screen shows how far along it is.`,
    fa: (s) =>
      `هر کمپین برای ارسال به سه چیز نیاز دارد: موضوع، متن، و گروهی که به آن فرستاده می‌شود. وقتی این‌ها را داشت، ${s.agent} گیرنده‌ها را در صف می‌گذارد و یکی‌یکی می‌فرستد — می‌توانید همین حالا بفرستید یا زمان تعیین کنید، و صفحهٔ کمپین‌ها پیشرفت کار را نشان می‌دهد.`,
  },
  {
    id: 'gmail',
    keys: {
      en: ['gmail', 'google', 'connect', 'oauth', 'account', 'mailbox', 'smtp'],
      fa: ['جیمیل', 'گوگل', 'اتصال', 'وصل', 'حساب', 'صندوق'],
    },
    en: () =>
      'Mail goes out through your own Gmail account, connected once from Setup with Google sign-in. Nothing is sent until that connection is live, and you can disconnect it there at any time.',
    fa: () =>
      'ایمیل‌ها از حساب جیمیل خودتان ارسال می‌شوند؛ یک بار در بخش راه‌اندازی با ورود گوگل وصلش می‌کنید. تا وقتی این اتصال برقرار نباشد چیزی ارسال نمی‌شود، و هر وقت بخواهید از همان‌جا می‌توانید قطعش کنید.',
  },
  {
    id: 'designer',
    when: (s) => s.has('templates'),
    keys: {
      en: ['design', 'designer', 'template', 'html', 'layout', 'brand', 'font', 'look'],
      fa: ['طراح', 'طراحی', 'قالب', 'تمپلیت', 'ظاهر', 'فونت', 'برند'],
    },
    en: () =>
      'The Email designer builds a reusable HTML template from a reference image and a few facts about your brand. Mark one as the default and every campaign is wrapped in it at send time, so the styling stays consistent without redoing it each send.',
    fa: () =>
      'طراح ایمیل از روی یک تصویر نمونه و چند نکته دربارهٔ برند شما، یک قالب HTML قابل استفادهٔ دوباره می‌سازد. یکی را پیش‌فرض کنید تا هنگام ارسال، همهٔ کمپین‌ها داخل همان قالب قرار بگیرند و ظاهر ایمیل‌ها یکدست بماند.',
  },
  {
    id: 'unsub',
    keys: {
      en: ['unsubscribe', 'opt', 'bounce', 'bounced', 'spam', 'suppression', 'complaint', 'blocked'],
      fa: ['لغو اشتراک', 'لغو', 'برگشت', 'اسپم', 'هرزنامه', 'تماس‌ممنوع', 'مسدود'],
    },
    en: () =>
      'Every email carries a working unsubscribe link, and mail clients get the one-click header too. Anyone who leaves — or whose address permanently fails — goes onto the do-not-contact list, and nothing sends to that list again, even if the address is imported a second time.',
    fa: () =>
      'در هر ایمیل یک لینک لغو اشتراک واقعی قرار می‌گیرد و هدر لغو یک‌کلیکی هم برای نرم‌افزارهای ایمیل فرستاده می‌شود. هر کسی که لغو کند — یا آدرسش برای همیشه برگشت بخورد — به فهرست تماس‌ممنوع می‌رود و دیگر هیچ ایمیلی برایش نمی‌رود، حتی اگر آن آدرس دوباره وارد شود.',
  },
  {
    id: 'replies',
    when: (s) => s.has('inbox'),
    keys: {
      en: ['reply', 'replies', 'inbox', 'answer', 'respond', 'incoming'],
      fa: ['پاسخ', 'پاسخ‌ها', 'جواب', 'صندوق ورودی', 'ورودی'],
    },
    en: () =>
      'Replies collects what comes back and sorts it, so delivery failures and unsubscribe requests are kept apart from people actually writing to you.',
    fa: () =>
      'بخش پاسخ‌ها، جواب‌هایی را که برمی‌گردد جمع و دسته‌بندی می‌کند تا خطاهای ارسال و درخواست‌های لغو اشتراک، از پیام‌های آدم‌های واقعی جدا بماند.',
  },
  {
    id: 'insights',
    when: (s) => s.has('insights'),
    keys: {
      en: ['insight', 'insights', 'analytics', 'report', 'open', 'opens', 'click', 'stats', 'performance'],
      fa: ['بینش', 'آنالیز', 'تحلیل', 'گزارش', 'بازشدن', 'باز شدن', 'کلیک', 'آمار', 'عملکرد'],
    },
    en: () =>
      'Insights reports opens and clicks for campaigns that have actually been sent. Until a campaign goes out there is nothing to report, so the screen stays empty on purpose rather than showing a shape with no data behind it.',
    fa: () =>
      'بخش بینش‌ها، بازشدن و کلیک کمپین‌هایی را که واقعاً ارسال شده‌اند گزارش می‌دهد. تا وقتی کمپینی ارسال نشده چیزی برای گزارش وجود ندارد، و این صفحه عمداً خالی می‌ماند تا نموداری بدون داده نشان ندهد.',
  },
  {
    id: 'research',
    keys: {
      en: ['research', 'find', 'prospect', 'lead', 'leads', 'discover', 'search'],
      fa: ['تحقیق', 'پیدا کردن', 'جستجو', 'سرنخ', 'مشتری جدید'],
    },
    en: () =>
      'The research agent looks for possible contacts by region and by the kind of people you describe. Everything it finds arrives as a suggestion with the source it came from — nothing is added to your audience until you accept it.',
    fa: () =>
      'ایجنت تحقیق، بر اساس منطقه و دسته‌ای از افراد که توصیف می‌کنید، دنبال مخاطبان احتمالی می‌گردد. هر چه پیدا کند به‌صورت پیشنهاد همراه با منبعش می‌آید — تا وقتی تأیید نکنید چیزی به مخاطبان شما اضافه نمی‌شود.',
  },
  {
    id: 'settings',
    keys: {
      en: ['setting', 'settings', 'password', 'language', 'theme', 'dark', 'sender', 'reply'],
      fa: ['تنظیم', 'تنظیمات', 'رمز', 'گذرواژه', 'زبان', 'تم', 'تیره', 'فرستنده'],
    },
    en: () =>
      "Settings holds the sender details, the agent's tone, your password, and the language and theme switches. Changing your password signs out every other session.",
    fa: () =>
      'در تنظیمات، مشخصات فرستنده، لحن ایجنت، رمز عبور شما و کلیدهای زبان و تم قرار دارد. با تغییر رمز عبور، همهٔ نشست‌های دیگر از حساب خارج می‌شوند.',
  },
  {
    id: 'help',
    /* No bare interrogatives. "how" and "what" — and چطور, چگونه — appear in
       almost every question anyone asks, so as keys they outscored the topic
       the question was actually about: "how do I import my contacts" scored
       as help, and so did "what is the price of gold". This topic is now
       reached by asking for help, not by asking anything at all. */
    keys: {
      en: ['help', 'guide', 'get started', 'explain', 'what can', 'can you do'],
      fa: ['کمک', 'راهنما', 'شروع', 'توضیح', 'چه کارهایی', 'چه کاری', 'قابلیت', 'چیکار'],
    },
    en: () =>
      'Ask about contacts, campaigns and sending, Gmail, unsubscribes, or the research agent. The Guide screen has the longer version of all of it.',
    fa: () =>
      'دربارهٔ مخاطبان، کمپین‌ها و ارسال، جیمیل، لغو اشتراک، یا ایجنت تحقیق بپرسید. توضیح کامل‌تر همهٔ این‌ها در صفحهٔ راهنما هست.',
  },
  {
    id: 'thanks',
    keys: {
      en: ['thanks', 'thank', 'nice', 'cool', 'great', 'awesome', 'perfect'],
      fa: ['ممنون', 'مرسی', 'سپاس', 'عالی', 'دمت گرم', 'خوبه'],
    },
    en: () => 'Any time. Ask whenever something on the panel is unclear.',
    fa: () => 'خواهش می‌کنم. هر وقت چیزی در پنل مبهم بود بپرسید.',
  },
]

const FALLBACK = {
  en: "I don't have an answer for that one — I only know this panel, and I'd rather say so than guess. Try asking about contacts, campaigns, sending, or Gmail. The Guide screen covers the rest.",
  fa: 'برای این یکی جوابی ندارم — من فقط این پنل را می‌شناسم و ترجیح می‌دهم به‌جای حدس زدن همین را بگویم. دربارهٔ مخاطبان، کمپین‌ها، ارسال یا جیمیل بپرسید. بقیه‌اش در صفحهٔ راهنما هست.',
}

/** Score by how many of a topic's keywords appear in the question. */
export function answerFor(question, state) {
  const lang = state?.lang === 'fa' ? 'fa' : 'en'
  const s = {
    agent: state?.agent || (lang === 'fa' ? 'دستیار' : 'the agent'),
    has: typeof state?.has === 'function' ? state.has : () => true,
  }
  const folded = fold(question || '')
  if (!folded) return FALLBACK[lang]
  const text = ` ${folded} `
  const words = folded.split(' ')

  /* Persian glues its suffixes straight onto the stem — "مخاطبانم" is
     "my contacts" and "مخاطبان" never appears as a separate word — so
     whole-word matching misses the ordinary way people write. Persian keys
     therefore match as a prefix of a word. English does not agglutinate
     like that, and a prefix rule there would let "list" match "listen", so
     English stays exact bar the plural. */
  const arabic = /\p{Script=Arabic}/u
  const hit = (key) => {
    if (key.includes(' ')) return text.includes(` ${key} `)
    if (arabic.test(key)) return words.some((w) => w.startsWith(key))
    return words.some((w) => w === key || w === `${key}s`)
  }

  let best = null
  let bestScore = 0
  for (const topic of TOPICS) {
    if (topic.when && !topic.when(s)) continue
    let score = 0
    /* Both languages' keywords are scored, because a bilingual customer
       types "gmail" and "کمپین" in one sentence and means both. Longer
       keys count double, so a specific word beats an incidental one. */
    for (const k of [...topic.keys.en, ...topic.keys.fa]) {
      const key = fold(k)
      if (key && hit(key)) score += key.length > 4 ? 2 : 1
    }
    if (score > bestScore) {
      bestScore = score
      best = topic
    }
  }
  return best ? best[lang](s) : FALLBACK[lang]
}

export const OPENERS = {
  en: ['Ask me anything about this panel.', 'What do you want to know?', "I'm listening."],
  fa: ['هر چیزی دربارهٔ این پنل بپرسید.', 'چه چیزی می‌خواهید بدانید؟', 'گوش می‌دهم.'],
}
