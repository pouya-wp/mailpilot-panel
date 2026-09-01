/* ============================================================
   CONTACTS

   Two things a generic CRM table usually gets wrong and this one
   does not:

   * the engagement score is a BAR, not a number. Sorting a column
     of 0–100 integers by eye is work; a column of bars is read in
     one pass.
   * the profile drawer leads with the agent's summary of the
     person, because that is the thing a human cannot reconstruct
     from the raw attribute list underneath it.
   ============================================================ */
import { useMemo, useState } from 'react'
import { loc, useI18n } from '../i18n'
import { invalidate, useDebounced } from '../api/hooks'
import { api } from '../api/client'
import {
  useContact,
  useContactStats,
  useContacts,
  useCreateContact,
  useDeleteContact,
  useUpdateContact,
} from '../api/resources'
import { Async } from '../ui/state'
import PageHeader from '../layout/PageHeader'
import ImportContacts from '../components/ImportContacts'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHead,
  Drawer,
  Field,
  Grid,
  Input,
  Kpi,
  Menu,
  Modal,
  Pagination,
  Progress,
  SearchBox,
  Select,
  Stagger,
  StatusBadge,
  Table,
  Tabs,
} from '../ui'
import { Sparkline } from '../ui/charts'
import { MiniStat } from './Campaigns'
import {
  IcContacts,
  IcDots,
  IcDownload,
  IcMail,
  IcPlus,
  IcSpark,
  IcTag,
  IcTrash,
  IcUpload,
} from '../components/NavIcons'

const PAGE_SIZE = 10

