/* ============================================================
   DELIVERABILITY

   Inbox placement is shown as a stacked bar per provider —
   inbox / promotions / spam — rather than a single "delivery
   rate". A message that lands in the Promotions tab counts as
   delivered by every provider's API and by most dashboards, and
   quietly halves the open rate. The stack is the only encoding
   that makes that visible.
   ============================================================ */
import { useMemo } from 'react'
import { useI18n } from '../i18n'
import { useDeliverability, useDomains } from '../api/resources'
import { navigate } from '../router'
import PageHeader from '../layout/PageHeader'
import SenderHealth from '../components/SenderHealth'
import { Badge, Button, Card, CardHead, Gauge, Grid, Kpi, Progress, Stagger } from '../ui'
import { AreaChart, BarList } from '../ui/charts'
import { IcCheckC, IcGlobe, IcRefresh, IcShield, IcSignal, IcWarn } from '../components/NavIcons'

export default function Deliverability({ onToast, embedded }) {
  const { t, lang, nf, pct, compact } = useI18n()

  /* One request. Reputation, placement, warm-up and the issue list are all
     facets of the same question, and computing them together server-side is
     what keeps them consistent with each other. */
  const query = useDeliverability()
  const domainsQ = useDomains()
  const d = query.data || {}
  const tot = { bounceRate: d.bounceRate || 0 }

  /* A rate needs sends behind it to mean anything. Below the floor these
     say so, exactly as the Sender Health card above them does — two cards
     on one screen disagreeing about the same fact makes the honest one
     look broken. */
  const behind = d.sample ?? 0
  const enough = behind >= (d.minSample ?? 50)
  const orNotYet = (value) => (enough ? value : t('sh.notEnough'))
  const PROVIDERS = d.providers || []
  const domains = domainsQ.data || []
  const warmup = d.warmup || { day: 0, total: 30, today: 0, cap: 1 }

  const rep = useMemo(() => {
    const raw = d.reputationSeries
    if (!raw) return { labels: [], score: [] }
    const fmt = new Intl.DateTimeFormat(lang === 'fa' ? 'fa-IR' : 'en-US', { day: 'numeric', month: 'short' })
    return { labels: raw.labels.map((x) => fmt.format(new Date(x))), score: raw.data }
  }, [d.reputationSeries, lang])

  const issues = d.issues || []

  return (
    <div className="page">
      {!embedded && (
      <PageHeader
        title={t('del.title')}
        sub={t('del.sub')}
        actions={
          <Button variant="primary" icon={<IcRefresh size={16} />} onClick={() => onToast?.(t('del.seedTest'))}>
            {t('del.seedTest')}
          </Button>
        }
      />
      )}

      <Stagger className="stack-v">
        <SenderHealth onToast={onToast} />
        <div className="kpirow" style={{ margin: 0 }}>
          {/* All four are measured on this account's own campaigns. The
              inbox-placement and complaint rates that used to sit here needed
              seed-list testing and a feedback loop we do not have. */}
          <Kpi label={t('m.reputation')} value={nf(d.reputation || 0)} icon={<IcShield size={15} />} />
          <Kpi label={t('m.deliveryRate')} value={orNotYet(pct(d.deliveryRate || 0, 1))} icon={<IcSignal size={15} />} />
          <Kpi label={t('m.bounceRate')} value={orNotYet(pct(tot.bounceRate, 2))} deltaInvert />
          <Kpi label={t('m.unsubRate')} value={orNotYet(pct(d.unsubRate || 0, 2))} deltaInvert />
        </div>

        <div className="cols cols--wide-narrow">
          <Card>
            <CardHead title={t('del.reputation')} icon={<IcSignal size={17} />} />
            <AreaChart
              height={230}
              labels={rep.labels}
              formatValue={(v) => nf(v)}
              series={[{ name: t('m.reputation'), data: rep.score, color: '#8fd3a8' }]}
            />
          </Card>

          <div className="stack-v">
            <Card>
              <CardHead title={t('m.reputation')} />
              <div className="row" style={{ gap: '2rem', alignItems: 'center' }}>
                <Gauge value={d.reputation || 0} size={128} tone="good" label={nf(d.reputation || 0)} sub="/ 100" caption={t('m.reputation')} />
                <div style={{ flex: 1, minWidth: 0, display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
                  {/* Read from the domains this deployment actually has. The
                      three bars here were pinned at 100/100/70 regardless. */}
                  {['spf', 'dkim', 'dmarc'].map((rec) => {
                    const ok = domains.length > 0 && domains.every((x) => x[rec])
                    return (
                      <Progress
                        key={rec}
                        label={rec.toUpperCase()}
                        right={domains.length ? (ok ? t('dom.verified') : t('dom.missing')) : '—'}
                        value={domains.length && ok ? 100 : 0}
                        tone={ok ? 'good' : 'warn'}
                      />
                    )
                  })}
                </div>
              </div>
            </Card>

          </div>
        </div>

        <div className="cols cols--2">
          {/* stacked placement per provider */}
          <Card>
            <CardHead title={t('del.providerMix')} sub={t('del.providerMixSub')} icon={<IcGlobe size={17} />} />
            {PROVIDERS.length === 0 ? (
              <p className="faint" style={{ fontSize: '1.25rem' }}>{t('del.noAudience')}</p>
            ) : (
              <BarList
                max={100}
                format={(v) => pct(v, 1)}
                items={PROVIDERS.map((p) => ({ id: p.id, label: p.label, value: p.share }))}
              />
            )}
          </Card>

          <div className="stack-v">
            <Card>
              {/* Today's real volume against this workspace's own throttle.
                  The day-N-of-30 counter above it was a fixed literal. */}
              <CardHead title={t('del.todayVolume')} sub={t('del.todayVolumeSub')} />
              <Progress
                value={warmup.today || 0}
                max={warmup.cap || 1}
                tone="good"
                label={t('set.throttle')}
                right={`${compact(warmup.today || 0)} / ${warmup.cap ? compact(warmup.cap) : '—'}`}
              />
            </Card>

            <Card>
              <CardHead title={t('del.issues')} icon={<IcWarn size={17} />} right={<Badge tone="warn">{nf(issues.length)}</Badge>} />
              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
                {issues.map((i) => (
                  <button className="tile" key={i.id} onClick={() => navigate(i.fix)}>
                    <span className="tile__icon" style={{ color: i.tone === 'bad' ? 'var(--bad)' : 'var(--warn)' }}>
                      <IcWarn size={16} />
                    </span>
                    <span className="tile__text">
                      <span className="tile__title" style={{ whiteSpace: 'normal', fontWeight: 500 }}>
                        {i.text ? i.text[lang] || i.text.en : ''}
                      </span>
                    </span>
                    <span className="tile__end">
                      <Badge tone={i.tone} size="sm">
                        {t('g.view')}
                      </Badge>
                    </span>
                  </button>
                ))}
              </div>
            </Card>
          </div>
        </div>
      </Stagger>
    </div>
  )
}
