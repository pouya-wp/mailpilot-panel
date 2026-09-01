/* ============================================================
   ANALYTICS

   The breakdown switcher rebuilds one bar list rather than
   swapping between four different charts. Comparing campaigns to
   segments to agents is only meaningful if the encoding stays
   identical, so the chart is the constant and the dimension is the
   variable — which is also why it is a Segmented control and not
   four tabs of separate cards.
   ============================================================ */
import { useMemo, useState } from 'react'
import { useI18n, loc } from '../i18n'
import {
  useAgents,
  useBreakdown,
  useCohorts,
  useDevices,
  useFunnel,
  useOverview,
  useSeries,
} from '../api/resources'
import { api } from '../api/client'
import { Async } from '../ui/state'
import PageHeader from '../layout/PageHeader'
import { Badge, Button, Card, CardHead, Grid, Kpi, Segmented, Select, Stagger } from '../ui'
import { AreaChart, BarList, CohortGrid, Donut, Funnel, RadialStat } from '../ui/charts'
import { IcChart, IcDownload, IcEye, IcInbox, IcSend, IcCursorClick } from '../components/NavIcons'

/* One ramp per funnel stage, in order. Kept beside the component rather than
   inline so the funnel and any future copy of it stay the same object. */
const FUNNEL_COLOURS = [
  'linear-gradient(90deg,#3f6ca9,#cfe1f2)',
  'linear-gradient(90deg,#3f7a8f,#a8dfe0)',
  'linear-gradient(90deg,#3f8f66,#8fd3a8)',
  'linear-gradient(90deg,#6b4fa8,#b98cff)',
  'linear-gradient(90deg,#a8762f,#e2b872)',
  'linear-gradient(90deg,#8a5a2b,#d6a86a)',
]

