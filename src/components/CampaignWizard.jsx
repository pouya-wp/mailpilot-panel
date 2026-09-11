/* ============================================================
   RUN A CAMPAIGN — the whole job, in four steps.

   Everything this does was already possible: search the finder,
   accept the leads, open the designer, make a campaign, attach a
   group, pick a send time. It was possible across four screens,
   in an order nobody states, where each screen does one part and
   none of them says what the next part is. The tester's words for
   that were "we've made it too hard — every section does its own
   thing".

   So this is not new capability. It is the existing capability in
   the order a person actually wants it:

     1. who to reach      — a kind of business, and where
     2. what came back    — kept, tagged, and put in a group
     3. what to send      — one of the designs, and a subject
     4. when it goes      — and how fast, which is the part that
                            decides whether the account survives

   NOTHING IS DONE BEHIND THE READER'S BACK. Each step commits its
   own work and says so: the leads really are on the contact list
   after step 2, whether or not step 4 is ever reached. That is
   why step 2 says so out loud — half-finished state that pretends
   to be nothing is how people lose work.
   ============================================================ */
import { useEffect, useMemo, useState } from 'react'
import { useI18n, loc } from '../i18n'
import { api } from '../api/client'
import { invalidate } from '../api/hooks'
import { navigate } from '../router'
import { Button, Card, Field, Input, Modal, Select, Segmented } from '../ui'
import { IcCheckC, IcSearch, IcSend, IcWarn } from './NavIcons'

/* The workspace's own hourly cap is the real control — the sender enforces
   it — so these are offered as plain rates rather than invented units. */
const RATES = [10, 25, 50, 100, 250]

/* Mirrors prospect.MAX_PER_RUN on the server, which is the real limit --
   this only stops the reader typing a number that will be silently
   clamped. The server clamps regardless. */
const FIND_CEILING = 40

