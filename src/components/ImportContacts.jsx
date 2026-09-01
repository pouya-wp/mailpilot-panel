/* ============================================================
   IMPORTING A CONTACT LIST.

   Three steps, and the middle one is the whole point.

     pick    the file they already have — .xlsx or .csv
     check   what the agent decided each column is
     import

   The check step exists because the mapping is a GUESS. It is a
   good guess, made by a model that can read "Correo" and
   "نشانی رایانامه" and can also see that the column full of
   things with @ in them is the email column whatever it is
   called. But a guess about which column holds an email address
   should be confirmed by a person before it reaches twenty
   thousand rows, so the sample is shown alongside it and every
   field can be reassigned by hand.
   ============================================================ */
import { useRef, useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../api/client'
import { invalidate } from '../api/hooks'
import { Badge, Button, Modal, Select } from '../ui'
import { IcCheckC, IcSpark, IcUpload, IcWarn } from './NavIcons'

const MAX_MB = 8

export default function ImportContacts({ open, onClose, onToast }) {
  const { t, nf } = useI18n()
  const file = useRef(null)

  const [stage, setStage] = useState('pick') // pick | check | done
  const [busy, setBusy] = useState(false)
  const [payload, setPayload] = useState(null) // { data, filename }
  const [analysis, setAnalysis] = useState(null)
  const [mapping, setMapping] = useState({})
  const [result, setResult] = useState(null)

  const reset = () => {
    setStage('pick')
    setPayload(null)
    setAnalysis(null)
    setMapping({})
    setResult(null)
    setBusy(false)
  }

  const close = () => {
    reset()
    onClose?.()
  }

  const choose = async (f) => {
    if (!f) return
    if (f.size > MAX_MB * 1024 * 1024) {
      onToast?.(t('imp.tooBig', { mb: MAX_MB }))
      return
    }
    setBusy(true)
    try {
      const data = await new Promise((resolve, reject) => {
        const reader = new FileReader()
        reader.onload = () => resolve(reader.result)
        reader.onerror = reject
        reader.readAsDataURL(f)
      })
      const out = await api.post('/contacts/import/analyse', { data, filename: f.name })
      setPayload({ data, filename: f.name })
      setAnalysis(out)
      setMapping(out.mapping || {})
      setStage('check')
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    } finally {
      setBusy(false)
    }
  }

  const run = async () => {
    setBusy(true)
    try {
      const out = await api.post('/contacts/import', { ...payload, mapping })
      setResult(out)
      setStage('done')
      invalidate('/contacts')
      invalidate('/segments')
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    } finally {
      setBusy(false)
    }
  }

  /* Every column, plus "not used" — so a wrong guess can be cleared, not just
     pointed somewhere else. */
  const columnOptions = [
    { value: '', label: t('imp.notUsed') },
    ...(analysis?.headers || []).map((h) => ({ value: h, label: h })),
  ]

  return (
    <Modal
      open={open}
      onClose={close}
      width={64}
      title={t('ct.importCsv')}
      footer={
        stage === 'check' ? (
          <>
            <Button variant="quiet" onClick={reset}>
              {t('imp.chooseAnother')}
            </Button>
            <Button
              variant="primary"
              loading={busy}
              disabled={!mapping.email}
              onClick={run}
            >
              {t('imp.importN', { n: nf(analysis?.rowCount || 0) })}
            </Button>
          </>
        ) : (
          <Button variant="quiet" onClick={close}>
            {stage === 'done' ? t('g.close') : t('g.cancel')}
          </Button>
        )
      }
    >
      {/* ---------------------------------------------------------- pick */}
      {stage === 'pick' && (
        <>
          <input
            ref={file}
            type="file"
            accept=".csv,.xlsx,text/csv,application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
            hidden
            onChange={(e) => {
              choose(e.target.files?.[0])
              e.target.value = ''
            }}
          />
          <button className="dropzone" disabled={busy} onClick={() => file.current?.click()}>
            {busy ? <span className="askbox__spin" /> : <IcUpload size={18} />}
            <span>{busy ? t('imp.reading') : t('imp.pick')}</span>
            <span className="faint">{t('imp.formats', { mb: MAX_MB })}</span>
          </button>
          <p className="faint" style={{ fontSize: '1.18rem', marginTop: '1.4rem' }}>
            {t('imp.pickHint')}
          </p>
        </>
      )}

      {/* --------------------------------------------------------- check */}
      {stage === 'check' && analysis && (
        <>
          <div className="row" style={{ gap: '0.8rem', marginBottom: '1.4rem', flexWrap: 'wrap' }}>
            <Badge tone="info">{t('imp.rowsFound', { n: nf(analysis.rowCount) })}</Badge>
            {analysis.source === 'ai' ? (
              <Badge tone="good">
                <IcSpark size={13} /> {t('imp.mappedByAgent')}
              </Badge>
            ) : (
              <Badge tone="warn">{t('imp.mappedByName')}</Badge>
            )}
          </div>

          {analysis.notes && <p className="imp__notes">{analysis.notes}</p>}

          <div className="imp__map">
            {Object.entries(analysis.fields || {}).map(([field, description]) => (
              <div key={field} className="imp__row">
                <div className="imp__field">
                  <span className="imp__fieldName">
                    {t(`imp.field.${field}`)}
                    {field === 'email' && <span className="field2__req">*</span>}
                  </span>
                  <span className="imp__fieldWhat">{description}</span>
                </div>
                <Select
                  value={mapping[field] || ''}
                  onChange={(v) =>
                    setMapping((m) => {
                      const next = { ...m }
                      if (v) next[field] = v
                      else delete next[field]
                      return next
                    })
                  }
                  options={columnOptions}
                />
              </div>
            ))}
          </div>

          {!mapping.email && (
            <p className="imp__warn">
              <IcWarn size={14} /> {t('imp.needEmail')}
            </p>
          )}

          {/* The sample is what makes the mapping checkable: the operator reads
              across a row and sees whether the columns landed where they say. */}
          <div className="imp__sample">
            <table>
              <thead>
                <tr>
                  {analysis.headers.map((h) => (
                    <th key={h}>{h}</th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {analysis.sample.map((row, i) => (
                  <tr key={i}>
                    {analysis.headers.map((h) => (
                      <td key={h}>{row[h]}</td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </>
      )}

      {/* ---------------------------------------------------------- done */}
      {stage === 'done' && result && (
        <div className="imp__done">
          <IcCheckC size={26} />
          <p className="imp__doneLine">
            {t('imp.created', { n: nf(result.created) })}
            {result.updated > 0 && ` · ${t('imp.updated', { n: nf(result.updated) })}`}
          </p>
          {result.skipped_suppressed > 0 && (
            <p className="faint">{t('imp.skipped', { n: nf(result.skipped_suppressed) })}</p>
          )}
          {result.error_count > 0 && (
            <p className="imp__warn">
              <IcWarn size={14} /> {t('imp.rowErrors', { n: nf(result.error_count) })}
            </p>
          )}
        </div>
      )}
    </Modal>
  )
}
