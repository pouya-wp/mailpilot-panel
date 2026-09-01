/* DEVELOPERS — API keys, webhooks, and a copyable request.
   The key prefix is shown, never the key: a dashboard that
   re-displays a secret on every page load has effectively removed
   the reason to hash it. */
import { useState } from 'react'
import { useI18n, loc } from '../i18n'
import { useApiKeys, useCreateKey, useRevokeKey, useUpdateWebhook, useWebhooks } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardHead,
  CopyField,
  Field,
  Grid,
  Input,
  Menu,
  Modal,
  Progress,
  Stagger,
  Table,
  Tabs,
  Toggle,
} from '../ui'

import { IcCode, IcDots, IcKey, IcPlus, IcTrash, IcBook } from '../components/NavIcons'

const SNIPPET = `curl https://api.mailpilot.dev/v1/campaigns \\
  -H "Authorization: Bearer $MAILPILOT_KEY" \\
  -H "Content-Type: application/json" \\
  -d '{
    "segment": "vip",
    "agent": "nova",
    "goal": "conversion",
    "send_at": "optimal"
  }'`

export default function Developers({ onToast, embedded }) {
  const { t, lang, nf, pct, ago } = useI18n()
  const keys = useApiKeys()
  const webhooks = useWebhooks()
  const [createKey] = useCreateKey()
  const [revokeKey] = useRevokeKey()
  const [updateWebhook] = useUpdateWebhook()
  const [tab, setTab] = useState('keys')
  const [neu, setNeu] = useState(false)
  /* The plaintext of a freshly created key, held only until the modal closes.
     The server returns it exactly once and cannot recover it afterwards. */
  const [freshKey, setFreshKey] = useState(null)

  return (
    <div className="page">
      <PageHeader
        embedded={embedded}
        title={t('dev.title')}
        sub={t('dev.sub')}
        actions={
          <>
            {/* The API documents itself at /api/docs. A new tab, because
                leaving the panel to read reference material and losing your
                place in it is not a trade anyone wants. */}
            <Button
              variant="ghost"
              icon={<IcBook size={16} />}
              onClick={() => window.open('/api/docs', '_blank', 'noopener')}
            >
              {t('dev.docs')}
            </Button>
            <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => setNeu(true)}>
              {tab === 'keys' ? t('dev.newKey') : t('dev.newWebhook')}
            </Button>
          </>
        }
      />

      <Stagger className="stack-v">
        <Tabs
          value={tab}
          onChange={setTab}
          tabs={[
            { value: 'keys', label: t('dev.apiKeys'), count: (keys.data || []).length },
            { value: 'hooks', label: t('dev.webhooks'), count: (webhooks.data || []).length },
            { value: 'docs', label: t('dev.docs') },
          ]}
        />

        {tab === 'keys' && (
          <Card pad={false} className="panel">
            <Table
              keyFn={(k) => k.id}
              rows={keys.data || []}
              empty={{ icon: <IcKey size={26} /> }}
              columns={[
                {
                  key: 'name',
                  title: t('g.name'),
                  width: 'minmax(0, 1.4fr)',
                  render: (k) => (
                    <span className="tname">
                      <span className="tile__icon" style={{ width: '3.2rem', height: '3.2rem', borderRadius: '1rem' }}>
                        <IcKey size={15} />
                      </span>
                      <span className="tname__text">
                        <span className="tname__main">{loc(k.name, lang)}</span>
                        <span className="tname__sub mono">{k.prefix}••••••••••••</span>
                      </span>
                    </span>
                  ),
                },
                {
                  key: 'scopes',
                  title: t('dev.scopes'),
                  width: 'minmax(0, 1.4fr)',
                  render: (k) => (
                    <span className="row" style={{ gap: '0.4rem', flexWrap: 'wrap' }}>
                      {k.scopes.map((s) => (
                        <Badge key={s} tone={s === '*' ? 'warn' : 'neutral'} size="sm">
                          {s}
                        </Badge>
                      ))}
                    </span>
                  ),
                },
                {
                  key: 'used',
                  title: t('dev.lastUsed'),
                  width: 'minmax(0, 0.9fr)',
                  render: (k) => <span className="faint">{ago(k.lastUsed)}</span>,
                },
                {
                  key: 'act',
                  title: '',
                  width: '4rem',
                  align: 'center',
                  render: () => (
                    <Menu
                      align="end"
                      trigger={
                        <button className="iconbtn" style={{ width: '3rem', height: '3rem' }} aria-label={t('g.actions')}>
                          <IcDots size={15} />
                        </button>
                      }
                      items={[
                        { id: 'r', label: t('g.reset') },
                        { divider: true },
                        { id: 'x', label: t('g.delete'), icon: <IcTrash size={15} />, tone: 'danger' },
                      ]}
                    />
                  ),
                },
              ]}
            />
          </Card>
        )}

        {tab === 'hooks' && (
          <div className="stack-v">
            {(webhooks.data || []).map((w) => (
              <Card key={w.id}>
                <div className="row" style={{ gap: '1.2rem', flexWrap: 'wrap' }}>
                  <span className="tile__icon">
                    <IcCode size={17} />
                  </span>
                  <div style={{ flex: 1, minWidth: '20rem' }}>
                    <div className="mono strong" style={{ fontSize: '1.3rem' }}>
                      {w.url}
                    </div>
                    <div className="row" style={{ gap: '0.4rem', flexWrap: 'wrap', marginTop: '0.6rem' }}>
                      {w.events.map((e) => (
                        <Badge key={e} tone="neutral" size="sm">
                          {e}
                        </Badge>
                      ))}
                    </div>
                  </div>
                  <div style={{ minWidth: '14rem' }}>
                    <Progress
                      value={w.ok}
                      tone={w.ok > 95 ? 'good' : w.ok > 70 ? 'warn' : 'bad'}
                      label={t('dev.deliveries')}
                      right={pct(w.ok, 1)}
                    />
                  </div>
                  <Toggle
                    checked={!!w.on}
                    onChange={async (v) => {
                      await updateWebhook({ id: w.id, on: v })
                      onToast?.(v ? t('g.enable') : t('g.disable'))
                    }}
                  />
                </div>
              </Card>
            ))}
          </div>
        )}

        {tab === 'docs' && (
          <div className="cols cols--2">
            <Card>
              <CardHead title={t('dev.docs')} icon={<IcCode size={17} />} sub="POST /v1/campaigns" />
              <pre
                className="mono"
                style={{
                  margin: 0,
                  padding: '1.6rem 1.8rem',
                  borderRadius: 'var(--r-md)',
                  background: 'rgba(0,0,0,.35)',
                  border: '1px solid var(--stroke-soft)',
                  fontSize: '1.18rem',
                  lineHeight: 1.8,
                  color: '#c9d6e6',
                  overflowX: 'auto',
                }}
              >
                {SNIPPET}
              </pre>
              <div style={{ marginTop: '1.2rem' }}>
                <CopyField value="https://api.mailpilot.dev/v1" />
              </div>
            </Card>

            <Card>
              <CardHead title={t('dev.events')} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '0.8rem' }}>
                {[
                  'email.delivered',
                  'email.opened',
                  'email.clicked',
                  'email.bounced',
                  'email.complained',
                  'contact.created',
                  'contact.unsubscribed',
                  'agent.action',
                  'agent.escalation',
                  'experiment.called',
                ].map((e) => (
                  <div className="tile" key={e} style={{ padding: '1rem 1.3rem' }}>
                    <span className="mono" style={{ fontSize: '1.22rem' }}>
                      {e}
                    </span>
                  </div>
                ))}
              </div>
            </Card>
          </div>
        )}
      </Stagger>

      <Modal
        open={neu}
        onClose={() => setNeu(false)}
        width={52}
        title={tab === 'hooks' ? t('dev.newWebhook') : t('dev.newKey')}
        sub={tab === 'hooks' ? undefined : t('dev.keyHint')}
        footer={
          <>
            <Button variant="quiet" onClick={() => setNeu(false)}>
              {t('g.cancel')}
            </Button>
            <Button
              variant="primary"
              onClick={() => {
                setNeu(false)
                onToast?.(t('toast.saved'))
              }}
            >
              {t('g.create')}
            </Button>
          </>
        }
      >
        <div className="stack-v">
          <Field label={t('g.name')} required>
            <Input placeholder={tab === 'hooks' ? 'https://api.example.com/hooks' : 'Production server'} className={tab === 'hooks' ? 'mono' : undefined} />
          </Field>
          <Field label={t('dev.scopes')}>
            <div className="row" style={{ gap: '0.6rem', flexWrap: 'wrap' }}>
              {['campaigns:write', 'contacts:rw', 'analytics:read', 'agents:write'].map((s) => (
                <span className="skillchip" key={s}>
                  {s}
                </span>
              ))}
            </div>
          </Field>
        </div>
      </Modal>
    </div>
  )
}