export default function CampaignWizard({ open, onClose, onToast }) {
  const { t, lang, nf } = useI18n()

  const [step, setStep] = useState(1)
  const [busy, setBusy] = useState(false)

  // step 1
  const [category, setCategory] = useState('')
  const [region, setRegion] = useState('')
  /* How many to look for. The tester's sentence is "twenty gold shops in
     Dubai" -- the count is half of it, and asking for it here is the
     difference between a search and a wish. */
  const [count, setCount] = useState(20)

  // step 2
  const [found, setFound] = useState(null)   // { found, withEmail }
  const [kept, setKept] = useState(null)     // { added, group, groupId }

  // step 3
  const [templates, setTemplates] = useState([])
  const [template, setTemplate] = useState('')
  const [subject, setSubject] = useState('')
  /* 'manual' is the flow this product has always had. 'professional'
     researches and writes a separate email for each recipient, so it does
     not ask for a subject -- there is one per prospect. */
  const [mode, setMode] = useState('manual')
  const [goal, setGoal] = useState('')
  const [brand, setBrand] = useState(null)

  // step 4
  const [when, setWhen] = useState('now')
  const [at, setAt] = useState('')
  const [rate, setRate] = useState(50)
  const [quiet, setQuiet] = useState(null)
  /* Who this would actually reach, and who it would not. Fetched on
     the last step because it is a question about a campaign that now
     has an audience. */
  const [flight, setFlight] = useState(null)
  const [madeId, setMadeId] = useState('')
  /* An optional A/B test on one variable. Off by default: the
     overwhelming majority of sends are not tests. */
  const [abField, setAbField] = useState('')
  const [abA, setAbA] = useState('')
  const [abB, setAbB] = useState('')

  /* Reset on close rather than on open: reopening should be a fresh run, and
     doing it on open would wipe the state the moment React re-rendered. */
  useEffect(() => {
    if (open) return
    const id = setTimeout(() => {
      setStep(1); setCategory(''); setRegion(''); setCount(20)
      setFound(null); setKept(null)
      setTemplate(''); setSubject('')
      setWhen('now'); setAt(''); setRate(50)
      setAbField(''); setAbA(''); setAbB(''); setFlight(null)
    }, 250)
    return () => clearTimeout(id)
  }, [open])

  /* The designs and the current sending rules, fetched once the reader is
     actually heading that way rather than on mount. */
  useEffect(() => {
    if (!open || step < 3) return
    api.get('/templates').then(setTemplates).catch(() => setTemplates([]))
    // whether professional mode can run at all, and what it still needs
    api.get('/brand-profile').then((p) => setBrand(p.completeness)).catch(() => {})
    api.get('/settings')
      .then((s) => {
        // the sending rules live under `sending`, not at the top level
        const snd = s.sending || {}
        setQuiet(snd.quietHours ? { from: snd.quietFrom, to: snd.quietTo } : null)
        if (snd.throttlePerHour) setRate(Math.min(snd.throttlePerHour, 50))
      })
      .catch(() => {})
  }, [open, step])

  /* The pre-flight, once there is a group to ask about. Read-only: nothing
     is queued and nothing is created, so opening step 4 and closing the
     dialog again leaves no trace. */
  useEffect(() => {
    if (!open || step !== 4 || !kept?.groupId) return
    api.get(`/campaigns/preflight?segment=${encodeURIComponent(kept.groupId)}`)
      .then(setFlight)
      .catch(() => setFlight(null))
  }, [open, step, kept])

  const total = kept?.added || 0
  const hours = rate > 0 ? Math.ceil(total / rate) : 0
  const plan = useMemo(() => {
    if (!total) return ''
    return t('wiz.planLine', {
      n: nf(total),
      rate: nf(rate),
      hours: hours <= 1 ? t('wiz.underAnHour') : t('wiz.hours', { n: nf(hours) }),
    })
  }, [total, rate, hours, t, nf])

  const fail = (err) => onToast?.(err?.message || t('err.failed'))

  /* ---- step 1: go and look ---- */
  const find = async () => {
    setBusy(true)
    try {
      const out = await api.post('/research/run', { region, category, lang, count })
      setFound(out)
      setStep(2)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  /* ---- step 2: keep them, which tags them and makes the group ---- */
  const keep = async () => {
    setBusy(true)
    try {
      const list = await api.get('/research/leads?status=new&size=200')
      const ids = (list.items || []).filter((l) => l.email).map((l) => l.id)
      if (!ids.length) {
        setStep(3)
        return
      }
      const out = await api.post('/research/leads/accept', { ids })
      setKept(out)
      invalidate('/contacts')
      invalidate('/segments')
      setStep(3)
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  /* ---- step 4: make the campaign, attach the group, start it ---- */
  const launch = async () => {
    if (!template) return onToast?.(t('wiz.needTemplate'))
    // professional mode writes its own subject, one per prospect
    if (mode === 'manual' && !subject.trim()) return onToast?.(t('wiz.needSubject'))
    setBusy(true)
    try {
      // the design's own HTML becomes the campaign's body
      const { html } = await api.get(`/templates/${template}/html`)
      const name = kept?.group || subject.trim()
      const made = await api.post('/campaigns', {
        name: { en: name, fa: name },
        subject: { en: subject.trim(), fa: subject.trim() },
        body: { en: html, fa: html },
        segment: kept?.groupId || undefined,
        write_mode: mode,
        goal: goal.trim(),
      })
      // The test, if one was defined. Before the send, because assignment
      // happens as the queue is filled and a variant defined afterwards
      // would apply to nobody.
      if (abField && abA.trim() && abB.trim()) {
        await api.put(`/campaigns/${made.id}/variants`,
                      { field: abField, values: [abA.trim(), abB.trim()] })
      }
      // the rate is a workspace setting, and the sender reads it per send,
      // so setting it here changes this campaign and every later one
      await api.patch('/settings', { throttle_per_hour: rate }).catch(() => {})
      const out = await api.post(`/campaigns/${made.id}/send`,
                                 when === 'now'
                                   ? { mode: 'now' }
                                   : { mode: 'schedule', scheduled_for: new Date(at).toISOString() })
      invalidate('/campaigns')
      invalidate('/stats')
      // the send route answers with the campaign, whose `recipients` is
      // what actually made it into the queue after suppression
      onToast?.(t('wiz.done', { n: nf(out.recipients ?? total) }))
      onClose?.()
      navigate('campaigns')
    } catch (err) {
      fail(err)
    } finally {
      setBusy(false)
    }
  }

  const steps = [t('wiz.s1'), t('wiz.s2'), t('wiz.s3'), t('wiz.s4')]

  return (
    <Modal
      open={open}
      onClose={onClose}
      width={64}
      title={t('wiz.title')}
      sub={t('wiz.sub')}
      footer={
        <>
          <Button variant="quiet" onClick={step === 1 ? onClose : () => setStep(step - 1)}>
            {step === 1 ? t('wiz.close') : t('wiz.back')}
          </Button>
          {step === 1 && (
            <Button variant="primary" icon={<IcSearch size={15} />} loading={busy}
                    disabled={!category.trim() || !region.trim()} onClick={find}>
              {t('wiz.find')}
            </Button>
          )}
          {step === 2 && (
            <Button variant="primary" icon={<IcCheckC size={15} />} loading={busy}
                    onClick={keep}>
              {t('wiz.keep')}
            </Button>
          )}
          {step === 3 && (
            <Button variant="primary" onClick={() => setStep(4)}
                    disabled={!template
                              || (mode === 'manual' && !subject.trim())
                              || (mode === 'professional' && !brand?.proReady)}>
              {t('wiz.next')}
            </Button>
          )}
          {step === 4 && (
            <Button variant="primary" icon={<IcSend size={15} />} loading={busy} onClick={launch}>
              {t('wiz.launch')}
            </Button>
          )}
        </>
      }
    >
      <div className="wiz">
        <ol className="wiz__rail">
          {steps.map((label, i) => (
            <li key={label}
                className={`wiz__dot${i + 1 === step ? ' wiz__dot--on' : ''}${i + 1 < step ? ' wiz__dot--done' : ''}`}>
              <span className="wiz__num">{i + 1 < step ? <IcCheckC size={13} /> : nf(i + 1)}</span>
              <span className="wiz__label">{label}</span>
            </li>
          ))}
        </ol>

        {step === 1 && (
          <div className="setup__grid">
            <Field label={t('res.category')} hint={t('res.categoryHint')} required>
              <Input value={category} placeholder={t('res.categoryPh')}
                     onChange={(e) => setCategory(e.target.value)} />
            </Field>
            <Field label={t('res.region')} hint={t('res.regionHint')} required>
              <Input value={region} placeholder={t('res.regionPh')}
                     onChange={(e) => setRegion(e.target.value)} />
            </Field>
            <Field label={t('res.count')} hint={t('res.countHint', { max: nf(FIND_CEILING) })}>
              <Input type="number" min={1} max={FIND_CEILING} value={count}
                     onChange={(e) => setCount(Math.max(1, Math.min(FIND_CEILING,
                                                                    Number(e.target.value) || 1)))} />
            </Field>
            <p className="wiz__note wiz__note--wide">
              <IcWarn size={15} />
              {t('res.rule')}
            </p>
          </div>
        )}

        {step === 2 && (
          <div className="stack-v">
            {found?.found ? (
              <>
                <div className="wiz__big">{t('wiz.foundTitle', { n: nf(found.found) })}</div>
                <p className="muted">{t('wiz.foundHint', { e: nf(found.withEmail || 0) })}</p>
              </>
            ) : (
              <p className="muted">{t('wiz.foundNone')}</p>
            )}
            {kept?.group && (
              <Card>
                <div className="strong">{t('wiz.kept', { n: nf(kept.added), tag: kept.group })}</div>
                <div className="faint">{t('wiz.keptHint')}</div>
              </Card>
            )}
          </div>
        )}

        {step === 3 && (
          <div className="stack-v">
            {/* Who writes it, asked before what it says — because in
                professional mode the subject is not the reader's to type. */}
            <div className="mode">
              <button type="button"
                      className={`mode__card${mode === 'manual' ? ' mode__card--on' : ''}`}
                      onClick={() => setMode('manual')}>
                <span className="mode__title">✍️ {t('mode.manual')}</span>
                <span className="mode__hint">{t('mode.manualHint')}</span>
              </button>
              <button type="button"
                      className={`mode__card${mode === 'professional' ? ' mode__card--on' : ''}`}
                      onClick={() => setMode('professional')}>
                <span className="mode__title">✨ {t('mode.pro')}</span>
                <span className="mode__hint">{t('mode.proHint')}</span>
                {brand && !brand.proReady && (
                  <span className="mode__warn">{t('mode.proNeeds')}</span>
                )}
              </button>
            </div>

            {mode === 'professional' && brand && !brand.proReady && (
              <Card>
                <div className="strong">{t('mode.proNeeds')}</div>
                <div className="faint">
                  {t('mode.proMissing', { fields: brand.missingForPro.length })}
                </div>
                <Button size="sm" variant="ghost" style={{ marginTop: '1.2rem' }}
                        onClick={() => { onClose?.(); navigate('settings') }}>
                  {t('mode.goBrand')}
                </Button>
              </Card>
            )}

            {mode === 'professional' && brand?.proReady && (
              <>
                <Field label={t('mode.goal')} hint={t('mode.goalHint')}>
                  <Input value={goal} onChange={(e) => setGoal(e.target.value)} />
                </Field>
                <p className="wiz__note">
                  <IcWarn size={15} />
                  {t('mode.proNote')}
                </p>
              </>
            )}

            {templates.length === 0 ? (
              <Card>
                <div className="strong">{t('wiz.noTemplates')}</div>
                <div className="faint">{t('wiz.noTemplatesHint')}</div>
                <Button size="sm" variant="ghost" style={{ marginTop: '1.2rem' }}
                        onClick={() => { onClose?.(); navigate('designer') }}>
                  {t('wiz.goDesigner')}
                </Button>
              </Card>
            ) : (
              <Field label={t('wiz.pickTemplate')} required>
                <Select
                  value={template}
                  onChange={(v) => {
                    setTemplate(v)
                    // the design's own subject is a better start than an empty box
                    const pick = templates.find((x) => x.id === v)
                    if (pick?.subject && !subject.trim()) setSubject(pick.subject)
                  }}
                  options={templates.map((x) => ({ value: x.id, label: loc(x.name, lang) }))}
                />
              </Field>
            )}
            {/* Professional mode writes a subject per prospect, so asking
                for one global subject here would be asking for something
                that gets thrown away. */}
            {mode === 'manual' && (
              <Field label={t('wiz.subject')} hint={t('wiz.subjectHint')} required>
                <Input value={subject} onChange={(e) => setSubject(e.target.value)} />
              </Field>
            )}

            {/* Optional, and only in manual mode: professional mode writes a
                different subject per prospect, so "version A's subject" is
                not a thing that exists there. */}
            {mode === 'manual' && (
              <Card>
                <div className="strong" style={{ marginBottom: '0.4rem' }}>{t('ab.title')}</div>
                <div className="faint" style={{ marginBottom: '1.2rem' }}>{t('ab.oneThing')}</div>
                <Segmented
                  size="sm"
                  value={abField || 'off'}
                  onChange={(v) => setAbField(v === 'off' ? '' : v)}
                  options={[
                    { value: 'off', label: t('ab.off') },
                    { value: 'subject', label: t('ab.subject') },
                    { value: 'cta', label: t('ab.cta') },
                    { value: 'angle', label: t('ab.angle') },
                  ]}
                />
                {abField && (
                  <div className="stack-v" style={{ marginTop: '1.4rem' }}>
                    <Field label={t('ab.a')}>
                      <Input value={abA} onChange={(e) => setAbA(e.target.value)} />
                    </Field>
                    <Field label={t('ab.b')}>
                      <Input value={abB} onChange={(e) => setAbB(e.target.value)} />
                    </Field>
                    {/* The split, shown before launch rather than discovered
                        afterwards. */}
                    <p className="faint">
                      {t('ab.allocation', { n: nf(Math.floor((kept?.added || 0) / 2)) })}
                    </p>
                  </div>
                )}
              </Card>
            )}
          </div>
        )}

        {step === 4 && (
          <div className="stack-v">
            <Segmented
              value={when}
              onChange={setWhen}
              options={[
                { value: 'now', label: t('wiz.whenNow') },
                { value: 'later', label: t('wiz.whenLater') },
              ]}
            />
            {when === 'later' && (
              <Field label={t('wiz.whenLater')}>
                <Input type="datetime-local" value={at} onChange={(e) => setAt(e.target.value)} />
              </Field>
            )}
            <Field label={t('wiz.rate')} hint={t('wiz.rateHint')}>
              <Select
                value={String(rate)}
                onChange={(v) => setRate(Number(v))}
                options={RATES.map((r) => ({ value: String(r), label: nf(r) }))}
              />
            </Field>
            {flight && (
              <Card>
                <div className="strong" style={{ marginBottom: '1rem' }}>{t('pf.title')}</div>
                <div className="pf">
                  <PfRow label={t('pf.selected')} value={nf(flight.selected)} t={t} />
                  <PfRow label={t('pf.eligible')} value={nf(flight.eligible)} strong t={t} />
                  {Object.entries(flight.counts || {})
                    .filter(([, n]) => n > 0)
                    .map(([reason, n]) => (
                      <PfRow key={reason} label={t(`pf.${reason}`)} value={nf(n)} muted t={t} />
                    ))}
                </div>
                <p className="pf__note">{t('pf.cannotOverride')}</p>
                {flight.senderHealth?.blocking && (
                  <p className="pf__blocked">{t('pf.blocked')}</p>
                )}
              </Card>
            )}

            <Card>
              <div className="strong" style={{ marginBottom: '0.6rem' }}>{t('wiz.plan')}</div>
              <div className="muted">{plan}</div>
              {quiet && (
                <div className="muted" style={{ marginTop: '0.6rem' }}>
                  {t('wiz.planQuiet', { from: quiet.from, to: quiet.to })}
                </div>
              )}
            </Card>
          </div>
        )}
      </div>
    </Modal>
  )
}


/* One line of the pre-flight summary. The excluded reasons are muted: the
   number that matters is how many will actually be written to. */
function PfRow({ label, value, strong, muted, t }) {
  return (
    <div className={`pf__row${strong ? ' pf__row--strong' : ''}${muted ? ' pf__row--muted' : ''}`}>
      <span>{label}</span>
      <span className="pf__value">{value}</span>
    </div>
  )
}
