/* ============================================================
   EMAIL DESIGNER — pictures and facts in, a sendable template out.

   The shape of the screen follows the shape of the job: what you
   are giving it on one side, what it made on the other. You add
   images, say what the email is for, and the agent writes the
   HTML around them. Then you look at it, change it if you want,
   and make it the house style.

   Two decisions worth naming:

   * THE PREVIEW IS A SANDBOXED IFRAME, and the HTML was already
     stripped of anything executable on the server. Two layers,
     because this document was written by a language model and
     will be edited by hand, and neither is a trustworthy author.

   * IMAGES ARE UPLOADED FIRST, not attached to the request. The
     model cannot see a picture; it can only be told a URL and
     what is in it. So the upload happens up front, the operator
     labels each one, and those labels are what the agent is
     actually designing around.
   ============================================================ */
import { useEffect, useRef, useState } from 'react'
import { loc, useI18n } from '../i18n'
import { api } from '../api/client'
import { useConfig } from '../api/config'
import { previewFill, tagsIn } from '../components/previewFill'
import { useTemplates } from '../api/resources'
import { invalidate } from '../api/hooks'
import PageHeader from '../layout/PageHeader'
import { Badge, Button, Card, CardHead, Field, Input, Modal, Tabs, Textarea } from '../ui'
import { IcCheckC, IcPlus, IcSpark, IcTrash, IcUpload, IcWarn, IcX } from '../components/NavIcons'

const MAX_MB = 4

