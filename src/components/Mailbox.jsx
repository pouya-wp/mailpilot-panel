/* ============================================================
   THE MAILBOX.

   Two audiences, two components, deliberately kept apart.

   `MailboxClient` is for the IMPLEMENTER. Creating an OAuth
   client in Google Cloud, pasting an id and a secret, and
   registering a redirect URI is setup work done once by the team
   that sells the panel. It lives in the wizard.

   `MailboxConnect` is for the CUSTOMER. One button, one sentence
   saying which address is connected, and a way to prove it works.
   Nobody using this product should have to know what a refresh
   token is.

   The redirect URI is shown, copyable, next to the fields. It has
   to match the Google console entry byte for byte, and a mismatch
   is the single most common reason this setup fails — so it is
   printed rather than described.
   ============================================================ */
import { useCallback, useEffect, useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../api/client'
import { Badge, Button, Card, CardHead, Field, Input } from '../ui'
import { Skeleton } from '../ui/state'
import { IcCheckC, IcCopy, IcMail, IcRefresh, IcSend, IcWarn } from './NavIcons'

/** Shared loader. Both halves need the same document. */
export function useMailbox() {
  const [status, setStatus] = useState(null)
  const [error, setError] = useState('')

  const load = useCallback(async () => {
    try {
      setStatus(await api.get('/google/status'))
      setError('')
    } catch (err) {
      setError(err.message)
    }
  }, [])

  useEffect(() => {
    load()
  }, [load])

  return { status, error, reload: load }
}

/* ============================================================ implementer */

export function MailboxClient({ onToast }) {
  const { t } = useI18n()
  const { status, reload } = useMailbox()
  const [clientId, setClientId] = useState('')
  const [secret, setSecret] = useState('')
  const [saving, setSaving] = useState(false)

  useEffect(() => {
    if (status) setClientId(status.clientId || '')
  }, [status?.clientId])

  if (!status) return <Skeleton rows={4} />

  const save = async () => {
    setSaving(true)
    try {
      await api.put('/google/client', { clientId, clientSecret: secret })
      setSecret('')
      await reload()
      onToast?.(t('gm.clientSaved'))
    } catch (err) {
      onToast?.(err.message)
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="mailbox">
      <div className="setup__grid">
        <Field label={t('gm.clientId')} hint={t('gm.clientIdHint')} wide>
          <Input
            className="mono"
            value={clientId}
            placeholder="1234567890-abc.apps.googleusercontent.com"
            onChange={(e) => setClientId(e.target.value)}
          />
        </Field>
        <Field
          label={t('gm.clientSecret')}
          /* Same rule as the OpenAI key: blank means keep what is installed,
             so correcting a typo in the id cannot silently wipe the secret. */
          hint={status.hasSecret ? t('gm.secretInstalled') : t('gm.secretHint')}
          wide
        >
          <Input
            className="mono"
            type="password"
            value={secret}
            placeholder={status.hasSecret ? '••••••••••••' : 'GOCSPX-…'}
            onChange={(e) => setSecret(e.target.value)}
          />
        </Field>
      </div>

      <RedirectUri value={status.redirectUri} t={t} onToast={onToast} />

      <Button variant="primary" loading={saving} onClick={save}>
        {t('gm.saveClient')}
      </Button>
    </div>
  )
}

function RedirectUri({ value, t, onToast }) {
  return (
    <div className="mailbox__uri">
      <div>
        <span className="mailbox__uriLabel">{t('gm.redirectUri')}</span>
        <code>{value}</code>
      </div>
      <Button
        variant="ghost"
        icon={<IcCopy size={14} />}
        onClick={() => {
          navigator.clipboard?.writeText(value)
          onToast?.(t('gm.copied'))
        }}
      >
        {t('g.copy')}
      </Button>
      <p className="mailbox__uriHint">{t('gm.redirectHint')}</p>
    </div>
  )
}

/* =============================================================== customer */

export function MailboxConnect({ onToast, embedded = false }) {
  const { t, ago } = useI18n()
  const { status, reload } = useMailbox()
  const [busy, setBusy] = useState('')

  /* The callback comes back as `#/settings?google=…`. Read it once, say what
     happened in the reader's language, then clean the URL so a refresh does
     not replay the message. */
  useEffect(() => {
    const query = new URLSearchParams(window.location.hash.split('?')[1] || '')
    const result = query.get('google')
    if (!result) return
    onToast?.(t(`gm.result.${result}`))
    // the result is consumed; the tab is not, or cleaning the URL would throw
    // the reader back to the agent tab they did not ask for
    window.history.replaceState(null, '', '#/settings?tab=sending')
    reload()
  }, []) // eslint-disable-line react-hooks/exhaustive-deps

  if (!status) return <Skeleton rows={3} />

  const act = async (name, fn) => {
    setBusy(name)
    try {
      await fn()
    } catch (err) {
      onToast?.(err.message)
    } finally {
      setBusy('')
    }
  }

  const connect = () =>
    act('connect', async () => {
      const { url } = await api.post('/google/connect')
      // A full navigation, not a popup: Google refuses to render its consent
      // screen inside a frame, and a blocked popup looks like a broken button.
      window.location.href = url
    })

  const body = !status.clientId ? (
    <p className="mailbox__note">
      <IcWarn size={15} /> {t('gm.noClient')}
    </p>
  ) : status.connected ? (
    <>
      <div className="mailbox__who">
        <span className="mailbox__ok">
          <IcCheckC size={16} />
        </span>
        <div>
          <strong>{status.email}</strong>
          <p>{status.connectedAt ? t('gm.since', { when: ago(status.connectedAt) }) : ''}</p>
        </div>
        <Badge tone="good">{t('gm.connected')}</Badge>
      </div>

      {status.fromMismatch && (
        <p className="mailbox__note">
          <IcWarn size={15} />
          {t('gm.fromMismatch', { from: status.fromEmail, mailbox: status.email })}
        </p>
      )}

      <p className="mailbox__limit">{t('gm.limit', { free: status.dailyHint?.free, work: status.dailyHint?.workspace })}</p>

      {status.queue?.queued > 0 && (
        <p className="mailbox__queue">{t('gm.queued', { n: status.queue.queued })}</p>
      )}

      <div className="mailbox__row">
        <Button
          icon={<IcSend size={15} />}
          loading={busy === 'test'}
          onClick={() =>
            act('test', async () => {
              const out = await api.post('/google/test', {})
              onToast?.(t('gm.testSent', { to: out.to }))
            })
          }
        >
          {t('gm.test')}
        </Button>
        <Button
          variant="ghost"
          icon={<IcRefresh size={15} />}
          loading={busy === 'connect'}
          onClick={connect}
        >
          {t('gm.reconnect')}
        </Button>
        <Button
          variant="quiet"
          loading={busy === 'off'}
          onClick={() =>
            act('off', async () => {
              await api.post('/google/disconnect')
              await reload()
              onToast?.(t('gm.disconnected'))
            })
          }
        >
          {t('gm.disconnect')}
        </Button>
      </div>
    </>
  ) : (
    <>
      <p className="mailbox__note">{t('gm.explain')}</p>
      <ul className="mailbox__scopes">
        <li>{t('gm.scope.send')}</li>
        <li>{t('gm.scope.read')}</li>
        <li>{t('gm.scope.not')}</li>
      </ul>
      <Button variant="primary" icon={<IcMail size={15} />} loading={busy === 'connect'} onClick={connect}>
        {t('gm.connect')}
      </Button>
    </>
  )

  if (embedded) return <div className="mailbox">{body}</div>

  return (
    <Card className="mailbox">
      <CardHead title={t('gm.title')} sub={t('gm.sub')} icon={<IcMail size={16} />} />
      {body}
    </Card>
  )
}
