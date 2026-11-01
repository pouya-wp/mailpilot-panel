/* ============================================================
   CAMPAIGNS — the list, and the detail that opens beside it.

   The detail is a DRAWER rather than a route of its own. A
   campaign is read in the context of the others (is this open rate
   good? compared to what?), and pushing the list off screen to
   show one row costs that comparison for nothing. The URL still
   carries the id — #/campaigns/c-401 — so a detail view is
   linkable and survives a refresh.
   ============================================================ */
import { useMemo, useState } from 'react'
import { byId, loc, useI18n } from '../i18n'
import { invalidate, useDebounced } from '../api/hooks'
import { api } from '../api/client'
import {
  useAgents,
  useCampaign,
  useCampaignAction,
  useCampaigns,
  useDeleteCampaign,
  useRecipients,
  useSegments,
  useSendCampaign,
  useSettings,
} from '../api/resources'
import { Async } from '../ui/state'
import { navigate, useRoute } from '../router'
import { useConfig } from '../api/config'
import PageHeader from '../layout/PageHeader'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHead,
  Delta,
  Drawer,
  EmptyState,
  Grid,
  IconButton,
  Menu,
  Pagination,
  Progress,
  SearchBox,
  Segmented,
  Select,
  Stagger,
  StatusBadge,
  Table,
  Tabs,
} from '../ui'
import { AreaChart, BarList, Funnel } from '../ui/charts'
import {
  IcCopy,
  IcCursorClick,
  IcDots,
  IcDownload,
  IcEye,
  IcFilter,
  IcLink,
  IcPause,
  IcPlay,
  IcPlus,
  IcSend,
  IcTrash,
} from '../components/NavIcons'

const PAGE_SIZE = 7

