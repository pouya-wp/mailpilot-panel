/* ============================================================
   SEGMENTS — live audiences, and the builder that defines one.

   The builder has two doors on purpose. The natural-language box
   at the top is the one most people will use; the rule rows below
   it are what the sentence COMPILES INTO, shown rather than
   hidden. An audience definition decides who gets emailed, so the
   reader has to be able to check the machine's reading of their
   sentence before 25,000 people receive something.
   ============================================================ */
import { useState } from 'react'
import { loc, useI18n } from '../i18n'
import { useAskSegment, useCreateSegment, useSegments } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import { EmptyState } from '../ui'
import {
  Badge,
  Button,
  Card,
  CardHead,
  Delta,
  Divider,
  Grid,
  IconButton,
  Input,
  Modal,
  Progress,
  Segmented,
  Select,
  Stagger,
  Textarea,
} from '../ui'
import { Sparkline } from '../ui/charts'
import { IcMinus, IcPlus, IcRefresh, IcSegment, IcSpark, IcTrash, IcUpload } from '../components/NavIcons'

const FIELDS = {
  en: {
    orders: 'Order count',
    ltv: 'Lifetime value',
    lastOpen: 'Last open',
    plan: 'Plan',
    tag: 'Tag',
    country: 'Country',
    score: 'Engagement score',
  },
  fa: {
    orders: 'تعداد سفارش',
    ltv: 'ارزش طول عمر',
    lastOpen: 'آخرین بازشدن',
    plan: 'پلن',
    tag: 'برچسب',
    country: 'کشور',
    score: 'امتیاز تعامل',
  },
}
const OPS = {
  en: { eq: 'is', neq: 'is not', gte: 'at least', lte: 'at most', before: 'before', after: 'after', has: 'contains' },
  fa: { eq: 'برابر است با', neq: 'برابر نیست با', gte: 'حداقل', lte: 'حداکثر', before: 'پیش از', after: 'پس از', has: 'شامل' },
}

