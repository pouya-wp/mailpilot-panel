/* ============================================================
   BRAND BRAIN

   Everything the agents read before they write. Kept as one page
   rather than buried in settings, because it is the highest-
   leverage screen in the product: the difference between drafts
   that sound like the company and drafts that sound like a model
   is entirely decided here.
   ============================================================ */
import { useEffect, useState } from 'react'
import { useI18n, loc } from '../i18n'
import { useConfig } from '../api/config'
import { api } from '../api/client'
import { invalidate } from '../api/hooks'
import { useKnowledge, useUpdateVoice } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardHead,
  Divider,
  Field,
  Grid,
  IconButton,
  Input,
  Modal,
  Progress,
  Segmented,
  Select,
  Slider,
  Stagger,
  Stagger as _S,
  Textarea,
  Toggle,
} from '../ui'

import {
  IcBook,
  IcBrain,
  IcCheckC,
  IcGlobe,
  IcLayers,
  IcMinus,
  IcPlug,
  IcPlus,
  IcRefresh,
  IcSpark,
  IcUpload,
} from '../components/NavIcons'

const SOURCE_ICON = { web: IcGlobe, file: IcBook, app: IcPlug, internal: IcLayers }

const VOICE_AXES = {
  en: [
    { id: 'formal', left: 'Casual', right: 'Formal', value: 38 },
    { id: 'warm', left: 'Neutral', right: 'Warm', value: 72 },
    { id: 'brief', left: 'Detailed', right: 'Brief', value: 64 },
    { id: 'bold', left: 'Understated', right: 'Bold', value: 45 },
  ],
  fa: [
    { id: 'formal', left: 'خودمانی', right: 'رسمی', value: 38 },
    { id: 'warm', left: 'خنثی', right: 'صمیمی', value: 72 },
    { id: 'brief', left: 'مفصل', right: 'کوتاه', value: 64 },
    { id: 'bold', left: 'آرام', right: 'جسور', value: 45 },
  ],
}

