/* SUPPRESSION — the addresses nothing will ever reach again.
   Kept as a first-class page rather than a settings sub-tab: it is
   the list that keeps you out of trouble, and it should be as easy
   to audit as the contact list itself. */
import { useState } from 'react'
import { useI18n } from '../i18n'
import { useDebounced } from '../api/hooks'
import { api } from '../api/client'
import { useAddSuppression, useRemoveSuppression, useSuppression } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import {
  Badge,
  Button,
  Card,
  Field,
  Input,
  Kpi,
  Modal,
  Pagination,
  SearchBox,
  Select,
  Stagger,
  Table,
} from '../ui'
import { IcDownload, IcPlus, IcShield, IcTrash } from '../components/NavIcons'

const REASON_TONE = { unsub: 'neutral', bounce: 'bad', complaint: 'warn', manual: 'info' }
const PAGE_SIZE = 10

export default function Suppression({ onToast, embedded }) {
  const { t, nf, date } = useI18n()
  const [q, setQ] = useState('')
  const [reason, setReason] = useState('all')
  const [page, setPage] = useState(1)
  const [add, setAdd] = useState(false)
  const [newEmail, setNewEmail] = useState('')
  const [newReason, setNewReason] = useState('manual')

  const search = useDebounced(q, 300)
  const query = useSuppression({ q: search, reason, page, size: PAGE_SIZE })
  const [addEntry, adding] = useAddSuppression()
  const [removeEntry] = useRemoveSuppression()

  /* Filtering, paging and the per-reason tally are all server-side, so the
     figures in the KPI row describe the whole list rather than the page. */
  const rows = query.data?.items || []
  const pages = query.data?.pages || 1
  const total = query.data?.total || 0
  const counts = query.data?.counts || {}

  return (
    <div className="page">
      {!embedded && (
      <PageHeader
        title={t('sup.title')}
        sub={t('sup.sub')}
        actions={
          <>
            <Button
              variant="ghost"
              icon={<IcDownload size={16} />}
              onClick={async () => {
                try {
                  await api.download('/suppression/export', 'blocked.csv')
                } catch (err) {
                  onToast?.(err.message)
                }
              }}
            >
              {t('g.export')}
            </Button>
            <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => setAdd(true)}>
              {t('sup.add')}
            </Button>
          </>
        }
      />
      )}

      <Stagger className="stack-v">
        <div className="kpirow" style={{ margin: 0 }}>
          <Kpi label={t('sup.title')} value={nf(total)} icon={<IcShield size={15} />} />
          <Kpi label={t('sup.reason.unsub')} value={nf(counts.unsub || 0)} />
          <Kpi label={t('sup.reason.bounce')} value={nf(counts.bounce || 0)} />
          <Kpi label={t('sup.reason.complaint')} value={nf(counts.complaint || 0)} />
        </div>

        <div className="toolbar" style={{ margin: 0 }}>
          <SearchBox value={q} onChange={(v) => { setQ(v); setPage(1) }} placeholder={t('g.search')} />
          <Select
            value={reason}
            onChange={(v) => { setReason(v); setPage(1) }}
            options={[
              { value: 'all', label: `${t('sup.reason')}: ${t('g.all')}` },
              { value: 'unsub', label: t('sup.reason.unsub') },
              { value: 'bounce', label: t('sup.reason.bounce') },
              { value: 'complaint', label: t('sup.reason.complaint') },
              { value: 'manual', label: t('sup.reason.manual') },
            ]}
          />
        </div>

        <Card pad={false} className="panel">
          <Table
            keyFn={(s) => s.id}
            rows={rows}
            empty={{ icon: <IcShield size={26} /> }}
            columns={[
              {
                key: 'email',
                title: t('ct.email'),
                width: 'minmax(0, 2fr)',
                render: (s) => <span className="mono ellip">{s.email}</span>,
              },
              {
                key: 'reason',
                title: t('sup.reason'),
                width: 'minmax(0, 1fr)',
                render: (s) => <Badge tone={REASON_TONE[s.reason]}>{t(`sup.reason.${s.reason}`)}</Badge>,
              },
              {
                key: 'at',
                title: t('sup.addedOn'),
                width: 'minmax(0, 1fr)',
                render: (s) => <span className="faint">{date(s.at, { day: 'numeric', month: 'short', year: 'numeric' })}</span>,
              },
              {
                key: 'act',
                title: '',
                width: '4rem',
                align: 'center',
                render: (row) => (
                  <button
                    className="iconbtn"
                    style={{ width: '3rem', height: '3rem' }}
                    aria-label={t('g.delete')}
                    onClick={async () => {
                      await removeEntry(row.id)
                      onToast?.(t('toast.saved'))
                    }}
                  >
                    <IcTrash size={14} />
                  </button>
                ),
              },
            ]}
          />
          <Pagination page={page} pages={pages} total={total} onChange={setPage} />
        </Card>
      </Stagger>

      <Modal
        open={add}
        onClose={() => setAdd(false)}
        width={48}
        title={t('sup.add')}
        footer={
          <>
            <Button variant="quiet" onClick={() => setAdd(false)}>
              {t('g.cancel')}
            </Button>
            <Button
              variant="primary"
              loading={adding.loading}
              disabled={!newEmail.trim()}
              onClick={async () => {
                try {
                  await addEntry({ email: newEmail.trim(), reason: newReason })
                  setAdd(false)
                  setNewEmail('')
                  onToast?.(t('toast.saved'))
                } catch (err) {
                  onToast?.(err.message)
                }
              }}
            >
              {t('g.create')}
            </Button>
          </>
        }
      >
        <div className="stack-v">
          <Field label={t('ct.email')} required>
            <Input
              placeholder="someone@example.com"
              className="mono"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
            />
          </Field>
          <Field label={t('sup.reason')}>
            <Select
              value={newReason}
              onChange={setNewReason}
              options={['manual', 'unsub', 'bounce', 'complaint'].map((r) => ({ value: r, label: t(`sup.reason.${r}`) }))}
            />
          </Field>
        </div>
      </Modal>
    </div>
  )
}
