/* ============================================================
   JOURNEYS

   The flow canvas is a vertical spine rather than a free 2D graph.
   A free canvas is the right tool when a flow branches wide, but
   it needs pan, zoom, minimap and edge routing to stay legible —
   and every real journey in this product is a mostly-linear
   sequence with the occasional condition. A spine reads top to
   bottom with no interaction at all, and the connector carries a
   travelling spark so the sequence reads as a direction.
   ============================================================ */
import { useRef, useState } from 'react'
import { gsap, reduced, useGSAP } from '../anim/core'
import { useI18n, byId, loc } from '../i18n'
import { useAgents, useJourneyAction, useJourneys } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHead,
  Delta,
  Drawer,
  Grid,
  Progress,
  Stagger,
  StatusBadge,
} from '../ui'

import {
  IcAgent,
  IcCheckC,
  IcClock2,
  IcCode,
  IcFlow,
  IcMail,
  IcPause,
  IcPlay,
  IcPlus,
  IcTag,
  IcTarget,
} from '../components/NavIcons'

const STEP_ICON = {
  email: IcMail,
  wait: IcClock2,
  branch: IcTarget,
  agent: IcAgent,
  tag: IcTag,
  webhook: IcCode,
  goal: IcCheckC,
}

export default function Automations({ onToast }) {
  const { t, lang, nf, pct, compact } = useI18n()
  const [open, setOpen] = useState(null)
  const query = useJourneys()
  const agents = useAgents()
  const [journeyAction] = useJourneyAction()

  return (
    <div className="page">
      <PageHeader
        title={t('auto.title')}
        sub={t('auto.sub')}
        actions={
          <>
            <Button variant="ghost">{t('auto.library')}</Button>
            <Button variant="primary" icon={<IcPlus size={16} />}>
              {t('auto.new')}
            </Button>
          </>
        }
      />

      <Stagger>
        <Grid min={34} gap={1.5}>
          {(query.data || []).map((j) => {
            const ag = byId(agents.data, j.agent)
            return (
              <Card key={j.id} tilt>
                <div className="row" style={{ gap: '1.2rem', marginBottom: '1.4rem' }}>
                  <span className="ucard__headIcon" style={{ width: '4.4rem', height: '4.4rem' }}>
                    <IcFlow size={20} />
                  </span>
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="agentcard__name" style={{ fontSize: '1.75rem' }}>
                      {loc(j.name, lang)}
                    </div>
                    <div className="agentcard__role">
                      {t('auto.trigger')}: {loc(j.trigger, lang)}
                    </div>
                  </div>
                  <StatusBadge status={j.status}>{t(`g.${j.status}`)}</StatusBadge>
                </div>

                {/* a compressed preview of the spine */}
                <div className="row" style={{ gap: '0.5rem', flexWrap: 'wrap', marginBottom: '1.4rem' }}>
                  {j.steps.map((s, i) => {
                    const Icon = STEP_ICON[s.type] ?? IcMail
                    return (
                      <span key={s.id} className="row" style={{ gap: '0.5rem' }}>
                        <span
                          className="flowstep__icon"
                          style={{ width: '2.8rem', height: '2.8rem', borderRadius: '0.9rem' }}
                          title={loc(s.label, lang)}
                        >
                          <Icon size={14} />
                        </span>
                        {i < j.steps.length - 1 && (
                          <span style={{ width: '1.1rem', height: '1.5px', background: 'rgba(150,195,232,.35)' }} />
                        )}
                      </span>
                    )
                  })}
                </div>

                <div className="agentcard__stats" style={{ marginBottom: '1.4rem' }}>
                  <div className="agentcard__stat">
                    <span className="agentcard__statV num-tab">{compact(j.enrolled)}</span>
                    <span className="agentcard__statL">{t('auto.enrolled')}</span>
                  </div>
                  <div className="agentcard__stat">
                    <span className="agentcard__statV num-tab">{compact(j.completed)}</span>
                    <span className="agentcard__statL">{t('auto.completed')}</span>
                  </div>
                  <div className="agentcard__stat">
                    <span className="agentcard__statV num-tab">{pct(j.conversion, 1)}</span>
                    <span className="agentcard__statL">{t('auto.conversion')}</span>
                  </div>
                </div>

                <Progress value={j.completed} max={j.enrolled} tone="good" label={t('auto.completed')} right={pct((j.completed / j.enrolled) * 100, 0)} />

                <div className="row" style={{ marginTop: '1.6rem', gap: '0.8rem' }}>
                  <Avatar name={loc(ag?.name, lang)} emoji={ag?.emoji} tint={ag?.tint} size={26} ring />
                  <span className="muted" style={{ fontSize: '1.2rem' }}>
                    {loc(ag?.name, lang)}
                  </span>
                  <span style={{ marginInlineStart: 'auto', display: 'flex', gap: '0.6rem' }}>
                    <Button
                      size="sm"
                      variant="quiet"
                      icon={j.status === 'active' ? <IcPause size={14} /> : <IcPlay size={14} />}
                      onClick={async () => {
                        const action = j.status === 'active' ? 'pause' : 'resume'
                        try {
                          await journeyAction({ id: j.id, action })
                          onToast?.(action === 'pause' ? t('toast.journeyPaused') : t('toast.journeyResumed'))
                        } catch (err) {
                          onToast?.(err.message || t('err.failed'))
                        }
                      }}
                    />
                    <Button size="sm" variant="ghost" onClick={() => setOpen(j)}>
                      {t('auto.canvas')}
                    </Button>
                  </span>
                </div>
              </Card>
            )
          })}
        </Grid>
      </Stagger>

      <FlowDrawer journey={open} onClose={() => setOpen(null)} onToast={onToast} />
    </div>
  )
}

