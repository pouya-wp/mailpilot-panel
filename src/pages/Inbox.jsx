/* ============================================================
   SMART INBOX

   Master–detail, and the detail leads with the AGENT'S DRAFT above
   the original message. That inversion is the whole product: the
   reader's job here is not to write a reply, it is to approve or
   correct one. Putting the draft second would make them read the
   incoming mail, compose a mental answer, and only then discover
   the machine had already written it.
   ============================================================ */
import { useMemo, useState } from 'react'
import { byId, loc, useI18n } from '../i18n'
import { useAgents, useInbox, useReply, useSyncReplies, useTeam } from '../api/resources'
import { api } from '../api/client'
import { invalidate } from '../api/hooks'
import { Async } from '../ui/state'
import PageHeader from '../layout/PageHeader'
import {
  Avatar,
  Badge,
  Button,
  Card,
  CardHead,
  EmptyState,
  Grid,
  Kpi,
  Menu,
  Segmented,
  Stagger,
  Tabs,
  Textarea,
} from '../ui'
import {
  IcAgent,
  IcCheckC,
  IcClock2,
  IcInbox,
  IcRefresh,
  IcReply,
  IcSend,
  IcSpark,
  IcTeam,
} from '../components/NavIcons'

const INTENT_TONE = {
  interested: 'good',
  question: 'info',
  objection: 'warn',
  unsubscribe: 'bad',
  ooo: 'neutral',
}