export default function Knowledge({ onToast, embedded }) {
  const { t, lang, nf, compact } = useI18n()
  const { agent } = useConfig()
  const voiceAxes = agent.voiceAxes !== false
  const query = useKnowledge()
  const [saveVoice] = useUpdateVoice()
  const sources = query.data?.sources || []

  /* The voice sliders and the banned list are EDITED here, so they are local
     state seeded from the server rather than read straight from the query —
     otherwise every keystroke would be reverted by the next refetch. */
  const [axes, setAxes] = useState(VOICE_AXES[lang] ?? VOICE_AXES.en)
  const [banned, setBanned] = useState([])
  const [adding, setAdding] = useState(false)

  useEffect(() => {
    const voice = query.data?.voice
    if (!voice) return
    const labels = VOICE_AXES[lang] ?? VOICE_AXES.en
    // the server stores the values; the labels are interface strings
    setAxes(labels.map((a) => ({ ...a, value: voice.axes?.find((x) => x.id === a.id)?.value ?? a.value })))
    setBanned(voice.banned || [])
  }, [query.data, lang])
  const [word, setWord] = useState('')
  const [voice, setVoice] = useState('')

  const totalChunks = query.data?.chunks ?? sources.reduce((s, k) => s + k.chunks, 0)

  return (
    <div className="page">
      {!embedded && (
      <PageHeader
        title={t('kb.title')}
        sub={t('kb.sub')}
        actions={
          <>
            {/* "Indexing" used to sit here as a button. Nothing indexes —
                sources are stored and quoted, not embedded — so it promised a
                job that does not exist. Removed rather than wired to a lie. */}
            <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => setAdding(true)}>
              {t('kb.addSource')}
            </Button>
          </>
        }
      />
      )}

      <Stagger className="cols cols--wide-narrow">
        <div className="stack-v">
          {/* ---- voice ---- */}
          <Card>
            <CardHead title={t('kb.voice')} sub={t('kb.voiceSub')} icon={<IcSpark size={17} />} />
            {/* A deployment can switch the sliders off entirely. When it has,
                the free-text below is the whole of the voice — and the numbers
                stop being sent to the model, not merely stop being drawn. */}
            <div
              style={{ display: 'flex', flexDirection: 'column', gap: '1.8rem' }}
              hidden={!voiceAxes}
            >
              {axes.map((a) => (
                <div key={a.id}>
                  <div className="row" style={{ justifyContent: 'space-between', marginBottom: '0.5rem' }}>
                    <span className="muted" style={{ fontSize: '1.22rem' }}>
                      {a.left}
                    </span>
                    <span className="muted" style={{ fontSize: '1.22rem' }}>
                      {a.right}
                    </span>
                  </div>
                  <Slider
                    value={a.value}
                    onChange={(v) => setAxes((xs) => xs.map((x) => (x.id === a.id ? { ...x, value: v } : x)))}
                  />
                </div>
              ))}
            </div>

            {voiceAxes && <Divider />}

            <Field label={t('kb.examplesHint')}>
              <Textarea
                rows={4}
                value={voice}
                onChange={(e) => setVoice(e.target.value)}
                placeholder={
                  lang === 'fa'
                    ? 'ما همیشه دوم‌شخص می‌نویسیم، از اصطلاحات فنی پرهیز می‌کنیم و هیچ‌وقت به مخاطب فشار نمی‌آوریم…'
                    : 'We always write in second person, avoid jargon, and never pressure the reader…'
                }
              />
            </Field>
          </Card>

          {/* ---- sources ---- */}
          <Card>
            <CardHead
              title={t('kb.sources')}
              icon={<IcLayers size={17} />}
              right={
                <Badge tone="neutral">
                  {compact(totalChunks)} {t('kb.chunks')}
                </Badge>
              }
            />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1rem' }}>
              {sources.map((s) => {
                const Icon = SOURCE_ICON[s.type] ?? IcBook
                return (
                  <div className="tile" key={s.id}>
                    <span className="tile__icon">
                      <Icon size={17} />
                    </span>
                    <span className="tile__text">
                      <span className="tile__title ellip">{loc(s.name, lang)}</span>
                      <span className="tile__sub">
                        {nf(s.chunks)} {t('kb.chunks')}
                      </span>
                    </span>
                    <span className="tile__end">
                      {s.status === 'indexing' ? (
                        <Badge tone="live" dot>
                          {t('kb.indexing')}
                        </Badge>
                      ) : (
                        <Badge tone="good" dot>
                          {t('kb.indexed')}
                        </Badge>
                      )}
                    </span>
                  </div>
                )
              })}
            </div>

            <Button
              variant="quiet"
              icon={<IcUpload size={15} />}
              style={{ marginTop: '1.2rem' }}
              onClick={() => setAdding(true)}
            >
              {t('kb.addSource')}
            </Button>
          </Card>
        </div>

        {/* ---- side column ---- */}
        <div className="stack-v">
          <Card>
            <CardHead title={t('kb.banned')} sub={t('kb.bannedHint')} icon={<IcMinus size={17} />} />
            <div className="row" style={{ gap: '0.6rem', flexWrap: 'wrap', marginBottom: '1.2rem' }}>
              {banned.map((w) => (
                <span className="skillchip" key={w} style={{ display: 'inline-flex', alignItems: 'center', gap: '0.6rem' }}>
                  {w}
                  <button
                    onClick={() => setBanned((bs) => bs.filter((x) => x !== w))}
                    style={{ color: 'var(--tx-4)', display: 'grid', placeItems: 'center' }}
                    aria-label={t('g.delete')}
                  >
                    <IcMinus size={11} />
                  </button>
                </span>
              ))}
            </div>
            <form
              className="row"
              style={{ gap: '0.8rem' }}
              onSubmit={(e) => {
                e.preventDefault()
                if (!word.trim()) return
                setBanned((bs) => [...bs, word.trim()])
                setWord('')
              }}
            >
              <Input value={word} onChange={(e) => setWord(e.target.value)} placeholder={t('kb.banned')} />
              <Button variant="ghost" type="submit" icon={<IcPlus size={15} />} />
            </form>
          </Card>

          <Card>
            <CardHead title={t('kb.indexed')} icon={<IcBrain size={17} />} />
            <Progress value={totalChunks} max={8000} tone="blue" label={t('kb.chunks')} right={compact(totalChunks)} />
            <div className="hr" />
            <div style={{ display: 'flex', flexDirection: 'column', gap: '1.2rem' }}>
              <Toggle checked onChange={() => {}} label={lang === 'fa' ? 'به‌روزرسانی خودکار منابع وب' : 'Auto-refresh web sources'} />
              <Toggle checked onChange={() => {}} label={lang === 'fa' ? 'یادگیری از کمپین‌های گذشته' : 'Learn from past campaigns'} />
              <Toggle checked={false} onChange={() => {}} label={lang === 'fa' ? 'استفاده از پاسخ‌های مشتریان' : 'Use customer replies'} />
            </div>
            <Button
              variant="primary"
              full
              icon={<IcCheckC size={15} />}
              onClick={async () => {
                try {
                  await saveVoice({ axes: axes.map(({ id, value }) => ({ id, value })), banned, notes: voice })
                  onToast?.(t('toast.saved'))
                } catch (err) {
                  onToast?.(err.message || t('err.failed'))
                }
              }}
              style={{ marginTop: '1.8rem' }}
            >
              {t('g.save')}
            </Button>
          </Card>
        </div>
      </Stagger>
      {adding && (
        <AddSource onClose={() => setAdding(false)} onToast={onToast} />
      )}
    </div>
  )
}


