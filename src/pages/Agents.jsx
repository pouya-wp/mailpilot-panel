/* ============================================================
   AI AGENTS — the roster, and the studio that configures one.

   The studio is the panel's most consequential form: autonomy,
   tools and guardrails together decide what a piece of software is
   allowed to do to a customer list without asking anyone. So it is
   laid out in that order, the autonomy control is the largest
   thing on the page, and the tool list is checkboxes rather than a
   free-text field — a permission you can typo is not a permission.
   ============================================================ */
import { useEffect, useState } from 'react'
import { byId, loc, useI18n } from '../i18n'
import { useAgent, useAgentAction, useAgents, useAgentTools, useMeta, useUpdateAgent } from '../api/resources'
import { Async } from '../ui/state'
import { navigate, useRoute } from '../router'
import PageHeader from '../layout/PageHeader'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHead,
  Checkbox,
  Divider,
  Drawer,
  Field,
  Grid,
  Input,
  Progress,
  Segmented,
  Select,
  Slider,
  Stagger,
  StatusBadge,
  Tabs,
  Textarea,
  Toggle,
} from '../ui'
import { RadialStat, Sparkline } from '../ui/charts'
import {
  IcAgent,
  IcBolt,
  IcCheckC,
  IcCode,
  IcEye,
  IcPause,
  IcPlay,
  IcPlus,
  IcRefresh,
  IcShield,
  IcSpark,
} from '../components/NavIcons'

const ALL_TOOLS = [
  'contacts.read',
  'contacts.write',
  'campaigns.write',
  'segments.write',
  'analytics.read',
  'brand.read',
  'inbox.read',
  'inbox.write',
  'domains.write',
  'suppression.write',
  'experiments.write',
  'crm.write',
]

/* A believable run trace. The point of showing it at all is that an
   autonomous agent has to be auditable — every step names the tool it
   called, so a human can tell what actually happened to the list. */
const TRACE = {
  en: [
    { title: 'Loaded audience', detail: 'Pulled 25,000 VIP contacts and their last 90 days of engagement.', tool: 'contacts.read(segment="vip")' },
    { title: 'Read brand voice', detail: 'Applied the brand brain: warm, second person, no exclamation marks.', tool: 'brand.read()' },
    { title: 'Drafted 4 subject lines', detail: 'Scored each against historical open rate for this segment.', tool: null },
    { title: 'Chose send time', detail: 'Per-contact optimum from the open-time model; median 08:40 local.', tool: 'analytics.read(metric="open_time")' },
    { title: 'Requested approval', detail: 'Autonomy is set to "act with approval", so the send was queued for a human.', tool: null },
  ],
  fa: [
    { title: 'بارگذاری مخاطبان', detail: '۲۵٬۰۰۰ مخاطب ویژه و تعامل ۹۰ روز اخیرشان خوانده شد.', tool: 'contacts.read(segment="vip")' },
    { title: 'خواندن لحن برند', detail: 'مغز برند اعمال شد: صمیمی، دوم‌شخص، بدون علامت تعجب.', tool: 'brand.read()' },
    { title: 'نوشتن ۴ موضوع', detail: 'هرکدام بر اساس نرخ بازشدن تاریخی همین بخش امتیاز گرفت.', tool: null },
    { title: 'انتخاب زمان ارسال', detail: 'بهینهٔ هر مخاطب از مدل زمان بازشدن؛ میانه ۰۸:۴۰ محلی.', tool: 'analytics.read(metric="open_time")' },
    { title: 'درخواست تأیید', detail: 'استقلال روی «با تأیید انسان» است، پس ارسال در صف تأیید قرار گرفت.', tool: null },
  ],
}

