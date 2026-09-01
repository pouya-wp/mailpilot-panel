/* ============================================================
   SENDING DOMAINS

   DNS values are the one place in the panel where the text is not
   translated and not mirrored: a TXT record is a literal that has
   to be copied exactly, so every value here is monospace, forced
   LTR, and copy-to-clipboard rather than selectable text.
   ============================================================ */
import { useState } from 'react'
import { useI18n } from '../i18n'
import { useAddDomain, useDomains, useVerifyDomain } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import {
  Badge,
  Button,
  Card,
  CardHead,
  CopyField,
  EmptyState,
  Field,
  Grid,
  Input,
  Modal,
  Stagger,
  StatusBadge,
  Toggle,
} from '../ui'
import { IcCheckC, IcGlobe, IcPlus, IcRefresh, IcShield, IcWarn, IcX } from '../components/NavIcons'

export default function Domains({ onToast, embedded }) {
  const { t, lang, nf } = useI18n()
  const query = useDomains()
  const [addDomain, adding] = useAddDomain()
  const [verify] = useVerifyDomain()
  const [add, setAdd] = useState(false)
  const [draft, setDraft] = useState('')
  const [dedicated, setDedicated] = useState(true)

  /* Reset on close, so reopening does not present the last attempt as
     though it had been typed again. */
  const closeAdd = () => {
    setAdd(false)
    setDraft('')
    setDedicated(true)
  }

  return (
    <div className="page">
      <PageHeader
        embedded={embedded}
        title={t('dom.title')}
        sub={t('dom.sub')}
        actions={
          <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => setAdd(true)}>
            {t('dom.add')}
          </Button>
        }
      />

      <Stagger className="stack-v">
        {(query.data || []).length === 0 && !query.loading && (
          <EmptyState
            icon={<IcGlobe size={26} />}
            title={t('dom.emptyTitle')}
            hint={t('dom.emptyHint')}
          />
        )}
        {(query.data || []).map((d) => (
          <Card key={d.id}>
            <CardHead
              title={<span className="mono">{d.domain}</span>}
              sub={d.dedicated ? `${t('dom.dedicatedIp')} · ${d.ip}` : t('g.all')}
              icon={<IcGlobe size={17} />}
              right={
                <div className="row" style={{ gap: '0.8rem' }}>
                  <StatusBadge status={d.status}>{t(`dom.${d.status}`)}</StatusBadge>
                  <Button
                    size="sm"
                    variant="ghost"
                    icon={<IcRefresh size={14} />}
                    onClick={async () => {
                      try {
                        /* The server re-checks the DNS records and answers with
                           the domain's new status — so a failed verification
                           reads as failed rather than as a cheerful toast. */
                        const res = await verify(d.id)
                        onToast?.(res?.status === 'verified' ? t('toast.domainVerified') : t('toast.domainPending'))
                      } catch (err) {
                        onToast?.(err.message || t('err.failed'))
                      }
                    }}
                  >
                    {t('dom.verify')}
                  </Button>
                </div>
              }
            />

            <div className="row" style={{ gap: '0.8rem', flexWrap: 'wrap', marginBottom: '1.6rem' }}>
              {[
                ['SPF', d.spf],
                ['DKIM', d.dkim],
                ['DMARC', d.dmarc],
                ['BIMI', d.bimi],
              ].map(([k, ok]) => (
                <Badge key={k} tone={ok ? 'good' : 'warn'} dot>
                  {k}
                </Badge>
              ))}
              <span className="faint" style={{ fontSize: '1.2rem', marginInlineStart: 'auto' }}>
                {t('m.reputation')} <b className="strong">{nf(d.reputation)}</b>
              </span>
            </div>

            <div className="caps" style={{ marginBottom: '0.8rem' }}>
              {t('dom.records')}
            </div>
            {d.records.map((r, i) => (
              <div className="dns" key={i}>
                <span className="dns__type">{r.type}</span>
                <CopyField value={r.host} />
                <CopyField value={r.value} />
                <span style={{ color: r.ok ? 'var(--good)' : 'var(--bad)', display: 'grid', placeItems: 'center' }}>
                  {r.ok ? <IcCheckC size={17} /> : <IcX size={17} />}
                </span>
              </div>
            ))}

            {d.status !== 'verified' && (
              <p
                className="row"
                style={{
                  gap: '0.8rem',
                  marginTop: '1.4rem',
                  padding: '1.1rem 1.3rem',
                  borderRadius: 'var(--r-sm)',
                  background: 'var(--warn-dim)',
                  border: '1px solid var(--warn-edge)',
                  color: 'var(--warn)',
                  fontSize: '1.22rem',
                }}
              >
                <IcWarn size={16} />
                {lang === 'fa'
                  ? 'تا کامل‌شدن رکوردها، ایمیل‌های این دامنه بدون امضا ارسال می‌شوند.'
                  : 'Until these records resolve, mail from this domain sends unsigned.'}
              </p>
            )}
          </Card>
        ))}
      </Stagger>

      <Modal
        open={add}
        onClose={closeAdd}
        width={52}
        title={t('dom.add')}
        sub={t('dom.sub')}
        footer={
          <>
            <Button variant="quiet" onClick={closeAdd}>
              {t('g.cancel')}
            </Button>
            <Button
              variant="primary"
              loading={adding}
              disabled={!draft.trim()}
              onClick={async () => {
                try {
                  await addDomain({ domain: draft.trim(), dedicated })
                  closeAdd()
                  onToast?.(t('toast.saved'))
                } catch (err) {
                  /* The server's own sentence: it distinguishes "that does not
                     look like a domain name" from "already added", and both
                     are things the reader can act on. */
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
          <Field label={t('dom.title')} required hint="mail.example.com">
            <Input
              placeholder="mail.example.com"
              className="mono"
              value={draft}
              onChange={(e) => setDraft(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter' && draft.trim() && !adding) e.currentTarget.blur()
              }}
            />
          </Field>
          <Toggle
            checked={dedicated}
            onChange={setDedicated}
            label={t('dom.dedicatedIp')}
            hint={t('del.warmup')}
          />
          <div
            style={{
              padding: '1.4rem 1.6rem',
              borderRadius: 'var(--r-md)',
              background: 'var(--info-dim)',
              border: '1px solid var(--info-edge)',
              fontSize: '1.25rem',
              lineHeight: 1.7,
              color: 'var(--tx-2)',
            }}
          >
            {lang === 'fa'
              ? 'بعد از افزودن، سه رکورد DNS به شما داده می‌شود. تا تأیید نشوند ارسالی از این دامنه انجام نمی‌شود.'
              : 'After adding, you get three DNS records. Nothing sends from this domain until they verify.'}
          </div>
        </div>
      </Modal>
    </div>
  )
}
