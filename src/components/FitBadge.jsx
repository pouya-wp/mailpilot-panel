/* ============================================================
   FIT

   Two exports, because §16.5 asks for two different things: a
   compact band in the contact row, and the rationale somewhere
   with room for it.

   THE NUMBER IS NOT THE POINT. "73" tells a reader nothing they
   can act on; "matches your ideal customer, in the target market"
   does. So the band leads and the score sits beside it as a
   detail, and the reasons live in `FitReasons` wherever there is
   space to read them.

   CONFIDENCE IS ALWAYS SHOWN SEPARATELY. A high fit we know
   nothing about and a high fit whose website we have read are
   different situations, and collapsing them is how a customer
   ends up trusting a guess.
   ============================================================ */
import { useI18n } from '../i18n'
import { Badge } from '../ui'

const TONE = {
  HIGH_FIT: 'good',
  GOOD_FIT: 'info',
  MEDIUM_FIT: 'warn',
  LOW_FIT: 'neutral',
}

/** Compact, for a table row. */
export default function FitBadge({ fit, size = 'sm' }) {
  const { t, nf } = useI18n()
  if (!fit) return <span className="faint">{t('fit.unknown')}</span>

  /* A native title rather than a custom popover: it is one line, it works
     in both directions without a layout pass, and the full rationale has a
     proper home in `FitReasons` rather than being crammed in here. */
  const summary = [
    ...(fit.reasons || []).map((r) => t(`fit.r.${r}`)),
    ...(fit.risks || []).map((r) => t(`fit.k.${r}`)),
  ].join(' · ')

  return (
    <span className="fitbadge" title={summary || undefined}>
      <Badge tone={TONE[fit.band] || 'neutral'} size={size}>
        {t(`fit.${fit.band}`)}
      </Badge>
      <span className="fitbadge__n">{nf(fit.score)}</span>
    </span>
  )
}

/** The rationale, for anywhere with room to read it. */
export function FitReasons({ fit }) {
  const { t, nf, pct } = useI18n()
  if (!fit) return null

  return (
    <div className="fitwhy">
      <div className="fitwhy__head">
        {t('fit.label')} {nf(fit.score)} · {t(`fit.${fit.band}`)}
      </div>

      {fit.reasons?.length > 0 && (
        <>
          <div className="fitwhy__label">{t('fit.why')}</div>
          <ul className="fitwhy__list">
            {fit.reasons.map((r) => <li key={r}>{t(`fit.r.${r}`)}</li>)}
          </ul>
        </>
      )}

      {fit.risks?.length > 0 && (
        <>
          <div className="fitwhy__label">{t('fit.risks')}</div>
          <ul className="fitwhy__list fitwhy__list--risk">
            {fit.risks.map((r) => <li key={r}>{t(`fit.k.${r}`)}</li>)}
          </ul>
        </>
      )}

      {/* Never folded into the score: how well they fit and how much we
          know about them are different questions with different remedies. */}
      <div className="fitwhy__foot">
        {t('fit.confidence')}: {pct((fit.confidence || 0) * 100, 0)}
      </div>
      {fit.offer && (
        <div className="fitwhy__foot">{t('fit.forOffer', { offer: fit.offer })}</div>
      )}
    </div>
  )
}
