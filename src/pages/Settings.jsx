/* ============================================================
   SETTINGS — everything administrative, in one place.

   Nine sidebar entries collapsed into tabs here. None of them was
   something an operator visits weekly; several are things they
   touch once, at setup, and never again. Giving each a permanent
   seat in the navigation made the panel look like a platform to
   administer rather than an agent to delegate to.

   Which tabs exist is decided by the DEPLOYMENT, not by this file
   — a customer who was not sold billing has no billing tab, and
   no billing endpoint either. `has()` is the single question.

   The first tab is the agent itself, because it is the only one
   most customers will ever open: what it is called, how it writes,
   and how much rope it has.
   ============================================================ */
import { useEffect, useMemo, useState } from 'react'
import { useI18n } from '../i18n'
import { useAuth } from '../api/auth'
import { api } from '../api/client'
import { useConfig } from '../api/config'
import { navigate, useRoute } from '../router'
import PageHeader from '../layout/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardHead,
  Field,
  Input,
  Select,
  Tabs,
  Textarea,
} from '../ui'
import { SaveBar, useDirty } from '../ui/SaveBar'
import Knowledge from './Knowledge'
import Domains from './Domains'
import Integrations from './Integrations'
import Developers from './Developers'
import Team from './Team'
import Billing from './Billing'
import { MailboxConnect } from '../components/Mailbox'
import { IcGear, IcSpark } from '../components/NavIcons'

export default function Settings({ onToast }) {
  const { t } = useI18n()
  const { has, ready } = useConfig()
  const { can } = useAuth()
  /* `#/settings?tab=sending` opens that tab directly. Used by the Google
     callback, which has to bring the reader back to the card that explains
     what just happened. */
  const { query } = useRoute()
  const [tab, setTab] = useState(() => query.tab || 'agent')

  /* Built from what this deployment actually includes. A tab that is not here
     is not reachable, and its endpoints answer 404.

     Memoised because the guard below depends on it: an array rebuilt every
     render made that effect fire every render. */
  const tabs = useMemo(() => [
    { value: 'agent', label: t('set.agent') },
    { value: 'voice', label: t('set.voice') },
    /* Not module-gated. Every deployment has people who sign in, and the only
       other way to change a password was an SSH command on the server. */
    { value: 'account', label: t('set.account') },
    /* Always present, unlike the DNS section inside it: the mailbox the
       agent sends from is not an optional extra, it is the product
       working at all. */
    { value: 'sending', label: t('set.sending') },
    has('integrations') && { value: 'integrations', label: t('nav.integrations') },
    has('team') && { value: 'team', label: t('nav.team') },
    has('billing') && { value: 'billing', label: t('nav.billing') },
    has('developers') && { value: 'developers', label: t('nav.developers') },
  ].filter(Boolean), [has, t])

  /* Landing on a tab this deployment does not have — from a bookmark, or after
     an owner switched a module off — falls back rather than rendering nothing.

     Guarded on `ready`: until the config arrives, `has()` answers false for
     everything, so without this every tab but the first looked invalid and got
     reset out from under the reader. */
  useEffect(() => {
    if (!ready) return
    if (!tabs.some((x) => x.value === tab)) setTab('agent')
  }, [ready, tabs, tab])

  return (
    <div className="page">
      <PageHeader
        title={t('nav.settings')}
        sub={t('set.sub')}
        actions={
          can('settings.write') && (
            <Button variant="ghost" icon={<IcGear size={16} />} onClick={() => navigate('setup')}>
              {t('set.openSetup')}
            </Button>
          )
        }
      />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />

      <div className="tabbody">
        {tab === 'agent' && <AgentSettings onToast={onToast} />}
        {tab === 'account' && <AccountSettings onToast={onToast} />}
        {tab === 'voice' && <Knowledge embedded onToast={onToast} />}
        {tab === 'sending' && (
          <>
            <MailboxConnect onToast={onToast} />
            {has('domains') && <Domains embedded onToast={onToast} />}
          </>
        )}
        {tab === 'integrations' && <Integrations embedded onToast={onToast} />}
        {tab === 'team' && <Team embedded onToast={onToast} />}
        {tab === 'billing' && <Billing embedded onToast={onToast} />}
        {tab === 'developers' && <Developers embedded onToast={onToast} />}
      </div>
    </div>
  )
}

/* ============================================================
   THE AGENT.

   One agent, not a roster. This is where the customer adjusts the
   three things they legitimately have an opinion about — its name,
   its tone, and whether it may act without being asked — and
   nothing else. Model choice, keys and budgets belong to the
   implementer and live in Setup.
   ============================================================ */
