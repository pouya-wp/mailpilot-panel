/* ============================================================
   INSIGHTS — the reporting section, for deployments that bought it.

   Home carries three figures because that is what someone who has
   delegated the work actually needs. This is the other audience:
   the customer who wants to read the numbers themselves, and who
   was sold that as part of the package.

   It is one nav entry rather than the two it used to be —
   performance and deliverability are the same question asked at
   different depths, and nobody navigating to "how are we doing"
   knew which of the two screens held their answer.
   ============================================================ */
import { useState } from 'react'
import { useI18n } from '../i18n'
import PageHeader from '../layout/PageHeader'
import { Tabs } from '../ui'
import Analytics from './Analytics'
import Deliverability from './Deliverability'

export default function Insights({ onToast }) {
  const { t } = useI18n()
  const [tab, setTab] = useState('performance')

  const tabs = [
    { value: 'performance', label: t('ins.performance') },
    { value: 'delivery', label: t('nav.deliverability') },
  ]

  return (
    <div className="page">
      <PageHeader title={t('nav.insights')} sub={t('ins.sub')} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />

      <div className="tabbody">
        {tab === 'performance' && <Analytics embedded onToast={onToast} />}
        {tab === 'delivery' && <Deliverability embedded onToast={onToast} />}
      </div>
    </div>
  )
}