/* ============================================================
   A SOURCE THE AGENT MAY QUOTE

   Deliberately small. This is a NAME and a KIND, not an upload:
   nothing is parsed, chunked or embedded, and pretending
   otherwise is what the "Indexing" button next to it used to do.
   What it buys is that the agent knows this document exists and
   can say so instead of inventing an answer.
   ============================================================ */
function AddSource({ onClose, onToast }) {
  const { t } = useI18n()
  const [name, setName] = useState('')
  const [type, setType] = useState('file')
  const [busy, setBusy] = useState(false)

  const save = async () => {
    if (!name.trim()) return
    setBusy(true)
    try {
      await api.post('/knowledge/sources', { name: name.trim(), type })
      onToast?.(t('kb.sourceAdded'))
      invalidate('/knowledge')
      onClose()
    } catch (err) {
      onToast?.(err.message)
    } finally {
      setBusy(false)
    }
  }

  return (
    <Modal
      open
      onClose={onClose}
      title={t('kb.addSource')}
      sub={t('kb.addSourceSub')}
      footer={
        <>
          <Button variant="quiet" onClick={onClose}>
            {t('g.cancel')}
          </Button>
          <Button variant="primary" loading={busy} disabled={!name.trim()} onClick={save}>
            {t('g.save')}
          </Button>
        </>
      }
    >
      <div className="stack-v">
        <Field label={t('kb.sourceName')} required>
          <Input
            autoFocus
            value={name}
            placeholder={t('kb.sourceNamePh')}
            onChange={(e) => setName(e.target.value)}
            onKeyDown={(e) => e.key === 'Enter' && name.trim() && save()}
          />
        </Field>
        <Field label={t('kb.sourceType')}>
          <Select
            value={type}
            onChange={setType}
            options={[
              { value: 'file', label: t('kb.typeFile') },
              { value: 'url', label: t('kb.typeUrl') },
              { value: 'note', label: t('kb.typeNote') },
            ]}
          />
        </Field>
      </div>
    </Modal>
  )
}