export default function Inbox({ onToast }) {
  const { t, lang, nf, pct, ago, time } = useI18n()
  const [filter, setFilter] = useState('needs')
  const [openId, setOpenId] = useState(null)
  const [draft, setDraft] = useState(null) // null = show the agent's own text

  /* The filter is a server round-trip: which threads are unhandled is the
     server's answer, and filtering a page of results client-side would only
     ever be filtering the page you already have. */
  const query = useInbox({ filter, size: 100 })
  const agents = useAgents()
  const [reply, replyState] = useReply()
  const [sync, syncing] = useSyncReplies()
  const team = useTeam()

  /* One place for "call it, report it, refresh". Three controls needed the
     same three lines and copying them is how one of them ends up silently
     swallowing its error. */
  const act = async (call, said) => {
    try {
      await call()
      onToast?.(said)
      invalidate('/inbox')
    } catch (err) {
      onToast?.(err.message)
    }
  }

  const list = query.data?.items || []
  const counts = query.data?.counts || { needs: 0, auto: 0, all: 0 }

  /* Fall back to the first row rather than pinning a selection that the
     current filter may not contain — switching to "auto-handled" must not
     leave the detail pane showing a thread that is no longer in the list. */
  const open = list.find((x) => x.id === openId) ?? list[0]
  const ag = open ? byId(agents.data, open.agent) : null
  const needs = counts.needs

  return (
    <div className="page">
      <PageHeader
        title={t('inbox.title')}
        sub={t('inbox.sub')}
        actions={
          /* This used to say "reset" and do nothing at all. It now does the
             one thing a person opening this screen wants: go and look. */
          <Button
            variant="ghost"
            icon={<IcRefresh size={16} />}
            loading={syncing.loading}
            onClick={async () => {
              try {
                const out = await sync()
                /* Bounces are reported too. They are the reason a list stays
                   clean, and silently removing addresses is the kind of thing
                   an operator should be told about rather than discover. */
                /* Three things can come back from a sync and each one is
                   worth saying: replies to read, addresses that no longer
                   exist, and people who asked to be left alone. The last two
                   change the list silently otherwise. */
                const bits = []
                if (out.added) bits.push(t('inbox.gotReplies', { n: out.added }))
                if (out.bounced) bits.push(t('inbox.gotBounces', { n: out.bounced }))
                if (out.optedOut) bits.push(t('inbox.gotOptOuts', { n: out.optedOut }))
                onToast?.(bits.length ? bits.join(' · ') : t('inbox.nothingNew'))
              } catch (err) {
                onToast?.(err.message)
              }
            }}
          >
            {t('inbox.check')}
          </Button>
        }
      />

      <Stagger className="stack-v">
        <div className="kpirow" style={{ margin: 0 }}>
          {/* Only what the inbox actually counts. The reply rate and the agent
              success rate that used to sit here were literals — 3.4% and 93.8%
              printed to every deployment, including ones with no threads at
              all. Rates belong to Analytics, where they are measured. */}
          <Kpi label={t('inbox.needsYou')} value={nf(needs)} icon={<IcInbox size={15} />} />
          <Kpi label={t('inbox.autoHandled')} value={nf(counts.auto || 0)} icon={<IcAgent size={15} />} />
          <Kpi label={t('inbox.allThreads')} value={nf(counts.all || 0)} />
          <Kpi
            label={t('inbox.handledShare')}
            value={counts.all ? pct((counts.auto / counts.all) * 100, 0) : '—'}
          />
        </div>

        <div className="inbox">
          {/* ---- list ---- */}
          <Card pad={false} style={{ padding: '0.8rem' }}>
            <div style={{ padding: '0.6rem 0.6rem 1rem' }}>
              <Segmented
                size="sm"
                value={filter}
                onChange={setFilter}
                options={[
                  { value: 'needs', label: t('inbox.needsYou') },
                  { value: 'auto', label: t('inbox.autoHandled') },
                  { value: 'all', label: t('inbox.all') },
                ]}
              />
            </div>

            {list.length === 0 ? (
              <EmptyState title={t('inbox.empty')} icon={<IcCheckC size={26} />} />
            ) : (
              list.map((th) => (
                <button
                  key={th.id}
                  className={`thread${th.id === open?.id ? ' thread--on' : ''}`}
                  onClick={() => {
                    setOpenId(th.id)
                    setDraft(null)
                  }}
                >
                  <Avatar name={loc(th.from, lang)} size={34} ring />
                  <span className="thread__body">
                    <span className="thread__top">
                      <span className="thread__from">{loc(th.from, lang)}</span>
                      <span className="thread__at">{ago(th.at)}</span>
                    </span>
                    <span className="thread__subject">{loc(th.subject, lang)}</span>
                    <span className="thread__preview">{loc(th.preview, lang)}</span>
                    <span className="thread__tags">
                      <Badge tone={INTENT_TONE[th.intent]} size="sm">
                        {t(`inbox.intent.${th.intent}`)}
                      </Badge>
                      {th.handled && (
                        <Badge tone="neutral" size="sm">
                          {t('inbox.autoHandled')}
                        </Badge>
                      )}
                    </span>
                  </span>
                </button>
              ))
            )}
          </Card>

          {/* ---- detail ---- */}
          {open ? (
            <div className="stack-v">
              <Card>
                <CardHead
                  title={loc(open.subject, lang)}
                  sub={`${loc(open.from, lang)} · ${open.email}`}
                  right={
                    <div className="row" style={{ gap: '0.8rem' }}>
                      <Badge tone={INTENT_TONE[open.intent]} dot>
                        {t(`inbox.intent.${open.intent}`)}
                      </Badge>
                      <span className="senti" title={t('inbox.sentiment')}>
                        <span className="senti__track">
                          <span className="senti__pin" style={{ insetInlineStart: `${open.sentiment * 100}%` }} />
                        </span>
                      </span>
                    </div>
                  }
                />

                {/* the agent's answer comes first */}
                <div className="msg msg--draft">
                  <div className="msg__label">
                    <IcSpark size={14} />
                    {t('inbox.draftReply')} · {loc(ag?.name, lang)}
                  </div>
                  {draft === null ? (
                    loc(open.draft, lang)
                  ) : (
                    <Textarea rows={5} value={draft} onChange={(e) => setDraft(e.target.value)} />
                  )}
                </div>

                <div className="row" style={{ gap: '0.8rem', marginTop: '1.4rem', flexWrap: 'wrap' }}>
                  <Button
                    variant="primary"
                    icon={<IcSend size={15} />}
                    loading={replyState.loading}
                    onClick={async () => {
                      await reply({
                        id: open.id,
                        send: true,
                        // only send an override when the reader actually edited it
                        text: draft === null ? undefined : { en: draft, fa: draft },
                      })
                      setDraft(null)
                      onToast?.(t('toast.launched'))
                    }}
                  >
                    {t('inbox.approve')}
                  </Button>
                  <Button
                    variant="ghost"
                    icon={<IcReply size={15} />}
                    onClick={() => setDraft(draft === null ? loc(open.draft, lang) : null)}
                  >
                    {t('inbox.rewrite')}
                  </Button>
                  {/* Both of these call routes that have existed all along.
                      The controls were rendered and translated and connected
                      to nothing, which reads to an operator as a broken app
                      rather than an unfinished one. */}
                  <Menu
                    trigger={
                      <Button variant="ghost" icon={<IcTeam size={15} />}>
                        {t('inbox.assign')}
                      </Button>
                    }
                    items={[
                      ...(team.data || []).map((m) => ({
                        id: m.id,
                        label: loc(m.name, lang) || m.email,
                        onClick: () => act(() => api.post(`/inbox/${open.id}/assign`,
                                                          { user_id: m.id }),
                                           t('inbox.assigned')),
                      })),
                      { divider: true },
                      {
                        id: 'none',
                        label: t('inbox.unassign'),
                        onClick: () => act(() => api.post(`/inbox/${open.id}/assign`,
                                                          { user_id: null }),
                                           t('inbox.unassigned')),
                      },
                    ]}
                  />
                  <Menu
                    trigger={
                      <Button variant="quiet" icon={<IcClock2 size={15} />}>
                        {t('inbox.snooze')}
                      </Button>
                    }
                    items={[4, 24, 72].map((h) => ({
                      id: `s${h}`,
                      label: t('inbox.snoozeFor', { h }),
                      onClick: () => act(() => api.post(`/inbox/${open.id}/snooze?hours=${h}`),
                                         t('inbox.snoozed', { h })),
                    }))}
                  />
                </div>
              </Card>

              <Card>
                <CardHead title={t('camp.content')} icon={<IcInbox size={17} />} />
                <div className="row" style={{ gap: '1.1rem', marginBottom: '1.2rem' }}>
                  <Avatar name={loc(open.from, lang)} size={36} ring />
                  <div style={{ flex: 1, minWidth: 0 }}>
                    <div className="strong" style={{ fontSize: '1.32rem' }}>
                      {loc(open.from, lang)}
                    </div>
                    <div className="faint mono" style={{ fontSize: '1.15rem' }}>
                      {open.email}
                    </div>
                  </div>
                  <span className="faint" style={{ fontSize: '1.15rem' }}>
                    {time(open.at)} · {ago(open.at)}
                  </span>
                </div>
                <div className="msg">{loc(open.preview, lang)}</div>
              </Card>
            </div>
          ) : (
            <Card>
              <EmptyState title={t('inbox.empty')} icon={<IcCheckC size={26} />} />
            </Card>
          )}
        </div>
      </Stagger>
    </div>
  )
}
