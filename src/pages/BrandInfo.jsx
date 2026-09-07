/* ============================================================
   BRAND INFORMATION — twelve questions, one per screen.

   This replaces the Brand Tone tab, which asked the wrong person
   the wrong thing: four unlabelled 0-100 sliders and a box for
   pasting emails so the model could copy their cadence. Neither
   is something a business owner knows the answer to, and the
   sliders quietly disagreed with the tone word set elsewhere.

   WHY ONE QUESTION PER SCREEN. The same twelve fields as a form
   is a wall that gets abandoned at the third row. One question,
   its own explanation, and a visible position in the sequence is
   the difference between a profile that gets filled in and one
   that does not — and this profile is what every generated email
   is built from, so a blank one is the whole feature failing.

   AUTOSAVE, ALWAYS. Every answer is written when the reader moves
   on, and the step number with it. Closing the tab mid-way and
   coming back a week later resumes on the question they were
   looking at. Nothing here is a session.

   SUGGESTIONS NEVER OVERWRITE. The website reader can propose an
   answer to most of these. A proposal is shown beside the field
   with a button to take it; it is never written in on the
   reader's behalf, and a field they have already answered shows
   "we read this, and left yours alone" instead.
   ============================================================ */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../api/client'
import { invalidate } from '../api/hooks'
import PageHeader from '../layout/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardHead,
  Field,
  IconButton,
  Input,
  Progress,
  Segmented,
  Textarea,
} from '../ui'
import { IcCheckC, IcGlobe, IcPlus, IcSpark, IcTrash, IcX } from '../components/NavIcons'

/* The order is the server's — `brandprofile.QUESTIONS` — so a step number
   here and a step number there can never mean different questions. */
const QUESTIONS = [
  { step: 1, field: 'brand_name', kind: 'text' },
  { step: 2, field: 'website_url', kind: 'url' },
  { step: 3, field: 'business_summary', kind: 'textarea' },
  { step: 4, field: 'offers', kind: 'offers' },
  { step: 5, field: 'ideal_customer_profile', kind: 'textarea' },
  { step: 6, field: 'customer_pain_points', kind: 'list' },
  { step: 7, field: 'customer_outcomes', kind: 'list' },
  { step: 8, field: 'differentiators', kind: 'list' },
  { step: 9, field: 'proof_points', kind: 'proof' },
  { step: 10, field: 'preferred_cta', kind: 'cta' },
  { step: 11, field: 'forbidden_claims', kind: 'list' },
  { step: 12, field: 'brand_voice', kind: 'tones' },
]
const TOTAL = QUESTIONS.length

/* Which questions may be left empty and still let the reader move on. The
   six the generator cannot work without are enforced by the server too;
   this is only so the Next button does not lie about being available. */
const OPTIONAL = new Set([
  'website_url', 'customer_pain_points', 'differentiators',
  'proof_points', 'preferred_cta', 'forbidden_claims',
])

