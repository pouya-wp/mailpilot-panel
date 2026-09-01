/* ============================================================
   SETUP — the implementer's wizard.

   This screen is not for the customer. It belongs to the team
   that installs the agent and hands it over, and it is the only
   place where a deployment's identity is decided: whose name is
   on it, which sections exist, which OpenAI account pays for the
   thinking, and who the agent is.

   Three deliberate choices:

   * EVERY STEP SAVES ON LEAVE. A wizard that only commits at the
     end punishes an interruption by throwing the work away. Each
     step PUTs its own fragment, so closing the tab at step four
     loses step four and nothing before it.

   * THE KEY IS TESTED, NOT TRUSTED. Pasting a key that does not
     work is the single most likely way to hand over a broken
     panel, so the AI step calls the provider and shows the reply
     before it will let you past.

   * WIPING DEMO DATA IS PART OF THE FLOW, not a setting buried
     somewhere. The step exists because the most common way to
     ship someone else's data to a customer is to forget.
   ============================================================ */
import { useEffect, useMemo, useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../api/client'
import { useConfig } from '../api/config'
import { navigate } from '../router'
import { Badge, Button, Card, Field, Input, Select, Textarea, Toggle } from '../ui'
import { SaveBar, useDirty } from '../ui/SaveBar'
import { MailboxClient } from '../components/Mailbox'
import { IcCheckC, IcGear, IcShield, IcSpark, IcTrash, IcWarn } from '../components/NavIcons'

const STEPS = ['brand', 'modules', 'ai', 'sending', 'agent', 'data', 'done']

export default function Setup({ onToast }) {
  const { t, lang } = useI18n()
  const { reload } = useConfig()

  const [step, setStep] = useState(0)
  const [cfg, setCfg] = useState(null)
  const [catalog, setCatalog] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')


  /* Local edits, flushed to the server when the step changes. */
  const [draft, setDraft] = useState({})

  /* Tracked against the CURRENT STEP's slice, not the whole draft: editing the
     brand should not light up the save button on the agent step.

     Declared after `draft` on purpose. Reading a `const` before its own
     declaration is a ReferenceError — "Cannot access 'draft' before
     initialization" — which took the whole screen down. */
  const { dirty, savedAt, commit, rebase } = useDirty(pickForStep(step, draft))

  useEffect(() => {
    let live = true
    Promise.all([api.get('/setup'), api.get('/setup/models')])
      .then(([config, cat]) => {
        if (!live) return
        setCfg(config)
        setCatalog(cat)
        setDraft({
          brand: { ...config.brand },
          lang: { ...config.lang },
          modules: [...config.modules],
          ai: {
            model: config.ai.model,
            search: config.ai.search,
            reasoning: config.ai.reasoning,
            maxTokens: config.ai.maxTokens,
            dailyCap: config.ai.dailyCap,
            monthlyCap: config.ai.monthlyCap,
            key: '',
          },
          sending: { ...config.sending },
          agent: { ...config.agent },
        })
      })
      .catch((err) => onToast?.(err.message))
    return () => {
      live = false
    }
  }, [onToast])

  const patch = (section, values) =>
    setDraft((d) => ({ ...d, [section]: { ...d[section], ...values } }))

  /* One PUT per step. `key: ''` is meaningful to the server — it means "leave
     the installed key alone" — so a step that did not touch it cannot clear it. */
  const flush = async (extra = {}) => {
    setSaving(true)
    setError('')
    try {
      const body = { ...pickForStep(step, draft), ...extra }
      const next = await api.put('/setup', body)
      setCfg(next)
      await reload()
      commit()
      return true
    } catch (err) {
      setError(err.message || t('err.failed'))
      return false
    } finally {
      setSaving(false)
    }
  }

  const go = async (delta) => {
    if (delta > 0 && !(await flush())) return
    const next = Math.min(STEPS.length - 1, Math.max(0, step + delta))
    setStep(next)
    setError('')
    // the next step starts clean, measured against its own values
    rebase(pickForStep(next, draft))
  }

  if (!cfg || !catalog) {
    return (
      <div className="page setup">
        <Card>
          <div className="faint">{t('g.loading')}</div>
        </Card>
      </div>
    )
  }

  const name = STEPS[step]

  return (
    <div className="page setup">
      <header className="setup__head">
        <div>
          <h1 className="setup__title">{t('setup.title')}</h1>
          <p className="setup__sub">{t('setup.sub')}</p>
        </div>
        <Badge tone="info">{t('setup.stepOf', { n: step + 1, total: STEPS.length })}</Badge>
      </header>

      <ol className="setup__rail">
        {STEPS.map((id, i) => (
          <li key={id} className={`setup__dot${i === step ? ' is-on' : ''}${i < step ? ' is-done' : ''}`}>
            <span>{i < step ? <IcCheckC size={13} /> : i + 1}</span>
            {t(`setup.step.${id}`)}
          </li>
        ))}
      </ol>

      <Card className="setup__card">
        {name === 'brand' && <StepBrand draft={draft} patch={patch} t={t} />}
        {name === 'modules' && (
          <StepModules draft={draft} setDraft={setDraft} catalog={catalog} t={t} lang={lang} />
        )}
        {name === 'ai' && (
          <StepAI draft={draft} patch={patch} catalog={catalog} cfg={cfg} t={t} lang={lang} onToast={onToast} />
        )}
        {name === 'sending' && <StepSending draft={draft} patch={patch} t={t} onToast={onToast} />}
        {name === 'agent' && <StepAgent draft={draft} patch={patch} catalog={catalog} t={t} />}
        {name === 'data' && <StepData t={t} onToast={onToast} />}
        {name === 'done' && <StepDone cfg={cfg} t={t} />}
      </Card>

      {/* Saving is available ON the step, not only as a side effect of moving
          to the next one — an interrupted setup should be able to keep what it
          has without pretending to move forward. */}
      {name !== 'done' && name !== 'data' && (
        <SaveBar
          dirty={dirty}
          saving={saving}
          savedAt={savedAt}
          error={error}
          onSave={() => flush()}
          label={t('save.thisStep')}
        />
      )}

      <div className="setup__actions">
        <Button variant="quiet" disabled={step === 0 || saving} onClick={() => go(-1)}>
          {t('g.back')}
        </Button>
        {name !== 'done' ? (
          <Button variant="primary" loading={saving} onClick={() => go(1)}>
            {t('g.next')}
          </Button>
        ) : (
          <Button
            variant="primary"
            icon={<IcCheckC size={15} />}
            loading={saving}
            onClick={async () => {
              setSaving(true)
              try {
                await api.post('/setup/complete')
                await reload()
                onToast?.(t('setup.finished'))
                navigate('home')
              } catch (err) {
                onToast?.(err.message)
              } finally {
                setSaving(false)
              }
            }}
          >
            {t('setup.finish')}
          </Button>
        )}
      </div>
    </div>
  )
}

/** What the picked model costs, said where the choice is made. */
function modelHint(catalog, value, t, lang) {
  const m = (catalog.models || []).find((x) => x.value === value)
  if (!m) return ''
  return t('setup.ai.modelHint', {
    id: m.value,
    inPrice: m.inPrice,
    outPrice: m.outPrice,
    context: m.context >= 1_000_000
      ? `${(m.context / 1_000_000).toFixed(2).replace(/0$/, '')}M`
      : `${Math.round(m.context / 1000)}K`,
  })
}

/* Only the current step's fragment is sent. Sending the whole draft every time
   would re-write fields the operator never looked at. */
function pickForStep(step, draft) {
  switch (STEPS[step]) {
    case 'brand':
      return { brand: draft.brand, lang: draft.lang }
    case 'modules':
      return { modules: draft.modules }
    case 'ai':
      return { ai: draft.ai }
    case 'sending':
      return { sending: draft.sending }
    case 'agent':
      return { agent: draft.agent }
    default:
      return {}
  }
}

/* ---------------------------------------------------------------- 1 · brand */
function StepBrand({ draft, patch, t }) {
  return (
    <>
      <StepHead title={t('setup.brand.title')} sub={t('setup.brand.sub')} />
      <div className="setup__grid">
        <Field label={t('setup.brand.name')} required>
          <Input
            value={draft.brand.name || ''}
            placeholder={t('setup.brand.namePh')}
            onChange={(e) => patch('brand', { name: e.target.value })}
          />
        </Field>
        <Field label={t('setup.brand.tagline')}>
          <Input
            value={draft.brand.tagline || ''}
            placeholder={t('setup.brand.taglinePh')}
            onChange={(e) => patch('brand', { tagline: e.target.value })}
          />
        </Field>
        <Field label={t('setup.brand.accent')} hint={t('setup.brand.accentHint')}>
          <div className="row" style={{ gap: '1rem' }}>
            <input
              type="color"
              className="swatch"
              value={draft.brand.accent || '#7ba3cd'}
              onChange={(e) => patch('brand', { accent: e.target.value })}
            />
            <Input
              className="mono"
              value={draft.brand.accent || ''}
              onChange={(e) => patch('brand', { accent: e.target.value })}
            />
          </div>
        </Field>
        <Field label={t('setup.brand.support')}>
          <Input
            className="mono"
            value={draft.brand.supportEmail || ''}
            placeholder="help@northwind.com"
            onChange={(e) => patch('brand', { supportEmail: e.target.value })}
          />
        </Field>
        <Field label={t('setup.brand.lang')} hint={t('setup.brand.langHint')}>
          <Select
            value={draft.lang.default || 'en'}
            onChange={(v) => patch('lang', { default: v })}
            options={[
              { value: 'en', label: 'English' },
              { value: 'fa', label: 'فارسی' },
            ]}
          />
        </Field>
        <Field label={t('setup.brand.lockLang')}>
          <Toggle
            checked={Boolean(draft.lang.locked)}
            onChange={(v) => patch('lang', { locked: v })}
            label={t('setup.brand.lockLangNote')}
          />
        </Field>
      </div>
    </>
  )
}

/* -------------------------------------------------------------- 2 · modules */
function StepModules({ draft, setDraft, catalog, t, lang }) {
  const toggle = (id) =>
    setDraft((d) => ({
      ...d,
      modules: d.modules.includes(id) ? d.modules.filter((m) => m !== id) : [...d.modules, id],
    }))

  return (
    <>
      <StepHead title={t('setup.modules.title')} sub={t('setup.modules.sub')} />
      <div className="modules">
        {catalog.modules.map((m) => {
          const on = draft.modules.includes(m.id) || m.core
          return (
            <label key={m.id} className={`module${on ? ' module--on' : ''}${m.core ? ' module--core' : ''}`}>
              <input
                type="checkbox"
                checked={on}
                disabled={m.core}
                onChange={() => toggle(m.id)}
              />
              <span className="module__text">
                <span className="module__name">
                  {lang === 'fa' ? m.fa : m.en}
                  {m.core && <Badge tone="neutral" size="sm">{t('setup.modules.always')}</Badge>}
                </span>
                <span className="module__note">{lang === 'fa' ? m.note_fa : m.note_en}</span>
              </span>
            </label>
          )
        })}
      </div>
      <p className="setup__foot">
        <IcWarn size={14} /> {t('setup.modules.enforced')}
      </p>
    </>
  )
}

/* ------------------------------------------------------------------- 3 · AI */
function StepAI({ draft, patch, catalog, cfg, t, lang, onToast }) {
  const [checking, setChecking] = useState(false)
  const [result, setResult] = useState(null)

  const check = async () => {
    setChecking(true)
    setResult(null)
    try {
      const out = await api.post('/setup/verify-key', {
        key: draft.ai.key || '',
        model: draft.ai.model || '',
      })
      setResult({ ok: true, ...out })
    } catch (err) {
      setResult({ ok: false, message: err.message })
    } finally {
      setChecking(false)
    }
  }

  return (
    <>
      <StepHead title={t('setup.ai.title')} sub={t('setup.ai.sub')} />
      <div className="setup__grid">
        <Field label={t('setup.ai.key')} hint={cfg.ai.configured ? t('setup.ai.installed', { hint: cfg.ai.keyHint }) : t('setup.ai.keyHint')}>
          <Input
            className="mono"
            type="password"
            placeholder="sk-…"
            value={draft.ai.key || ''}
            onChange={(e) => patch('ai', { key: e.target.value })}
          />
        </Field>
        <Field label={t('setup.ai.model')} hint={modelHint(catalog, draft.ai.model, t, lang)}>
          <Select
            value={draft.ai.model}
            onChange={(v) => patch('ai', { model: v })}
            options={catalog.models.map((m) => ({
              value: m.value,
              label: `${m.label} — ${(lang === 'fa' && m.note_fa) || m.note}`,
            }))}
          />
        </Field>
        <Field label={t('setup.ai.reasoning')} hint={t('setup.ai.reasoningHint')}>
          <Select
            value={draft.ai.reasoning}
            onChange={(v) => patch('ai', { reasoning: v })}
            options={(catalog.reasoning || []).map((r) => ({ value: r, label: t(`setup.reasoning.${r}`) }))}
          />
        </Field>
        <Field label={t('setup.ai.search')} hint={t('setup.ai.searchHint')}>
          <Toggle
            checked={Boolean(draft.ai.search)}
            onChange={(v) => patch('ai', { search: v })}
            label={t('setup.ai.searchLabel')}
          />
        </Field>
      </div>

      {/* ---- the spend guards ----
          A loop is what empties an OpenAI account, not a long prompt, so these
          are part of setup rather than an advanced setting nobody finds. */}
      <div className="setup__stepHead" style={{ marginTop: '2.4rem' }}>
        <span className="setup__stepIcon">
          <IcShield size={17} />
        </span>
        <div>
          <h2>{t('setup.ai.limits')}</h2>
          <p>{t('setup.ai.limitsSub')}</p>
        </div>
      </div>
      <div className="setup__grid">
        <Field label={t('setup.ai.maxTokens')} hint={t('setup.ai.maxTokensHint', { max: cfg.ai.hardMaxTokens })}>
          <Input
            type="number"
            min={64}
            max={cfg.ai.hardMaxTokens}
            value={draft.ai.maxTokens ?? ''}
            onChange={(e) => patch('ai', { maxTokens: e.target.value })}
          />
        </Field>
        <Field label={t('setup.ai.dailyCap')} hint={t('setup.ai.capHint')}>
          <Input
            type="number"
            min={0}
            value={draft.ai.dailyCap ?? ''}
            onChange={(e) => patch('ai', { dailyCap: e.target.value })}
          />
        </Field>
        <Field label={t('setup.ai.monthlyCap')} hint={t('setup.ai.capHint')}>
          <Input
            type="number"
            min={0}
            value={draft.ai.monthlyCap ?? ''}
            onChange={(e) => patch('ai', { monthlyCap: e.target.value })}
          />
        </Field>
      </div>
      {cfg.usage && (
        <p className="setup__foot">
          <IcShield size={14} />
          {t('setup.ai.usedSoFar', {
            today: cfg.usage.today.tokens.toLocaleString(),
            month: cfg.usage.month.tokens.toLocaleString(),
            burst: cfg.usage.burstMax,
          })}
        </p>
      )}

      <div className="row" style={{ gap: '1rem', marginTop: '1.6rem' }}>
        <Button variant="ghost" icon={<IcSpark size={15} />} loading={checking} onClick={check}>
          {t('setup.ai.test')}
        </Button>
        {result?.ok && (
          <Badge tone="good">
            <IcCheckC size={13} /> {t('setup.ai.works', { model: result.model })}
          </Badge>
        )}
        {result && !result.ok && <Badge tone="bad">{result.message}</Badge>}
      </div>

      {cfg.ai.configured && (
        <button
          className="linkbtn"
          onClick={async () => {
            await api.put('/setup', { ai: { clearKey: true } })
            onToast?.(t('setup.ai.cleared'))
          }}
        >
          {t('setup.ai.clear')}
        </button>
      )}
    </>
  )
}

/* -------------------------------------------------------------- 4 · sending */
function StepSending({ draft, patch, t, onToast }) {
  return (
    <>
      <StepHead title={t('setup.sending.title')} sub={t('setup.sending.sub')} />
      <div className="setup__grid">
        <Field label={t('setup.sending.fromName')}>
          <Input
            value={draft.sending.fromName || ''}
            placeholder={t('setup.sending.fromNamePh')}
            onChange={(e) => patch('sending', { fromName: e.target.value })}
          />
        </Field>
        <Field label={t('setup.sending.fromEmail')}>
          <Input
            className="mono"
            value={draft.sending.fromEmail || ''}
            placeholder="hello@mail.northwind.com"
            onChange={(e) => patch('sending', { fromEmail: e.target.value })}
          />
        </Field>
        <Field label={t('setup.sending.replyTo')}>
          <Input
            className="mono"
            value={draft.sending.replyTo || ''}
            placeholder="replies@northwind.com"
            onChange={(e) => patch('sending', { replyTo: e.target.value })}
          />
        </Field>
      </div>

      {/* The OAuth client, and only the client. Which MAILBOX gets connected
          is the customer's decision and happens in Settings — an implementer
          should not be authorising someone else's Google account. */}
      <h3 className="setup__subhead">{t('gm.clientTitle')}</h3>
      <p className="setup__subnote">{t('gm.clientSub')}</p>
      <MailboxClient onToast={onToast} />
    </>
  )
}

/* ---------------------------------------------------------------- 5 · agent */
function StepAgent({ draft, patch, catalog, t }) {
  return (
    <>
      <StepHead title={t('setup.agent.title')} sub={t('setup.agent.sub')} />
      <div className="setup__grid">
        <Field label={t('setup.agent.name')} required>
          <Input
            value={draft.agent.name || ''}
            placeholder={t('setup.agent.namePh')}
            onChange={(e) => patch('agent', { name: e.target.value })}
          />
        </Field>
        <Field label={t('setup.agent.role')}>
          <Input
            value={draft.agent.role || ''}
            placeholder={t('setup.agent.rolePh')}
            onChange={(e) => patch('agent', { role: e.target.value })}
          />
        </Field>
        <Field label={t('setup.agent.tone')}>
          <Select
            value={draft.agent.tone}
            onChange={(v) => patch('agent', { tone: v })}
            options={catalog.tones.map((x) => ({ value: x, label: t(`setup.tone.${x}`) }))}
          />
        </Field>
        <Field label={t('setup.agent.autonomy')} hint={t('setup.agent.autonomyHint')}>
          <Select
            value={draft.agent.autonomy}
            onChange={(v) => patch('agent', { autonomy: v })}
            options={catalog.autonomy.map((x) => ({ value: x, label: t(`setup.autonomy.${x}`) }))}
          />
        </Field>
      </div>

      <Field label={t('setup.agent.brief')} hint={t('setup.agent.briefHint')}>
        <Textarea
          rows={4}
          value={draft.agent.brief || ''}
          placeholder={t('setup.agent.briefPh')}
          onChange={(e) => patch('agent', { brief: e.target.value })}
        />
      </Field>
      <Field label={t('setup.agent.voiceAxes')} hint={t('setup.agent.voiceAxesHint')}>
        <Toggle
          checked={draft.agent.voiceAxes !== false}
          onChange={(v) => patch('agent', { voiceAxes: v })}
          label={t('setup.agent.voiceAxesOn')}
        />
      </Field>

      <Field label={t('setup.agent.guardrails')} hint={t('setup.agent.guardrailsHint')}>
        <Textarea
          rows={3}
          value={draft.agent.guardrails || ''}
          placeholder={t('setup.agent.guardrailsPh')}
          onChange={(e) => patch('agent', { guardrails: e.target.value })}
        />
      </Field>
    </>
  )
}

/* ----------------------------------------------------------------- 6 · data */
function StepData({ t, onToast }) {
  const [wiping, setWiping] = useState(false)
  const [done, setDone] = useState(null)

  return (
    <>
      <StepHead title={t('setup.data.title')} sub={t('setup.data.sub')} />
      <Card className="danger-card">
        <div>
          <div className="strong">{t('setup.data.wipe')}</div>
          <div className="faint">{t('setup.data.wipeNote')}</div>
        </div>
        <Button
          variant="ghost"
          className="btn--danger"
          icon={<IcTrash size={15} />}
          loading={wiping}
          onClick={async () => {
            setWiping(true)
            try {
              const out = await api.post('/setup/wipe-demo')
              setDone(out.rows)
              onToast?.(t('setup.data.wiped', { n: out.rows }))
            } catch (err) {
              onToast?.(err.message)
            } finally {
              setWiping(false)
            }
          }}
        >
          {t('setup.data.wipeAction')}
        </Button>
      </Card>
      {done !== null && (
        <p className="setup__foot">
          <IcCheckC size={14} /> {t('setup.data.wiped', { n: done })}
        </p>
      )}
    </>
  )
}

/* ----------------------------------------------------------------- 7 · done */
function StepDone({ cfg, t }) {
  const summary = useMemo(
    () => [
      { k: t('setup.brand.name'), v: cfg.brand.name },
      { k: t('setup.modules.title'), v: cfg.modules.length },
      { k: t('setup.ai.title'), v: cfg.ai.configured ? cfg.ai.model : t('setup.ai.none') },
      { k: t('setup.agent.name'), v: cfg.agent.name },
    ],
    [cfg, t]
  )
  return (
    <>
      <StepHead title={t('setup.done.title')} sub={t('setup.done.sub')} />
      <dl className="summary">
        {summary.map((row) => (
          <div key={row.k}>
            <dt>{row.k}</dt>
            <dd>{row.v}</dd>
          </div>
        ))}
      </dl>
    </>
  )
}

function StepHead({ title, sub }) {
  return (
    <div className="setup__stepHead">
      <span className="setup__stepIcon">
        <IcGear size={17} />
      </span>
      <div>
        <h2>{title}</h2>
        <p>{sub}</p>
      </div>
    </div>
  )
}
