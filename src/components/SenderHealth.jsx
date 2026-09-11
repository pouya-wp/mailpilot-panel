/* ============================================================
   SENDER HEALTH

   Whether this account is safe to send from, and what to do
   about it if not.

   THE SCORE IS NOT THE POINT. A number on its own — "74" — is
   not something anyone can act on, and a status light without
   reasons is a shrug with a colour. So the reasons are the body
   of this card and the score is a detail in the corner.

   UNKNOWN IS A REAL STATE, SHOWN AS ONE. Authentication used to
   be a tick or a cross, which meant a domain nobody had checked
   looked like a domain that had failed — and, after the old
   "verify" button, like one that had passed. Three states, and
   the middle one says so plainly.

   NOT ENOUGH DATA IS ALSO A REAL STATE. Two bounces out of three
   sends is three sends, not a 67% bounce rate, and a bar chart
   would present it as the latter. Below the floor the card says
   what it does not know.
   ============================================================ */
import { useState } from 'react'
import { useI18n } from '../i18n'
import { api } from '../api/client'
import { useApi } from '../api/hooks'
import { Badge, Button, Card, CardHead } from '../ui'
import { IcCheckC, IcRefresh, IcShield, IcWarn, IcX } from './NavIcons'

const TONE = { HEALTHY: 'good', WARNING: 'warn', CRITICAL: 'bad' }
const LABEL = { HEALTHY: 'sh.healthy', WARNING: 'sh.warning', CRITICAL: 'sh.critical' }

/* pass / fail / unknown, each with its own mark. The unknown one is
   deliberately not a cross: "we could not check" is not "this is broken". */
const AUTH_MARK = {
  pass: { icon: IcCheckC, tone: 'good', label: 'sh.pass' },
  fail: { icon: IcX, tone: 'bad', label: 'sh.fail' },
  unknown: { icon: IcWarn, tone: 'neutral', label: 'sh.unknown' },
}

export default function SenderHealth({ onToast }) {
  const { t, nf, pct } = useI18n()
  const query = useApi('/sender-health')
  const [checking, setChecking] = useState(false)

  const h = query.data
  if (!h) return null

  const recheck = async () => {
    setChecking(true)
    try {
      await api.post('/sender-health/recheck')
      query.reload?.()
    } catch (err) {
      onToast?.(err.message || t('err.failed'))
    } finally {
      setChecking(false)
    }
  }

  const sig = h.signals || {}
  const thin = !h.enoughData

  return (
    <Card>
      <CardHead
        title={t('sh.title')}
        sub={t('sh.sub')}
        icon={<IcShield size={17} />}
        right={
          <div className="row" style={{ gap: '0.8rem' }}>
            <Badge tone={TONE[h.status] || 'neutral'} dot>
              {t(LABEL[h.status] || 'sh.unknown')}
            </Badge>
            <Button size="sm" variant="ghost" icon={<IcRefresh size={14} />}
                    loading={checking} onClick={recheck}>
              {checking ? t('sh.checking') : t('sh.recheck')}
            </Button>
          </div>
        }
      />

      {/* ---- authentication, in three states ---- */}
      <div className="shealth__auth">
        {['spf', 'dkim', 'dmarc'].map((key) => {
          const state = h.authentication?.[key] || 'unknown'
          const mark = AUTH_MARK[state] || AUTH_MARK.unknown
          const Icon = mark.icon
          return (
            <div className={`shealth__authRow shealth__authRow--${state}`} key={key}>
              <Icon size={15} />
              <span className="shealth__authName">{t(`sh.${key}`)}</span>
              <span className="shealth__authState">{t(mark.label)}</span>
            </div>
          )
        })}
      </div>

      {/* ---- the measurable risks ---- */}
      <div className="shealth__grid">
        <Figure label={t('sh.bounceRate')}
                value={thin ? null : pct((sig.hardBounceRate || 0) * 100, 2)} t={t} />
        <Figure label={t('sh.unsubRate')}
                value={thin ? null : pct((sig.unsubscribeRate || 0) * 100, 2)} t={t} />
        <Figure label={t('sh.volume')} value={nf(sig.sentToday || 0)} t={t} />
        <Figure label={t('sh.suppression')} value={nf(sig.suppressed || 0)} t={t} />
      </div>
      {thin && (
        <p className="shealth__thin">
          {t('sh.notEnoughHint', { n: nf(h.thresholds?.min_sample ?? 50) })}
        </p>
      )}

      {/* ---- why, which is the part that can be acted on ---- */}
      {h.reasons?.length > 0 && (
        <>
          <div className="shealth__label">{t('sh.reasons')}</div>
          <ul className="shealth__reasons">
            {h.reasons.map((r) => (
              <li key={r.id} className={`shealth__reason shealth__reason--${r.tone}`}>
                {t(`sh.r.${r.id}`)}
                {/* the sample the number came from, so a rate is never
                    asserted without saying how much is behind it */}
                {r.sample !== undefined && (
                  <span className="faint"> · {t('ab.sampleSize')} {nf(r.sample)}</span>
                )}
              </li>
            ))}
          </ul>
        </>
      )}

      {h.recommendedActions?.length > 0 && (
        <>
          <div className="shealth__label">{t('sh.recommendations')}</div>
          <ul className="shealth__reasons">
            {h.recommendedActions.map((a) => (
              <li key={a.id} className="shealth__reason">{t(`sh.a.${a.id}`)}</li>
            ))}
          </ul>
        </>
      )}
    </Card>
  )
}

function Figure({ label, value, t }) {
  return (
    <div className="shealth__fig">
      <div className="shealth__figLabel">{label}</div>
      <div className={`shealth__figValue${value === null ? ' shealth__figValue--none' : ''}`}>
        {value === null ? t('sh.notEnough') : value}
      </div>
    </div>
  )
}