export default function Segments({ onToast, embedded }) {
  const { t, lang, nf, compact, pct } = useI18n()
  const query = useSegments()
  const [ask, asking] = useAskSegment()
  const [createSegment, creating] = useCreateSegment()

  const [builder, setBuilder] = useState(false)
  const [name, setName] = useState('')
  const [prompt, setPrompt] = useState('')
  const [match, setMatch] = useState('all')
  const [rules, setRules] = useState([{ id: 1, field: 'orders', op: 'gte', value: '2' }])
  const [preview, setPreview] = useState(null)

  const addRule = () => setRules((rs) => [...rs, { id: Date.now(), field: 'score', op: 'gte', value: '50' }])
  const setRule = (id, patch) => setRules((rs) => rs.map((r) => (r.id === id ? { ...r, ...patch } : r)))
  const dropRule = (id) => setRules((rs) => rs.filter((r) => r.id !== id))

  /* The sentence is compiled by the API, and the RULES come back — not a
     saved segment. An audience definition decides who gets emailed, so the
     reader sees the machine's reading of their sentence, and how many people
     it actually matches, before anything is created. */
  const compile = async () => {
    try {
      const out = await ask({ prompt })
      // Guarded, though the endpoint does promise these. A shape error here
      // surfaces to the reader as "Cannot read properties of undefined",
      // which tells them nothing they can act on.
      setRules((out.rules || []).map((r, i) => ({ id: i + 1, ...r })))
      setMatch(out.match || 'all')
      setPreview(out.preview || null)
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    }
  }

  return (
    <div className="page">
      {!embedded && (
      <PageHeader
        title={t('seg.title')}
        sub={t('seg.sub')}
        actions={
          <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => setBuilder(true)}>
            {t('seg.new')}
          </Button>
        }
      />
      )}

      <Stagger>
        <Grid min={30} gap={1.5}>
          {(query.data || []).length === 0 && !query.loading && (
            <EmptyState
              icon={<IcSegment size={26} />}
              title={t('seg.emptyTitle')}
              hint={t('seg.emptyHint')}
            />
          )}
          {(query.data || []).map((s) => (
            <Card key={s.id} tilt>
              <div className="row" style={{ gap: '1.2rem', marginBottom: '1.4rem' }}>
                <span
                  className="agentcard__face"
                  style={{ background: s.tint, width: '4.6rem', height: '4.6rem', fontSize: '2.2rem' }}
                >
                  {s.emoji}
                </span>
                <div style={{ flex: 1, minWidth: 0 }}>
                  <div className="agentcard__name" style={{ fontSize: '1.75rem' }}>
                    {loc(s.name, lang)}
                  </div>
                  <div className="row" style={{ gap: '0.6rem', marginTop: '0.4rem' }}>
                    {s.live && (
                      <Badge tone="live" dot size="sm">
                        {t('g.active')}
                      </Badge>
                    )}
                    <span className="faint" style={{ fontSize: '1.1rem' }}>
                      {nf(s.rules.length)} {t('auto.steps')}
                    </span>
                  </div>
                </div>
              </div>

              <div className="row" style={{ justifyContent: 'space-between', alignItems: 'flex-end' }}>
                <div>
                  <div
                    style={{
                      fontFamily: 'var(--font-display)',
                      fontSize: '3rem',
                      fontWeight: 600,
                      color: '#f0f5fb',
                      letterSpacing: '-0.025em',
                      lineHeight: 1,
                    }}
                  >
                    {compact(s.size)}
                  </div>
                  <div className="faint" style={{ fontSize: '1.15rem', marginTop: '0.3rem' }}>
                    {t('m.contacts')}
                  </div>
                </div>
                <Delta value={s.growth} />
              </div>

              <Divider />

              <div className="row" style={{ justifyContent: 'space-between' }}>
                <span className="muted" style={{ fontSize: '1.22rem' }}>
                  {t('m.openRate')} <b className="strong">{pct(s.openRate, 1)}</b>
                </span>
                <Button size="sm" variant="ghost" onClick={() => setBuilder(true)}>
                  {t('g.edit')}
                </Button>
              </div>
            </Card>
          ))}
        </Grid>
      </Stagger>

      <Modal
        open={builder}
        onClose={() => setBuilder(false)}
        width={72}
        title={t('seg.new')}
        sub={t('seg.builder')}
        footer={
          <>
            <Button variant="quiet" onClick={() => setBuilder(false)}>
              {t('g.cancel')}
            </Button>
            <Button
              variant="primary"
              loading={creating.loading}
              onClick={async () => {
                try {
                  await createSegment({
                    name: name || prompt.slice(0, 40) || 'Segment',
                    match,
                    rules: rules.map(({ field, op, value }) => ({ field, op, value })),
                  })
                  setBuilder(false)
                  onToast?.(t('toast.saved'))
                } catch (err) {
                  onToast?.(err.message || t('err.failed'))
                }
              }}
            >
              {t('g.create')}
            </Button>
          </>
        }
      >
        <div className="stack-v">
          <Card>
            <CardHead title={t('seg.aiSuggest')} icon={<IcSpark size={17} />} />
            <Input
              value={name}
              onChange={(e) => setName(e.target.value)}
              placeholder={t('g.name')}
              style={{ marginBottom: '1rem' }}
            />
            <Textarea rows={3} value={prompt} onChange={(e) => setPrompt(e.target.value)} placeholder={t('seg.aiPlaceholder')} />
            <Button
              variant="primary"
              icon={<IcSpark size={15} />}
              loading={asking.loading}
              onClick={compile}
              style={{ marginTop: '1.2rem' }}
            >
              {asking.loading ? t('comp.thinking') : t('seg.builder')}
            </Button>
          </Card>

          <Card>
            <CardHead
              title={t('seg.builder')}
              right={
                <Segmented
                  size="sm"
                  value={match}
                  onChange={setMatch}
                  options={[
                    { value: 'all', label: t('seg.matchAll') },
                    { value: 'any', label: t('seg.matchAny') },
                    /* Saying "everyone" out loud. A group with no rules used
                       to mean the whole contact list silently, which is how a
                       group somebody forgot to finish became a send to every
                       address on file. */
                    { value: 'everyone', label: t('seg.matchEveryone') },
                  ]}
                />
              }
            />

            {match === 'everyone' && (
              <p className="seg__everyone">{t('seg.everyoneNote')}</p>
            )}

            {match !== 'everyone' && rules.map((r, i) => (
              <div key={r.id}>
                {i > 0 && <div className="rule__join">{match === 'all' ? 'AND' : 'OR'}</div>}
                <div className="rule">
                  <Select
                    value={r.field}
                    onChange={(v) => setRule(r.id, { field: v })}
                    options={Object.entries(FIELDS[lang] ?? FIELDS.en).map(([value, label]) => ({ value, label }))}
                  />
                  <Select
                    value={r.op}
                    onChange={(v) => setRule(r.id, { op: v })}
                    options={Object.entries(OPS[lang] ?? OPS.en).map(([value, label]) => ({ value, label }))}
                  />
                  <Input value={r.value} onChange={(e) => setRule(r.id, { value: e.target.value })} />
                  <IconButton label={t('g.delete')} onClick={() => dropRule(r.id)} disabled={rules.length === 1}>
                    <IcMinus size={15} />
                  </IconButton>
                </div>
              </div>
            ))}

            {match !== 'everyone' && (
              <Button variant="quiet" icon={<IcPlus size={15} />} onClick={addRule} style={{ marginTop: '1.2rem' }}>
                {t('seg.addRule')}
              </Button>
            )}
          </Card>

          <Card>
            <CardHead
              title={t('seg.preview')}
              right={
                <Badge tone="live" dot>
                  {preview ? compact(preview.matched) : '—'}
                </Badge>
              }
            />
            <Progress
              value={preview ? (preview.matched / Math.max(preview.total, 1)) * 100 : 0}
              tone="blue"
              label={t('seg.size')}
              right={preview ? pct((preview.matched / Math.max(preview.total, 1)) * 100, 1) : '—'}
            />
            <p className="faint" style={{ fontSize: '1.2rem', marginTop: '1rem' }}>
              {lang === 'fa'
                ? 'این بخش زنده است و با تغییر داده‌ها خودش را دوباره محاسبه می‌کند.'
                : 'This segment is live and recalculates itself as data changes.'}
            </p>
          </Card>
        </div>
      </Modal>
    </div>
  )
}