export default function BrandInfo({ onToast, embedded }) {
  const { t, nf } = useI18n()
  const [profile, setProfile] = useState(null)
  const [step, setStep] = useState(1)
  const [view, setView] = useState('loading')  // loading | wizard | review
  const [busy, setBusy] = useState(false)
  const [reading, setReading] = useState(false)

  /* The answer being edited. Local so typing is not reverted by a refetch,
     flushed to the server on every move. */
  const [draft, setDraft] = useState(null)
  const saved = useRef(null)

  useEffect(() => {
    api.get('/brand-profile')
      .then((p) => {
        setProfile(p)
        setStep(p.current_step || 1)
        setView(p.completed ? 'review' : 'wizard')
      })
      .catch(() => setView('wizard'))
  }, [])

  const question = QUESTIONS[step - 1]
  const value = draft !== null ? draft : profile?.[question?.field]

  /* Seed the editor whenever the question changes. */
  useEffect(() => {
    if (!profile || !question) return
    setDraft(null)
    saved.current = profile[question.field]
  }, [step, profile, question])

  const patch = useCallback(async (body, { quiet = true } = {}) => {
    setBusy(true)
    try {
      const next = await api.patch('/brand-profile', body)
      setProfile(next)
      invalidate('/config')
      if (!quiet) onToast?.(t('bi.saved'))
      return next
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
      return null
    } finally {
      setBusy(false)
    }
  }, [onToast, t])

  /* Write the current answer, then move. Saving on the way out rather than
     on every keystroke: a request per character would be a request per
     character, and the answer is only meaningful once they stop typing. */
  const go = async (delta) => {
    const next = Math.max(1, Math.min(TOTAL, step + delta))
    const body = { current_step: next }
    if (draft !== null && question) body[question.field] = draft
    await patch(body)
    if (next === step && delta > 0) return
    setStep(next)
  }

  const finish = async () => {
    const body = { current_step: TOTAL, completed: true }
    if (draft !== null && question) body[question.field] = draft
    const next = await patch(body, { quiet: false })
    if (next) setView('review')
  }

  const readSite = async () => {
    setReading(true)
    try {
      // save the URL first, or the server reads whatever was there before
      if (draft !== null) await patch({ website_url: draft })
      const next = await api.post('/brand-profile/analyze')
      setProfile(next)
      const n = Object.keys(next.analysis?.suggestions || {}).length
      onToast?.(n ? t('bi.readDone', { n: nf(n) }) : t('bi.readNone'))
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    } finally {
      setReading(false)
    }
  }

  const takeSuggestion = async (field) => {
    const next = await patch({ [field]: profile.analysis.suggestions[field] })
    if (next) setDraft(null)
  }

  const done = profile?.completeness
  const filled = useMemo(() => {
    if (!question) return false
    const v = value
    return Array.isArray(v) ? v.length > 0 : Boolean(String(v ?? '').trim())
  }, [value, question])

  if (view === 'loading') return null

  /* ------------------------------------------------------------ review */
  if (view === 'review') {
    return (
      <div className="page">
        {!embedded && <PageHeader title={t('bi.title')} sub={t('bi.sub')} />}
        <CompletionBar done={done} t={t} nf={nf} />
        <Card>
          <CardHead title={t('bi.reviewTitle')} sub={t('bi.reviewSub')} icon={<IcCheckC size={17} />} />
          <div className="bi__review">
            {QUESTIONS.map((q) => (
              <div className="bi__row" key={q.field}>
                <div className="bi__rowText">
                  <div className="bi__rowLabel">{t(`bi.q${q.step}`)}</div>
                  <div className={`bi__rowValue${answered(profile[q.field]) ? '' : ' bi__rowValue--empty'}`}>
                    {summarise(profile[q.field], q, t) || t('bi.notAnswered')}
                  </div>
                </div>
                <Button size="sm" variant="ghost"
                        onClick={() => { setStep(q.step); setView('wizard') }}>
                  {t('bi.editThis')}
                </Button>
              </div>
            ))}
          </div>
        </Card>
      </div>
    )
  }

  /* ------------------------------------------------------------ wizard */
  const suggestion = profile?.analysis?.suggestions?.[question.field]
  const alreadyMine = suggestion && profile.confirmed?.includes(question.field)

  return (
    <div className="page">
      {!embedded && <PageHeader title={t('bi.title')} sub={t('bi.sub')} />}
      <CompletionBar done={done} t={t} nf={nf} />

      <Card>
        <div className="bi__head">
          <Badge tone="info">{t('bi.progress', { n: nf(step), total: nf(TOTAL) })}</Badge>
          {OPTIONAL.has(question.field) && <span className="muted">{t('bi.optional')}</span>}
        </div>
        <Progress value={step} max={TOTAL} tone="blue" height={4} />

        <h2 className="bi__q">{t(`bi.q${step}`)}</h2>
        <p className="bi__hint">{t(`bi.q${step}Hint`)}</p>

        <Answer
          question={question}
          value={value}
          onChange={setDraft}
          t={t}
          profile={profile}
        />

        {question.field === 'website_url' && (
          <Button variant="ghost" icon={<IcGlobe size={15} />} loading={reading}
                  disabled={!String(value || '').trim()}
                  onClick={readSite} style={{ marginTop: '1.4rem' }}>
            {reading ? t('bi.reading') : t('bi.readSite')}
          </Button>
        )}

        {suggestion && !alreadyMine && (
          <div className="bi__suggest">
            <div className="bi__suggestHead">
              <IcSpark size={14} />
              {t('bi.suggestion')}
            </div>
            <div className="bi__suggestBody">{summarise(suggestion, question, t)}</div>
            <Button size="sm" variant="ghost" onClick={() => takeSuggestion(question.field)}>
              {t('bi.useSuggestion')}
            </Button>
          </div>
        )}
        {suggestion && alreadyMine && (
          <div className="bi__suggest bi__suggest--kept">
            <div className="bi__suggestHead">{t('bi.suggestionKept')}</div>
            <div className="bi__suggestBody">{t('bi.suggestionKeptHint')}</div>
          </div>
        )}

        <div className="bi__nav">
          <Button variant="quiet" disabled={step === 1 || busy} onClick={() => go(-1)}>
            {t('bi.prev')}
          </Button>
          {step < TOTAL ? (
            <Button variant="primary" loading={busy}
                    disabled={!filled && !OPTIONAL.has(question.field)}
                    onClick={() => go(1)}>
              {t('bi.next')}
            </Button>
          ) : (
            <Button variant="primary" loading={busy} disabled={!filled} onClick={finish}>
              {t('bi.finish')}
            </Button>
          )}
        </div>
      </Card>
    </div>
  )
}

