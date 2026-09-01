/* ============================================================
   DASHBOARD — the command centre.

   Layout follows the question the reader actually arrives with:
   "did anything go wrong while I was away, and what should I do
   next?" So the order is health and volume first, then what the
   agents DID, then what they RECOMMEND, then the long tail of
   breakdowns. The recommendation card is deliberately the only
   accent-lit surface on the page — it is the one thing here that
   asks for a decision.
   ============================================================ */
import { useMemo, useState } from 'react'
import { byId, loc, useI18n } from '../i18n'
import {
  useActOnRecommendation,
  useActivity,
  useAgents,
  useCampaigns,
  useDevices,
  useEvents,
  useFunnel,
  useHeatmap,
  useOverview,
  useRecommendations,
  useSeries,
  useTeam,
  useTopCampaigns,
} from '../api/resources'
import { Async } from '../ui/state'
import { navigate } from '../router'
import PageHeader from '../layout/PageHeader'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHead,
  Delta,
  Gauge,
  Kpi,
  Num,
  Progress,
  Segmented,
  Stagger,
  StatusBadge,
} from '../ui'
import { AreaChart, BarList, Donut, Funnel, Heatmap, Sparkline } from '../ui/charts'
import {
  IcAgent,
  IcArrow,
  IcBolt,
  IcCalendar,
  IcCheckC,
  IcCompose,
  IcCursorClick,
  IcEye,
  IcMoney,
  IcPlus,
  IcSend,
  IcSpark,
  IcWarn,
} from '../components/NavIcons'

const EVENT_TONE = {
  opened: 'var(--s1)',
  clicked: 'var(--s3)',
  delivered: 'var(--s2)',
  replied: 'var(--violet)',
  converted: 'var(--good)',
  bounced: 'var(--bad)',
  unsubscribed: 'var(--warn)',
}

/* One ramp per funnel stage, in order. */
const FUNNEL_COLOURS = [
  'linear-gradient(90deg,#3f6ca9,#cfe1f2)',
  'linear-gradient(90deg,#3f7a8f,#a8dfe0)',
  'linear-gradient(90deg,#3f8f66,#8fd3a8)',
  'linear-gradient(90deg,#6b4fa8,#b98cff)',
  'linear-gradient(90deg,#a8762f,#e2b872)',
  'linear-gradient(90deg,#8a5a2b,#d6a86a)',
]
const DEVICE_COLOURS = ['#7ba3cd', '#8fd3a8', '#b98cff']