export default function Designer({ onToast }) {
  const { t, lang, nf } = useI18n()
  const { ai, brand } = useConfig()

  const templates = useTemplates()
  const [assets, setAssets] = useState([])
  const [picked, setPicked] = useState([])

  const [brief, setBrief] = useState('')
  const [facts, setFacts] = useState('')
  /* Design references: a screenshot of a Pinterest board, a brand-guide PDF,
     an email you liked. These are LOOKED at, never embedded in the result. */
  const [refs, setRefs] = useState([])
  const [refNote, setRefNote] = useState('')
  const [busy, setBusy] = useState(false)

  const [draft, setDraft] = useState(null) // { html, subject, notes, issues }
  const [tab, setTab] = useState('preview')
  const [saving, setSaving] = useState(false)
  const [naming, setNaming] = useState(false)
  const [name, setName] = useState('')

  const file = useRef(null)

  const loadAssets = async () => {
    try {
      setAssets(await api.get('/assets'))
    } catch (err) {
      onToast?.(err.message)
    }
  }
  useEffect(() => {
    loadAssets()
  }, [])

  /* ---- upload ----
     Read as a data URI and post as JSON. Everything else in this panel is a
     JSON request with a bearer token, and an image small enough to survive
     Gmail is small enough to base64. */
  const upload = async (files, { reference = false } = {}) => {
    for (const f of Array.from(files || [])) {
      if (f.size > MAX_MB * 1024 * 1024) {
        onToast?.(t('des.tooBig', { mb: MAX_MB, name: f.name }))
        continue
      }
      try {
        const data = await new Promise((resolve, reject) => {
          const reader = new FileReader()
          reader.onload = () => resolve(reader.result)
          reader.onerror = reject
          reader.readAsDataURL(f)
        })
        const made = await api.post('/assets', {
          name: f.name, mime: f.type, data, reference,
        })
        if (reference) {
          setRefs((r) => [made, ...r])
        } else {
          setAssets((a) => [made, ...a])
          setPicked((p) => [...p, made.id])
        }
      } catch (err) {
        onToast?.(err.message || t('err.failed'))
      }
    }
  }

  /* What each picture IS, in the operator's words. This is the only thing the
     model knows about an image it cannot see, so it is worth a field. */
  const describe = async (id, note) => {
    setAssets((a) => a.map((x) => (x.id === id ? { ...x, note } : x)))
  }

  const generate = async () => {
    if (!brief.trim()) return
    setBusy(true)
    setDraft(null)
    try {
      const out = await api.post('/ai/template', {
        brief,
        facts,
        lang,
        assets: picked,
        palette: '',
        references: refs.map((r) => r.id),
        referenceNote: refNote,
      })
      setDraft(out)
      setTab('preview')
      // Said plainly rather than left as a silent no-op: a PDF is stored and
      // kept, but its pages cannot be shown to the model.
      if (out.pdfsNotRead > 0) onToast?.(t('des.pdfNotRead', { n: out.pdfsNotRead }))
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    } finally {
      setBusy(false)
    }
  }

  const save = async () => {
    setSaving(true)
    try {
      const made = await api.post('/templates', {
        name: { en: name || brief.slice(0, 40), fa: name || brief.slice(0, 40) },
        html: draft.html,
        subject: draft.subject,
        source: 'ai',
      })
      invalidate('/templates')
      setNaming(false)
      onToast?.(t('des.saved'))
      return made
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    } finally {
      setSaving(false)
    }
  }

  const list = templates.data || []

  return (
    <div className="page">
      <PageHeader title={t('nav.designer')} sub={t('des.sub')} />

      {!ai.configured && (
        <Card className="home__notice">
          <IcWarn size={18} />
          <div>
            <div className="strong">{t('home.noKey')}</div>
            <div className="faint">{t('des.noKeySub')}</div>
          </div>
        </Card>
      )}

      <div className="cols cols--narrow-wide">
        {/* ------------------------------------------------ what you give it */}
        <div className="stack-v">
          <Card>
            <CardHead title={t('des.images')} sub={t('des.imagesSub')} />

            <input
              ref={file}
              type="file"
              accept="image/png,image/jpeg,image/gif,image/webp"
              multiple
              hidden
              onChange={(e) => {
                upload(e.target.files)
                e.target.value = ''
              }}
            />
            <button className="dropzone" onClick={() => file.current?.click()}>
              <IcPlus size={18} />
              <span>{t('des.addImages')}</span>
              <span className="faint">{t('des.imageTypes', { mb: MAX_MB })}</span>
            </button>

            {assets.length > 0 && (
              <div className="assets">
                {assets.map((a) => {
                  const on = picked.includes(a.id)
                  return (
                    <div key={a.id} className={`asset${on ? ' asset--on' : ''}`}>
                      <button
                        className="asset__pick"
                        onClick={() =>
                          setPicked((p) => (on ? p.filter((x) => x !== a.id) : [...p, a.id]))
                        }
                        aria-pressed={on}
                      >
                        <img src={a.url} alt={a.name || ''} />
                        {on && (
                          <span className="asset__tick">
                            <IcCheckC size={14} />
                          </span>
                        )}
                      </button>
                      <input
                        className="asset__note"
                        value={a.note || ''}
                        placeholder={t('des.describe')}
                        onChange={(e) => describe(a.id, e.target.value)}
                        /* Saved on blur, not on every keystroke: this is a
                           caption someone types once, not a search field. */
                        onBlur={(e) =>
                          api.patch(`/assets/${a.id}`, { note: e.target.value }).catch(() => {})
                        }
                      />
                      <button
                        className="asset__del"
                        aria-label={t('g.delete')}
                        onClick={async () => {
                          try {
                            await api.del(`/assets/${a.id}`)
                            setAssets((x) => x.filter((y) => y.id !== a.id))
                            setPicked((p) => p.filter((x) => x !== a.id))
                          } catch (err) {
                            onToast?.(err.message)
                          }
                        }}
                      >
                        <IcTrash size={13} />
                      </button>
                    </div>
                  )
                })}
              </div>
            )}
          </Card>

          <Card>
            <CardHead title={t('des.reference')} sub={t('des.referenceSub')} />

            <div className="refbox">
              <label className="refbox__drop">
                <input
                  type="file"
                  accept="image/*,application/pdf"
                  multiple
                  hidden
                  onChange={(e) => {
                    upload(e.target.files, { reference: true })
                    e.target.value = ''
                  }}
                />
                <IcUpload size={16} />
                <span>{t('des.referenceDrop')}</span>
              </label>

              {refs.length > 0 && (
                <div className="refbox__list">
                  {refs.map((r) => (
                    <div key={r.id} className="refchip">
                      {r.mime === 'application/pdf' ? (
                        <span className="refchip__pdf">PDF</span>
                      ) : (
                        <img src={r.url} alt="" />
                      )}
                      <span className="refchip__name">{r.name}</span>
                      <button
                        aria-label={t('g.delete')}
                        onClick={async () => {
                          try {
                            await api.del(`/assets/${r.id}`)
                            setRefs((x) => x.filter((y) => y.id !== r.id))
                          } catch (err) {
                            onToast?.(err.message)
                          }
                        }}
                      >
                        <IcX size={12} />
                      </button>
                    </div>
                  ))}
                </div>
              )}

              <Textarea
                rows={2}
                value={refNote}
                placeholder={t('des.referenceNotePh')}
                onChange={(e) => setRefNote(e.target.value)}
              />
              <p className="refbox__note">{t('des.referenceHow')}</p>
            </div>
          </Card>

          <Card>
            <CardHead title={t('des.brief')} />
            <Field label={t('des.whatFor')} required>
              <Textarea
                rows={3}
                value={brief}
                placeholder={t('des.briefPh')}
                onChange={(e) => setBrief(e.target.value)}
              />
            </Field>
            <Field label={t('des.facts')} hint={t('des.factsHint')}>
              <Textarea
                rows={4}
                value={facts}
                placeholder={t('des.factsPh')}
                onChange={(e) => setFacts(e.target.value)}
              />
            </Field>
            <Button
              variant="primary"
              full
              icon={<IcSpark size={16} />}
              loading={busy}
              disabled={!brief.trim() || !ai.configured}
              onClick={generate}
            >
              {draft ? t('des.regenerate') : t('des.generate')}
            </Button>
          </Card>
        </div>

        {/* --------------------------------------------------- what it made */}
        <div className="stack-v">
          {!draft && !busy && (
            <Card className="des__empty">
              <IcSpark size={26} />
              <p>{t('des.emptyState')}</p>
            </Card>
          )}

          {busy && (
            <Card className="des__empty">
              <span className="askbox__spin" />
              <p>{t('des.working')}</p>
            </Card>
          )}

          {draft && (
            <Card pad={false} className="panel">
              <div className="panel__head">
                <span className="ucard__title">{draft.subject || t('des.result')}</span>
                <div className="row" style={{ gap: '0.8rem', marginInlineStart: 'auto' }}>
                  <Button size="sm" variant="ghost" onClick={() => setNaming(true)}>
                    {t('des.save')}
                  </Button>
                </div>
              </div>

              <Tabs
                tabs={[
                  { value: 'preview', label: t('des.preview') },
                  { value: 'code', label: 'HTML' },
                ]}
                value={tab}
                onChange={setTab}
              />

              {draft.notes && <p className="des__notes">{draft.notes}</p>}

              {/* Sandboxed, and the HTML was already stripped server-side. The
                  sandbox attribute is empty on purpose: no scripts, no forms,
                  no same-origin access. */}
              {tab === 'preview' ? (
                <>
                  {/* Filled, not raw. The preview's whole job is "what will
                      this look like when it lands", and {{content}} printed as
                      literal braces is the one thing no recipient will ever
                      see. What gets SAVED still has the holes — filling the
                      stored copy would turn a reusable frame into one email. */}
                  <iframe
                    className="des__frame"
                    title={t('des.preview')}
                    sandbox=""
                    srcDoc={previewFill(draft.html, { lang, brand: brand.name })}
                  />
                  <p className="des__previewNote">
                    {t('des.previewNote', { tags: tagsIn(draft.html).length })}
                  </p>
                </>
              ) : (
                <Textarea
                  className="des__code mono"
                  rows={18}
                  value={draft.html}
                  onChange={(e) => setDraft((d) => ({ ...d, html: e.target.value }))}
                />
              )}

              {draft.issues?.length > 0 && (
                <div className="des__issues">
                  {draft.issues.map((i) => (
                    <div key={i.id} className={`des__issue des__issue--${i.tone}`}>
                      <IcWarn size={14} />
                      {loc(i, lang)}
                    </div>
                  ))}
                </div>
              )}
            </Card>
          )}

          {/* ------------------------------------------------ saved templates */}
          {list.length > 0 && (
            <Card>
              <CardHead title={t('des.saved_')} sub={t('des.savedSub')} />
              <div className="stack-v">
                {list.map((tp) => (
                  <div key={tp.id} className="tpl">
                    <div className="tpl__text">
                      <span className="tpl__name">
                        {loc(tp.name, lang)}
                        {tp.isDefault && (
                          <Badge tone="good" size="sm">
                            {t('des.isDefault')}
                          </Badge>
                        )}
                        {tp.source === 'ai' && (
                          <Badge tone="info" size="sm">
                            AI
                          </Badge>
                        )}
                      </span>
                      <span className="tpl__sub">{tp.subject || t('des.noSubject')}</span>
                    </div>
                    <div className="row" style={{ gap: '0.6rem' }}>
                      <Button
                        size="sm"
                        variant="quiet"
                        disabled={!tp.hasHtml}
                        onClick={async () => {
                          try {
                            const got = await api.get(`/templates/${tp.id}/html`)
                            setDraft({
                              html: got.html,
                              subject: tp.subject,
                              notes: '',
                              issues: got.issues,
                            })
                            setTab('preview')
                          } catch (err) {
                            onToast?.(err.message)
                          }
                        }}
                      >
                        {t('des.open')}
                      </Button>
                      <Button
                        size="sm"
                        variant="ghost"
                        disabled={tp.isDefault || !tp.hasHtml}
                        onClick={async () => {
                          try {
                            await api.post(`/templates/${tp.id}/default`)
                            invalidate('/templates')
                            onToast?.(t('des.madeDefault'))
                          } catch (err) {
                            onToast?.(err.message)
                          }
                        }}
                      >
                        {t('des.useForAll')}
                      </Button>
                    </div>
                  </div>
                ))}
              </div>
            </Card>
          )}
        </div>
      </div>

      <Modal
        open={naming}
        onClose={() => setNaming(false)}
        width={44}
        title={t('des.save')}
        footer={
          <>
            <Button variant="quiet" onClick={() => setNaming(false)}>
              {t('g.cancel')}
            </Button>
            <Button variant="primary" loading={saving} onClick={save}>
              {t('g.save')}
            </Button>
          </>
        }
      >
        <Field label={t('des.templateName')} required>
          <Input
            value={name}
            placeholder={t('des.templateNamePh')}
            onChange={(e) => setName(e.target.value)}
          />
        </Field>
      </Modal>
    </div>
  )
}
