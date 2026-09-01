/* ACTIVITY LOG — humans, agents and the system in one stream.
   Filtering by actor KIND rather than by name is the useful cut:
   the question people bring to an audit log in an agentic product
   is "what did the software do on its own", not "what did Sara
   do". */
import { useState } from 'react'
import { useI18n, byId, loc } from '../i18n'
import { useDebounced } from '../api/hooks'
import { useActivity, useAgents, useTeam } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import { Avatar, Badge, Button, Card, SearchBox, Segmented, Stagger } from '../ui'

import { IcAgent, IcDownload, IcGear, IcList, IcTeam } from '../components/NavIcons'

const KIND_ICON = { agent: IcAgent, human: IcTeam, system: IcGear }

export default function Logs() {
  const { t, lang, ago, date, time } = useI18n()
  const [kind, setKind] = useState('all')
  const [q, setQ] = useState('')

  /* Debounced, because this searches a table the server scans — a request per
     keystroke would queue behind itself on a long log. */
  const search = useDebounced(q, 300)
  const query = useActivity({ kind, q: search, size: 100 })
  const agents = useAgents()
  const team = useTeam()

  const list = query.data?.items || []

  const who = (a) =>
    a.kind === 'agent'
      ? loc(byId(agents.data, a.actor)?.name, lang)
      : a.kind === 'human'
        ? loc(byId(team.data, a.actor)?.name, lang)
        : t('log.system')

  return (
    <div className="page">
      <PageHeader
        title={t('log.title')}
        sub={t('log.sub')}
        actions={
          <Button variant="ghost" icon={<IcDownload size={16} />}>
            {t('g.export')}
          </Button>
        }
      />

      <Stagger className="stack-v">
        <div className="toolbar" style={{ margin: 0 }}>
          <SearchBox value={q} onChange={setQ} placeholder={t('g.search')} />
          <Segmented
            size="sm"
            value={kind}
            onChange={setKind}
            options={[
              { value: 'all', label: t('g.all') },
              { value: 'agent', label: t('log.agent') },
              { value: 'human', label: t('log.human') },
              { value: 'system', label: t('log.system') },
            ]}
          />
        </div>

        <Card>
          <div className="feed">
            {list.map((a) => {
              const Icon = KIND_ICON[a.kind] ?? IcList
              const ag = a.kind === 'agent' ? byId(agents.data, a.actor) : null
              return (
                <div className="feed__item" key={a.id}>
                  <div className="feed__rail">
                    {ag ? (
                      <Avatar name={loc(ag.name, lang)} emoji={ag.emoji} tint={ag.tint} size={28} ring />
                    ) : (
                      <span className={`feed__dot feed__dot--${a.tone}`}>
                        <Icon size={13} />
                      </span>
                    )}
                  </div>
                  <div className="feed__body">
                    <div className="feed__text">
                      <b>{who(a)}</b> {loc(a.action, lang)}
                    </div>
                    <div className="feed__meta">
                      <Badge tone="neutral" size="sm">
                        {t(`log.${a.kind}`)}
                      </Badge>
                      <span className="mono">{a.target}</span>
                      <span>{date(a.at, { day: 'numeric', month: 'short' })}</span>
                      <span>{time(a.at)}</span>
                      <span>· {ago(a.at)}</span>
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
