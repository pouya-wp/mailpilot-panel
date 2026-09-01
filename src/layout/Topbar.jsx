/* ============================================================
   TOP BAR — breadcrumb, command trigger, language, alerts, account.

   The language switch is the only control here with real
   choreography: the lit pill travels between EN and FA the same
   way the sidebar marker travels between rows. It is the panel's
   most consequential control — it re-lays out the entire app — so
   it gets a gesture that acknowledges the change rather than a
   silent class swap.
   ============================================================ */
import { useRef } from 'react'
import { gsap, reduced, useGSAP } from '../anim/core'
import { loc, useI18n } from '../i18n'
import { navigate, useRoute } from '../router'
import { useAuth } from '../api/auth'
import { useMarkNotificationsRead, useNotifications } from '../api/resources'
import { Avatar, IconButton, Menu, useIndicator } from '../ui'
import MusicToggle from '../components/MusicToggle'
import {
  IcBell,
  IcBook,
  IcChart,
  IcChevron,
  IcGear,
  IcMoon,
  IcSearch,
  IcSidebar,
  IcSpark,
  IcSun,
  IcTeam,
  IcX,
} from '../components/NavIcons'
import { navItem } from './nav'
import { useConfig } from '../api/config'

export default function Topbar({ onOpenCommand, onBurger, onToast }) {
  const { t, lang, setLang, langs, rtl, ago, nf, theme, toggleTheme } = useI18n()
  const { path } = useRoute()
  const { has, langLocked } = useConfig()
  const item = navItem(path)
  const { user, logout } = useAuth()
  const notifQ = useNotifications()
  const [markRead] = useMarkNotificationsRead()
  const notifs = notifQ.data?.items || []
  const unread = notifQ.data?.unread || 0

  /* ---- the travelling language pill ---- */
  const langBox = useRef(null)
  useIndicator(
    langBox,
    '[data-on="1"]',
    (host, r) => {
      const pill = host.querySelector('.lang__pill')
      if (!pill) return
      gsap.to(pill, {
        x: r.x - 3,
        y: r.y - 3,
        width: r.w,
        height: r.h,
        duration: reduced() ? 0 : 0.45,
        ease: 'snap',
        overwrite: 'auto',
      })
    },
    [lang, rtl]
  )

  const switchLang = (id) => {
    if (id === lang) return
    setLang(id)
    onToast?.(t('toast.langChanged'))
  }

  return (
    <header className="tbar">
      <button className="iconbtn ash__burger" onClick={onBurger} aria-label={t('app.expand')}>
        <IcSidebar size={17} />
      </button>

      <div className="tbar__crumbs">
        <span>{t('app.workspace')}</span>
        <span className="tbar__crumbSep">
          <IcChevron size={12} dir="end" flip={rtl} />
        </span>
        <b>{item ? t(item.labelKey) : t('nav.dashboard')}</b>
      </div>

      <div className="tbar__spacer" />

      <button className="tbar__search" onClick={onOpenCommand}>
        <IcSearch size={15} />
        <span>{t('app.search')}</span>
        <kbd className="kbd">{t('app.commandHint')}</kbd>
      </button>

      <div className="tbar__right">
        <MusicToggle />

        {/* theme */}
        <IconButton
          label={theme === 'dark' ? t('app.themeLight') : t('app.themeDark')}
          /* the circle opens from the button that was pressed */
          onClick={(e) => toggleTheme(e.currentTarget)}
        >
          {theme === 'dark' ? <IcSun size={17} /> : <IcMoon size={17} />}
        </IconButton>

        {/* Language. Hidden entirely where the deployment fixed it — a
            disabled switch would just invite someone to ask why. */}
        {!langLocked && (
        <div className="lang" ref={langBox}>
          <span className="lang__pill" aria-hidden="true" />
          {langs.map((l) => (
            <button
              key={l.id}
              data-on={l.id === lang ? '1' : '0'}
              className={`lang__btn${l.id === lang ? ' lang__btn--on' : ''}`}
              onClick={() => switchLang(l.id)}
              title={l.label}
            >
              {l.short}
            </button>
          ))}
        </div>
        )}

        {/* notifications */}
        <Menu
          align="end"
          width={36}
          trigger={
            <IconButton label={t('app.notifications')} active={unread > 0}>
              <span style={{ position: 'relative', display: 'grid', placeItems: 'center' }}>
                <IcBell size={17} />
                {unread > 0 && (
                  <span
                    style={{
                      position: 'absolute',
                      insetInlineEnd: '-0.5rem',
                      top: '-0.4rem',
                      minWidth: '1.5rem',
                      height: '1.5rem',
                      padding: '0 0.35rem',
                      borderRadius: '9.9rem',
                      display: 'grid',
                      placeItems: 'center',
                      fontSize: '1rem',
                      fontWeight: 700,
                      color: '#0d1116',
                      background: 'var(--blue-1)',
                      boxShadow: '0 0 1.2rem rgba(150,195,232,.8)',
                    }}
                  >
                    {nf(unread)}
                  </span>
                )}
              </span>
            </IconButton>
          }
          items={[
            {
              id: 'head',
              label: (
                <div className="notif__head" style={{ width: '100%' }}>
                  <span className="notif__title">{t('app.notifications')}</span>
                  <span
                    className="muted"
                    style={{ fontSize: '1.15rem', cursor: 'pointer' }}
                    onClick={(e) => {
                      e.stopPropagation()
                      markRead()
                    }}
                  >
                    {t('app.markAllRead')}
                  </span>
                </div>
              ),
            },
            ...notifs.map((n) => ({
              id: n.id,
              label: (
                <span className="notif__body">
                  <span className="notif__itemTitle">{loc(n.title, lang)}</span>
                  <span className="notif__itemText">{loc(n.body, lang)}</span>
                  <span className="notif__at">{ago(n.at)}</span>
                </span>
              ),
              icon: <span className={`notif__dot notif__dot--${n.tone}`} />,
            })),
          ]}
        />

        {/* account */}
        <Menu
          align="end"
          width={24}
          trigger={
            <button className="acct">
              <Avatar name={loc(user?.name, lang) || t('app.account')} size={30} />
              <span className="acct__text">
                <span className="acct__name">{loc(user?.name, lang) || t('app.account')}</span>
                <span className="acct__plan">{user?.role ? t(`team.role.${user.role}`) : t('app.plan')}</span>
              </span>
            </button>
          }
          items={[
            /* Team and billing are tabs inside Settings, not screens of
               their own — and they only exist when the deployment includes
               them, so an entry that leads nowhere is not offered at all. */
            has('team') && { id: 'profile', label: t('app.profile'), icon: <IcTeam size={15} />,
                             onClick: () => navigate('settings?tab=team') },
            { id: 'settings', label: t('nav.settings'), icon: <IcGear size={15} />, onClick: () => navigate('settings') },
            /* This said "billing" and led to a tab nobody wanted from here.
               The thing a person opens their own menu looking for is how the
               sending is going, so it points at the analytics screen. */
            has('insights') && { id: 'insights', label: t('nav.insights'), icon: <IcChart size={15} />,
                                 onClick: () => navigate('insights') },
            { divider: true },
            { id: 'help', label: t('app.help'), icon: <IcBook size={15} />, onClick: () => navigate('guide') },
            { id: 'out', label: t('app.signOut'), icon: <IcX size={15} />, tone: 'danger', onClick: logout },
          ].filter(Boolean)}
        />
      </div>
    </header>
  )
}