function AgentSettings({ onToast }) {
  const { t } = useI18n()
  const { can } = useAuth()
  const { agent, ai, reload } = useConfig()
  const editable = can('settings.write')

  const [form, setForm] = useState(null)
  const [catalog, setCatalog] = useState(null)
  const [saving, setSaving] = useState(false)
  const [error, setError] = useState('')
  const { dirty, savedAt, commit, rebase } = useDirty(form)

  useEffect(() => {
    if (!editable) return
    let live = true
    Promise.all([api.get('/setup'), api.get('/setup/models')])
      .then(([cfg, cat]) => {
        if (!live) return
        setForm({ ...cfg.agent })
        // what the server has becomes the clean baseline; without this the
        // form would count as changed the moment it finished loading
        rebase({ ...cfg.agent })
        setCatalog(cat)
      })
      .catch(() => {})
    return () => {
      live = false
    }
  }, [editable])

  /* A viewer still gets to know who they are talking to; they just cannot
     change it. Reading the agent's name needs no owner permission. */
  if (!editable) {
    return (
      <Card>
        <div className="stack-v">
          <Field label={t('setup.agent.name')}>
            <div className="strong">{agent.name}</div>
          </Field>
          <Field label={t('setup.agent.role')}>
            <div className="faint">{agent.role || '—'}</div>
          </Field>
          <p className="faint">{t('set.readOnly')}</p>
        </div>
      </Card>
    )
  }

  if (!form || !catalog) {
    return (
      <Card>
        <div className="faint">{t('g.loading')}</div>
      </Card>
    )
  }

  const save = async () => {
    setSaving(true)
    setError('')
    try {
      await api.put('/setup', { agent: form })
      await reload()
      commit()
    } catch (err) {
      // shown in place, next to the button that failed, rather than as a toast
      // that has already faded by the time the reader looks up
      setError(err.message || t('err.failed'))
    } finally {
      setSaving(false)
    }
  }

  const set = (values) => setForm((f) => ({ ...f, ...values }))

  return (
    <Card>
      <div className="row" style={{ justifyContent: 'space-between', marginBottom: '1.8rem' }}>
        <span className="ucard__title">{t('set.agent')}</span>
        <Badge tone={ai.configured ? 'good' : 'warn'}>
          <IcSpark size={13} /> {ai.configured ? t('set.aiOn') : t('set.aiOff')}
        </Badge>
      </div>

      <div className="setup__grid">
        <Field label={t('setup.agent.name')} required>
          <Input value={form.name || ''} onChange={(e) => set({ name: e.target.value })} />
        </Field>
        <Field label={t('setup.agent.role')}>
          <Input value={form.role || ''} onChange={(e) => set({ role: e.target.value })} />
        </Field>
        <Field label={t('setup.agent.tone')}>
          <Select
            value={form.tone}
            onChange={(v) => set({ tone: v })}
            options={catalog.tones.map((x) => ({ value: x, label: t(`setup.tone.${x}`) }))}
          />
        </Field>
        <Field label={t('setup.agent.autonomy')} hint={t('setup.agent.autonomyHint')}>
          <Select
            value={form.autonomy}
            onChange={(v) => set({ autonomy: v })}
            options={catalog.autonomy.map((x) => ({ value: x, label: t(`setup.autonomy.${x}`) }))}
          />
        </Field>
      </div>

      <Field label={t('setup.agent.brief')} hint={t('setup.agent.briefHint')}>
        <Textarea rows={4} value={form.brief || ''} onChange={(e) => set({ brief: e.target.value })} />
      </Field>
      <Field label={t('setup.agent.guardrails')} hint={t('setup.agent.guardrailsHint')}>
        <Textarea
          rows={3}
          value={form.guardrails || ''}
          onChange={(e) => set({ guardrails: e.target.value })}
        />
      </Field>

      <SaveBar dirty={dirty} saving={saving} savedAt={savedAt} error={error} onSave={save} />
    </Card>
  )
}


/* ============================================================
   THE ACCOUNT

   One thing: the password. The endpoint behind it verifies the
   current one and revokes every other session, which is the
   right behaviour and worth telling the reader about — a person
   who changes their password because they think someone else has
   it wants to know the other sessions are gone.
   ============================================================ */
function AccountSettings({ onToast }) {
  const { t } = useI18n()
  const { user } = useAuth()
  const [current, setCurrent] = useState('')
  const [next, setNext] = useState('')
  const [again, setAgain] = useState('')
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState('')

  const tooShort = next.length > 0 && next.length < 8
  const mismatch = again.length > 0 && next !== again
  const ready = current && next.length >= 8 && next === again

  const save = async () => {
    setBusy(true)
    setError('')
    try {
      await api.post('/auth/password', { current_password: current, new_password: next })
      setCurrent(''); setNext(''); setAgain('')
      onToast?.(t('acct.changed'))
    } catch (err) {
      // the server's own sentence — "current password is incorrect" is the
      // one thing the reader can act on
      setError(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Card>
      <CardHead title={t('acct.title')} sub={t('acct.sub', { email: user?.email || '' })} />
      <div className="stack-v" style={{ maxWidth: '42rem' }}>
        <Field label={t('acct.current')} error={error}>
          <Input type="password" value={current} autoComplete="current-password"
                 onChange={(e) => setCurrent(e.target.value)} />
        </Field>
        <Field label={t('acct.new')} hint={t('acct.newHint')}
               error={tooShort ? t('acct.tooShort') : ''}>
          <Input type="password" value={next} autoComplete="new-password"
                 onChange={(e) => setNext(e.target.value)} />
        </Field>
        <Field label={t('acct.again')} error={mismatch ? t('acct.mismatch') : ''}>
          <Input type="password" value={again} autoComplete="new-password"
                 onChange={(e) => setAgain(e.target.value)}
                 onKeyDown={(e) => e.key === 'Enter' && ready && save()} />
        </Field>
        <p className="muted" style={{ fontSize: '1.18rem', lineHeight: 1.6, margin: 0 }}>
          {t('acct.note')}
        </p>
        <Button variant="primary" loading={busy} disabled={!ready} onClick={save}>
          {t('acct.save')}
        </Button>
      </div>
    </Card>
  )
}
