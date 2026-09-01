/* ============================================================
   AUDIENCE — people, groups, and the do-not-contact list.

   These were three sidebar entries. They are one question with
   three answers, and splitting them made the operator navigate to
   find out something they were already looking at: a contact's
   group membership lived on a different screen from the contact.

   The tabs are not a compromise. Contacts is the list, Groups is
   how it is cut, and Blocked is the part of it nothing may reach —
   the same population, three views.

   The bodies are the original pages, rendered without their own
   headers. See the `embedded` prop.
   ============================================================ */
import { useState } from 'react'
import { useI18n } from '../i18n'
import PageHeader from '../layout/PageHeader'
import { Tabs } from '../ui'
import Contacts from './Contacts'
import Segments from './Segments'
import Suppression from './Suppression'
import Research from './Research'

export default function Audience({ onToast }) {
  const { t } = useI18n()
  const [tab, setTab] = useState('people')

  const tabs = [
    { value: 'people', label: t('aud.people') },
    { value: 'groups', label: t('aud.groups') },
    { value: 'blocked', label: t('aud.blocked') },
    { value: 'research', label: t('aud.research') },
  ]

  return (
    <div className="page">
      <PageHeader title={t('nav.audience')} sub={t('aud.sub')} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />

      <div className="tabbody">
        {tab === 'people' && <Contacts embedded onToast={onToast} />}
        {tab === 'groups' && <Segments embedded onToast={onToast} />}
        {tab === 'blocked' && <Suppression embedded onToast={onToast} />}
        {tab === 'research' && <Research onToast={onToast} />}
      </div>
    </div>
  )
}