/* ============================================================
   One answer, in whichever shape its question needs.
   ============================================================ */
function Answer({ question, value, onChange, t, profile }) {
  const { kind, field, step } = question

  if (kind === 'text' || kind === 'url') {
    return (
      <Input
        value={value || ''}
        className={kind === 'url' ? 'mono' : undefined}
        placeholder={kind === 'url' ? 'https://example.com' : ''}
        onChange={(e) => onChange(e.target.value)}
      />
    )
  }

  if (kind === 'textarea') {
    return <Textarea rows={4} value={value || ''} onChange={(e) => onChange(e.target.value)} />
  }

  if (kind === 'cta') {
    return (
      <div className="bi__cards">
        {(profile?.ctas || []).map((id) => (
          <button
            key={id}
            type="button"
            className={`bi__card${value === id ? ' bi__card--on' : ''}`}
            onClick={() => onChange(id)}
          >
            {t(`bi.cta.${id}`)}
          </button>
        ))}
      </div>
    )
  }

  if (kind === 'tones') {
    const picked = Array.isArray(value) ? value : []
    return (
      <div className="bi__cards">
        {(profile?.tones || []).map((id) => (
          <button
            key={id}
            type="button"
            className={`bi__card${picked.includes(id) ? ' bi__card--on' : ''}`}
            onClick={() => onChange(picked.includes(id)
              ? picked.filter((x) => x !== id)
              : [...picked, id])}
          >
            {t(`bi.tone.${id}`)}
          </button>
        ))}
      </div>
    )
  }

  if (kind === 'offers') {
    const rows = Array.isArray(value) ? value : []
    const set = (i, key, v) => onChange(rows.map((r, j) => (j === i ? { ...r, [key]: v } : r)))
    return (
      <div className="stack-v">
        {rows.map((row, i) => (
          <div className="bi__offer" key={i}>
            <Field label={t('bi.q4Name')}>
              <Input value={row.name || ''} onChange={(e) => set(i, 'name', e.target.value)} />
            </Field>
            <Field label={t('bi.q4Desc')}>
              <Input value={row.description || ''} onChange={(e) => set(i, 'description', e.target.value)} />
            </Field>
            <IconButton aria-label={t('bi.remove')}
                        onClick={() => onChange(rows.filter((_, j) => j !== i))}>
              <IcTrash size={15} />
            </IconButton>
          </div>
        ))}
        <Button size="sm" variant="ghost" icon={<IcPlus size={14} />}
                onClick={() => onChange([...rows, { name: '', description: '' }])}>
          {t('bi.addAnother')}
        </Button>
      </div>
    )
  }

  if (kind === 'proof') {
    const rows = Array.isArray(value) ? value : []
    return (
      <div className="stack-v">
        <Segmented
          size="sm"
          value={rows.length ? 'yes' : 'no'}
          onChange={(v) => onChange(v === 'yes' ? [{ kind: 'result', text: '' }] : [])}
          options={[
            { value: 'yes', label: t('bi.q9Yes') },
            { value: 'no', label: t('bi.q9No') },
          ]}
        />
        {rows.map((row, i) => (
          <div className="bi__listRow" key={i}>
            <Input value={row.text || ''}
                   onChange={(e) => onChange(rows.map((r, j) => (j === i ? { ...r, text: e.target.value } : r)))} />
            <IconButton aria-label={t('bi.remove')}
                        onClick={() => onChange(rows.filter((_, j) => j !== i))}>
              <IcX size={14} />
            </IconButton>
          </div>
        ))}
        {rows.length > 0 && (
          <Button size="sm" variant="ghost" icon={<IcPlus size={14} />}
                  onClick={() => onChange([...rows, { kind: 'result', text: '' }])}>
            {t('bi.addAnother')}
          </Button>
        )}
      </div>
    )
  }

  // a plain list of short lines: pains, outcomes, differentiators, guardrails
  const rows = Array.isArray(value) ? value : []
  return (
    <div className="stack-v">
      {rows.map((row, i) => (
        <div className="bi__listRow" key={i}>
          <Input value={row}
                 onChange={(e) => onChange(rows.map((r, j) => (j === i ? e.target.value : r)))} />
          <IconButton aria-label={t('bi.remove')}
                      onClick={() => onChange(rows.filter((_, j) => j !== i))}>
            <IcX size={14} />
          </IconButton>
        </div>
      ))}
      <Button size="sm" variant="ghost" icon={<IcPlus size={14} />}
              onClick={() => onChange([...rows, ''])}>
        {t(`bi.q${step}` ) && t('bi.addAnother')}
      </Button>
    </div>
  )
}

/* The persistent completion state the brief asks for, on both views. */
function CompletionBar({ done, t, nf }) {
  if (!done) return null
  return (
    <div className="bi__state">
      <Badge tone={done.complete ? 'good' : 'info'} dot>
        {done.complete
          ? t('bi.completeBadge')
          : t('bi.partialBadge', { percent: nf(done.percent) })}
      </Badge>
      {!done.proReady && done.missingForPro.length > 0 && (
        <span className="muted">
          {t('bi.proBlocked', { fields: done.missingForPro.length })}
        </span>
      )}
    </div>
  )
}

function answered(v) {
  return Array.isArray(v) ? v.length > 0 : Boolean(String(v ?? '').trim())
}

/** A one-line version of an answer, for the review list and suggestions. */
function summarise(v, q, t) {
  if (!answered(v)) return ''
  if (q.kind === 'cta') return t(`bi.cta.${v}`)
  if (q.kind === 'tones') return v.map((x) => t(`bi.tone.${x}`)).join('، ')
  if (q.kind === 'offers') return v.map((o) => o.name).filter(Boolean).join('، ')
  if (q.kind === 'proof') return v.map((o) => o.text).filter(Boolean).join('، ')
  if (Array.isArray(v)) return v.join('، ')
  return String(v)
}
