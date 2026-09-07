/* TEAM — members and what each role may actually do. The
   permission matrix is printed rather than described, because
   "Editor" means something different in every product and a reader
   deciding what to grant someone should not have to guess. */
import { useState } from 'react'
import { useI18n, loc } from '../i18n'
import { useChangeRole, useInviteMember, useRemoveMember, useTeam } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHead,
  Field,
  Input,
  Menu,
  Modal,
  Select,
  Stagger,
  Table,
} from '../ui'

import { IcCheckC, IcDots, IcPlus, IcTeam, IcTrash, IcX } from '../components/NavIcons'

const ROLES = ['owner', 'admin', 'editor', 'analyst', 'viewer']
const ROLE_TONE = { owner: 'good', admin: 'info', editor: 'neutral', analyst: 'neutral', viewer: 'neutral' }

/* rows are capability keys; the matrix is what each role can do */
const CAPS = [
  { id: 'campaigns.send', en: 'Send campaigns', fa: 'ارسال کمپین', roles: ['owner', 'admin', 'editor'] },
  { id: 'agents.deploy', en: 'Deploy agents', fa: 'استقرار ایجنت', roles: ['owner', 'admin'] },
  { id: 'contacts.export', en: 'Export contacts', fa: 'خروجی مخاطبان', roles: ['owner', 'admin'] },
  { id: 'content.edit', en: 'Edit content', fa: 'ویرایش محتوا', roles: ['owner', 'admin', 'editor'] },
  { id: 'analytics.view', en: 'View analytics', fa: 'دیدن تحلیل‌ها', roles: ['owner', 'admin', 'editor', 'analyst', 'viewer'] },
  { id: 'billing.manage', en: 'Manage billing', fa: 'مدیریت صورتحساب', roles: ['owner'] },
  { id: 'team.invite', en: 'Invite members', fa: 'دعوت اعضا', roles: ['owner', 'admin'] },
]

export default function Team({ onToast, embedded }) {
  const { t, lang, nf, ago } = useI18n()
  const query = useTeam()
  const [sendInvite, inviting] = useInviteMember()
  const [changeRole] = useChangeRole()
  const [removeMember] = useRemoveMember()
  const [inviteOpen, setInviteOpen] = useState(false)
  const [inviteEmail, setInviteEmail] = useState('')
  const [inviteRole, setInviteRole] = useState('editor')

  return (
    <div className="page">
      <PageHeader
        embedded={embedded}
        title={t('team.title')}
        sub={t('team.sub')}
        actions={
          <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => setInviteOpen(true)}>
            {t('team.invite')}
          </Button>
        }
      />

      <Stagger className="stack-v">
        <Card pad={false} className="panel">
          <Table
            keyFn={(m) => m.id}
            rows={query.data || []}
            empty={{ icon: <IcTeam size={26} /> }}
            columns={[
              {
                key: 'name',
                title: t('g.name'),
                width: 'minmax(0, 2fr)',
                render: (m) => (
                  <span className="tname">
                    <Avatar name={loc(m.name, lang)} size={34} ring />
                    <span className="tname__text">
                      <span className="tname__main">{loc(m.name, lang)}</span>
                      <span className="tname__sub mono">{m.email}</span>
                    </span>
                  </span>
                ),
              },
              {
                key: 'role',
                title: t('team.role'),
                width: 'minmax(0, 1fr)',
                render: (m) => <Badge tone={ROLE_TONE[m.role]}>{t(`team.role.${m.role}`)}</Badge>,
              },
              {
                key: 'status',
                title: t('g.status'),
                width: 'minmax(0, 1fr)',
                render: (m) =>
                  m.status === 'pending' ? (
                    <Badge tone="warn" dot>
                      {t('team.pending')}
                    </Badge>
                  ) : (
                    <Badge tone="good" dot>
                      {t('g.active')}
                    </Badge>
                  ),
              },
              {
                key: 'active',
                title: t('team.lastActive'),
                width: 'minmax(0, 1fr)',
                render: (m) => <span className="faint">{m.active ? ago(m.active) : '—'}</span>,
              },
              {
                key: 'act',
                title: '',
                width: '4rem',
                align: 'center',
                render: (m) => (
                  <Menu
                    align="end"
                    trigger={
                      <button className="iconbtn" style={{ width: '3rem', height: '3rem' }} aria-label={t('g.actions')}>
                        <IcDots size={15} />
                      </button>
                    }
                    items={[
                      { id: 'e', label: t('g.edit') },
                      { divider: true },
                      { id: 'x', label: t('g.delete'), icon: <IcTrash size={15} />, tone: 'danger', disabled: m.role === 'owner' },
                    ]}
                  />
                ),
              },
            ]}
          />
        </Card>

        {/* ---- permission matrix ---- */}
        <Card>
          <CardHead title={t('team.permissions')} icon={<IcTeam size={17} />} />
          <div style={{ overflowX: 'auto' }}>
            <div
              style={{
                display: 'grid',
                gridTemplateColumns: `minmax(18rem, 1.6fr) repeat(${ROLES.length}, minmax(0, 1fr))`,
                gap: '0.4rem',
                minWidth: '58rem',
              }}
            >
              <span />
              {ROLES.map((r) => (
                <span key={r} className="caps" style={{ textAlign: 'center' }}>
                  {t(`team.role.${r}`)}
                </span>
              ))}

              {CAPS.map((c) => (
                <div key={c.id} style={{ display: 'contents' }}>
                  <span
                    style={{
                      display: 'flex',
                      alignItems: 'center',
                      fontSize: '1.28rem',
                      color: 'var(--tx-2)',
                      padding: '1rem 0',
                      borderTop: '1px solid var(--stroke-soft)',
                    }}
                  >
                    {lang === 'fa' ? c.fa : c.en}
                  </span>
                  {ROLES.map((r) => (
                    <span
                      key={r}
                      style={{
                        display: 'grid',
                        placeItems: 'center',
                        padding: '1rem 0',
                        borderTop: '1px solid var(--stroke-soft)',
                        color: c.roles.includes(r) ? 'var(--good)' : 'var(--tx-4)',
                      }}
                    >
                      {c.roles.includes(r) ? <IcCheckC size={16} /> : <IcX size={13} />}
                    </span>
                  ))}
                </div>
              ))}
            </div>
          </div>
        </Card>
      </Stagger>

      <Modal
        open={inviteOpen}
        onClose={() => setInviteOpen(false)}
        width={50}
        title={t('team.invite')}
        footer={
          <>
            <Button variant="quiet" onClick={() => setInviteOpen(false)}>
              {t('g.cancel')}
            </Button>
            <Button
              variant="primary"
              loading={inviting.loading}
              onClick={async () => {
                try {
                  await sendInvite({ email: inviteEmail, role: inviteRole })
                  setInviteOpen(false)
                  onToast?.(t('toast.saved'))
                } catch (err) {
                  onToast?.(err.message || t('err.failed'))
                }
              }}
            >
              {t('team.invite')}
            </Button>
          </>
        }
      >
        <div className="stack-v">
          <Field label={t('ct.email')} required>
            <Input
              placeholder="name@company.com"
              className="mono"
              value={inviteEmail}
              onChange={(e) => setInviteEmail(e.target.value)}
            />
          </Field>
          <Field label={t('team.role')} hint={t('team.permissions')}>
            <Select
              value={inviteRole}
              onChange={setInviteRole}
              options={ROLES.filter((r) => r !== 'owner').map((r) => ({ value: r, label: t(`team.role.${r}`) }))}
            />
          </Field>
        </div>
      </Modal>
    </div>
  )
}
