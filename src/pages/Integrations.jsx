/* INTEGRATIONS — grouped by what the connection is FOR, not by
   vendor name, so the reader scanning for "where does revenue data
   come from" lands in one section rather than reading fourteen
   logos. */
import { useMemo, useState } from 'react'
import { useI18n, loc } from '../i18n'
import { useIntegrations, useToggleIntegration } from '../api/resources'
import PageHeader from '../layout/PageHeader'
import { Badge, Button, Card, CardHead, EmptyState, SearchBox, Segmented, Stagger, Toggle } from '../ui'
import { Async } from '../ui/state'
import { IcPlug, IcSearch } from '../components/NavIcons'

const CATS = ['all', 'ecommerce', 'crm', 'data', 'messaging', 'ads', 'ai']

export default function Integrations({ onToast, embedded }) {
  const { t, lang, nf } = useI18n()
  const [cat, setCat] = useState('all')
  const [q, setQ] = useState('')
  const query = useIntegrations()
  const [toggle] = useToggleIntegration()

  const list = useMemo(() => {
    const needle = q.trim().toLowerCase()
    return (query.data || []).filter((i) => {
      if (cat !== 'all' && i.cat !== cat) return false
      return !needle || i.name.toLowerCase().includes(needle)
    })
  }, [cat, q, query.data])

  const grouped = useMemo(() => {
    const byCat = {}
    list.forEach((i) => {
      ;(byCat[i.cat] ||= []).push(i)
    })
    return byCat
  }, [list])

  const connected = (query.data || []).filter((i) => i.on).length

  return (
    <div className="page">
      <PageHeader
        embedded={embedded}
        title={t('int.title')}
        sub={t('int.sub')}
        actions={
          <Badge tone="good" dot>
            {nf(connected)} {t('g.connected')}
          </Badge>
        }
      />

      <Stagger className="stack-v">
        <div className="toolbar" style={{ margin: 0 }}>
          <SearchBox value={q} onChange={setQ} placeholder={t('g.search')} />
          <Segmented
            size="sm"
            value={cat}
            onChange={setCat}
            options={CATS.map((c) => ({ value: c, label: c === 'all' ? t('g.all') : t(`int.category.${c}`) }))}
          />
        </div>

        {Object.keys(grouped).length === 0 ? (
          <Card>
            <EmptyState title={t('g.empty')} hint={t('g.emptyHint')} icon={<IcSearch size={26} />} />
          </Card>
        ) : (
          Object.entries(grouped).map(([c, items]) => (
            <Card key={c}>
              <CardHead title={t(`int.category.${c}`)} icon={<IcPlug size={17} />} />
              <div className="intgrid">
                {items.map((i) => (
                  <div className="card intcard" key={i.id}>
                    <span className="intcard__logo">{i.emoji}</span>
                    <span className="intcard__text">
                      <span className="intcard__name">{i.name}</span>
                      <span className="intcard__desc">{loc(i.desc, lang)}</span>
                    </span>
                    <Toggle
                      checked={!!i.on}
                      onChange={async (v) => {
                        await toggle({ id: i.id, on: v })
                        onToast?.(v ? t('g.connected') : t('g.disconnect'))
                      }}
                    />
                  </div>
                ))}
              </div>
            </Card>
          ))
        )}
      </Stagger>
    </div>
  )
}