export default function Contacts({ onToast, embedded }) {
  const [importing, setImporting] = useState(false)
  const [adding, setAdding] = useState(false)
  const [tagging, setTagging] = useState(false)
  const [bulking, setBulking] = useState(false)
  const { t, lang, nf, pct, compact, money, ago, date } = useI18n()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('all')
  const [seg, setSeg] = useState('all')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState([])
  const [openId, setOpenId] = useState(null)

  const search = useDebounced(q, 300)
  const query = useContacts({ q: search, status, tag: seg, page, size: PAGE_SIZE })
  const statsQ = useContactStats()
  const detail = useContact(openId)
  const [removeContact] = useDeleteContact()

  const rows = query.data?.items || []
  const pages = query.data?.pages || 1
  const total = query.data?.total || 0
  const stats = statsQ.data || { total: 0, engaged: 0, dormant: 0 }
  const open = detail.data

  const columns = [
    {
      key: 'name',
      title: t('g.name'),
      width: 'minmax(0, 2.2fr)',
      render: (c) => (
        <span className="tname">
          <Avatar name={loc(c.name, lang)} size={32} ring />
          <span className="tname__text">
            <span className="tname__main">{loc(c.name, lang)}</span>
            <span className="tname__sub mono">{c.email}</span>
          </span>
        </span>
      ),
    },
    {
      key: 'status',
      title: t('g.status'),
      width: 'minmax(0, 0.9fr)',
      render: (c) => <StatusBadge status={c.status}>{t(`ct.${c.status}`)}</StatusBadge>,
    },
    {
      key: 'score',
      title: t('ct.score'),
      width: 'minmax(0, 1.1fr)',
      render: (c) => (
        <span style={{ width: '100%', display: 'flex', alignItems: 'center', gap: '0.9rem' }}>
          <span style={{ flex: 1, minWidth: '4rem' }}>
            <Progress
              value={c.score}
              tone={c.score >= 60 ? 'good' : c.score >= 25 ? 'blue' : 'warn'}
            />
          </span>
          <span className="num-tab faint" style={{ fontSize: '1.15rem' }}>
            {nf(c.score)}
          </span>
        </span>
      ),
    },
    {
      key: 'tags',
      title: t('ct.tags'),
      width: 'minmax(0, 1.2fr)',
      render: (c) =>
        c.tags.length ? (
          <span className="row" style={{ gap: '0.4rem', flexWrap: 'wrap' }}>
            {c.tags.slice(0, 2).map((tg) => (
              <Badge key={tg} tone="neutral" size="sm">
                {tg}
              </Badge>
            ))}
            {c.tags.length > 2 && <span className="faint">+{nf(c.tags.length - 2)}</span>}
          </span>
        ) : (
          <span className="faint">—</span>
        ),
    },
    {
      key: 'ltv',
      title: t('ct.lifetime'),
      width: 'minmax(0, 0.8fr)',
      align: 'end',
      render: (c) => <span className="num-tab">{money(c.ltv)}</span>,
    },
    {
      key: 'lastOpen',
      title: t('ct.lastOpen'),
      width: 'minmax(0, 0.9fr)',
      render: (c) => <span className="faint">{ago(c.lastOpen)}</span>,
    },
    {
      key: 'act',
      title: '',
      width: '4rem',
      align: 'center',
      render: (c) => (
        <span onClick={(e) => e.stopPropagation()}>
          <Menu
            align="end"
            trigger={
              <button className="iconbtn" style={{ width: '3rem', height: '3rem' }} aria-label={t('g.actions')}>
                <IcDots size={15} />
              </button>
            }
            items={[
              { id: 'v', label: t('ct.profile'), onClick: () => setOpenId(c.id) },
              { id: 'tag', label: t('ct.tags'), icon: <IcTag size={15} /> },
              { divider: true },
              { id: 'x', label: t('g.delete'), icon: <IcTrash size={15} />, tone: 'danger' },
            ]}
          />
        </span>
      ),
    },
  ]

  return (
    <div className="page">
      {!embedded && (
      <PageHeader
        title={t('ct.title')}
        sub={t('ct.sub')}
        actions={
          <>
            <Button
              variant="ghost"
              icon={<IcDownload size={16} />}
              onClick={async () => {
                try {
                  await api.download('/contacts/export', 'contacts.csv')
                } catch (err) {
                  onToast?.(err.message)
                }
              }}
            >
              {t('g.export')}
            </Button>
            <Button variant="ghost" icon={<IcUpload size={16} />} onClick={() => setImporting(true)}>
              {t('ct.importCsv')}
            </Button>
            <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => setAdding(true)}>
              {t('ct.add')}
            </Button>
          </>
        }
      />
      )}

      <Stagger className="stack-v">
        <div className="kpirow" style={{ margin: 0 }}>
          {/* No deltas here. These counts have no stored history to compare
              against, and a made-up percentage beside a real number is worse
              than no percentage at all. */}
          <Kpi label={t('m.contacts')} value={compact(stats.total)} icon={<IcContacts size={15} />} />
          <Kpi label={t('m.engaged')} value={compact(stats.engaged)} />
          <Kpi label={t('m.dormant')} value={compact(stats.dormant)} />
          <Kpi
            label={t('ct.subscribed')}
            value={compact(stats.subscribed || 0)}
            hint={`${compact(stats.unsubscribed || 0)} ${t('ct.unsubscribed')}`}
          />
        </div>

        <div className="toolbar" style={{ margin: 0 }}>
          <SearchBox value={q} onChange={(v) => { setQ(v); setPage(1) }} placeholder={t('g.search')} />
          <Select
            value={status}
            onChange={(v) => { setStatus(v); setPage(1) }}
            options={[
              { value: 'all', label: `${t('g.status')}: ${t('g.all')}` },
              { value: 'subscribed', label: t('ct.subscribed') },
              { value: 'unsubscribed', label: t('ct.unsubscribed') },
              { value: 'bounced', label: t('ct.bounced') },
            ]}
          />
          <Select
            value={seg}
            onChange={(v) => { setSeg(v); setPage(1) }}
            options={[
              { value: 'all', label: `${t('ct.tags')}: ${t('g.all')}` },
              ...['vip', 'newsletter', 'trial', 'beta', 'enterprise'].map((tg) => ({ value: tg, label: tg })),
            ]}
          />
          <div className="toolbar__spacer" />

          {/* Adding and importing live in the TOOLBAR, not only in the page
              header — the header is hidden when this list is embedded as the
              Audience tab, which is the only route the navigation offers. The
              buttons existed and were unreachable. */}
          {embedded && selected.length === 0 && (
            <>
              <Button size="sm" variant="ghost" icon={<IcUpload size={14} />} onClick={() => setImporting(true)}>
                {t('ct.importCsv')}
              </Button>
              <Button size="sm" variant="primary" icon={<IcPlus size={14} />} onClick={() => setAdding(true)}>
                {t('ct.add')}
              </Button>
            </>
          )}

          {selected.length > 0 && (
            <>
              <span className="muted" style={{ fontSize: '1.25rem' }}>
                {t('g.selected', { n: nf(selected.length) })}
              </span>
              <Button
                size="sm"
                variant="ghost"
                icon={<IcTag size={14} />}
                onClick={() => setTagging(true)}
              >
                {t('ct.tags')}
              </Button>
              <Button
                size="sm"
                variant="danger"
                icon={<IcTrash size={14} />}
                loading={bulking}
                onClick={async () => {
                  /* Asked, because it is a bulk delete and there is no undo.
                     The count is in the question — "delete 340 contacts?" is a
                     different decision from "delete this one?". */
                  if (!window.confirm(t('ct.bulkDeleteAsk', { n: selected.length }))) return
                  setBulking(true)
                  try {
                    const out = await api.post('/contacts/bulk/delete', { ids: selected })
                    onToast?.(t('ct.bulkDeleted', { n: out.deleted }))
                    setSelected([])
                    invalidate('/contacts')
                  } catch (err) {
                    onToast?.(err.message)
                  } finally {
                    setBulking(false)
                  }
                }}
              >
                {t('g.delete')}
              </Button>
            </>
          )}
        </div>

        <Card pad={false} className="panel">
          <Table
            columns={columns}
            rows={rows}
            keyFn={(c) => c.id}
            selectable
            selected={selected}
            onSelect={setSelected}
            onRowClick={(c) => setOpenId(c.id)}
            empty={{ icon: <IcContacts size={26} /> }}
          />
          <Pagination page={page} pages={pages} total={total} onChange={setPage} />
        </Card>
      </Stagger>

      <ContactDrawer contact={open} onClose={() => setOpenId(null)} />
      {adding && <AddContact onClose={() => setAdding(false)} onToast={onToast} />}
      {tagging && (
        <BulkTag
          ids={selected}
          onClose={() => setTagging(false)}
          onDone={() => { setSelected([]); invalidate('/contacts') }}
          onToast={onToast}
        />
      )}
      <ImportContacts
        open={importing}
        onClose={() => setImporting(false)}
        onToast={onToast}
      />

    </div>
  )
}

