/* ============================================================
   HOME — the agent's desk.

   This screen replaced the dashboard, the composer, the agent
   roster, the automation canvas and the recommendation feed. All
   of those asked the operator to hold a model of the system in
   their head: pick a goal, pick a tone, pick a length, pick a
   segment, pick a send time, then read a wall of numbers to find
   out whether it worked.

   What is here instead is one input and a short answer. The
   operator says what they want; the agent decides the audience,
   writes the mail, and hands back something with exactly two
   buttons on it. The numbers are three figures, not thirty,
   because a person who has delegated the work does not need a
   cockpit — they need to know it is running and to be told when
   it is not.

   Conversations ARE kept, and the history panel reopens them.
   That reversed an earlier decision: the fear was that a chat log
   invites people to treat this as a chatbot, but in use the
   opposite happened — people lost the thread of a campaign they
   were half-way through describing. The durable record of what
   was actually SENT still lives in Campaigns, where it is
   auditable; this is just the working conversation.
   ============================================================ */
import { useCallback, useEffect, useRef, useState } from 'react'
import { loc, useI18n } from '../i18n'
import { api } from '../api/client'
import { useAuth } from '../api/auth'
import { useConfig } from '../api/config'
import {
  useAsk,
  useConfirmAction,
  useContactStats,
  useCreateCampaign,
  useOverview,
  useSegments,
  useSendCampaign,
} from '../api/resources'
import { navigate } from '../router'
import CampaignWizard from '../components/CampaignWizard'
import { Button, Card, Select } from '../ui'
import { Skeleton } from '../ui/state'
import Num from '../anim/Num'
import {
  IcArrowUp,
  IcCheckC,
  IcClock2,
  IcGlobe,
  IcList,
  IcPlus,
  IcSend,
  IcSpark,
  IcTrash,
  IcWarn,
  IcX,
} from '../components/NavIcons'

/* Openers, not features. Each one is a whole request that the agent can act on
   end to end — the point is to show that a sentence is the interface. */
const STARTERS = [
  { id: 'promo', en: 'Write and send a spring promotion to my best customers',
    fa: 'یک پیشنهاد بهاری برای بهترین مشتریانم بنویس و بفرست' },
  { id: 'winback', en: 'Win back everyone who has not opened anything in 3 months',
    fa: 'هرکسی که سه ماه چیزی باز نکرده را برگردان' },
  { id: 'report', en: 'How did last month go?', fa: 'ماه گذشته چطور بود؟' },
]

/* ============================================================
   PAST CONVERSATIONS

   A drawer rather than a panel in the page, and it closes on
   Escape, on the backdrop, and on picking something — three ways
   out, because it is a detour and not a destination.

   Each row shows when it was and how long it ran. That is enough
   to recognise the conversation you are looking for; a preview of
   the first message sounds helpful and in practice is a wall of
   near-identical openings.
   ============================================================ */
function ChatHistory({ open, chats, chatId, onClose, onOpen, onDelete, onNew, t, nf, ago }) {
  useEffect(() => {
    if (!open) return undefined
    const onKey = (e) => e.key === 'Escape' && onClose()
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open, onClose])

  if (!open) return null

  return (
    <div className="hist" role="dialog" aria-modal="true" aria-label={t('home.history')}>
      <button className="hist__scrim" aria-label={t('g.close')} onClick={onClose} />

      <aside className="hist__panel">
        <header className="hist__head">
          <h2>{t('home.history')}</h2>
          <button className="hist__x" onClick={onClose} aria-label={t('g.close')}>
            <IcX size={16} />
          </button>
        </header>

        <button className="hist__new" onClick={onNew}>
          <IcPlus size={14} />
          {t('home.newChat')}
        </button>

        <div className="hist__list">
          {chats.length === 0 ? (
            <p className="hist__empty">{t('home.noHistory')}</p>
          ) : (
            chats.map((c) => (
              <div key={c.id} className={`hist__row${c.id === chatId ? ' is-on' : ''}`}>
                <button className="hist__open" onClick={() => onOpen(c.id)}>
                  <span className="hist__title">{c.title || t('home.untitled')}</span>
                  <span className="hist__meta">
                    {ago(c.updatedAt)} · {t('home.turns', { n: nf(c.turns) })}
                  </span>
                </button>
                <button
                  className="hist__del"
                  aria-label={t('g.delete')}
                  onClick={() => onDelete(c.id)}
                >
                  <IcTrash size={13} />
                </button>
              </div>
            ))
          )}
        </div>
      </aside>
    </div>
  )
}


