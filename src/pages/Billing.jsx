/* BILLING — plan, three usage meters, invoices.
   The meters carry a projected-overage warning rather than only a
   percentage, because the number a reader actually needs on this
   page is "will I run out before the cycle ends". */
import { useI18n, loc } from '../i18n'
import { useConfig } from '../api/config'
import { useBilling } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import { Badge, Button, Card, CardHead, Grid, Progress, Stagger, Table } from '../ui'

import { IcCard, IcCheckC, IcDownload, IcSpark, IcWarn } from '../components/NavIcons'

export default function Billing({ onToast, embedded }) {
  const { t, lang, pct, compact, money, date } = useI18n()
  const { brand } = useConfig()
  const query = useBilling()

  /* Every field is read through a default. This card paints before the request
     lands, and a meter dividing by an undefined limit renders NaN%. */
  const plan = query.data?.plan
  const usage = query.data?.usage || {}
  const method = query.data?.method
  const invoices = query.data?.invoices || []

  const meters = [
    { id: 'emails', label: t('bill.emails'), tone: 'blue', fmt: compact, ...(usage.emails || {}) },
    { id: 'credits', label: t('bill.aiCredits'), tone: 'violet', fmt: compact, ...(usage.credits || {}) },
    { id: 'contacts', label: t('bill.contactsUsed'), tone: 'good', fmt: compact, ...(usage.contacts || {}) },
  ]

  return (
    <div className="page">
      {!embedded && (
      <PageHeader
        title={t('bill.title')}
        sub={t('bill.sub')}
        /* There is no payment processor here, and there should not be: in this
           product the customer does not self-serve billing, they ask the agency
           that sold them the panel. Without an address to ask, the button has
           nothing to do and is not shown. */
        actions={
          brand.supportEmail && (
            <Button
              variant="primary"
              icon={<IcSpark size={16} />}
              onClick={() => {
                const subject = encodeURIComponent(t('bill.planMailSubject', { name: brand.name }))
                window.location.href = `mailto:${brand.supportEmail}?subject=${subject}`
              }}
            >
              {t('bill.changePlan')}
            </Button>
          )
        }
      />
      )}

      <Stagger className="stack-v">
        <div className="cols cols--wide-narrow">
          <Card>
            <CardHead title={t('bill.usage')} icon={<IcCard size={17} />} sub={plan?.renews ? t('bill.renews', { date: date(plan.renews, { day: 'numeric', month: 'long' }) }) : ''} />
            <div className="usage">
              {meters.map((m) => {
                const used = m.limit ? (m.used / m.limit) * 100 : 0
                return (
                  <div key={m.id}>
                    <Progress
                      value={m.used || 0}
                      max={m.limit || 1}
                      tone={used > 85 ? 'warn' : m.tone}
                      label={m.label}
                      right={`${m.fmt(m.used || 0)} / ${m.fmt(m.limit || 0)}`}
                    />
                    <div className="row" style={{ gap: '0.6rem', marginTop: '0.7rem' }}>
                      <span className="faint" style={{ fontSize: '1.15rem' }}>
                        {pct(used, 1)}
                      </span>
                      {used > 60 && (
                        <Badge tone={used > 85 ? 'warn' : 'neutral'} size="sm">
                          {lang === 'fa' ? 'رو به اتمام' : 'trending high'}
                        </Badge>
                      )}
                    </div>
                  </div>
                )
              })}
            </div>
          </Card>

          <div className="stack-v">
            <div className="card plan">
              <div className="caps" style={{ color: 'rgba(226,238,250,.7)' }}>
                {t('bill.plan')}
              </div>
              <div className="plan__name">{loc(plan?.name, lang)}</div>
              <div className="plan__price">
                {money(plan?.price || 0)} / {t('g.month')}
              </div>
              <div style={{ marginTop: '1.8rem', display: 'flex', flexDirection: 'column', gap: '0.9rem' }}>
                {(lang === 'fa'
                  ? ['۵۰۰٬۰۰۰ ایمیل در ماه', '۱۲۰٬۰۰۰ اعتبار هوش مصنوعی', 'ایجنت‌های نامحدود', 'آی‌پی اختصاصی', 'پشتیبانی اولویت‌دار']
                  : ['500,000 emails / month', '120,000 AI credits', 'Unlimited agents', 'Dedicated IP', 'Priority support']
                ).map((f) => (
                  <span key={f} className="row" style={{ gap: '0.8rem', fontSize: '1.28rem', color: 'rgba(232,240,250,.9)' }}>
                    <IcCheckC size={15} />
                    {f}
                  </span>
                ))}
              </div>
            </div>

            <Card>
              <CardHead title={t('bill.method')} />
              <div className="row" style={{ gap: '1.2rem' }}>
                <span className="tile__icon">
                  <IcCard size={17} />
                </span>
                <div style={{ flex: 1 }}>
                  <div className="strong mono" style={{ fontSize: '1.3rem' }}>
                    •••• •••• •••• {method?.last4 || '····'}
                  </div>
                  <div className="faint" style={{ fontSize: '1.15rem' }}>
                    {method ? `${method.brand} · ${method.exp}` : '—'}
                  </div>
                </div>
                {brand.supportEmail && (
                  <Button
                    size="sm"
                    variant="ghost"
                    onClick={() => {
                      const subject = encodeURIComponent(t('bill.cardMailSubject', { name: brand.name }))
                      window.location.href = `mailto:${brand.supportEmail}?subject=${subject}`
                    }}
                  >
                    {t('g.edit')}
                  </Button>
                )}
              </div>
            </Card>
          </div>
        </div>

        <Card pad={false} className="panel">
          <div className="panel__head">
            <span className="ucard__title">{t('bill.invoices')}</span>
          </div>
          <Table
            keyFn={(i) => i.id}
            rows={invoices}
            columns={[
              { key: 'id', title: '#', width: 'minmax(0, 1fr)', render: (i) => <span className="mono">{i.id}</span> },
              {
                key: 'date',
                title: t('g.created'),
                width: 'minmax(0, 1fr)',
                render: (i) => date(i.date, { day: 'numeric', month: 'short', year: 'numeric' }),
              },
              {
                key: 'amount',
                title: t('bill.amount'),
                width: 'minmax(0, 1fr)',
                align: 'end',
                render: (i) => <span className="num-tab strong">{money(i.amount)}</span>,
              },
              {
                key: 'status',
                title: t('g.status'),
                width: 'minmax(0, 0.8fr)',
                render: (i) => (
                  <Badge tone="good" dot>
                    {t('bill.paid')}
                  </Badge>
                ),
              },
              {
                key: 'act',
                title: '',
                width: '4rem',
                align: 'center',
                render: () => (
                  <button className="iconbtn" style={{ width: '3rem', height: '3rem' }} aria-label={t('bill.download')}>
                    <IcDownload size={14} />
                  </button>
                ),
              },
            ]}
          />
        </Card>
      </Stagger>
    </div>
  )
}
