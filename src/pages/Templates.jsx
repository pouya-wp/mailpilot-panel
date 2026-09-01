/* ============================================================
   TEMPLATES

   The thumbnails are wireframes built from bars, not renders. At
   the size a gallery card actually gets, a real screenshot of an
   email is an unreadable grey rectangle; the bar skeleton carries
   the one thing you are choosing between — the LAYOUT — and reads
   at a glance.
   ============================================================ */
import { useMemo, useState } from 'react'
import { useI18n, loc } from '../i18n'
import { useTemplates } from '../api/resources'
import { navigate } from '../router'
import PageHeader from '../layout/PageHeader'
import { Badge, Button, Card, EmptyState, Menu, SearchBox, Segmented, Stagger } from '../ui'
import { Async } from '../ui/state'
import { IcCopy, IcDots, IcEye, IcPlus, IcTemplate, IcTrash } from '../components/NavIcons'

const CATS = ['all', 'promo', 'newsletter', 'lifecycle', 'transactional']
const CAT_LABEL = {
  en: { all: 'All', promo: 'Promotional', newsletter: 'Newsletter', lifecycle: 'Lifecycle', transactional: 'Transactional' },
  fa: { all: 'همه', promo: 'تبلیغاتی', newsletter: 'خبرنامه', lifecycle: 'چرخهٔ عمر', transactional: 'تراکنشی' },
}

export default function Templates({ onToast }) {
  const { t, lang, nf } = useI18n()
  const [cat, setCat] = useState('all')
  const [search, setSearch] = useState('')
  const q = useTemplates(cat)

  /* The category filter is a SERVER round-trip (the API already supports it)
     while the text search stays local — it runs over at most a few dozen
     templates, so a request per keystroke would cost more than it saved. */
  const list = useMemo(() => {
    const needle = search.trim().toLowerCase()
    const rows = q.data || []
    if (!needle) return rows
    return rows.filter((tp) => [tp.name.en, tp.name.fa].some((v) => (v || '').toLowerCase().includes(needle)))
  }, [q.data, search])

  return (
    <div className="page">
      <PageHeader
        title={t('tpl.title')}
        sub={t('tpl.sub')}
        actions={
          <Button variant="primary" icon={<IcPlus size={16} />} onClick={() => navigate('composer')}>
            {t('tpl.new')}
          </Button>
        }
      />

      <Stagger className="stack-v">
        <div className="toolbar" style={{ margin: 0 }}>
          <SearchBox value={search} onChange={setSearch} placeholder={t('g.search')} />
          <Segmented
            size="sm"
            value={cat}
            onChange={setCat}
            options={CATS.map((c) => ({ value: c, label: (CAT_LABEL[lang] ?? CAT_LABEL.en)[c] }))}
          />
        </div>

        {list.length === 0 ? (
          <Card>
            <EmptyState title={t('g.empty')} hint={t('g.emptyHint')} icon={<IcTemplate size={26} />} />
          </Card>
        ) : (
          <div className="tplgrid">
            {list.map((tp) => (
              <div className="card tpl" key={tp.id}>
                <div className="tpl__thumb">
                  <span className="tpl__glow" style={{ background: tp.accent }} />
                  <span className="tpl__bar" style={{ width: '38%' }} />
                  <span className="tpl__bar tpl__bar--hero" />
                  <span className="tpl__bar" style={{ width: '90%' }} />
                  <span className="tpl__bar" style={{ width: '76%' }} />
                  <span className="tpl__bar" style={{ width: '84%' }} />
                  <span className="tpl__bar tpl__bar--btn" style={{ background: tp.accent, opacity: 0.7 }} />
                </div>
                <div className="tpl__meta">
                  <span className="tpl__name ellip">{loc(tp.name, lang)}</span>
                  <span className="tpl__used">{t('tpl.used', { n: nf(tp.used) })}</span>
                  <Menu
                    align="end"
                    trigger={
                      <button className="iconbtn" style={{ width: '3rem', height: '3rem' }} aria-label={t('g.actions')}>
                        <IcDots size={15} />
                      </button>
                    }
                    items={[
                      { id: 'p', label: t('comp.preview'), icon: <IcEye size={15} /> },
                      { id: 'u', label: t('comp.use'), icon: <IcCopy size={15} />, onClick: () => navigate('composer') },
                      { divider: true },
                      { id: 'x', label: t('g.delete'), icon: <IcTrash size={15} />, tone: 'danger' },
                    ]}
                  />
                </div>
              </div>
            ))}
          </div>
        )}
      </Stagger>
    </div>
  )
}
