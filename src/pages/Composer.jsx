/* ============================================================
   AI COMPOSER

   The brief on one side, the rendered email on the other. The
   generate button runs a fake stream — text arriving a token at a
   time behind a blinking caret — because the honest shape of this
   interaction is "wait, then watch it appear", and a spinner would
   misrepresent how long the reader is actually going to sit here.

   The preview is a real document: it takes its OWN direction from
   the language the email is written in, not from the interface.
   Someone running the panel in Persian may well be writing an
   English campaign, and the preview has to show what the recipient
   will actually receive.
   ============================================================ */
import { useEffect, useMemo, useRef, useState } from 'react'
import { gsap, reduced, useGSAP } from '../anim/core'
import { loc, useI18n } from '../i18n'
import { useAgents, useCompose, useCreateCampaign, useSegments, useSendCampaign } from '../api/resources'
import { navigate } from '../router'
import PageHeader from '../layout/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardHead,
  Field,
  Grid,
  Input,
  Progress,
  Segmented,
  Select,
  Slider,
  Stagger,
  Textarea,
  Toggle,
  Tooltip,
} from '../ui'
import {
  IcCheckC,
  IcCompose,
  IcDesktop,
  IcEye,
  IcMobile,
  IcRefresh,
  IcSend,
  IcSpark,
  IcTemplate,
  IcWarn,
} from '../components/NavIcons'

/* The drafts the "model" returns. Written out per language and per tone so
   changing the tone visibly changes the copy — a demo where every setting
   produces the same paragraph teaches the reader that none of them matter. */
const DRAFTS = {
  en: {
    friendly: {
      subject: 'Your early access starts now',
      body: [
        'Hi {{first_name}}, we held a few things back for you.',
        'The summer collection is live for VIP customers a full day before anyone else. No code, no queue — your account is already on the list.',
        'It runs until Friday, and the pieces that sold out last season are back in limited numbers.',
      ],
      cta: 'Shop the collection',
    },
    professional: {
      subject: 'Early access to the summer collection',
      body: [
        'Hello {{first_name}},',
        'As a VIP customer, your account has been granted access to the summer collection 24 hours ahead of general release.',
        'Availability is limited on several returning items. Access closes Friday at 23:59 in your local time zone.',
      ],
      cta: 'View the collection',
    },
    playful: {
      subject: 'Psst — the good stuff is open',
      body: [
        'Hey {{first_name}} 👋',
        'We unlocked the summer collection a day early, just for you. Everyone else is still refreshing the homepage.',
        'Last season’s sell-outs are back, and there are not many of them. Go on.',
      ],
      cta: 'Take me there',
    },
    urgent: {
      subject: '24 hours: your VIP window is open',
      body: [
        '{{first_name}} — your early access window is open now and closes Friday.',
        'The four pieces that sold out in under an hour last season are back in limited numbers.',
        'Once general release starts, VIP pricing ends.',
      ],
      cta: 'Claim your access',
    },
    luxury: {
      subject: 'An invitation, before anyone else',
      body: [
        'Dear {{first_name}},',
        'The summer collection opens to you a day before it opens to the world. Each piece is made in a run of forty.',
        'Your private access remains open until Friday evening.',
      ],
      cta: 'Enter the collection',
    },
  },
  fa: {
    friendly: {
      subject: 'دسترسی زودهنگام تو از همین حالا',
      body: [
        'سلام {{first_name}}، چند چیز را برایت کنار گذاشتیم.',
        'مجموعهٔ تابستان یک روز زودتر از همه برای مشتریان ویژه باز شده است. نه کدی لازم است، نه صفی — حسابت از قبل در فهرست است.',
        'تا جمعه ادامه دارد و آن‌هایی که فصل قبل تمام شدند، به تعداد محدود برگشته‌اند.',
      ],
      cta: 'دیدن مجموعه',
    },
    professional: {
      subject: 'دسترسی زودهنگام به مجموعهٔ تابستان',
      body: [
        'سلام {{first_name}}،',
        'به‌عنوان مشتری ویژه، حساب شما ۲۴ ساعت پیش از عرضهٔ عمومی به مجموعهٔ تابستان دسترسی یافته است.',
        'موجودی چند قلم بازگشته محدود است. دسترسی جمعه ساعت ۲۳:۵۹ به وقت محلی شما بسته می‌شود.',
      ],
      cta: 'مشاهدهٔ مجموعه',
    },
    playful: {
      subject: 'یواشکی — چیزهای خوب باز شد',
      body: [
        'سلام {{first_name}} 👋',
        'مجموعهٔ تابستان را یک روز زودتر فقط برای تو باز کردیم. بقیه هنوز دارند صفحهٔ اصلی را رفرش می‌کنند.',
        'آن‌هایی که فصل قبل تمام شدند برگشته‌اند و تعدادشان کم است. برو ببین.',
      ],
      cta: 'ببرم آنجا',
    },
    urgent: {
      subject: '۲۴ ساعت: پنجرهٔ ویژهٔ تو باز است',
      body: [
        '{{first_name}} — پنجرهٔ دسترسی زودهنگامت همین حالا باز است و جمعه بسته می‌شود.',
        'چهار قلمی که فصل قبل زیر یک ساعت تمام شد، به تعداد محدود برگشته است.',
        'با شروع عرضهٔ عمومی، قیمت ویژه تمام می‌شود.',
      ],
      cta: 'گرفتن دسترسی',
    },
    luxury: {
      subject: 'یک دعوت، پیش از همه',
      body: [
        '{{first_name}} گرامی،',
        'مجموعهٔ تابستان یک روز زودتر از جهان برای شما باز می‌شود. هر قطعه در شمارگان چهل ساخته شده است.',
        'دسترسی خصوصی شما تا عصر جمعه باز می‌ماند.',
      ],
      cta: 'ورود به مجموعه',
    },
  },
}