export default function Analytics({ embedded, onToast }) {
  const { t, lang, nf, pct, compact, money } = useI18n()
  const [range, setRange] = useState('30')
  const [dim, setDim] = useState('campaign')
  const [metric, setMetric] = useState('openRate')

  const n = Number(range)

  /* Every figure on this page is computed by the API. The client used to
     divide opens by sent in three different components; doing it once on the
     server is what stops two cards disagreeing about "open rate". */
  const overview = useOverview(n)
  const seriesQ = useSeries(n)
  const funnelQ = useFunnel()
  const cohortsQ = useCohorts()
  const devicesQ = useDevices()
  const agentsQ = useAgents()
  const breakdownQ = useBreakdown(dim, metric)

  const tot = overview.data?.totals || {}
  /* Measured against the previous window by the server; zero when there is
     no baseline to measure against. */
  const deltas = overview.data?.deltas || {}
  const cohorts = (cohortsQ.data || []).map((c) => ({ label: c.month, values: c.values }))

  /* Axis labels arrive as ISO dates — only the client knows the reader's
     language and calendar, so the formatting happens here. */
  const chart = useMemo(() => {
    const raw = seriesQ.data
    if (!raw) return { labels: [], a: [], b: [] }
    const fmt = new Intl.DateTimeFormat(lang === 'fa' ? 'fa-IR' : 'en-US', { day: 'numeric', month: 'short' })
    return {
      labels: raw.labels.map((d) => fmt.format(new Date(d))),
      a: raw.series.find((x) => x.key === 'sent')?.data || [],
      b: raw.series.find((x) => x.key === 'opens')?.data || [],
    }
  }, [seriesQ.data, lang])

  /* The breakdown switcher is a server round-trip rather than four client-side
     reshapes of the same rows: the API already knows how to rank campaigns,
     segments, agents and devices by any of the three metrics. */
  const breakdown = (breakdownQ.data || []).map((r) => ({
    id: r.id,
    label: loc(r.label, lang),
    value: r.value,
  }))

  const fmt = (v) => pct(v, 1)

  return (
    <div className="page">
      {!embedded && (
      <PageHeader
        title={t('an.title')}
        sub={t('an.sub')}
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
            {/* The numbers on this screen are campaign figures, so the
                export is the campaign sheet — one file with the rates already
                computed, rather than a second half-format nobody maintains. */}
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
              {t('an.export')}
            </Button>
          </>
        }
      />
      )}

      <Stagger className="stack-v">
        <div className="kpirow" style={{ margin: 0 }}>
          <Kpi label={t('m.sent')} value={compact(tot.sent)}  icon={<IcSend size={15} />} />
          <Kpi label={t('m.openRate')} value={pct(tot.openRate, 1)}  icon={<IcEye size={15} />} />
          <Kpi label={t('m.clickRate')} value={pct(tot.clickRate, 1)}  icon={<IcCursorClick size={15} />} />
          <Kpi label={t('m.replies')} value={compact(tot.replies || 0)} delta={deltas.delivered} icon={<IcInbox size={15} />} />
          <Kpi label={t('m.unsubRate')} value={pct(tot.unsubRate || 0, 2)} deltaInvert />
        </div>

        <Card>
          <CardHead
            title={t('dash.pulse')}
            sub={t('dash.pulseSub')}
            icon={<IcChart size={17} />}
            right={<Badge tone="neutral">{t(`g.last${range}`)}</Badge>}
          />
          <AreaChart
            height={280}
            labels={chart.labels}
            formatValue={(v) => nf(v)}
            series={[
              { name: t('g.thisMonth'), data: chart.a, color: '#cfe1f2' },
              { name: t('g.vsLast', { period: t('g.month') }), data: chart.b, color: '#8fd3a8', dashed: true },
            ]}
          />
        </Card>

        <div className="cols cols--wide-narrow">
          <Card>
            <CardHead title={t('an.breakdown')} sub={t('an.breakdownSub')} />

            {/* On their own row, not in the header's `right` slot. That slot is
                sized for a badge; a Select plus a four-way switch spilled out
                of it at every width. */}
            <div className="breakdown__controls">
              <Select
                value={metric}
                onChange={setMetric}
                options={[
                  { value: 'openRate', label: t('m.openRate') },
                  { value: 'clickRate', label: t('m.clickRate') },
                ]}
              />
              {/* "by agent" is gone: this product has one agent now, so that
                  dimension could only ever return a single bar. */}
              <Segmented
                size="sm"
                value={dim}
                onChange={setDim}
                options={[
                  { value: 'campaign', label: t('an.byCampaign') },
                  { value: 'segment', label: t('an.bySegment') },
                  { value: 'device', label: t('an.byDevice') },
                ]}
              />
            </div>

            {breakdown.length === 0 ? (
              <p className="faint" style={{ fontSize: '1.25rem', margin: '1.4rem 0 0' }}>
                {t('an.breakdownEmpty')}
              </p>
            ) : (
              <BarList items={breakdown} format={fmt} />
            )}
          </Card>

          <div className="stack-v">
            <Card>
              <CardHead title={t('dash.funnel')} />
              <Funnel
                format={(v) => compact(v)}
                stages={(funnelQ.data || []).map((stage, i) => ({
                  key: stage.key,
                  label: t(`m.${stage.key}`),
                  value: stage.value,
                  color: FUNNEL_COLOURS[i % FUNNEL_COLOURS.length],
                }))}
              />
            </Card>

            <Card>
              <CardHead title={t('an.byAgent')} />
              <div className="row" style={{ gap: '1.2rem', justifyContent: 'space-around', flexWrap: 'wrap' }}>
                {(agentsQ.data || []).slice(0, 4).map((a) => (
                  <RadialStat
                    key={a.id}
                    size={82}
                    value={a.success}
                    color={a.status === 'paused' ? '#e0b473' : '#8fd3a8'}
                    center={pct(a.success, 0)}
                    label={loc(a.name, lang)}
                  />
                ))}
              </div>
            </Card>
          </div>
        </div>

        <div className="cols cols--2">
          <Card>
            <CardHead title={t('an.cohort')} sub={t('an.cohortSub')} />
            <CohortGrid cohorts={cohorts} periods={['M0', 'M1', 'M2', 'M3', 'M4', 'M5']} />
          </Card>

        </div>
      </Stagger>
    </div>
  )
}