export default function Dashboard({ onToast }) {
  const { t, lang, nf, pct, compact, money, ago, time, date } = useI18n()
  const [range, setRange] = useState('30')
  const [dismissed, setDismissed] = useState([])

  const n = Number(range)

  const overview = useOverview(n)
  const seriesQ = useSeries(n)
  const heatQ = useHeatmap()
  const funnelQ = useFunnel()
  const devicesQ = useDevices()
  const agentsQ = useAgents()
  const teamQ = useTeam()
  const eventsQ = useEvents(8)
  const recosQ = useRecommendations()
  const topQ = useTopCampaigns(5)
  const activityQ = useActivity({ size: 6 })
  const upcomingQ = useCampaigns({ status: 'scheduled', size: 5 })
  const [actOnReco] = useActOnRecommendation()

  const tot = overview.data?.totals || {}
  const credits = overview.data?.credits?.credits

  /* Axis labels arrive as ISO dates. Only the client knows the reader's
     language and calendar, so the formatting stays here. */
  const charts = useMemo(() => {
    const raw = seriesQ.data
    if (!raw) return { labels: [], sent: [], opens: [], clicks: [] }
    const fmt = new Intl.DateTimeFormat(lang === 'fa' ? 'fa-IR' : 'en-US', { day: 'numeric', month: 'short' })
    const pick = (key) => raw.series.find((x) => x.key === key)?.data || []
    return {
      labels: raw.labels.map((d) => fmt.format(new Date(d))),
      sent: pick('sent'),
      opens: pick('opens'),
      clicks: pick('clicks'),
    }
  }, [seriesQ.data, lang])

  const heat = heatQ.data?.values || []
  /* Weekday names are locale data, not content — Intl already has them, and
     the grid starts on Monday because it is read as a working week. */
  const wd = useMemo(() => {
    const fmt = new Intl.DateTimeFormat(lang === 'fa' ? 'fa-IR' : 'en-US', { weekday: 'short' })
    return Array.from({ length: 7 }, (_, i) => fmt.format(new Date(2024, 0, 1 + i)))
  }, [lang])
  const hours = Array.from({ length: 12 }, (_, i) => `${i * 2}`.padStart(2, '0'))

  const upcoming = upcomingQ.data?.items || []
  const top = topQ.data || []
  const recos = (recosQ.data || []).filter((r) => !dismissed.includes(r.id))

  return (
    <div className="page">
      <PageHeader
        title={t('dash.title')}
        sub={t('dash.sub')}
        actions={
          <>
            <Segmented
              size="sm"
              value={range}
              onChange={setRange}
              options={[
                { value: '7', label: t('g.last7') },
                { value: '30', label: t('g.last30') },
                { value: '90', label: t('g.last90') },
              ]}
            />
            <Button variant="ghost" icon={<IcCompose size={16} />} onClick={() => navigate('composer')}>
              {t('dash.askAgent')}
            </Button>
            <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => navigate('campaigns')}>
              {t('dash.newCampaign')}
            </Button>
          </>
        }
      />

      <Stagger className="stack-v">
        {/* ---------- KPI row ---------- */}
        <div className="kpirow" style={{ margin: 0 }}>
          <Kpi
            label={t('m.sent')}
            icon={<IcSend size={15} />}
            value={<Num value={tot.sent || 0} from={0} format={compact} flash={false} />}
            delta={12.4}
            hint={t('g.vsLast', { period: t('g.month') })}
            spark={<Sparkline data={charts.sent.slice(-14)} color="#7ba3cd" height={38} />}
          />
          <Kpi
            label={t('m.openRate')}
            icon={<IcEye size={15} />}
            value={<Num value={tot.openRate || 0} from={0} format={(v) => pct(v, 1)} flash={false} />}
            delta={4.8}
            hint={t('g.vsLast', { period: t('g.month') })}
            spark={<Sparkline data={charts.opens.slice(-14)} color="#8fd3a8" height={38} />}
          />
          <Kpi
            label={t('m.clickRate')}
            icon={<IcCursorClick size={15} />}
            value={<Num value={tot.clickRate || 0} from={0} format={(v) => pct(v, 1)} flash={false} />}
            delta={-1.2}
            hint={t('g.vsLast', { period: t('g.month') })}
            spark={<Sparkline data={charts.clicks.slice(-14)} color="#b98cff" height={38} />}
          />
          <Kpi
            label={t('m.revenue')}
            icon={<IcMoney size={15} />}
            tone="accent"
            value={<Num value={tot.revenue || 0} from={0} format={(v) => money(v)} flash={false} />}
            delta={22.1}
            hint={t('g.vsLast', { period: t('g.month') })}
          />
        </div>

        {/* ---------- pulse + health ---------- */}
        <div className="cols cols--wide-narrow">
          <Card>
            <CardHead
              title={t('dash.pulse')}
              sub={t('dash.pulseSub')}
              icon={<IcBolt size={17} />}
              right={<Badge tone="neutral">{t(`g.last${range}`)}</Badge>}
            />
            <AreaChart
              height={260}
              labels={charts.labels}
              formatValue={(v) => nf(v)}
              series={[
                { name: t('m.sent'), data: charts.sent, color: '#cfe1f2' },
                { name: t('m.opens'), data: charts.opens, color: '#8fd3a8' },
                { name: t('m.clicks'), data: charts.clicks, color: '#b98cff' },
              ]}
            />
          </Card>

          <div className="stack-v">
            <Card>
              <CardHead title={t('dash.health')} sub={t('dash.healthSub')} icon={<IcCheckC size={17} />} />
              <div className="row" style={{ gap: '2.2rem', alignItems: 'center' }}>
                <Gauge value={94} size={132} tone="good" label={nf(94)} sub="/ 100" caption={t('m.reputation')} />
                <div style={{ flex: 1, display: 'flex', flexDirection: 'column', gap: '1.3rem', minWidth: 0 }}>
                  <Progress
                    label={t('m.deliverability')}
                    right={pct(tot.deliveryRate || 0, 1)}
                    value={tot.deliveryRate || 0}
                    tone="good"
                  />
                  <Progress label={t('m.bounceRate')} right={pct(tot.bounceRate || 0, 2)} value={tot.bounceRate || 0} max={5} tone="warn" />
                  <Progress label={t('m.unsubRate')} right={pct(tot.unsubRate || 0, 2)} value={tot.unsubRate || 0} max={1} tone="violet" />
                </div>
              </div>
            </Card>

            <Card>
              <CardHead title={t('dash.deviceSplit')} />
              <div className="row" style={{ gap: '2rem' }}>
                <Donut
                  size={132}
                  thickness={14}
                  data={(devicesQ.data || []).map((d, i) => ({ ...d, color: DEVICE_COLOURS[i % 3] }))}
                  center={devicesQ.data?.[0] ? pct(devicesQ.data[0].value, 0) : '—'}
                  sub={devicesQ.data?.[0]?.id || ''}
                />
                <div style={{ flex: 1, minWidth: 0 }}>
                  <BarList
                    format={(v) => pct(v, 0)}
                    max={100}
                    items={(devicesQ.data || []).map((d) => ({ id: d.id, label: d.id, value: d.value }))}
                  />
                </div>
              </div>
            </Card>
          </div>
        </div>

        {/* ---------- recommendations ---------- */}
        <Card>
          <CardHead
            title={t('dash.recommend')}
            sub={t('dash.recommendSub')}
            icon={<IcSpark size={17} />}
            right={<Badge tone="live" dot>{nf(recos.length)}</Badge>}
          />
          {recos.length === 0 ? (
            <p className="muted" style={{ padding: '2rem 0', textAlign: 'center' }}>
              {t('inbox.empty')}
            </p>
          ) : (
            recos.map((r) => {
              const ag = byId(agentsQ.data, r.agent)
              return (
                <div className="reco" key={r.id}>
                  <Avatar name={loc(ag.name, lang)} emoji={ag.emoji} tint={ag.tint} size={40} ring />
                  <div className="reco__body">
                    <div className="reco__title">{loc(r.title, lang)}</div>
                    <div className="reco__text">{loc(r.body, lang)}</div>
                    <div className="reco__foot">
                      <span className="reco__lift">
                        +{nf(r.lift, { maximumFractionDigits: 1 })}% {t('exp.lift')}
                      </span>
                      <Badge tone="neutral" size="sm">
                        {loc(ag.name, lang)}
                      </Badge>
                      <span className="faint" style={{ fontSize: '1.15rem' }}>
                        {t('ag.autonomy')}: {t(`ag.autonomy.${ag.autonomy}`)}
                      </span>
                    </div>
                  </div>
                  <div className="row" style={{ gap: '0.7rem', alignSelf: 'center' }}>
                    <Button
                      size="sm"
                      variant="quiet"
                      onClick={async () => {
                        setDismissed((d) => [...d, r.id])
                        await actOnReco({ id: r.id, action: 'dismiss' })
                      }}
                    >
                      {t('dash.dismiss')}
                    </Button>
                    <Button
                      size="sm"
                      variant="primary"
                      onClick={async () => {
                        setDismissed((d) => [...d, r.id])
                        await actOnReco({ id: r.id, action: 'apply' })
                        onToast?.(t('toast.applied'))
                      }}
                    >
                      {t('g.apply')}
                    </Button>
                  </div>
                </div>
              )
            })
          )}
        </Card>

        {/* ---------- funnel · agents · stream ---------- */}
        <div className="cols cols--3">
          <Card>
            <CardHead title={t('dash.funnel')} />
            <Funnel
              format={(v) => compact(v)}
              stages={(funnelQ.data || []).map((stage, i) => ({
                key: stage.key,
                label: t('m.' + stage.key),
                value: stage.value,
                color: FUNNEL_COLOURS[i % FUNNEL_COLOURS.length],
              }))}
            />
          </Card>

          <Card>
            <CardHead
              title={t('dash.agentActivity')}
              sub={t('dash.agentActivitySub')}
              icon={<IcAgent size={17} />}
              right={
                <Button size="sm" variant="quiet" onClick={() => navigate('agents')}>
                  {t('g.viewAll')}
                </Button>
              }
            />
            <BarList
              format={(v) => nf(v)}
              items={(agentsQ.data || []).map((a) => ({
                id: a.id,
                label: loc(a.name, lang),
                value: a.actionsToday,
                tone: a.status === 'paused' ? 'warn' : 'blue',
                icon: a.emoji,
              }))}
            />
            <div className="hr" />
            <div className="row" style={{ justifyContent: 'space-between' }}>
              <span className="muted" style={{ fontSize: '1.22rem' }}>
                {t('dash.creditsLeft', { n: nf(credits ? credits.left : 0) })}
              </span>
              <Button size="sm" variant="ghost" onClick={() => navigate('billing')}>
                {t('dash.topUp')}
              </Button>
            </div>
          </Card>

          <Card>
            <CardHead
              title={t('dash.liveFeed')}
              right={<Badge tone="live" dot>{t('g.running')}</Badge>}
            />
            <div className="stream">
              {(eventsQ.data || []).map((e) => (
                <div className="stream__row" key={e.id}>
                  <span className="stream__type" style={{ background: EVENT_TONE[e.type], boxShadow: `0 0 1rem ${EVENT_TONE[e.type]}` }} />
                  <span className="stream__who">{e.who}</span>
                  <span className="stream__at">{ago(e.at)}</span>
                </div>
              ))}
            </div>
          </Card>
        </div>

        {/* ---------- heatmap + upcoming ---------- */}
        <div className="cols cols--wide-narrow">
          <Card>
            <CardHead title={t('dash.heatmap')} sub={t('dash.heatmapSub')} icon={<IcCalendar size={17} />} />
            <Heatmap
              rows={7}
              cols={12}
              values={heat}
              rowLabels={wd}
              colLabels={hours}
              format={(v) => pct(v, 1)}
              onPick={() => onToast?.(t('camp.sendOptimal'))}
            />
          </Card>

          <div className="stack-v">
            <Card>
              <CardHead
                title={t('dash.upcoming')}
                icon={<IcCalendar size={17} />}
                right={
                  <Button size="sm" variant="quiet" onClick={() => navigate('campaigns')}>
                    {t('g.viewAll')}
                  </Button>
                }
              />
              {upcoming.length === 0 ? (
                <p className="muted" style={{ fontSize: '1.25rem' }}>{t('dash.upcomingEmpty')}</p>
              ) : (
                upcoming.map((c) => (
                  <button className="tile" key={c.id} onClick={() => navigate(`campaigns/${c.id}`)} style={{ marginBottom: '0.9rem' }}>
                    <span className="tile__icon">
                      <IcSend size={17} />
                    </span>
                    <span className="tile__text">
                      <span className="tile__title ellip">{loc(c.name, lang)}</span>
                      <span className="tile__sub">
                        {date(c.scheduledFor, { day: 'numeric', month: 'short' })} · {time(c.scheduledFor)} ·{' '}
                        {compact(c.recipients)} {t('camp.recipients')}
                      </span>
                    </span>
                    <span className="tile__end">
                      <StatusBadge status={c.status}>{t('g.scheduled')}</StatusBadge>
                    </span>
                  </button>
                ))
              )}
            </Card>

            <Card>
              <CardHead title={t('dash.topCampaigns')} />
              <BarList
                format={(v) => pct(v, 1)}
                max={100}
                items={top.map((c) => ({ id: c.id, label: loc(c.name, lang), value: c.openRate }))}
              />
            </Card>
          </div>
        </div>

        {/* ---------- activity ---------- */}
        <Card>
          <CardHead
            title={t('log.title')}
            icon={<IcBolt size={17} />}
            right={
              <Button size="sm" variant="quiet" onClick={() => navigate('logs')}>
                {t('g.viewAll')}
              </Button>
            }
          />
          <div className="feed">
            {(activityQ.data?.items || []).map((a) => {
              const who =
                a.kind === 'agent'
                  ? loc(byId(agentsQ.data, a.actor)?.name, lang)
                  : a.kind === 'human'
                    ? loc(byId(teamQ.data, a.actor)?.name, lang)
                    : t('log.system')
              return (
                <div className="feed__item" key={a.id}>
                  <div className="feed__rail">
                    <span className={`feed__dot feed__dot--${a.tone}`}>
                      {a.kind === 'agent' ? <IcAgent size={13} /> : a.kind === 'human' ? <IcCheckC size={13} /> : <IcWarn size={13} />}
                    </span>
                  </div>
                  <div className="feed__body">
                    <div className="feed__text">
                      <b>{who}</b> {loc(a.action, lang)}
                    </div>
                    <div className="feed__meta">
                      <span>{ago(a.at)}</span>
                      <span className="mono">{a.target}</span>
                    </div>
                  </div>
                </div>
              )
            })}
          </div>
        </Card>
      </Stagger>
    </div>
  )
}