const SUBJECT_IDEAS = {
  en: [
    { text: 'Your early access starts now', score: 92 },
    { text: 'Before anyone else: summer is open', score: 88 },
    { text: '24 hours of VIP pricing', score: 84 },
    { text: 'We held these back for you', score: 79 },
  ],
  fa: [
    { text: 'دسترسی زودهنگام تو از همین حالا', score: 92 },
    { text: 'پیش از همه: تابستان باز شد', score: 88 },
    { text: '۲۴ ساعت قیمت ویژه', score: 84 },
    { text: 'این‌ها را برایت نگه داشتیم', score: 79 },
  ],
}

/* The API returns the draft as paragraphs; the record stores one body. */
const SPLIT = '\n\n'

export default function Composer({ onToast }) {
  const { t, lang, nf, pct, compact } = useI18n()

  const [brief, setBrief] = useState('')
  const [goal, setGoal] = useState('conversion')
  const [tone, setTone] = useState('friendly')
  const [length, setLength] = useState('medium')
  const [emoji, setEmoji] = useState(true)
  const [deep, setDeep] = useState(true)
  const [creativity, setCreativity] = useState(65)
  const [segment, setSegment] = useState('vip')
  const [agent, setAgent] = useState('nova')
  const [mailLang, setMailLang] = useState(lang)
  const [device, setDevice] = useState('desktop')

  const segments = useSegments()
  const agents = useAgents()
  const [compose, composing] = useCompose()
  const [createCampaign, creating] = useCreateCampaign()
  const [sendCampaign, sendingCampaign] = useSendCampaign()

  /* The subject the reader picked, if they picked one of the alternatives. */
  const [subject, setSubject] = useState(null)

  /* `result` is whatever the server last returned; `shown` is how much of it
     has been revealed. Keeping them separate is what lets the reveal be a
     presentation concern rather than something the request has to model. */
  const [result, setResult] = useState(null)
  const [shown, setShown] = useState(0)
  const [failed, setFailed] = useState(null)
  const timers = useRef([])

  const paras = result?.body || []
  const busy = composing.loading || (result !== null && shown < paras.length)
  const done = result !== null && shown >= paras.length && !composing.loading

  useEffect(() => () => timers.current.forEach(clearTimeout), [])

  const generate = async () => {
    timers.current.forEach(clearTimeout)
    timers.current = []
    setResult(null)
    setShown(0)
    setFailed(null)
    try {
      const draft = await compose({
        brief,
        goal,
        tone,
        length,
        lang: mailLang,
        emoji,
        personalize: deep,
        creativity,
        segment,
        agent,
      })
      setResult(draft)
      setSubject(null)
      /* One timeout per paragraph rather than a per-character interval: the
         caret already carries "it is still writing", and re-rendering the
         whole preview 400 times would fight every tween on the page. */
      draft.body.forEach((_, i) => {
        timers.current.push(setTimeout(() => setShown(i + 1), 220 + i * 520))
      })
    } catch (err) {
      // a paused agent, an exhausted credit budget, a guardrail — all of these
      // are things the reader can act on, so say which one it was
      setFailed(err)
      onToast?.(err.message || t('err.failed'))
    }
  }

  const seg = (segments.data || []).find((s) => s.id === segment)

  return (
    <div className="page">
      <PageHeader
        title={t('comp.title')}
        sub={t('comp.sub')}
        actions={
          <>
            <Button variant="ghost" icon={<IcTemplate size={16} />}>
              {t('comp.saveTemplate')}
            </Button>
            <Button variant="ghost" icon={<IcSend size={16} />} onClick={() => onToast?.(t('comp.sendTest'))}>
              {t('comp.sendTest')}
            </Button>
            <Button
              variant="primary"
              icon={<IcSend size={16} />}
              loading={creating.loading || sendingCampaign.loading}
              disabled={!done}
              onClick={async () => {
                const line = subject || result?.subject || ''
                try {
                  const created = await createCampaign({
                    /* The draft is written in ONE language; the record wants
                       both sides, so the other mirrors it rather than being
                       left blank and rendering as an empty name. */
                    name: { en: line, fa: line },
                    subject: { en: line, fa: line },
                    body: { en: paras.join(SPLIT), fa: paras.join(SPLIT) },
                    type: 'broadcast',
                    agent,
                    segment,
                  })
                  await sendCampaign({ id: created.id, mode: 'now' })
                  onToast?.(t('toast.launched'))
                  navigate(`campaigns/${created.id}`)
                } catch (err) {
                  // the draft is already saved by this point if the send is what
                  // failed, so the message is the whole of what went wrong
                  onToast?.(err.message || t('err.failed'))
                }
              }}
            >
              {t('camp.sendNow')}
            </Button>
          </>
        }
      />

      <Stagger className="cols cols--narrow-wide">
        {/* ---------- the brief ---------- */}
        <div className="stack-v">
          <Card>
            <CardHead title={t('comp.brief')} icon={<IcCompose size={17} />} />
            <Textarea
              rows={5}
              value={brief}
              onChange={(e) => setBrief(e.target.value)}
              placeholder={t('comp.briefPlaceholder')}
            />

            <div className="hr" />

            <Grid cols={2} gap={1.4}>
              <Field label={t('comp.goal')}>
                <Select
                  value={goal}
                  onChange={setGoal}
                  options={['awareness', 'conversion', 'retention', 'winback', 'nurture'].map((g) => ({
                    value: g,
                    label: t(`comp.goal.${g}`),
                  }))}
                />
              </Field>
              <Field label={t('comp.tone')}>
                <Select
                  value={tone}
                  onChange={setTone}
                  options={['friendly', 'professional', 'playful', 'urgent', 'luxury'].map((g) => ({
                    value: g,
                    label: t(`comp.tone.${g}`),
                  }))}
                />
              </Field>
              <Field label={t('camp.audience')}>
                <Select
                  value={segment}
                  onChange={setSegment}
                  options={(segments.data || []).map((s) => ({ value: s.id, label: `${s.emoji} ${loc(s.name, lang)}` }))}
                />
              </Field>
              <Field label={t('ag.title')}>
                <Select
                  value={agent}
                  onChange={setAgent}
                  options={(agents.data || []).map((a) => ({ value: a.id, label: `${a.emoji} ${loc(a.name, lang)}` }))}
                />
              </Field>
            </Grid>

            <div className="hr" />

            <Field label={t('comp.length')}>
              <Segmented
                size="sm"
                value={length}
                onChange={setLength}
                options={['short', 'medium', 'long'].map((l) => ({ value: l, label: t(`comp.length.${l}`) }))}
              />
            </Field>

            <div style={{ marginTop: '1.6rem' }}>
              <div className="row" style={{ justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                <span className="field2__label">{t('ag.temperature')}</span>
                <span className="strong num-tab">{nf(creativity)}</span>
              </div>
              <Slider value={creativity} onChange={setCreativity} ticks={['0', '25', '50', '75', '100']} />
            </div>

            <div className="hr" />

            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.4rem' }}>
              <Toggle checked={emoji} onChange={setEmoji} label={t('comp.emojis')} />
              <Toggle checked={deep} onChange={setDeep} label={t('comp.personalize')} hint={t('comp.personalizeHint')} />
            </div>

            <Button
              variant="primary"
              size="lg"
              full
              loading={busy}
              icon={<IcSpark size={17} />}
              onClick={generate}
              style={{ marginTop: '2rem' }}
            >
              {busy ? t('comp.thinking') : done ? t('comp.regenerate') : t('comp.generate')}
            </Button>

            <p className="faint" style={{ fontSize: '1.15rem', marginTop: '1rem', textAlign: 'center' }}>
              {compact(seg?.size ?? 0)} {t('camp.recipients')} · {t('comp.readTime')} ~{nf(paras.length * 12)}s
            </p>
          </Card>

          {/* subject ideas appear only once there is a draft to attach them to */}
          {done && (
            <Card>
              <CardHead title={t('comp.subjectLines')} icon={<IcSpark size={17} />} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                {(result?.suggestions || []).map((s, i) => (
                  <button
                    className={`tile${(subject || result?.subject) === s.text ? ' tile--on' : ''}`}
                    key={i}
                    onClick={() => {
                      setSubject(s.text)
                      onToast?.(t('comp.use'))
                    }}
                  >
                    <span className="tile__text">
                      <span className="tile__title" style={{ whiteSpace: 'normal' }}>
                        {s.text}
                      </span>
                      <span className="tile__sub">
                        {t('comp.grade')} {nf(s.score)}/100
                      </span>
                    </span>
                    <span className="tile__end">
                      <Badge tone={s.score > 85 ? 'good' : s.score > 80 ? 'info' : 'neutral'} size="sm">
                        {nf(s.score)}
                      </Badge>
                    </span>
                  </button>
                ))}
              </div>
            </Card>
          )}
        </div>

        {/* ---------- the preview ---------- */}
        <div className="stack-v">
          <Card>
            <CardHead
              title={t('comp.preview')}
              icon={<IcEye size={17} />}
              right={
                <div className="row" style={{ gap: '0.8rem' }}>
                  <Segmented
                    size="sm"
                    value={mailLang}
                    onChange={setMailLang}
                    options={[
                      { value: 'en', label: 'EN' },
                      { value: 'fa', label: 'FA' },
                    ]}
                  />
                  <Segmented
                    size="sm"
                    value={device}
                    onChange={setDevice}
                    options={[
                      { value: 'desktop', label: t('comp.desktop'), icon: <IcDesktop size={14} /> },
                      { value: 'mobile', label: t('comp.mobile'), icon: <IcMobile size={14} /> },
                    ]}
                  />
                </div>
              }
            />

            <MailPreview
              device={device}
              dir={mailLang === 'fa' ? 'rtl' : 'ltr'}
              subject={subject || result?.subject || ''}
              paras={paras}
              shown={shown}
              busy={busy}
              cta={result?.cta || ''}
              idle={!result && !composing.loading}
              idleText={t('comp.briefPlaceholder')}
              lang={mailLang}
            />
          </Card>

          {done && (
            <Grid min={22} gap={1.5}>
              <Card>
                <CardHead title={t('comp.spamScore')} />
                <div className="row" style={{ gap: '1.4rem' }}>
                  <div style={{ flex: 1 }}>
                    <Progress
                      value={result?.analysis?.spamScore || 0}
                      max={10}
                      tone={(result?.analysis?.spamScore || 0) < 3 ? 'good' : 'warn'}
                      right={`${nf(result?.analysis?.spamScore || 0, { maximumFractionDigits: 1 })} / 10`}
                      label={t('del.inbox')}
                    />
                  </div>
                  <Badge tone="good" dot>
                    {t('del.clean')}
                  </Badge>
                </div>
                <ul style={{ margin: '1.4rem 0 0', padding: 0, listStyle: 'none', display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
                  {[
                    { ok: true, en: 'Text-to-image ratio is healthy', fa: 'نسبت متن به تصویر سالم است' },
                    { ok: true, en: 'Unsubscribe link present', fa: 'لینک لغو اشتراک وجود دارد' },
                    /* The brand brain's banned list is enforced by the API, not
                       merely displayed — this row reports what it actually caught. */
                    {
                      ok: !(result?.analysis?.guardrailViolations || []).length,
                      en: (result?.analysis?.guardrailViolations || []).length
                        ? `Banned wording: ${result.analysis.guardrailViolations.join(', ')}`
                        : 'No banned wording',
                      fa: (result?.analysis?.guardrailViolations || []).length
                        ? `واژهٔ ممنوع: ${result.analysis.guardrailViolations.join('، ')}`
                        : 'واژهٔ ممنوعی به کار نرفته',
                    },
                  ].map((r, i) => (
                    <li key={i} className="row" style={{ gap: '0.8rem', fontSize: '1.22rem', color: 'var(--tx-3)' }}>
                      <span style={{ color: r.ok ? 'var(--good)' : 'var(--warn)', display: 'grid', placeItems: 'center' }}>
                        {r.ok ? <IcCheckC size={15} /> : <IcWarn size={15} />}
                      </span>
                      {lang === 'fa' ? r.fa : r.en}
                    </li>
                  ))}
                </ul>
              </Card>

              <Card>
                <CardHead title={t('comp.grade')} />
                <Grid cols={2} gap={1.2}>
                  <MiniFig label={t('comp.readTime')} value={`${nf(result?.analysis?.readSeconds || 0)}s`} />
                  <MiniFig
                    label={t('comp.grade')}
                    value={nf(result?.analysis?.readability || 0, { maximumFractionDigits: 1 })}
                  />
                  <MiniFig
                    label={t('comp.length')}
                    value={`${nf(result?.analysis?.words || 0)} ${lang === 'fa' ? 'کلمه' : 'words'}`}
                  />
                  <MiniFig label={t('m.credits')} value={nf(result?.creditsCharged || 0)} />
                </Grid>
              </Card>
            </Grid>
          )}
        </div>
      </Stagger>
    </div>
  )
}

/* ---------- the rendered email ---------- */
function MailPreview({ device, dir, subject, paras, shown, busy, cta, idle, idleText, lang }) {
  const box = useRef(null)

  /* Each paragraph rises as it lands. Keyed off `shown` so only the newly
     arrived one animates — re-running the stagger on every tick would make
     the whole letter jitter as it writes itself. */
  useGSAP(
    () => {
      if (reduced() || !shown) return
      const el = box.current?.querySelector(`[data-p="${shown - 1}"]`)
      if (!el) return
      gsap.from(el, { opacity: 0, y: 14, filter: 'blur(0.4rem)', duration: 0.6, ease: 'glide' })
    },
    { dependencies: [shown], scope: box }
  )

  return (
    <div className={`mail mail--${device}`} ref={box}>
      <div className="mail__chrome">
        <span className="mail__dot" />
        <span className="mail__dot" />
        <span className="mail__dot" />
        <span className="mail__addr">hello@mail.acme.io</span>
      </div>
      <div className="mail__body" dir={dir}>
        <div className="mail__brand">ACME</div>

        {idle ? (
          <>
            <h2 className="mail__subject" style={{ opacity: 0.32 }}>
              {lang === 'fa' ? 'اینجا موضوع ایمیل می‌آید' : 'Your subject line lands here'}
            </h2>
            <p className="mail__p" style={{ opacity: 0.3 }}>
              {idleText}
            </p>
          </>
        ) : (
          <>
            <h2 className="mail__subject">{subject}</h2>
            {paras.slice(0, shown).map((p, i) => (
              <p className="mail__p" data-p={i} key={i}>
                {p}
                {busy && i === shown - 1 && <span className="mail__caret" />}
              </p>
            ))}
            {busy && shown === 0 && (
              <p className="mail__p">
                <span className="mail__caret" />
              </p>
            )}
            {!busy && shown >= paras.length && (
              <>
                <a className="mail__cta">{cta}</a>
                <div className="mail__hr" />
                <div className="mail__foot">
                  {dir === 'rtl'
                    ? 'این ایمیل را دریافت کردید چون مشترک آکمی هستید. لغو اشتراک'
                    : 'You are receiving this because you subscribed to Acme. Unsubscribe'}
                </div>
              </>
            )}
          </>
        )}
      </div>
    </div>
  )
}

function MiniFig({ label, value }) {
  return (
    <div>
      <div style={{ fontSize: '1.12rem', color: 'var(--tx-4)' }}>{label}</div>
      <div
        style={{
          marginTop: '0.25rem',
          fontFamily: 'var(--font-display)',
          fontSize: '1.9rem',
          fontWeight: 600,
          color: '#eef3fa',
          letterSpacing: '-0.02em',
        }}
      >
        {value}
      </div>
    </div>
  )
}