/* ============================================================
   ADDING ONE PERSON

   The importer handles a spreadsheet; this handles the person
   someone just met. Deliberately four fields — the rest of a
   contact (score, orders, lifetime value) is measured, not typed,
   and asking for it here would invite someone to make it up.
   ============================================================ */
function AddContact({ onClose, onToast }) {
  const { t } = useI18n()
  const [create, creating] = useCreateContact()
  const [form, setForm] = useState({ email: '', name: '', country: '', tags: '' })
  const [error, setError] = useState('')

  const patch = (bit) => setForm((f) => ({ ...f, ...bit }))
  const ready = form.email.includes('@') && form.email.length > 4

  const save = async () => {
    setError('')
    try {
      await create({
        email: form.email.trim().toLowerCase(),
        name: form.name.trim(),
        country: form.country.trim().toUpperCase().slice(0, 2),
        tags: form.tags.split(',').map((x) => x.trim()).filter(Boolean),
        source: 'manual',
      })
      onToast?.(t('ct.added'))
      onClose()
    } catch (err) {
      // 409 for a duplicate or a suppressed address — the server's sentence is
      // the useful one, so it is shown rather than replaced with "failed"
      setError(err.message)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={t('ct.add')}
      sub={t('ct.addSub')}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t('g.cancel')}
          </Button>
          <Button variant="primary" loading={creating.loading} disabled={!ready} onClick={save}>
            {t('ct.addSave')}
          </Button>
        </>
      }
    >
      <div className="stack-v">
        <Field label={t('imp.field.email')} required error={error}>
          <Input
            className="mono"
            autoFocus
            value={form.email}
            placeholder="ali@example.com"
            onChange={(e) => patch({ email: e.target.value })}
            onKeyDown={(e) => e.key === 'Enter' && ready && save()}
          />
        </Field>
        <Field label={t('imp.field.name')}>
          <Input
            value={form.name}
            placeholder={t('ct.namePh')}
            onChange={(e) => patch({ name: e.target.value })}
          />
        </Field>
        <Field label={t('imp.field.country')} hint={t('ct.countryHint')}>
          <Input
            value={form.country}
            placeholder="IR"
            maxLength={2}
            onChange={(e) => patch({ country: e.target.value })}
          />
        </Field>
        <Field label={t('imp.field.tags')} hint={t('ct.tagsHint')}>
          <Input
            value={form.tags}
            placeholder="vip, tehran"
            onChange={(e) => patch({ tags: e.target.value })}
          />
        </Field>
      </div>
    </Modal>
  )
}


