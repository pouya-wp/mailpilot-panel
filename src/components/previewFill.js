/* ============================================================
   FILLING A TEMPLATE FOR PREVIEW

   A template is a frame with holes in it: {{content}} where the
   message goes, {{first_name}} where a name goes, {{unsubscribe}}
   on the footer link. Rendered raw, the preview showed those
   braces as literal text — so the one screen whose job is "what
   will this look like when it arrives" answered with something no
   recipient will ever see.

   Two rules.

   THE PREVIEW IS FILLED, THE TEMPLATE IS NOT. What gets saved
   still has the holes; only the picture is filled in. Filling the
   stored copy would turn a reusable frame into one specific email
   — which is the mistake the {{content}} slot exists to prevent.

   THE SAMPLE IS IN THE READER'S LANGUAGE. A Persian customer
   previewing a Persian template should not see English lorem, and
   the fill has to carry dir="rtl" with it or the sample paragraph
   lands left-aligned inside a right-aligned design and the preview
   lies about the layout.
   ============================================================ */

const SAMPLE = {
  en: {
    subject: 'A short spring note',
    first: 'Sam',
    body: [
      'We put a few things aside that we thought you would like, and they are ready whenever you are.',
      'Nothing here is on for long — the pieces below are the ones people have been asking after all week.',
      'If now is not the moment, that is completely fine. We will be here.',
    ],
    cta: 'Take a look',
    unsubscribe: 'Unsubscribe',
  },
  fa: {
    subject: 'یک یادداشت کوتاه بهاری',
    first: 'سارا',
    body: [
      'چند چیز را کنار گذاشتیم که فکر کردیم خوشتان بیاید، و هر وقت شما آماده باشید آماده‌اند.',
      'هیچ‌کدام زیاد نمی‌مانند — این‌هایی که پایین می‌بینید همان‌هایی‌اند که این هفته سراغشان را گرفته‌اند.',
      'اگر الان وقتش نیست، هیچ اشکالی ندارد. ما همین‌جاییم.',
    ],
    cta: 'ببینید',
    unsubscribe: 'لغو اشتراک',
  },
}

/** Paragraphs, styled to sit inside a table-based email without fighting it. */
function paragraphs(lines, rtl) {
  const align = rtl ? 'right' : 'left'
  return lines
    .map(
      (line) =>
        `<p style="margin:0 0 16px;font-size:16px;line-height:1.7;text-align:${align}">${line}</p>`
    )
    .join('')
}

/**
 * Fill a template's merge tags with believable sample content.
 *
 * @param {string} html      the stored template, holes and all
 * @param {object} opts      { lang, brand } — the reader's language and the
 *                           deployment's brand name
 * @returns {string}         html safe to drop into a preview frame
 */
export function previewFill(html, { lang = 'en', brand = '' } = {}) {
  if (!html) return ''
  const s = SAMPLE[lang] || SAMPLE.en
  const rtl = lang === 'fa'

  return (
    html
      .replace(/\{\{\s*content\s*\}\}/g, paragraphs(s.body, rtl))
      .replace(/\{\{\s*subject\s*\}\}/g, s.subject)
      .replace(/\{\{\s*first_name\s*\}\}/g, s.first)
      .replace(/\{\{\s*name\s*\}\}/g, s.first)
      .replace(/\{\{\s*brand\s*\}\}/g, brand || (rtl ? 'برند شما' : 'Your brand'))
      // links go nowhere on purpose: a preview that navigates is a preview that
      // loses the thing you were looking at
      .replace(/\{\{\s*unsubscribe\s*\}\}/g, '#')
      .replace(/\{\{\s*cta_url\s*\}\}/g, '#')
      .replace(/\{\{\s*email\s*\}\}/g, rtl ? 'sara@example.com' : 'sam@example.com')
      // anything the model invented that we do not know about. Left visible but
      // marked, because a silent blank hides a tag that will ship unfilled.
      .replace(
        /\{\{\s*([a-zA-Z_]+)\s*\}\}/g,
        (_, tag) =>
          `<span style="background:#fff3cd;color:#664d03;padding:1px 5px;border-radius:3px">${tag}?</span>`
      )
  )
}

/** Which merge tags a template still contains — shown as a checklist. */
export function tagsIn(html) {
  const found = new Set()
  for (const m of (html || '').matchAll(/\{\{\s*([a-zA-Z_]+)\s*\}\}/g)) found.add(m[1])
  return [...found]
}