function FlowDrawer({ journey, onClose, onToast }) {
  const { t, lang, nf, pct, compact } = useI18n()
  const canvas = useRef(null)

  /* The spark runs the spine on a loop once the drawer is open. Long rest
     between passes: the drawer stays open while someone reads the steps, and
     a light ticking down the page the whole time is a distraction, not a cue. */
  useGSAP(
    () => {
      if (!journey || reduced() || !canvas.current) return
      const sparks = canvas.current.querySelectorAll('.flowlink__spark')
      if (!sparks.length) return
      const tl = gsap.timeline({ repeat: -1, repeatDelay: 4, delay: 0.6 })
      sparks.forEach((s, i) => {
        tl.fromTo(
          s,
          { top: '-0.25rem', opacity: 0 },
          { top: 'calc(100% - 0.25rem)', opacity: 1, duration: 0.42, ease: 'power1.inOut' },
          i * 0.34
        ).to(s, { opacity: 0, duration: 0.16 }, i * 0.34 + 0.42)
      })
      return () => tl.kill()
    },
    { dependencies: [journey?.id], scope: canvas }
  )

  if (!journey) return null
  const j = journey

  return (
    <Drawer
      open={!!journey}
      onClose={onClose}
      width={62}
      title={loc(j.name, lang)}
      sub={`${t('auto.trigger')}: ${loc(j.trigger, lang)}`}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t('g.close')}
          </Button>
          <Button variant="primary" icon={<IcCheckC size={15} />} onClick={() => onToast?.(t('toast.saved'))}>
            {t('g.save')}
          </Button>
        </>
      }
    >
      <Grid min={16} gap={1.2} style={{ marginBottom: '1.8rem' }}>
        <StatBox label={t('auto.enrolled')} value={compact(j.enrolled)} />
        <StatBox label={t('auto.completed')} value={compact(j.completed)} />
        <StatBox label={t('auto.conversion')} value={pct(j.conversion, 1)} />
      </Grid>

      <Card>
        <CardHead title={t('auto.canvas')} icon={<IcFlow size={17} />} />
        <div className="flow" ref={canvas}>
          {j.steps.map((s, i) => {
            const Icon = STEP_ICON[s.type] ?? IcMail
            return (
              <div key={s.id} style={{ width: '100%', display: 'flex', flexDirection: 'column', alignItems: 'center' }}>
                <div className={`flowstep flowstep--${s.type}`}>
                  <span className="flowstep__icon">
                    <Icon size={16} />
                  </span>
                  <span className="flowstep__text">
                    <span className="flowstep__title">{loc(s.label, lang)}</span>
                    <span className="flowstep__kind">{t(`auto.step.${s.type}`)}</span>
                  </span>
                  <span className="faint mono" style={{ fontSize: '1.1rem' }}>
                    {nf(i + 1)}
                  </span>
                </div>
                {i < j.steps.length - 1 && (
                  <span className="flowlink">
                    <span className="flowlink__spark" />
                  </span>
                )}
              </div>
            )
          })}

          <span className="flowlink">
            <span className="flowlink__spark" />
          </span>
          <Button variant="quiet" icon={<IcPlus size={15} />}>
            {t('auto.addStep')}
          </Button>
        </div>
      </Card>
    </Drawer>
  )
}

export function StatBox({ label, value }) {
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
    </div>
  )
}