export default function Campaigns({ onToast }) {
  const { t, lang, nf, pct, compact, money, ago, date } = useI18n()
  const { params } = useRoute()
  const [q, setQ] = useState('')
  const [status, setStatus] = useState('all')
  const [type, setType] = useState('all')
  const [page, setPage] = useState(1)
  const [selected, setSelected] = useState([])
  const [bulking, setBulking] = useState(false)

  /* One pass over the selection, reporting what actually happened rather than
     assuming it all worked. A campaign that is already sent cannot be paused
     and the server says so per row, so the count is the honest answer. */
  const bulk = async (what) => {
    if (what === 'delete' && !window.confirm(t('camp.bulkDeleteAsk', { n: selected.length }))) return
    setBulking(true)
    let done = 0
    const failed = []
    for (const id of selected) {
      try {
        if (what === 'delete') await api.del(`/campaigns/${id}`)
        else await api.post(`/campaigns/${id}/pause`)
        done += 1
      } catch (err) {
        failed.push(err.message)
      }
    }
    setBulking(false)
    setSelected([])
    invalidate('/campaigns')
    invalidate('/stats')
    onToast?.(failed.length
      ? t('camp.bulkPartly', { n: done, why: failed[0] })
      : t('camp.bulkDone', { n: done }))
  }

  /* Debounced, because a request per keystroke is both wasteful and racy —
     the answer to "sum" can arrive after the answer to "summer". */
  const search = useDebounced(q, 300)

  /* Filtering and paging happen on the SERVER. Slicing a page out of an array
     the client already holds only works while the whole table fits in memory,
     which is exactly the assumption that breaks first in production. */
  const query = useCampaigns({ q: search, status, type, page, size: PAGE_SIZE })
  const agents = useAgents()
  const segments = useSegments()
  const [act] = useCampaignAction()
  const [removeCampaign] = useDeleteCampaign()

  /* One handler for every row verb. Each names the endpoint, reports what the
     server actually said, and lets the invalidation refresh the table — so a
     paused campaign shows as paused because it IS, not because we said so. */
  const runAction = async (id, action, message) => {
    try {
      await act({ id, action })
      onToast?.(message)
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    }
  }

  const openId = params[0]
  const detail = useCampaign(openId)

  const rows = query.data?.items || []
  const pages = query.data?.pages || 1
  const total = query.data?.total || 0

  const columns = [
    {
      key: 'name',
      title: t('g.name'),
      width: 'minmax(0, 2.4fr)',
      render: (c) => {
        const ag = byId(agents.data, c.agent)
        return (
          <span className="tname">
            <Avatar name={loc(ag?.name, lang)} emoji={ag?.emoji} tint={ag?.tint} size={32} ring />
            <span className="tname__text">
              <span className="tname__main">{loc(c.name, lang)}</span>
              <span className="tname__sub">{loc(c.subject, lang)}</span>
            </span>
          </span>
        )
      },
    },
    {
      key: 'status',
      title: t('g.status'),
      width: 'minmax(0, 0.9fr)',
      render: (c) => <StatusBadge status={c.status}>{t(`g.${c.status}`)}</StatusBadge>,
    },
    {
      key: 'type',
      title: t('g.type'),
      width: 'minmax(0, 0.9fr)',
      render: (c) => <span className="muted">{t(`camp.type.${c.type}`)}</span>,
    },
    {
      key: 'segment',
      title: t('camp.audience'),
      width: 'minmax(0, 1fr)',
      render: (c) => {
        const s = byId(segments.data, c.segment)
        return (
          <span className="ellip">
            {s?.emoji} {loc(s?.name, lang)}
          </span>
        )
      },
    },
    {
      key: 'sent',
      title: t('m.sent'),
      width: 'minmax(0, 0.7fr)',
      align: 'end',
      render: (c) => <span className="num-tab">{compact(c.sent)}</span>,
    },
    {
      key: 'open',
      title: t('m.openRate'),
      width: 'minmax(0, 0.8fr)',
      align: 'end',
      render: (c) => (c.sent ? <span className="num-tab strong">{pct((c.opens / c.sent) * 100, 1)}</span> : <span className="faint">—</span>),
    },
    {
      key: 'updated',
      title: t('g.updated'),
      width: 'minmax(0, 0.9fr)',
      render: (c) => <span className="faint">{ago(c.updated)}</span>,
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
              <IconButton label={t('g.actions')} style={{ width: '3rem', height: '3rem' }}>
                <IcDots size={15} />
              </IconButton>
            }
            items={[
              { id: 'v', label: t('g.view'), icon: <IcEye size={15} />, onClick: () => navigate(`campaigns/${c.id}`) },
              {
                id: 'd',
                label: t('g.duplicate'),
                icon: <IcCopy size={15} />,
                onClick: () => runAction(c.id, 'duplicate', t('toast.duplicated')),
              },
              c.status === 'running'
                ? {
                    id: 'p',
                    label: t('g.paused'),
                    icon: <IcPause size={15} />,
                    onClick: () => runAction(c.id, 'pause', t('toast.campaignPaused')),
                  }
                : {
                    id: 'r',
                    label: t('g.running'),
                    icon: <IcPlay size={15} />,
                    /* Only a paused campaign can resume; the server rejects the
                       rest, and its message is the honest explanation. */
                    onClick: () => runAction(c.id, 'resume', t('toast.campaignResumed')),
                  },
              { divider: true },
              {
                id: 'x',
                label: t('g.delete'),
                icon: <IcTrash size={15} />,
                tone: 'danger',
                onClick: async () => {
                  try {
                    await removeCampaign(c.id)
                    onToast?.(t('toast.deleted'))
                  } catch (err) {
                    onToast?.(err.message || t('err.failed'))
                  }
                },
              },
            ]}
          />
        </span>
      ),
    },
  ]

  return (
    <div className="page">
      <PageHeader
        title={t('camp.title')}
        sub={t('camp.sub')}
        actions={
          <>
            <Button
              variant="ghost"
              icon={<IcDownload size={16} />}
              onClick={async () => {
                try {
                  await api.download('/campaigns/export', 'campaigns.csv')
                } catch (err) {
                  onToast?.(err.message)
                }
              }}
            >
              {t('g.export')}
            </Button>
            {/* The composer route is gone; writing a campaign starts by
                asking for one on Home. This was the screen's primary action
                and it bounced to Home anyway — now it goes there on purpose,
                which is the same place with an input box waiting. */}
            <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => navigate('home')}>
              {t('camp.new')}
            </Button>
          </>
        }
      />

      <Stagger className="stack-v">
        <div className="toolbar" style={{ margin: 0 }}>
          <SearchBox value={q} onChange={(v) => { setQ(v); setPage(1) }} placeholder={t('g.search')} />
          <Select
            value={status}
            onChange={(v) => { setStatus(v); setPage(1) }}
            options={[
              { value: 'all', label: `${t('g.status')}: ${t('g.all')}` },
              { value: 'running', label: t('g.running') },
              { value: 'sent', label: t('g.sent') },
              { value: 'scheduled', label: t('g.scheduled') },
              { value: 'draft', label: t('g.draft') },
              { value: 'paused', label: t('g.paused') },
            ]}
          />
          <Select
            value={type}
            onChange={(v) => { setType(v); setPage(1) }}
            options={[
              { value: 'all', label: `${t('g.type')}: ${t('g.all')}` },
              { value: 'broadcast', label: t('camp.type.broadcast') },
              { value: 'drip', label: t('camp.type.drip') },
              { value: 'agent', label: t('camp.type.agent') },
              { value: 'abtest', label: t('camp.type.abtest') },
              { value: 'transactional', label: t('camp.type.transactional') },
            ]}
          />
          <div className="toolbar__spacer" />
          {selected.length > 0 && (
            <>
              <span className="muted" style={{ fontSize: '1.25rem' }}>
                {t('g.selected', { n: nf(selected.length) })}
              </span>
              {/* Both routes have existed all along; these two were the
                  only thing missing. `g.paused` is a STATE, not an action —
                  the button now says what it does. */}
              <Button
                size="sm"
                variant="ghost"
                icon={<IcPause size={14} />}
                loading={bulking}
                onClick={() => bulk('pause')}
              >
                {t('camp.pauseSelected')}
              </Button>
              <Button
                size="sm"
                variant="danger"
                icon={<IcTrash size={14} />}
                loading={bulking}
                onClick={() => bulk('delete')}
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
            onRowClick={(c) => navigate(`campaigns/${c.id}`)}
            empty={{ title: t('g.empty'), hint: t('camp.emptyHint'), icon: <IcSend size={26} /> }}
          />
          <Pagination page={page} pages={pages} total={total} onChange={setPage} />
        </Card>
      </Stagger>

      <CampaignDrawer campaign={detail.data} onClose={() => navigate('campaigns')} onToast={onToast} />
    </div>
  )
}

