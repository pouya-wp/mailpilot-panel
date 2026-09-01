/* ============================================================
   GUIDE — how to use the thing.

   Written for the CUSTOMER, not the implementer. Everything about
   keys, modules and deployment lives in Setup and in
   deploy/README; none of it belongs in front of someone whose job
   is sending email.

   Two rules held throughout:

   * Only document what this deployment actually has. A guide that
     explains Billing to a customer who was not sold Billing is
     worse than no guide — it teaches them to look for a screen
     that does not exist. Every section is gated on `has()`.

   * Say what the agent DOES, not what the buttons are called. A
     person who reads "ask for what you want in plain words" can
     find the box; a person who reads "click the Ask button" has
     learned nothing they could not see.
   ============================================================ */
import { useState } from 'react'
import { useI18n } from '../i18n'
import { useConfig } from '../api/config'
import { navigate } from '../router'
import PageHeader from '../layout/PageHeader'
import { Card, Tabs } from '../ui'
import {
  IcCampaign,
  IcContacts,
  IcDashboard,
  IcGear,
  IcInbox,
  IcSpark,
  IcTemplate,
} from '../components/NavIcons'

export default function Guide() {
  const { t, lang } = useI18n()
  const { has, agent, brand, ai } = useConfig()
  const [tab, setTab] = useState('start')

  const name = agent.name || t('guide.theAgent')

  /* Each entry is [id, icon, module]. A null module means the section is
     always relevant. */
  const sections = [
    ['start', IcDashboard, null],
    ['asking', IcSpark, null],
    ['campaigns', IcCampaign, 'campaigns'],
    ['audience', IcContacts, 'audience'],
    ['designer', IcTemplate, 'templates'],
    ['replies', IcInbox, 'inbox'],
    ['settings', IcGear, null],
  ].filter(([, , module]) => !module || has(module))

  const tabs = sections.map(([id]) => ({ value: id, label: t(`guide.${id}.tab`) }))
  const current = sections.find(([id]) => id === tab) || sections[0]

  return (
    <div className="page guide">
      <PageHeader title={t('nav.guide')} sub={t('guide.sub', { brand: brand.name })} />
      <Tabs tabs={tabs} value={tab} onChange={setTab} />

      <div className="tabbody">
        <Card className="guide__card">
          <Article id={current[0]} Icon={current[1]} name={name} aiOn={ai.configured} t={t} lang={lang} />
        </Card>
      </div>
    </div>
  )
}

function Article({ id, Icon, name, aiOn, t, lang }) {
  /* The body of each section is a list of [heading, paragraph] pairs held in
     the dictionaries, so the guide translates like everything else rather than
     being two copies of the same prose in one file. */
  const steps = []
  for (let i = 1; i <= 8; i++) {
    const heading = t(`guide.${id}.h${i}`, { name })
    // an untranslated key comes back as the key itself; that is where the
    // section ends
    if (heading === `guide.${id}.h${i}`) break
    steps.push([heading, t(`guide.${id}.p${i}`, { name })])
  }

  return (
    <>
      <div className="guide__head">
        <span className="guide__icon">
          <Icon size={20} />
        </span>
        <div>
          <h2>{t(`guide.${id}.title`, { name })}</h2>
          <p>{t(`guide.${id}.lead`, { name })}</p>
        </div>
      </div>

      {id === 'asking' && !aiOn && (
        <p className="guide__note">{t('guide.asking.noKey')}</p>
      )}

      <ol className="guide__steps">
        {steps.map(([heading, body], i) => (
          <li key={i}>
            <h3>{heading}</h3>
            <p>{body}</p>
          </li>
        ))}
      </ol>

      {id === 'start' && (
        <button className="guide__cta" onClick={() => navigate('home')}>
          {t('guide.start.cta', { name })}
        </button>
      )}
    </>
  )
}