/* The tool results are shaped per tool; the sentence only ever needs numbers,
   and a missing one reads better as 0 than as "undefined". */
function resultCounts(result) {
  return {
    n: result?.added ?? result?.total ?? result?.queued ?? result?.sent?.length ?? 0,
    skipped: result?.alreadyThere ?? 0,
    name: result?.name || result?.email || '',
  }
}

/* `datetime-local` wants a local wall-clock string, not an ISO instant — and
   `toISOString()` returns UTC, which sets the minimum to the wrong moment for
   anyone east or west of Greenwich. This is the reader's own clock, trimmed to
   the minute the input works in. */
function localNow() {
  const now = new Date()
  now.setMinutes(now.getMinutes() - now.getTimezoneOffset())
  return now.toISOString().slice(0, 16)
}


export default function Home({ onToast }) {
  const { t, lang, nf, pct, compact, ago } = useI18n()
  const { agent, ai, has, setupComplete } = useConfig()
  const { can } = useAuth()
  const [ask, asking] = useAsk()
  const [confirmAction, confirming] = useConfirmAction()
  const [createCampaign, creating] = useCreateCampaign()
  const [send, sending] = useSendCampaign()

  const [message, setMessage] = useState('')
  const [wizard, setWizard] = useState(false)
  /* When to send. Fetched once a draft exists so the button can name the slot
     it is offering instead of saying "optimal" and meaning nothing. */
  const [bestTime, setBestTime] = useState(null)
  const [pickedAt, setPickedAt] = useState('')
  const [showPicker, setShowPicker] = useState(false)
  /* True once the text needs a second line. Drives the two-row layout. */
  const [tall, setTall] = useState(false)
  const [answer, setAnswer] = useState(null)
  /* The audience for the draft on screen. Seeded from the agent's choice, and
     changeable — the agent gets it right most of the time and is not asked to
     be right every time. */
  const [audienceId, setAudienceId] = useState('')
  const groups = useSegments()
  const [history, setHistory] = useState([])
  const box = useRef(null)

  /* The conversation this exchange belongs to. Null until the first message,
     so opening the screen and leaving does not create an empty one. */
  const [chatId, setChatId] = useState(null)
  const [chats, setChats] = useState([])
  const [showHistory, setShowHistory] = useState(false)

  const loadChats = useCallback(async () => {
    try {
      const out = await api.get('/chats?size=40')
      setChats(out.items || [])
    } catch {
      /* the panel works without its history; a failure here is not worth a
         toast in front of someone who was trying to write an email */
    }
  }, [])

  useEffect(() => {
    loadChats()
  }, [loadChats])

  const overview = useOverview(30)
  const contacts = useContactStats()
  const tot = overview.data?.totals || {}

  /* "Has this account ever sent anything?" is the question that decides whether
     the strip below is a report or a checklist. */
  const started = (tot.sent || 0) > 0

  const steps = [
    {
      id: 'ai',
      done: ai.configured,
      title: t('home.stepAi'),
      hint: t('home.stepAiHint'),
      cta: t('home.openSetup'),
      go: can('settings.write') ? () => navigate('setup') : null,
    },
    {
      id: 'audience',
      done: (contacts.data?.total || 0) > 0,
      title: t('home.stepAudience'),
      hint: t('home.stepAudienceHint'),
      cta: t('home.stepAudienceCta'),
      go: has('audience') ? () => navigate('audience') : null,
    },
    {
      id: 'send',
      done: false,
      title: t('home.stepSend'),
      hint: t('home.stepSendHint'),
      cta: null,
      go: null,
    },
  ]

  useEffect(() => {
    box.current?.focus()
  }, [])

  useEffect(() => {
    if (!answer?.draft) return
    let live = true
    api
      .get('/campaigns/best-time')
      .then((slot) => live && setBestTime(slot))
      .catch(() => {})
    return () => {
      live = false
    }
  }, [answer?.draft])

  /* Grow the field to its content and decide which shape the box is in.

     Reset to `auto` first: scrollHeight only shrinks back if the element is
     not already holding the taller height open. One line of slack is allowed
     before switching to the two-row layout, so a single wrapped word does not
     make the whole box jump. */
  useEffect(() => {
    const el = box.current
    if (!el) return
    const cs = getComputedStyle(el)
    const line = parseFloat(cs.lineHeight) || 20
    const padding = parseFloat(cs.paddingTop) + parseFloat(cs.paddingBottom)
    /* The height of exactly one line, measured rather than guessed. A
       multiplier of the line height alone lands within a pixel or two of this,
       which is close enough to tip an EMPTY box into the two-row shape. */
    const oneLine = line + padding

    el.style.height = 'auto'
    const content = el.scrollHeight
    el.style.height = `${Math.min(content, line * 8 + padding)}px`
    setTall(content > oneLine + line * 0.5)
  }, [message])

  const run = async (text) => {
    const said = (text ?? message).trim()
    if (!said || asking.loading) return
    setMessage('')
    setAnswer(null)
    try {
      const out = await ask({ message: said, lang, history })
      setAnswer(out)
      setAudienceId(out.audience?.id || '')
      /* Only the last few turns are replayed to the model, and only so a
         follow-up like "make it shorter" has something to refer to. The full
         conversation is on the server. */
      setHistory((h) => [...h, { role: 'user', text: said },
                         { role: 'agent', text: out.reply }].slice(-6))

      /* Written after the answer lands, both turns together: saving the
         question first would leave a half-conversation behind every failure. */
      try {
        let id = chatId
        if (!id) {
          id = (await api.post('/chats')).id
          setChatId(id)
        }
        await api.post(`/chats/${id}/turns`, { role: 'user', text: said })
        await api.post(`/chats/${id}/turns`, {
          role: 'agent',
          text: out.reply || '',
          meta: { intent: out.intent, searched: out.searched },
        })
        loadChats()
      } catch {
        /* the exchange happened and is on screen; failing to file it is not a
           reason to tell the reader their message did not work */
      }
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    }
  }

  /* Reopen a past conversation: its turns become the replay context, and the
     last answer is shown so the screen picks up where it left off. */
  const openChat = async (id) => {
    try {
      const out = await api.get(`/chats/${id}`)
      setChatId(id)
      setShowHistory(false)
      setAnswer(null)
      setHistory((out.turns || []).map((x) => ({ role: x.role, text: x.text })).slice(-6))
      const lastAgent = [...(out.turns || [])].reverse().find((x) => x.role === 'agent')
      if (lastAgent) {
        setAnswer({ ok: true, reply: lastAgent.text, intent: lastAgent.meta?.intent || 'other',
                    draft: null, audience: null, steps: [], needs: [], citations: [] })
      }
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    }
  }

  const startNew = () => {
    setChatId(null)
    setHistory([])
    setAnswer(null)
    setMessage('')
    setShowHistory(false)
    box.current?.focus()
  }

  /* Approve = create the campaign the agent drafted and send it, in one go.
     The two calls stay separate on the server so a refused send still leaves
     the writing saved; from here it is one decision. */
  /* `mode` is one of now | optimal | schedule. The campaign is created first
     either way: a refused SEND then leaves the writing saved as a draft
     instead of throwing it away, which is why these stay two calls. */
  const approve = async (mode = 'now', at = null) => {
    if (!answer?.draft) return
    /* Checked BEFORE anything is written. This used to create the campaign and
       then fail the send, which left a draft nobody asked for and an error
       that arrived too late to act on. */
    if (!audienceId) {
      onToast?.(t('home.pickAudienceFirst'))
      return
    }
    const line = answer.draft.subject
    try {
      const made = await createCampaign({
        name: { en: line, fa: line },
        subject: { en: line, fa: line },
        body: { en: answer.draft.body.join('\n\n'), fa: answer.draft.body.join('\n\n') },
        type: 'broadcast',
        segment: audienceId,
      })
      await send({ id: made.id, mode, scheduled_for: at })
      onToast?.(mode === 'now' ? t('toast.launched') : t('toast.scheduled'))
      navigate(`campaigns/${made.id}`)
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    }
  }

  /* "Tuesday 10:00" beats "optimal". If the account has no history to learn
     from, the label says it is a starting point rather than a finding. */
  const slotLabel = () => {
    if (!bestTime) return ''
    const when = new Date(bestTime.at)
    const day = new Intl.DateTimeFormat(lang === 'fa' ? 'fa-IR' : 'en-US', {
      weekday: 'long',
    }).format(when)
    const time = String(bestTime.hour).padStart(2, '0') + ':00'
    return `${day} ${time}`
  }

  const busy = asking.loading
  const working = creating.loading || sending.loading

  /* Approving is a separate round trip on purpose: the signature the server
     minted travels back unchanged, so what runs is what was on the screen. */
  async function runPending(item, index) {
    try {
      await confirmAction({ tool: item.tool, args: item.args, sig: item.sig })
      onToast?.(t('act.done'))
      dropPending(index)
    } catch (err) {
      onToast?.(err.message)
    }
  }

  function dropPending(index) {
    setAnswer((prev) =>
      prev ? { ...prev, pending: prev.pending.filter((_, i) => i !== index) } : prev
    )
  }

  const removeChat = async (id) => {
    try {
      await api.del(`/chats/${id}`)
      if (id === chatId) startNew()
      loadChats()
    } catch (err) {
      onToast?.(err.message)
    }
  }

  return (
    <div className="page home">
      {/* Past conversations live in a drawer, not on the page. They used to sit
          in a bar above the greeting — the first thing you saw on opening your
          agent was a list of things you had already said, and expanding it
          pushed the input box down. The trigger is one icon, out of the flow. */}
      <button
        className="home__histBtn"
        onClick={() => setShowHistory(true)}
        aria-label={t('home.history')}
        title={t('home.history')}
      >
        <IcList size={16} />
        {chats.length > 0 && <span className="home__histN">{nf(chats.length)}</span>}
      </button>

      {(chatId || history.length > 0) && (
        <button className="home__newBtn" onClick={startNew}>
          <IcPlus size={14} />
          {t('home.newChat')}
        </button>
      )}

      <ChatHistory
        open={showHistory}
        chats={chats}
        chatId={chatId}
        onClose={() => setShowHistory(false)}
        onOpen={(id) => {
          openChat(id)
          setShowHistory(false)
        }}
        onDelete={removeChat}
        onNew={() => {
          startNew()
          setShowHistory(false)
        }}
        t={t}
        nf={nf}
        ago={ago}
      />

      {/* ---- the ask ---- */}
      <div className="home__hero">
        <h1 className="home__greet">
          {t('home.greet', { name: agent.name })}
        </h1>
        <p className="home__sub">{agent.role || t('home.subFallback')}</p>

        <form
          className={`askbox${busy ? ' askbox--busy' : ''}${tall ? ' askbox--tall' : ''}`}
          onSubmit={(e) => {
            e.preventDefault()
            run()
          }}
        >
          <textarea
            ref={box}
            className="askbox__input"
            rows={1}
            value={message}
            placeholder={t('home.placeholder')}
            onChange={(e) => setMessage(e.target.value)}
            onKeyDown={(e) => {
              // Enter sends; Shift+Enter is a newline. This is a command box
              // that happens to wrap, not a document.
              if (e.key === 'Enter' && !e.shiftKey) {
                e.preventDefault()
                run()
              }
            }}
          />
          {/* Present only once there is something to send. An empty box with a
              live send button reads as a form to fill in; an empty box with
              nothing but a caret reads as an invitation. */}
          {(message.trim() || busy) && (
            <button
              type="submit"
              className="askbox__send"
              disabled={busy || !message.trim()}
              aria-label={t('home.send')}
            >
              {busy ? <span className="askbox__spin" aria-hidden="true" /> : <IcArrowUp size={18} />}
            </button>
          )}
        </form>

        {/* The guided run. Under the ask box rather than beside it: the box
            is the fast path for someone who knows what they want, and this
            is the one for someone who knows the goal but not which five
            screens it is spread across. */}
        <div className="home__runrow">
          <Button variant="primary" icon={<IcSpark size={16} />} onClick={() => setWizard(true)}>
            {t('wiz.open')}
          </Button>
        </div>

        {!answer && !busy && (
          <div className="home__starters">
            {STARTERS.map((s) => (
              <button key={s.id} className="starter" onClick={() => run(loc(s, lang))}>
                {loc(s, lang)}
              </button>
            ))}
          </div>
        )}
      </div>

      {/* ---- setup nudge: only the person who can fix it is told ---- */}
      {!ai.configured && (
        <Card className="home__notice">
          <IcWarn size={18} />
          <div>
            <div className="strong">{t('home.noKey')}</div>
            <div className="faint">{t('home.noKeySub')}</div>
          </div>
          <Button size="sm" variant="ghost" onClick={() => navigate('setup')}>
            {t('home.openSetup')}
          </Button>
        </Card>
      )}

      {busy && (
        <Card className="home__answer">
          <Skeleton rows={3} />
        </Card>
      )}

      {/* ---- what the agent said ---- */}
      {answer && !busy && (
        <Card className="home__answer">
          <div className="answer__reply">{answer.reply}</div>

          {/* Only when the agent actually went and looked. An answer about the
              outside world should show where it read it — and it is also how
              the reader can tell an assumption from a finding. */}
          {answer.citations?.length > 0 && (
            <div className="answer__sources">
              <span className="answer__sourcesLabel">
                <IcGlobe size={13} /> {t('home.sources')}
              </span>
              {answer.citations.map((c, i) => (
                <a key={i} href={c.url} target="_blank" rel="noopener noreferrer" className="source">
                  {c.title || c.url}
                </a>
              ))}
            </div>
          )}

          {/* Things the agent has ALREADY done. Reversible, internal work
              runs without asking — this is the receipt, not a request. */}
          {answer.did?.length > 0 && (
            <ul className="answer__did">
              {answer.did.map((item, i) => (
                <li key={i} className={item.ok ? '' : 'answer__did--failed'}>
                  {item.ok ? <IcCheckC size={14} /> : <IcWarn size={14} />}
                  {item.ok ? t(`act.${item.tool}`, resultCounts(item.result)) : item.error}
                </li>
              ))}
            </ul>
          )}

          {/* Things it wants to do that reach real people. The agent asking is
              never enough; this button is. */}
          {answer.pending?.length > 0 && (
            <div className="answer__pending">
              {answer.pending.map((item, i) => (
                <div key={i} className="pending">
                  <div className="pending__what">
                    <IcSend size={14} />
                    <span>{item.says}</span>
                  </div>
                  <div className="pending__row">
                    <Button
                      variant="primary"
                      loading={confirming.loading}
                      onClick={() => runPending(item, i)}
                    >
                      {t('act.approve')}
                    </Button>
                    <Button variant="quiet" onClick={() => dropPending(i)}>
                      {t('act.discard')}
                    </Button>
                  </div>
                </div>
              ))}
            </div>
          )}

          {answer.steps?.length > 0 && (
            <ul className="answer__steps">
              {answer.steps.map((step, i) => (
                <li key={i}>
                  <IcCheckC size={14} />
                  {step}
                </li>
              ))}
            </ul>
          )}

          {/* A question is asked ONLY when the agent genuinely could not
              proceed. Everything it could assume, it assumed. */}
          {answer.needs?.length > 0 && (
            <div className="answer__needs">
              {answer.needs.map((need, i) => (
                <button key={i} className="starter" onClick={() => setMessage(need)}>
                  {need}
                </button>
              ))}
            </div>
          )}

          {answer.draft && (
            <div className="draft">
              <div className="draft__head">
                <span className="draft__subject">{answer.draft.subject}</span>
                {answer.audience && (
                  <span className="draft__to">
                    {t('home.to')} <b>{loc(answer.audience.name, lang)}</b>
                    {' · '}
                    {nf(answer.audience.size)}
                  </span>
                )}
              </div>
              {/* Who it goes to, as a control rather than a caption. The agent
                  fills it in when it can; on a fresh account there is nothing
                  for it to choose, and this is where the operator says so
                  instead of finding out from a failed send. */}
              <div className="draft__aud">
                <span>{t('home.to')}</span>
                <Select
                  value={audienceId}
                  onChange={setAudienceId}
                  options={[
                    { value: '', label: t('home.pickAudience') },
                    ...(groups.data || []).map((g) => ({
                      value: g.id,
                      label: `${loc(g.name, lang)} · ${nf(g.size)}`,
                    })),
                  ]}
                />
                {!audienceId && (
                  <span className="draft__audHint">{t('home.noGroupsYet')}</span>
                )}
              </div>

              <div className="draft__body">
                {answer.draft.body.map((p, i) => (
                  <p key={i}>{p}</p>
                ))}
              </div>
              {answer.draft.cta && <span className="draft__cta">{answer.draft.cta}</span>}

              {bestTime && (
                <p className="draft__why">
                  {bestTime.basis === 'history'
                    ? t('home.whyHistory', {
                        rate: `${bestTime.openRate}%`,
                        n: bestTime.campaigns,
                      })
                    : t('home.whyDefault')}
                </p>
              )}

              {showPicker && (
                <div className="draft__picker">
                  {/* `min` is the browser's own guard, and the disabled
                      button is the one that matters — a time in the past is
                      not "later", it is DUE, and the sender would pick the
                      campaign up within the minute. The server refuses it too;
                      this is so the mistake cannot be made in the first place
                      rather than explained afterwards. */}
                  <input
                    type="datetime-local"
                    className="input__el"
                    value={pickedAt}
                    min={localNow()}
                    onChange={(e) => setPickedAt(e.target.value)}
                  />
                  <Button
                    variant="primary"
                    loading={working}
                    disabled={!pickedAt || new Date(pickedAt) <= new Date()}
                    onClick={() => approve('schedule', new Date(pickedAt).toISOString())}
                  >
                    {t('home.scheduleIt')}
                  </Button>
                </div>
              )}

              <div className="draft__actions">
                {/* The recommendation leads, because waiting for the hour
                    an audience actually reads is the whole reason to know it. */}
                {bestTime && (
                  <Button
                    variant="primary"
                    icon={<IcClock2 size={15} />}
                    loading={working}
                    onClick={() => approve('optimal')}
                  >
                    {t('home.sendAt', { when: slotLabel() })}
                  </Button>
                )}
                <Button
                  variant={bestTime ? 'ghost' : 'primary'}
                  icon={<IcSend size={15} />}
                  loading={working}
                  onClick={() => approve('now')}
                >
                  {t('home.approve')}
                </Button>
                <Button variant="quiet" onClick={() => setShowPicker((v) => !v)}>
                  {t('home.pickTime')}
                </Button>
                <Button variant="quiet" onClick={() => setMessage(t('home.reviseHint'))}>
                  {t('home.revise')}
                </Button>
              </div>
            </div>
          )}
        </Card>
      )}

      {/* ---- three numbers, not thirty — once there are numbers ---- */}
      {has('campaigns') && started && (
        <div className="home__figures">
          <Figure label={t('m.sent')} value={<Num value={tot.sent || 0} from={0} format={compact} />} />
          <Figure label={t('m.openRate')} value={<Num value={tot.openRate || 0} from={0} format={(v) => pct(v, 1)} />} />
          <Figure label={t('m.clickRate')} value={<Num value={tot.clickRate || 0} from={0} format={(v) => pct(v, 1)} />} />
        </div>
      )}

      {has('campaigns') && !started && !overview.loading && (
        <div className="firstrun">
          <span className="firstrun__label">{t('home.setupLeft')}</span>
          <div className="firstrun__steps">
            {steps.map((step) => (
              <div key={step.id} className={`step${step.done ? ' step--done' : ''}`}>
                <span className="step__mark">
                  {step.done ? <IcCheckC size={14} /> : <i />}
                </span>
                <span className="step__text">
                  <span className="step__title">{step.title}</span>
                  <span className="step__hint">{step.hint}</span>
                </span>
                {!step.done && step.go && (
                  <Button size="sm" variant="ghost" onClick={step.go}>
                    {step.cta}
                  </Button>
                )}
              </div>
            ))}
          </div>
        </div>
      )}

      <CampaignWizard open={wizard} onClose={() => setWizard(false)} onToast={onToast} />
    </div>
  )
}

function Figure({ label, value }) {
  return (
    <div className="figure">
      <span className="figure__label">{label}</span>
      <span className="figure__value">{value}</span>
    </div>
  )
}
