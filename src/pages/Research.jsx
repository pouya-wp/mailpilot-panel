/* ============================================================
   RESEARCH — who to reach, by place and by kind.

   Two inputs, as asked for: a region and a category. The agent
   searches the open web and comes back with a brief and a list of
   candidates.

   WHY THIS IS A REVIEW QUEUE.

   The obvious build is "type a city, get five hundred addresses,
   press send". It is also the build that ends the product for
   whoever uses it, and the reasons are worth having on the screen
   rather than buried in a docstring:

   * a model INVENTS addresses when it has none — well-formed,
     plausible, belonging to nobody. Those hard-bounce, and a
     bounce rate over about 2% gets a sender filtered. Every later
     email, including to customers who asked for it, lands in spam.
   * a published address is not consent. `info@` on a shop's site
     is not permission to add that shop to a marketing list.
   * the account doing the sending is the customer's own Gmail,
     and Google closes those.

   So every lead carries the URL it was read from, anything without
   a citation is dropped server-side, and nothing reaches the
   sending list until a person selects it and says yes.
   ============================================================ */
import { useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../api/client'
import { invalidate, useApi } from '../api/hooks'
import { useConfig } from '../api/config'
import { navigate } from '../router'
import { Async } from '../ui/state'
import {
  Badge,
  Button,
  Card,
  CardHead,
  EmptyState,
  Field,
  Input,
  Pagination,
  Segmented,
  Table,
} from '../ui'
import { IcGlobe, IcPlus, IcSearch, IcTeam, IcTrash, IcWarn } from '../components/NavIcons'

/* Mirrors prospect.MAX_PER_RUN. Past it a search stops finding real
   businesses and starts inventing them, and an invented address is a
   bounce against the customer's own Gmail. */
const FIND_CEILING = 40

export default function Research({ onToast }) {
  const { t, nf, lang } = useI18n()
  const { ai } = useConfig()

  const [region, setRegion] = useState('')
  const [category, setCategory] = useState('')
  const [count, setCount] = useState(20)
  const [running, setRunning] = useState(false)
  const [lastRun, setLastRun] = useState(null)

  const [status, setStatus] = useState('new')
  const [page, setPage] = useState(1)
  const [picked, setPicked] = useState([])
  const [working, setWorking] = useState(false)
  /* Where the last batch landed, so the reader can walk straight to it
     instead of going to look for thirty new rows in the contact list. */
  const [landed, setLanded] = useState(null)

  const leads = useApi(`/research/leads?status=${status}&page=${page}&size=50`)
  const counts = leads.data?.counts || {}
  const rows = leads.data?.items || []

  const ready = region.trim() && category.trim()

  const run = async () => {
    if (!ready) return
    setRunning(true)
    try {
      const out = await api.post('/research/run', { region, category, lang, count })
      setLastRun(out)
      setStatus('new')
      setPage(1)
      invalidate('/research/leads')
      onToast?.(t('res.found', { n: out.found, e: out.withEmail }))
    } catch (err) {
      onToast?.(err.message)
    } finally {
      setRunning(false)
    }
  }

  const act = async (what) => {
    if (!picked.length) return
    setWorking(true)
    try {
      const out = await api.post(`/research/leads/${what}`, { ids: picked })
      if (what !== 'accept') {
        onToast?.(t('res.dismissed', { n: out.dismissed }))
      } else if (out.group) {
        /* Name the group they went into. "30 added" on its own leaves the
           reader holding thirty addresses with no idea where they landed. */
        onToast?.(t('res.acceptedInto', { n: out.added, tag: out.group }))
        setLanded({ name: out.group, id: out.groupId })
      } else {
        onToast?.(t('res.accepted', { n: out.added, skip: out.alreadyThere + out.noAddress }))
      }
      setPicked([])
      invalidate('/research/leads')
      invalidate('/contacts')
      invalidate('/segments')
    } catch (err) {
      onToast?.(err.message)
    } finally {
      setWorking(false)
    }
  }

  return (
    <div className="stack-v">
      <Card>
        <CardHead title={t('res.title')} sub={t('res.sub')} icon={<IcSearch size={17} />} />

        {!ai.configured && <p className="res__warn">{t('res.noKey')}</p>}
        {ai.configured && !ai.search && <p className="res__warn">{t('res.noSearch')}</p>}

        <div className="setup__grid">
          <Field label={t('res.region')} hint={t('res.regionHint')}>
            <Input
              value={region}
              placeholder={t('res.regionPh')}
              onChange={(e) => setRegion(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && ready && run()}
            />
          </Field>
          <Field label={t('res.category')} hint={t('res.categoryHint')}>
            <Input
              value={category}
              placeholder={t('res.categoryPh')}
              onChange={(e) => setCategory(e.target.value)}
              onKeyDown={(e) => e.key === 'Enter' && ready && run()}
            />
          </Field>
          {/* Same ceiling as the server's, which clamps regardless — this only
              stops the reader typing a number that would be silently reduced. */}
          <Field label={t('res.count')} hint={t('res.countHint', { max: nf(FIND_CEILING) })}>
            <Input
              type="number"
              min={1}
              max={FIND_CEILING}
              value={count}
              onChange={(e) => setCount(Math.max(1, Math.min(FIND_CEILING, Number(e.target.value) || 1)))}
              onKeyDown={(e) => e.key === 'Enter' && ready && run()}
            />
          </Field>
        </div>

        <Button
          variant="primary"
          icon={<IcGlobe size={15} />}
          loading={running}
          disabled={!ready || !ai.configured}
          onClick={run}
        >
          {t('res.go')}
        </Button>

        {/* Said on the screen, not only in the code. Whoever presses the
            button is the person who carries the consequence. */}
        <p className="res__rule">
          <IcWarn size={14} /> {t('res.rule')}
        </p>
      </Card>

      {lastRun && (
        <Card>
          <CardHead title={t('res.brief')} />
          <p className="res__brief">{lastRun.brief}</p>
          {lastRun.angles?.length > 0 && (
            <ul className="res__angles">
              {lastRun.angles.map((a, i) => <li key={i}>{a}</li>)}
            </ul>
          )}
          <p className="res__counts">
            {t('res.summary', {
              n: lastRun.found,
              e: lastRun.withEmail,
              d: lastRun.droppedWithoutSource || 0,
            })}
          </p>
        </Card>
      )}

      {landed && (
        <Card>
          <div className="row" style={{ gap: '1.2rem', flexWrap: 'wrap', alignItems: 'center' }}>
            <span className="tile__icon"><IcTeam size={17} /></span>
            <div style={{ flex: 1, minWidth: '18rem' }}>
              <div className="strong">{landed.name}</div>
              <div className="faint" style={{ fontSize: '1.18rem' }}>{t('res.groupHint')}</div>
            </div>
            <Button size="sm" variant="primary" onClick={() => navigate('audience?tab=groups')}>
              {t('res.showGroup')}
            </Button>
          </div>
        </Card>
      )}

      <Card pad={false} style={{ padding: '1.4rem 1.8rem' }}>
        <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap', marginBottom: '1.2rem' }}>
          <Segmented
            size="sm"
            value={status}
            onChange={(v) => { setStatus(v); setPage(1); setPicked([]) }}
            options={[
              { value: 'new', label: `${t('res.toReview')} · ${nf(counts.new || 0)}` },
              { value: 'accepted', label: `${t('res.accepted0')} · ${nf(counts.accepted || 0)}` },
              { value: 'dismissed', label: `${t('res.dismissed0')} · ${nf(counts.dismissed || 0)}` },
            ]}
          />
          {picked.length > 0 && (
            <>
              <span className="muted" style={{ fontSize: '1.24rem' }}>
                {t('g.selected', { n: nf(picked.length) })}
              </span>
              <Button size="sm" variant="primary" icon={<IcPlus size={14} />}
                      loading={working} onClick={() => act('accept')}>
                {t('res.accept')}
              </Button>
              <Button size="sm" variant="quiet" icon={<IcTrash size={14} />}
                      loading={working} onClick={() => act('dismiss')}>
                {t('res.dismiss')}
              </Button>
            </>
          )}
        </div>

        <Async query={leads}>
          {rows.length === 0 ? (
            <EmptyState title={t('res.empty')} hint={t('res.emptyHint')} />
          ) : (
            <Table
              columns={[
                { key: 'who', label: t('res.who'),
                  render: (r) => (
                    <div className="tname__text">
                      <span>{r.name}</span>
                      <span className="tname__sub">{[r.kind, r.region].filter(Boolean).join(' · ')}</span>
                    </div>
                  ) },
                { key: 'email', label: t('res.email'),
                  render: (r) => r.email
                    ? <span className="mono">{r.email}</span>
                    : <Badge tone="neutral">{t('res.noAddress')}</Badge> },
                { key: 'src', label: t('res.source'),
                  /* The citation, clickable. A lead you cannot check is a
                     lead you cannot trust, and this is how you check it. */
                  render: (r) => r.source
                    ? <a className="res__src" href={r.source} target="_blank" rel="noopener noreferrer">
                        {new URL(r.source).hostname.replace(/^www\./, '')}
                      </a>
                    : '—' },
                { key: 'note', label: t('res.why'),
                  render: (r) => <span className="res__note">{r.note || '—'}</span> },
              ]}
              rows={rows}
              keyFn={(r) => r.id}
              selectable={status === 'new'}
              selected={picked}
              onSelect={setPicked}
            />
          )}
        </Async>

        {leads.data?.pages > 1 && (
          <Pagination page={page} pages={leads.data.pages} total={leads.data.total}
                      onChange={setPage} />
        )}
      </Card>
    </div>
  )
}