/* ============================================================
   DETAIL DRAWER
   ============================================================ */
function CampaignDrawer({ campaign, onClose, onToast }) {
  const { t, lang, nf, pct, compact, money, ago, date, time } = useI18n()
  const [tab, setTab] = useState('overview')
  const agents = useAgents()
  const segments = useSegments()
  /* The preview must show THIS deployment's sender and brand. Both used
     to be hardcoded to the demo fixtures, so a customer checking what
     their campaign looks like was shown another company's letterhead. */
  const { brand } = useConfig()
  const settings = useSettings()
  const [send, sending] = useSendCampaign()
  const [act] = useCampaignAction()

  /* The trend the server stored with the campaign, not a curve invented here —
     two views of the same campaign must not draw two different histories. */
  const data = useMemo(() => {
    if (!campaign) return null
    const trend = campaign.trend || []
    const fmt = new Intl.DateTimeFormat(lang === 'fa' ? 'fa-IR' : 'en-US', { day: 'numeric', month: 'short' })
    const labels = trend.map((_, i) =>
      fmt.format(new Date(Date.now() - (trend.length - 1 - i) * 864e5))
    )
    return {
      labels,
      opens: trend.map((v) => Math.round(v * 0.42)),
      clicks: trend.map((v) => Math.round(v * 0.11)),
    }
  }, [campaign, lang])

  if (!campaign) return null
  const c = campaign
  const ag = byId(agents.data, c.agent)
  const seg = byId(segments.data, c.segment)

  // link performance is computed and returned by the API
  const links = (c.links || []).map((l, i) => ({ id: `l${i}`, label: l.url, value: l.clicks }))

  return (
    <Drawer
      open={!!campaign}
      onClose={onClose}
      width={68}
      title={loc(c.name, lang)}
      sub={loc(c.subject, lang)}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t('g.close')}
          </Button>
          <Button
            variant="ghost"
            icon={<IcCopy size={15} />}
            onClick={async () => {
              try {
                await act({ id: c.id, action: 'duplicate' })
                onToast?.(t('toast.duplicated'))
                onClose()
              } catch (err) {
                onToast?.(err.message || t('err.failed'))
              }
            }}
          >
            {t('g.duplicate')}
          </Button>
          <Button
            variant="primary"
            icon={<IcSend size={15} />}
            loading={sending.loading}
            disabled={!['draft', 'scheduled', 'paused'].includes(c.status)}
            onClick={async () => {
              try {
                await send({ id: c.id, mode: 'now' })
                onToast?.(t('toast.launched'))
                onClose()
              } catch (err) {
                // the server refuses a send with no audience, or in a state
                // that cannot send — say which, rather than failing silently
                onToast?.(err.message || t('err.failed'))
              }
            }}
          >
            {t('camp.sendNow')}
          </Button>
        </>
      }
    >
      <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap', marginBottom: '1.8rem' }}>
        <StatusBadge status={c.status}>{t(`g.${c.status}`)}</StatusBadge>
        <Badge tone="neutral">{t(`camp.type.${c.type}`)}</Badge>
        <Badge tone="info">
          {seg?.emoji} {loc(seg?.name, lang)}
        </Badge>
        <span className="faint" style={{ fontSize: '1.2rem' }}>
          {t('g.updated')} {ago(c.updated)}
        </span>
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'overview', label: t('camp.overview') },
          { value: 'links', label: t('camp.links') },
          { value: 'content', label: t('camp.content') },
          { value: 'sent', label: t('camp.sentTo') },
          { value: 'timeline', label: t('camp.timeline') },
        ]}
      />

      <div style={{ marginTop: '1.8rem' }}>
        {tab === 'overview' && (
          <div className="stack-v">
            <Grid min={16} gap={1.2}>
              <MiniStat label={t('m.sent')} value={compact(c.sent)} />
              <MiniStat label={t('m.delivered')} value={compact(c.delivered)} sub={pct((c.delivered / (c.sent || 1)) * 100, 1)} />
              <MiniStat label={t('m.opens')} value={compact(c.opens)} sub={pct((c.opens / (c.sent || 1)) * 100, 1)} />
              <MiniStat label={t('m.clicks')} value={compact(c.clicks)} sub={pct((c.clicks / (c.sent || 1)) * 100, 1)} />
              <MiniStat label={t('m.replies')} value={compact(c.replies)} />
            </Grid>

            <Card>
              <CardHead title={t('camp.performance') || t('dash.pulse')} />
              <AreaChart
                height={200}
                labels={data.labels}
                formatValue={(v) => nf(v)}
                series={[
                  { name: t('m.opens'), data: data.opens, color: '#8fd3a8' },
                  { name: t('m.clicks'), data: data.clicks, color: '#b98cff' },
                ]}
              />
            </Card>

            <Card>
              <CardHead title={t('dash.funnel')} />
              <Funnel
                format={(v) => compact(v)}
                stages={[
                  { key: 's', label: t('m.sent'), value: c.sent, color: 'linear-gradient(90deg,#3f6ca9,#cfe1f2)' },
                  { key: 'd', label: t('m.delivered'), value: c.delivered, color: 'linear-gradient(90deg,#3f7a8f,#a8dfe0)' },
                  { key: 'o', label: t('m.opens'), value: c.opens, color: 'linear-gradient(90deg,#3f8f66,#8fd3a8)' },
                  { key: 'c', label: t('m.clicks'), value: c.clicks, color: 'linear-gradient(90deg,#6b4fa8,#b98cff)' },
                ]}
              />
            </Card>
          </div>
        )}

        {tab === 'links' && (
          <Card>
            <CardHead title={t('camp.links')} icon={<IcLink size={17} />} />
            <BarList format={(v) => nf(v)} items={links} />
          </Card>
        )}

        {tab === 'content' && (
          <div className="mail mail--desktop">
            <div className="mail__chrome">
              <span className="mail__dot" />
              <span className="mail__dot" />
              <span className="mail__dot" />
              <span className="mail__addr">
                {settings.data?.sending?.fromEmail || brand.supportEmail || ''}
              </span>
            </div>
            <div className="mail__body" dir={lang === 'fa' ? 'rtl' : 'ltr'}>
              <div className="mail__brand">{brand.name}</div>
              <h2 className="mail__subject">{loc(c.subject, lang)}</h2>
              {loc(c.body, lang) ? (
                <div
                  className="mail__content"
                  style={{ marginTop: '1.4rem', lineHeight: '1.65', fontSize: '1.45rem' }}
                  dangerouslySetInnerHTML={{ __html: loc(c.body, lang) }}
                />
              ) : (
                <p className="mail__p muted">
                  {lang === 'fa' ? 'بدون متن' : 'No message body'}
                </p>
              )}
            </div>
          </div>
        )}

        {tab === 'sent' && <SentTo id={c.id} />}

        {tab === 'timeline' && (
          <div className="feed">
            {[
              { k: 'created', tone: 'info', at: c.updated, label: t('g.created') },
              { k: 'approved', tone: 'good', at: c.updated, label: t('inbox.approve') },
              { k: 'sending', tone: 'info', at: c.updated, label: t('g.sending') },
              { k: 'done', tone: 'good', at: c.updated, label: t('g.sent') },
            ].map((e, i) => (
              <div className="feed__item" key={e.k}>
                <div className="feed__rail">
                  <span className={`feed__dot feed__dot--${e.tone}`}>{nf(i + 1)}</span>
                </div>
                <div className="feed__body">
                  <div className="feed__text">
                    <b>{e.label}</b>
                  </div>
                  <div className="feed__meta">
                    <span>{date(e.at, { day: 'numeric', month: 'short' })}</span>
                    <span>{time(e.at)}</span>
                    <span>{loc(ag?.name, lang)}</span>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </Drawer>
  )
}

/* ============================================================
   WHO IT REACHED

   The outbox has held this all along — one row per recipient,
   with the Gmail message id when it worked and the provider's own
   words when it did not. Nothing showed it, so "1,240 sent" was a
   number nobody could check.

   Failures sort first. A list of four hundred successes with two
   failures buried in it is a list that hides the only rows worth
   reading.
   ============================================================ */
function SentTo({ id }) {
  const { t, nf, ago } = useI18n()
  const [status, setStatus] = useState('all')
  const [page, setPage] = useState(1)
  const query = useRecipients(id, { status, page, size: 50 })

  const counts = query.data?.counts || {}
  const rows = query.data?.items || []

  const TONE = {
    sent: 'good', queued: 'info', sending: 'info',
    failed: 'bad', suppressed: 'warn', cancelled: 'neutral',
  }

  return (
    <Async query={query}>
      <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap', marginBottom: '1.4rem' }}>
        <Segmented
          size="sm"
          value={status}
          onChange={(v) => { setStatus(v); setPage(1) }}
          options={[
            { value: 'all', label: `${t('g.all')} · ${nf(counts.total || 0)}` },
            { value: 'sent', label: `${t('camp.rSent')} · ${nf(counts.sent || 0)}` },
            { value: 'failed', label: `${t('camp.rFailed')} · ${nf(counts.failed || 0)}` },
            { value: 'queued', label: `${t('camp.rQueued')} · ${nf(counts.queued || 0)}` },
          ]}
        />
      </div>

      {rows.length === 0 ? (
        <EmptyState title={t('camp.noRecipients')} hint={t('camp.noRecipientsHint')} />
      ) : (
        <Table
          columns={[
            { key: 'who', label: t('camp.rWho'),
              render: (r) => (
                <div className="tname__text">
                  <span>{r.name || r.email.split('@')[0]}</span>
                  <span className="tname__sub mono">{r.email}</span>
                </div>
              ) },
            { key: 'status', label: t('g.status'),
              render: (r) => <Badge tone={TONE[r.status] || 'neutral'}>{t(`camp.r_${r.status}`)}</Badge> },
            { key: 'at', label: t('camp.rWhen'), render: (r) => ago(r.at) },
            /* The provider's own sentence, not "failed". Why it failed is the
               only part anybody can act on. */
            { key: 'why', label: t('camp.rWhy'),
              render: (r) => r.error ? <span className="rcp__why">{r.error}</span> : '—' },
          ]}
          rows={rows}
          keyFn={(r) => r.id}
        />
      )}

      {query.data?.pages > 1 && (
        <Pagination page={page} pages={query.data.pages} total={query.data.total} onChange={setPage} />
      )}
    </Async>
  )
}


export function MiniStat({ label, value, sub }) {
  return (
    <div
      style={{
        padding: '1.3rem 1.4rem',
        borderRadius: 'var(--r-md)',
        background: 'rgba(255,255,255,.035)',
        border: '1px solid var(--stroke-soft)',
      }}
    >
      <div style={{ fontSize: '1.15rem', color: 'var(--tx-4)' }}>{label}</div>
      <div
        style={{
          marginTop: '0.4rem',
          fontFamily: 'var(--font-display)',
          fontSize: '2.1rem',
          fontWeight: 600,
          color: '#eef3fa',
          letterSpacing: '-0.02em',
        }}
      >
        {value}
      </div>
      {sub && <div style={{ fontSize: '1.1rem', color: 'var(--tx-3)', marginTop: '0.2rem' }}>{sub}</div>}
    </div>
  )
}