/* ============================================================
   PUTTING PEOPLE IN A GROUP

   A segment in this product is a RULE, not a hand-kept list —
   it is re-evaluated whenever anything reads it, so there is no
   membership to append to. A tag IS the thing you can set
   directly, and a segment whose rule is `tag has "vip"` picks
   these people up from the moment this saves.

   That is worth saying on the screen, because "add to group" and
   "tag" sound like different features until you know.
   ============================================================ */
function BulkTag({ ids, onClose, onDone, onToast }) {
  const { t } = useI18n()
  const [tags, setTags] = useState('')
  const [busy, setBusy] = useState(false)

  const list = tags.split(',').map((x) => x.trim()).filter(Boolean)

  const apply = async (mode) => {
    if (!list.length) return
    setBusy(true)
    try {
      const out = await api.post('/contacts/bulk/tag', {
        ids,
        addTags: mode === 'add' ? list : [],
        removeTags: mode === 'remove' ? list : [],
      })
      onToast?.(t('ct.bulkTagged', { n: out.updated }))
      onDone()
      onClose()
    } catch (err) {
      onToast?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={t('ct.bulkTagTitle', { n: ids.length })}
      sub={t('ct.bulkTagSub')}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t('g.cancel')}
          </Button>
          <Button variant="ghost" disabled={!list.length} loading={busy}
                  onClick={() => apply('remove')}>
            {t('ct.bulkRemove')}
          </Button>
          <Button variant="primary" disabled={!list.length} loading={busy}
                  onClick={() => apply('add')}>
            {t('ct.bulkAdd')}
          </Button>
        </>
      }
    >
      <Field label={t('imp.field.tags')} hint={t('ct.tagsHint')}>
        <Input
          autoFocus
          value={tags}
          placeholder="vip, tehran"
          onChange={(e) => setTags(e.target.value)}
          onKeyDown={(e) => e.key === 'Enter' && list.length && apply('add')}
        />
      </Field>
      <p className="muted" style={{ fontSize: '1.18rem', lineHeight: 1.6, margin: '1rem 0 0' }}>
        {t('ct.bulkTagHow')}
      </p>
    </Modal>
  )
}