export default function Agents({ onToast }) {
  const { t, lang, nf, pct, ago } = useI18n()
  const { params } = useRoute()
  const openId = params[0]
  const query = useAgents()
  const detail = useAgent(openId)
  const [agentAction] = useAgentAction()
  const open = detail.data

  return (
    <div className="page">
      <PageHeader
        title={t('ag.title')}
        sub={t('ag.sub')}
        actions={
          <Button variant="primary" icon={<IcPlus size={16} />}>
            {t('ag.new')}
          </Button>
        }
      />

      <Stagger className="stack-v">
        <Grid min={30} gap={1.5}>
          {(query.data || []).map((a) => (
            <div className={`card agentcard${a.status === 'active' ? ' agentcard--live' : ''}`} key={a.id}>
              <div className="agentcard__top">
                <span className="agentcard__face" style={{ background: a.tint }}>
                  {a.emoji}
                </span>
                <div className="agentcard__names">
                  <div className="agentcard__name">{loc(a.name, lang)}</div>
                  <div className="agentcard__role">{loc(a.role, lang)}</div>
                </div>
                <StatusBadge status={a.status}>{t(`g.${a.status}`)}</StatusBadge>
              </div>

              <div className="agentcard__stats">
                <div className="agentcard__stat">
                  <span className="agentcard__statV num-tab">{nf(a.actionsToday)}</span>
                  <span className="agentcard__statL">{t('ag.actionsToday')}</span>
                </div>
                <div className="agentcard__stat">
                  <span className="agentcard__statV num-tab">{pct(a.success, 1)}</span>
                  <span className="agentcard__statL">{t('ag.successRate')}</span>
                </div>
                <div className="agentcard__stat">
                  <span className="agentcard__statV num-tab">{nf(a.runs)}</span>
                  <span className="agentcard__statL">{t('ag.runs')}</span>
                </div>
              </div>

              <div style={{ margin: '-0.4rem 0 0.2rem' }}>
                <Sparkline data={a.sparkline} color={a.status === 'paused' ? '#e0b473' : '#9dc0dd'} height={34} />
              </div>

              <div className="agentcard__skills">
                {a.skills.slice(0, 4).map((s) => (
                  <span className="skillchip" key={s}>
                    {s}
                  </span>
                ))}
              </div>

              <div className="agentcard__foot">
                <Badge tone="neutral" size="sm">
                  {t(`ag.autonomy.${a.autonomy}`)}
                </Badge>
                <span className="faint" style={{ fontSize: '1.1rem' }}>
                  {t('ag.lastRun')} {ago(a.lastRun)}
                </span>
                <span style={{ marginInlineStart: 'auto', display: 'flex', gap: '0.6rem' }}>
                  <Button
                    size="sm"
                    variant="quiet"
                    icon={a.status === 'active' ? <IcPause size={14} /> : <IcPlay size={14} />}
                    onClick={async () => {
                      const next = a.status === 'active' ? 'pause' : 'resume'
                      await agentAction({ id: a.id, action: next })
                      onToast?.(next === 'pause' ? t('toast.agentPaused') : t('toast.agentResumed'))
                    }}
                  />
                  <Button size="sm" variant="ghost" onClick={() => navigate(`agents/${a.id}`)}>
                    {t('ag.studio')}
                  </Button>
                </span>
              </div>
            </div>
          ))}

          {/* the "hire" affordance is a card of the same size, so the grid
              never has a ragged last row */}
          <button className="card agentcard" style={{ alignItems: 'center', justifyContent: 'center', gap: '1.2rem' }}>
            <span className="empty__icon">
              <IcPlus size={24} />
            </span>
            <span className="agentcard__name">{t('ag.new')}</span>
            <span className="agentcard__role" style={{ textAlign: 'center', maxWidth: '24rem' }}>
              {t('ag.autonomyHint')}
            </span>
          </button>
        </Grid>
      </Stagger>

      <AgentStudio agent={open} onClose={() => navigate('agents')} onToast={onToast} />
    </div>
  )
}

/* ============================================================
   STUDIO
   ============================================================ */
