/* ============================================================
   EXPERIMENTS

   The confidence bar is the load-bearing element here. An A/B
   result with the winner highlighted but no confidence attached is
   how teams talk themselves into promoting noise, so the threshold
   is drawn as a physical mark on the track: you can see whether
   the test has crossed it without reading a number.
   ============================================================ */
import { useState } from 'react'
import { useI18n, loc } from '../i18n'
import { useExperiments, usePromoteExperiment } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardHead,
  Grid,
  Kpi,
  Modal,
  Field,
  Input,
  Select,
  Segmented,
  Slider,
  Stagger,
  StatusBadge,
  Toggle,
} from '../ui'

import { IcFlask, IcPlus, IcSpark, IcTrendUp } from '../components/NavIcons'

const THRESHOLD = 95

export default function Experiments({ onToast }) {
  const { t, lang, nf, pct, compact } = useI18n()
  const query = useExperiments()
  const [promote] = usePromoteExperiment()
  const experiments = query.data || []
  const [neu, setNeu] = useState(false)
  const [auto, setAuto] = useState(true)
  const [split, setSplit] = useState(50)

  const running = experiments.filter((x) => x.status === 'running').length

  return (
    <div className="page">
      <PageHeader
        title={t('exp.title')}
        sub={t('exp.sub')}
        actions={
          <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => setNeu(true)}>
            {t('exp.new')}
          </Button>
        }
      />

      <Stagger className="stack-v">
        <div className="kpirow" style={{ margin: 0 }}>
          <Kpi label={t('exp.running')} value={nf(running)} icon={<IcFlask size={15} />} />
          <Kpi label={t('exp.called')} value={nf(experiments.length - running)} />
          <Kpi label={t('exp.lift')} value={`+${pct(14.2, 1)}`} delta={3.4} icon={<IcTrendUp size={15} />} />
          <Kpi label={t('m.openRate')} value={pct(44.7, 1)} delta={4.9} />
        </div>

        {experiments.map((x) => {
          /* Variant ids are namespaced by the API (`x-1-a`), so the control
             arm is found by its LABEL. Matching on a bare 'a' silently
             returned undefined and took the page down. */
          const variants = x.variants || []
          if (!variants.length) return null
          const best = variants.reduce((a, b) => (b.rate > a.rate ? b : a))
          const base = variants.find((v) => v.label === 'A') || variants[0]
          const lift = base.rate ? ((best.rate - base.rate) / base.rate) * 100 : 0
          const called = x.confidence >= THRESHOLD

          return (
            <Card key={x.id}>
              <CardHead
                title={loc(x.name, lang)}
                sub={`${t('exp.metric')}: ${t(`m.${x.metric}`)}`}
                icon={<IcFlask size={17} />}
                right={
                  <div className="row" style={{ gap: '0.8rem' }}>
                    <StatusBadge status={x.status === 'running' ? 'sending' : 'active'}>
                      {t(x.status === 'running' ? 'exp.running' : 'exp.called')}
                    </StatusBadge>
                    {called && (
                      <Button
                        size="sm"
                        variant="primary"
                        onClick={async () => {
                          try {
                            await promote(x.id)
                            onToast?.(t('toast.applied'))
                          } catch (err) {
                            // below 95% the server refuses, and says why
                            onToast?.(err.message || t('err.failed'))
                          }
                        }}
                      >
                        {t('exp.autoPromote')}
                      </Button>
                    )}
                  </div>
                }
              />

              <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem', marginBottom: '1.6rem' }}>
                {variants.map((v) => (
                  <div className={`variant${v.winner ? ' variant--win' : ''}`} key={v.id}>
                    <span className="variant__tag">{v.label}</span>
                    <span className="variant__text">
                      <span className="variant__copy">{loc(v.text, lang)}</span>
                      <span className="variant__meta">
                        {compact(v.sent)} {t('m.sent')} · {pct(v.split, 0)} {t('exp.split')}
                      </span>
                    </span>
                    <span className="variant__rate">
                      <span className="variant__rateV num-tab">{pct(v.rate, 1)}</span>
                      {v.winner && (
                        <div>
                          <Badge tone="good" size="sm">
                            {t('exp.winner')}
                          </Badge>
                        </div>
                      )}
                    </span>
                  </div>
                ))}
              </div>

              {/* confidence, with the promote threshold drawn on the track */}
              <div>
                <div className="row" style={{ justifyContent: 'space-between', marginBottom: '0.7rem' }}>
                  <span className="muted" style={{ fontSize: '1.25rem' }}>
                    {t('exp.confidence')}
                  </span>
                  <span className="row" style={{ gap: '1rem' }}>
                    <span className="strong num-tab">{pct(x.confidence, 1)}</span>
                    <span className="reco__lift">
                      +{nf(lift, { maximumFractionDigits: 1 })}% {t('exp.lift')}
                    </span>
                  </span>
                </div>
                <div className="prog__track" style={{ position: 'relative', height: '0.9rem' }}>
                  <span
                    className={`prog__fill prog__fill--${called ? 'good' : 'warn'}`}
                    style={{ width: `${x.confidence}%` }}
                  />
                  <span
                    title={`${THRESHOLD}%`}
                    style={{
                      position: 'absolute',
                      insetInlineStart: `${THRESHOLD}%`,
                      insetBlock: '-0.35rem',
                      width: '2px',
                      background: 'rgba(240,246,252,.85)',
                      boxShadow: '0 0 0.9rem rgba(240,246,252,.9)',
                      borderRadius: '9.9rem',
                    }}
                  />
                </div>
                <p className="faint" style={{ fontSize: '1.15rem', marginTop: '0.7rem' }}>
                  {called
                    ? lang === 'fa'
                      ? 'از آستانه رد شده — می‌شود برنده را ارتقا داد.'
                      : 'Past the threshold — the winner can be promoted.'
                    : lang === 'fa'
                      ? `هنوز زیر آستانهٔ ${THRESHOLD}٪ است؛ داده بیشتری لازم است.`
                      : `Still under the ${THRESHOLD}% threshold; needs more data.`}
                </p>
              </div>
            </Card>
          )
        })}
      </Stagger>

      <Modal
        open={neu}
        onClose={() => setNeu(false)}
        width={58}
        title={t('exp.new')}
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
            <Input placeholder={lang === 'fa' ? 'مثلاً: موضوع کوتاه در برابر بلند' : 'e.g. Short vs long subject'} />
          </Field>
          <Grid cols={2} gap={1.4}>
            <Field label={t('exp.metric')}>
              <Select
                value="openRate"
                onChange={() => {}}
                options={[
                  { value: 'openRate', label: t('m.openRate') },
                  { value: 'clickRate', label: t('m.clickRate') },
                ]}
              />
            </Field>
            <Field label={t('camp.audience')}>
              <Select value="vip" onChange={() => {}} options={[{ value: 'vip', label: 'VIP' }]} />
            </Field>
          </Grid>
          <div>
            <div className="row" style={{ justifyContent: 'space-between', marginBottom: '0.4rem' }}>
              <span className="field2__label">{t('exp.split')}</span>
              <span className="strong num-tab">
                {pct(split, 0)} / {pct(100 - split, 0)}
              </span>
            </div>
            <Slider value={split} min={10} max={90} step={5} onChange={setSplit} />
          </div>
          <Toggle checked={auto} onChange={setAuto} label={t('exp.autoPromote')} hint={t('exp.autoPromoteHint')} />
        </div>
      </Modal>
    </div>
  )
}