function ContactDrawer({ contact, onClose }) {
  const { t, lang, nf, pct, money, ago, date } = useI18n()
  const [tab, setTab] = useState('overview')
  if (!contact) return null
  const c = contact

  const summary =
    lang === 'fa'
      ? `${loc(c.name, lang)} در ${nf(c.orders)} سفارش ${money(c.ltv)} خرج کرده و بیشتر روی ${c.device === 'mobile' ? 'موبایل' : 'دسکتاپ'} ایمیل باز می‌کند. امتیاز تعاملش ${nf(c.score)} است؛ ${c.score >= 60 ? 'یکی از فعال‌ترین‌هاست' : c.score >= 25 ? 'در میانهٔ لیست قرار دارد' : 'در خطر ریزش است'}.`
      : `${loc(c.name, lang)} has spent ${money(c.ltv)} across ${nf(c.orders)} orders and opens mostly on ${c.device}. Engagement score is ${nf(c.score)} — ${c.score >= 60 ? 'one of your most active contacts' : c.score >= 25 ? 'mid-list' : 'at risk of churning'}.`

  return (
    <Drawer open={!!contact} onClose={onClose} width={58} title={loc(c.name, lang)} sub={c.email}>
      <div className="row" style={{ gap: '1.4rem', marginBottom: '1.8rem' }}>
        <Avatar name={loc(c.name, lang)} size={64} ring />
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="row" style={{ gap: '0.7rem', flexWrap: 'wrap' }}>
            <StatusBadge status={c.status}>{t(`ct.${c.status}`)}</StatusBadge>
            {c.tags.map((tg) => (
              <Badge key={tg} tone="neutral" size="sm">
                {tg}
              </Badge>
            ))}
          </div>
          <p className="muted" style={{ fontSize: '1.2rem', marginTop: '0.7rem' }}>
            {loc(c.source, lang)} · {t('g.created')} {date(c.created, { day: 'numeric', month: 'short', year: 'numeric' })}
          </p>
        </div>
      </div>

      <Card style={{ marginBottom: '1.6rem' }}>
        <CardHead title={t('ct.aiSummary')} icon={<IcSpark size={17} />} />
        <p style={{ margin: 0, fontSize: '1.35rem', lineHeight: 1.8, color: 'var(--tx-2)' }}>{summary}</p>
      </Card>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'overview', label: t('camp.overview') },
          { value: 'attributes', label: t('ct.attributes') },
          { value: 'activity', label: t('ct.activity') },
        ]}
      />

      <div style={{ marginTop: '1.8rem' }}>
        {tab === 'overview' && (
          <Grid min={16} gap={1.2}>
            <MiniStat label={t('ct.score')} value={nf(c.score)} />
            <MiniStat label={t('ct.lifetime')} value={money(c.ltv)} />
            <MiniStat label={t('m.conversions')} value={nf(c.orders)} />
            <MiniStat label={t('ct.lastOpen')} value={ago(c.lastOpen)} />
          </Grid>
        )}

        {tab === 'attributes' && (
          <Card pad={false} style={{ padding: '0.6rem 1.8rem' }}>
            {[
              [t('ct.email'), c.email],
              [t('g.status'), t(`ct.${c.status}`)],
              [t('ct.source'), loc(c.source, lang)],
              ['country', c.country],
              ['device', c.device],
              [t('g.created'), date(c.created, { day: 'numeric', month: 'short', year: 'numeric' })],
            ].map(([k, v]) => (
              <div
                key={k}
                className="row"
                style={{ justifyContent: 'space-between', padding: '1.2rem 0', borderBottom: '1px solid var(--stroke-soft)' }}
              >
                <span className="muted" style={{ fontSize: '1.25rem' }}>
                  {k}
                </span>
                <span className="strong mono" style={{ fontSize: '1.25rem' }}>
                  {v}
                </span>
              </div>
            ))}
          </Card>
        )}

        {tab === 'activity' && (
          <div className="feed">
            {(c.activity || []).length === 0 ? (
              <p className="muted" style={{ fontSize: '1.25rem' }}>{t('g.empty')}</p>
            ) : (
              c.activity.map((e, i) => (
                <div className="feed__item" key={i}>
                  <div className="feed__rail">
                    <span className="feed__dot feed__dot--info">
                      <IcMail size={13} />
                    </span>
                  </div>
                  <div className="feed__body">
                    <div className="feed__text">{t(`m.${e.type}`, {}) || e.type}</div>
                    <div className="feed__meta">{ago(e.at)}</div>
                  </div>
                </div>
              ))
            )}
          </div>
        )}
      </div>
    </Drawer>
  )
}