function AgentStudio({ agent, onClose, onToast }) {
  const { t, lang, nf, pct, ago } = useI18n()
  const meta = useMeta()
  const toolsQ = useAgentTools()
  const [saveAgent, saving] = useUpdateAgent()
  const [runAgent, running] = useAgentAction()
  const [tab, setTab] = useState('config')
  const MODELS = meta.data?.models || []
  /* The tool list comes from the API, so the studio can never offer an agent
     a capability the server would reject. */
  const ALL_TOOLS_LIVE = toolsQ.data || ALL_TOOLS

  const [autonomy, setAutonomy] = useState(agent?.autonomy ?? 'approve')
  /* The model list is FETCHED, so it is empty on the first render — falling
     back to `MODELS[0].value` crashed the studio before the list arrived. */
  const [model, setModel] = useState(agent?.model ?? '')
  const [temp, setTemp] = useState(Math.round((agent?.temperature ?? 0.5) * 100))
  const [budget, setBudget] = useState(agent?.budget ?? 100)
  const [tools, setTools] = useState(agent?.tools ?? [])
  const [instructions, setInstructions] = useState(agent?.instructions ?? '')

  /* The drawer is mounted before the agent it edits has loaded, so the form
     is seeded once the record arrives rather than at first render. */
  useEffect(() => {
    if (!agent) return
    setAutonomy(agent.autonomy)
    setModel(agent.model || '')
    setTemp(Math.round((agent.temperature ?? 0.5) * 100))
    setBudget(agent.budget)
    setTools(agent.tools || [])
    setInstructions(agent.instructions || '')
  }, [agent?.id])

  /* Adopt the first model once the list lands, if the agent named none. */
  useEffect(() => {
    if (!model && MODELS.length) setModel(MODELS[0].value)
  }, [model, MODELS])

  if (!agent) return null

  const toggleTool = (tl) => setTools((ts) => (ts.includes(tl) ? ts.filter((x) => x !== tl) : [...ts, tl]))

  return (
    <Drawer
      open={!!agent}
      onClose={onClose}
      width={72}
      title={loc(agent.name, lang)}
      sub={loc(agent.role, lang)}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t('g.cancel')}
          </Button>
          <Button
            variant="ghost"
            icon={<IcRefresh size={15} />}
            loading={running.loading}
            onClick={async () => {
              try {
                const res = await runAgent({ id: agent.id, action: 'run' })
                /* A dry run never mails anyone. What it tells you is whether
                   this agent would have been allowed to act unsupervised. */
                onToast?.(res?.may_act_alone ? t('toast.testAutonomous') : t('toast.testApproval'))
              } catch (err) {
                // most often the daily budget, which the server refuses with 429
                onToast?.(err.message || t('err.failed'))
              }
            }}
          >
            {t('ag.test')}
          </Button>
          <Button
            variant="primary"
            icon={<IcCheckC size={15} />}
            loading={saving.loading}
            onClick={async () => {
              try {
                await saveAgent({
                  id: agent.id,
                  autonomy,
                  model,
                  temperature: temp / 100,
                  budget,
                  tools,
                  instructions,
                })
                onToast?.(t('toast.saved'))
                onClose()
              } catch (err) {
                onToast?.(err.message || t('err.failed'))
              }
            }}
          >
            {t('ag.deploy')}
          </Button>
        </>
      }
    >
      <div className="row" style={{ gap: '1.4rem', marginBottom: '1.8rem' }}>
        <span className="agentcard__face" style={{ background: agent.tint, width: '6rem', height: '6rem', fontSize: '3rem' }}>
          {agent.emoji}
        </span>
        <div style={{ flex: 1, minWidth: 0 }}>
          <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap' }}>
            <StatusBadge status={agent.status}>{t(`g.${agent.status}`)}</StatusBadge>
            <Badge tone="info">{agent.model}</Badge>
            <Badge tone="neutral">{t(`ag.autonomy.${autonomy}`)}</Badge>
          </div>
          <p className="muted" style={{ fontSize: '1.2rem', marginTop: '0.7rem' }}>
            {t('ag.lastRun')} {ago(agent.lastRun)} · {nf(agent.runs)} {t('ag.runs')} · {pct(agent.success, 1)}{' '}
            {t('ag.successRate')}
          </p>
        </div>
        <div className="row" style={{ gap: '1.4rem' }}>
          <RadialStat value={agent.success} size={78} color="#8fd3a8" center={pct(agent.success, 0)} label={t('ag.successRate')} />
          <RadialStat
            value={agent.actionsToday}
            max={agent.budget}
            size={78}
            color="#7ba3cd"
            center={nf(agent.actionsToday)}
            label={t('ag.budget')}
          />
        </div>
      </div>

      <Tabs
        value={tab}
        onChange={setTab}
        tabs={[
          { value: 'config', label: t('ag.instructions') },
          { value: 'tools', label: t('ag.tools'), count: tools.length },
          { value: 'trace', label: t('ag.trace') },
          { value: 'memory', label: t('ag.memory') },
        ]}
      />

      <div style={{ marginTop: '1.8rem' }} className="stack-v">
        {tab === 'config' && (
          <>
            <Card>
              <CardHead title={t('ag.autonomy')} sub={t('ag.autonomyHint')} icon={<IcShield size={17} />} />
              <Segmented
                value={autonomy}
                onChange={setAutonomy}
                options={['suggest', 'approve', 'full'].map((a) => ({ value: a, label: t(`ag.autonomy.${a}`) }))}
              />
              {autonomy === 'full' && (
                <p
                  className="row"
                  style={{
                    gap: '0.8rem',
                    marginTop: '1.4rem',
                    padding: '1.1rem 1.3rem',
                    borderRadius: 'var(--r-sm)',
                    background: 'var(--warn-dim)',
                    border: '1px solid var(--warn-edge)',
                    color: 'var(--warn)',
                    fontSize: '1.22rem',
                  }}
                >
                  <IcShield size={16} />
                  {lang === 'fa'
                    ? 'این ایجنت بدون تأیید انسان به مخاطبان واقعی ایمیل می‌فرستد.'
                    : 'This agent will email real contacts with no human approval.'}
                </p>
              )}
            </Card>

            <Card>
              <CardHead title={t('ag.instructions')} icon={<IcCode size={17} />} />
              <Textarea
                rows={7}
                value={instructions}
                onChange={(e) => setInstructions(e.target.value)}
                placeholder={
                  lang === 'fa'
                    ? 'تو کپی‌رایتر ارشد آکمی هستی. همیشه دوم‌شخص بنویس، هر ایمیل فقط یک دکمهٔ اصلی داشته باشد، و هرگز از علامت تعجب استفاده نکن…'
                    : 'You are the senior copywriter at Acme. Always write in second person, one primary CTA per email, and never use exclamation marks…'
                }
              />
            </Card>

            <Grid cols={2} gap={1.5}>
              <Card>
                <CardHead title={t('ag.model')} />
                <Field label={t('set.defaultModel')}>
                  <Select value={model} onChange={setModel} options={MODELS} />
                </Field>
                <div style={{ marginTop: '1.6rem' }}>
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                    <span className="field2__label">{t('ag.temperature')}</span>
                    <span className="strong num-tab">{nf(temp / 100, { maximumFractionDigits: 2 })}</span>
                  </div>
                  <Slider value={temp} onChange={setTemp} ticks={['0', '0.5', '1']} />
                </div>
              </Card>

              <Card>
                <CardHead title={t('ag.guardrails')} icon={<IcShield size={17} />} />
                <div style={{ marginBottom: '1.4rem' }}>
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: '0.4rem' }}>
                    <span className="field2__label">{t('ag.budget')}</span>
                    <span className="strong num-tab">{nf(budget)}</span>
                  </div>
                  <Slider value={budget} min={10} max={500} step={10} onChange={setBudget} />
                </div>
                <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
                  <Toggle checked onChange={() => {}} label={t('set.quietHours')} hint={t('set.quietHoursHint')} />
                  <Toggle checked onChange={() => {}} label={t('set.throttle')} hint={t('set.throttleHint')} />
                </div>
              </Card>
            </Grid>
          </>
        )}

        {tab === 'tools' && (
          <Card>
            <CardHead title={t('ag.tools')} sub={t('ag.autonomyHint')} icon={<IcBolt size={17} />} />
            <Grid cols={2} gap={1.1}>
              {ALL_TOOLS_LIVE.map((tl) => (
                <label
                  key={tl}
                  className="tile"
                  style={{ cursor: 'pointer', padding: '1.1rem 1.3rem' }}
                  onClick={() => toggleTool(tl)}
                >
                  <Checkbox checked={tools.includes(tl)} onChange={() => toggleTool(tl)} />
                  <span className="mono" style={{ fontSize: '1.22rem' }}>
                    {tl}
                  </span>
                  {tl.endsWith('.write') && (
                    <span className="tile__end">
                      <Badge tone="warn" size="sm">
                        write
                      </Badge>
                    </span>
                  )}
                </label>
              ))}
            </Grid>
          </Card>
        )}

        {tab === 'trace' && (
          <Card>
            <CardHead title={t('ag.trace')} sub={t('ag.traceSub')} icon={<IcEye size={17} />} />
            <div className="trace">
              {(agent.trace || TRACE[lang] || TRACE.en).map((s, i) => (
                <div className="trace__step" key={i}>
                  <div className="trace__rail">
                    <span className="trace__node">{nf(i + 1)}</span>
                  </div>
                  <div className="trace__body">
                    <div className="trace__title">{loc(s.title, lang)}</div>
                    <div className="trace__detail">{loc(s.detail, lang)}</div>
                    {s.tool && <div className="trace__tool">{s.tool}</div>}
                  </div>
                </div>
              ))}
            </div>
          </Card>
        )}

        {tab === 'memory' && (
          <Card>
            <CardHead title={t('ag.memory')} icon={<IcSpark size={17} />} />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {(agent.memory || []).map((m, i) => (
                <div className="tile" key={i}>
                  <span className="tile__icon">
                    <IcSpark size={16} />
                  </span>
                  <span className="tile__text">
                    <span className="tile__title" style={{ whiteSpace: 'normal', fontWeight: 500 }}>
                      {m}
                    </span>
                  </span>
                </div>
              ))}
            </div>
          </Card>
        )}
      </div>
    </Drawer>
  )
}
