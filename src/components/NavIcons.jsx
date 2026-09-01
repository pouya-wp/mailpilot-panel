/* ============================================================
   The icon set for the admin shell.

   Same construction as components/Icons.jsx — 24px grid, 1.6 stroke,
   round caps, sized in `rem` off the 10-design-px root so a glyph
   stays in proportion to the control around it at every viewport.

   Everything here is drawn symmetric or vertically mirrored where
   it matters, because the panel flips to RTL and an arrow that
   points "forward" has to point the other way. Those are the
   `Arrow`/`Chevron` pair, which read a `flip` prop.
   ============================================================ */
const box = (size) => ({ width: `${size / 10}rem`, height: `${size / 10}rem`, flex: '0 0 auto' })

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

const make = (path, vb = '0 0 24 24') =>
  function Icon({ size = 18, ...rest }) {
    return (
      <svg style={box(size)} viewBox={vb} {...base} {...rest}>
        {path}
      </svg>
    )
  }

/* ---------- navigation ---------- */
export const IcDashboard = make(
  <>
    <rect x="3" y="3" width="7.5" height="8.5" rx="2.2" />
    <rect x="13.5" y="3" width="7.5" height="5.5" rx="2.2" />
    <rect x="3" y="14.5" width="7.5" height="6.5" rx="2.2" />
    <rect x="13.5" y="11.5" width="7.5" height="9.5" rx="2.2" />
  </>
)

export const IcCampaign = make(
  <>
    <path d="M3.5 9.5v5a1.5 1.5 0 001.5 1.5h1.8L15 20.5V3.5L6.8 8H5a1.5 1.5 0 00-1.5 1.5z" />
    <path d="M18 9a4 4 0 010 6" />
    <path d="M6.8 16v4" />
  </>
)

export const IcCompose = make(
  <>
    <path d="M4 20l1-4.2L15.2 5.6a2.1 2.1 0 013 3L8 18.9 4 20z" />
    <path d="M13.6 7.2l3.2 3.2" />
    <path d="M19.4 3.2l.5 1.3 1.3.5-1.3.5-.5 1.3-.5-1.3-1.3-.5 1.3-.5.5-1.3z" fill="currentColor" stroke="none" />
  </>
)

export const IcTemplate = make(
  <>
    <rect x="3" y="4" width="18" height="16" rx="3" />
    <path d="M3 9h18M9 9v11" />
  </>
)

export const IcAgent = make(
  <>
    <rect x="4" y="7.5" width="16" height="12" rx="4" />
    <path d="M12 3.2v4.3M8.5 13v1.6M15.5 13v1.6" />
    <circle cx="12" cy="3" r="1.3" fill="currentColor" stroke="none" />
    <path d="M2.6 12v3M21.4 12v3" />
  </>
)

export const IcFlow = make(
  <>
    <rect x="3" y="3.4" width="6.4" height="5.2" rx="2" />
    <rect x="14.6" y="15.4" width="6.4" height="5.2" rx="2" />
    <rect x="3" y="15.4" width="6.4" height="5.2" rx="2" />
    <path d="M6.2 8.6v3.2a2 2 0 002 2h9.6v1.6" />
    <path d="M6.2 14v1.4" />
  </>
)

export const IcBrain = make(
  <>
    <path d="M12 4.4a3 3 0 00-5.6 1.2 3 3 0 00-1.5 5.2A3.1 3.1 0 006.6 16a3 3 0 005.4 1.6z" />
    <path d="M12 4.4a3 3 0 015.6 1.2 3 3 0 011.5 5.2 3.1 3.1 0 01-1.7 5.2 3 3 0 01-5.4 1.6z" />
    <path d="M12 4.4v15.2" />
  </>
)

export const IcInbox = make(
  <>
    <path d="M3.5 12.5V7a3 3 0 013-3h11a3 3 0 013 3v5.5" />
    <path d="M3.5 12.5H8l1.4 2.4h5.2l1.4-2.4h4.5V17a3 3 0 01-3 3h-11a3 3 0 01-3-3v-4.5z" />
  </>
)

export const IcFlask = make(
  <>
    <path d="M10 3.5h4M10.8 3.5v5.6L5.6 17.4A2.4 2.4 0 007.7 21h8.6a2.4 2.4 0 002.1-3.6l-5.2-8.3V3.5" />
    <path d="M7.8 14.8h8.4" />
  </>
)

export const IcContacts = make(
  <>
    <circle cx="9.2" cy="8.6" r="3.2" />
    <path d="M3.6 19.2c.6-3.1 2.9-4.9 5.6-4.9s5 1.8 5.6 4.9" />
    <path d="M16.4 5.8a3 3 0 010 5.7M18 14.8c2 .6 3.3 2.1 3.7 4.4" />
  </>
)

export const IcSegment = make(
  <>
    <circle cx="9" cy="12" r="6.2" />
    <circle cx="15" cy="12" r="6.2" />
  </>
)

export const IcShield = make(
  <>
    <path d="M12 3.2l7 2.6v5.6c0 4.3-2.8 7.6-7 9.4-4.2-1.8-7-5.1-7-9.4V5.8l7-2.6z" />
    <path d="M9 12.2l2.1 2.1 4-4.2" />
  </>
)

export const IcChart = make(
  <>
    <path d="M3.5 20.5h17" />
    <rect x="5" y="11" width="3.4" height="7" rx="1.4" />
    <rect x="10.3" y="6.5" width="3.4" height="11.5" rx="1.4" />
    <rect x="15.6" y="14" width="3.4" height="4" rx="1.4" />
  </>
)

export const IcSignal = make(
  <>
    <path d="M4 20V9.5M9.3 20V4.5M14.7 20v-8.4M20 20V7" />
  </>
)

export const IcGlobe = make(
  <>
    <circle cx="12" cy="12" r="8.6" />
    <path d="M3.6 12h16.8" />
    <path d="M12 3.4c2.3 2.4 3.4 5.3 3.4 8.6s-1.1 6.2-3.4 8.6c-2.3-2.4-3.4-5.3-3.4-8.6S9.7 5.8 12 3.4z" />
  </>
)

export const IcPlug = make(
  <>
    <path d="M9 3.4v4.2M15 3.4v4.2" />
    <path d="M6.4 7.6h11.2v3.9a5.6 5.6 0 01-11.2 0V7.6z" />
    <path d="M12 17.1v3.5" />
  </>
)

export const IcCode = make(
  <>
    <path d="M8.6 8L4.4 12l4.2 4M15.4 8l4.2 4-4.2 4M13.4 5.6l-2.8 12.8" />
  </>
)

export const IcTeam = make(
  <>
    <circle cx="12" cy="7.4" r="3.1" />
    <path d="M6.4 19.4c.5-3 2.7-4.7 5.6-4.7s5.1 1.7 5.6 4.7" />
    <circle cx="4.6" cy="9.6" r="2.1" />
    <circle cx="19.4" cy="9.6" r="2.1" />
    <path d="M2.4 17.4c.3-1.8 1.2-2.9 2.7-3.1M21.6 17.4c-.3-1.8-1.2-2.9-2.7-3.1" />
  </>
)

export const IcCard = make(
  <>
    <rect x="2.8" y="5" width="18.4" height="14" rx="3" />
    <path d="M2.8 10h18.4M6.4 15h3.4" />
  </>
)

export const IcList = make(
  <>
    <path d="M8.4 6.6h12M8.4 12h12M8.4 17.4h12M4 6.6h.01M4 12h.01M4 17.4h.01" />
  </>
)

export const IcGear = make(
  <>
    <circle cx="12" cy="12" r="3.1" />
    <path d="M19.2 14.4a1.6 1.6 0 00.32 1.76l.06.06a1.9 1.9 0 11-2.7 2.7l-.06-.06a1.6 1.6 0 00-1.76-.32 1.6 1.6 0 00-.97 1.46v.17a1.9 1.9 0 11-3.8 0v-.09a1.6 1.6 0 00-1.05-1.46 1.6 1.6 0 00-1.76.32l-.06.06a1.9 1.9 0 11-2.7-2.7l.06-.06a1.6 1.6 0 00.32-1.76 1.6 1.6 0 00-1.46-.97H3.4a1.9 1.9 0 110-3.8h.09A1.6 1.6 0 004.95 8.8a1.6 1.6 0 00-.32-1.76l-.06-.06a1.9 1.9 0 112.7-2.7l.06.06a1.6 1.6 0 001.76.32h.08A1.6 1.6 0 0010.2 3.2v-.17a1.9 1.9 0 013.8 0v.09a1.6 1.6 0 00.97 1.46 1.6 1.6 0 001.76-.32l.06-.06a1.9 1.9 0 112.7 2.7l-.06.06a1.6 1.6 0 00-.32 1.76v.08a1.6 1.6 0 001.46.97h.17a1.9 1.9 0 010 3.8h-.09a1.6 1.6 0 00-1.46.97z" />
  </>
)

/* ---------- actions & status ---------- */
export const IcPlus = make(<path d="M12 5.4v13.2M5.4 12h13.2" />)
export const IcMinus = make(<path d="M5.4 12h13.2" />)
export const IcX = make(<path d="M6.2 6.2l11.6 11.6M17.8 6.2L6.2 17.8" />)
export const IcSearch = make(
  <>
    <circle cx="10.8" cy="10.8" r="6.4" />
    <path d="M15.6 15.6L20 20" />
  </>
)
export const IcBell = make(
  <>
    <path d="M6.4 10.4a5.6 5.6 0 1111.2 0c0 4 1.2 5.2 1.8 5.8H4.6c.6-.6 1.8-1.8 1.8-5.8z" />
    <path d="M10.2 19.2a2 2 0 003.6 0" />
  </>
)
export const IcPlay = make(<path d="M8 5.6l10 6.4-10 6.4V5.6z" />)
export const IcPause = make(<path d="M9.2 5.6v12.8M14.8 5.6v12.8" />)
export const IcRefresh = make(
  <>
    <path d="M20 11.4a8 8 0 10-1.6 5.6" />
    <path d="M20.3 4.9v5h-5" />
  </>
)
export const IcTrash = make(
  <>
    <path d="M4.6 6.6h14.8M9.4 6.6V4.8a1.4 1.4 0 011.4-1.4h2.4a1.4 1.4 0 011.4 1.4v1.8" />
    <path d="M6.4 6.6l.9 12.1a1.8 1.8 0 001.8 1.7h5.8a1.8 1.8 0 001.8-1.7l.9-12.1" />
  </>
)
export const IcCopy = make(
  <>
    <rect x="8.4" y="8.4" width="11.2" height="11.2" rx="2.6" />
    <path d="M15.4 8.4V6.8a2.4 2.4 0 00-2.4-2.4H6.8a2.4 2.4 0 00-2.4 2.4v6.2a2.4 2.4 0 002.4 2.4h1.6" />
  </>
)
export const IcDownload = make(
  <>
    <path d="M12 3.6v11.2M7.6 10.6l4.4 4.4 4.4-4.4" />
    <path d="M4.4 18.4v.6a1.8 1.8 0 001.8 1.8h11.6a1.8 1.8 0 001.8-1.8v-.6" />
  </>
)
export const IcUpload = make(
  <>
    <path d="M12 15.4V4.2M7.6 8.6L12 4.2l4.4 4.4" />
    <path d="M4.4 18.4v.6a1.8 1.8 0 001.8 1.8h11.6a1.8 1.8 0 001.8-1.8v-.6" />
  </>
)
export const IcFilter = make(<path d="M3.8 5.4h16.4l-6.3 7.4v5.6l-3.8 2.2v-7.8L3.8 5.4z" />)
export const IcDots = make(
  <>
    <circle cx="5.6" cy="12" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="12" cy="12" r="1.4" fill="currentColor" stroke="none" />
    <circle cx="18.4" cy="12" r="1.4" fill="currentColor" stroke="none" />
  </>
)
export const IcSpark = make(
  <>
    <path
      d="M12 2.8l1.9 4.7 4.7 1.9-4.7 1.9L12 16l-1.9-4.7-4.7-1.9 4.7-1.9L12 2.8z"
      fill="currentColor"
      stroke="none"
      opacity="0.95"
    />
    <path
      d="M18.6 15.6l.8 1.9 1.9.8-1.9.8-.8 1.9-.8-1.9-1.9-.8 1.9-.8.8-1.9z"
      fill="currentColor"
      stroke="none"
      opacity="0.6"
    />
  </>
)
export const IcSun = make(
  <>
    <circle cx="12" cy="12" r="4.2" />
    <path d="M12 2.6v2.4M12 19v2.4M2.6 12H5M19 12h2.4M5.3 5.3l1.7 1.7M17 17l1.7 1.7M18.7 5.3L17 7M7 17l-1.7 1.7" />
  </>
)
export const IcMoon = make(<path d="M20.4 14.4A8.6 8.6 0 019.6 3.6a8.6 8.6 0 1010.8 10.8z" />)
export const IcBolt = make(<path d="M13 3L5.5 13.2h5.2L10 21l7.6-10.4h-5.2L13 3z" />)
export const IcMail = make(
  <>
    <rect x="3" y="5" width="18" height="14" rx="3" />
    <path d="M3.5 7.5l7.3 5a2 2 0 002.4 0l7.3-5" />
  </>
)
export const IcFlame = make(
  <path d="M12 3.2c3 3.1 5.6 5.4 5.6 9a5.6 5.6 0 11-11.2 0c0-1.6.6-2.9 1.6-4.2.5 1 1.2 1.6 2 1.9-.4-2.6.3-4.9 2-6.7z" />
)
export const IcTrendUp = make(
  <>
    <path d="M4 15.5l5-5 3.2 3.2L20 6.5" />
    <path d="M15.5 6.5H20V11" />
  </>
)
export const IcTarget = make(
  <>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" stroke="none" />
  </>
)
export const IcWarn = make(
  <>
    <path d="M12 3.8l8.6 15a1.4 1.4 0 01-1.2 2.1H4.6a1.4 1.4 0 01-1.2-2.1l8.6-15z" />
    <path d="M12 9.6v4.4M12 17.4h.01" />
  </>
)
export const IcInfoC = make(
  <>
    <circle cx="12" cy="12" r="8.6" />
    <path d="M12 11.2v5M12 7.8h.01" />
  </>
)
export const IcCheckC = make(
  <>
    <circle cx="12" cy="12" r="8.6" />
    <path d="M8.2 12.2l2.6 2.6 5-5.2" />
  </>
)
export const IcClock2 = make(
  <>
    <circle cx="12" cy="12" r="8.6" />
    <path d="M12 7v5.2l3.4 2" />
  </>
)
export const IcEye = make(
  <>
    <path d="M2.6 12S6 5.8 12 5.8 21.4 12 21.4 12 18 18.2 12 18.2 2.6 12 2.6 12z" />
    <circle cx="12" cy="12" r="2.9" />
  </>
)
export const IcCursorClick = make(
  <>
    <path d="M6.2 4.6l12.4 6-5.2 1.5-2 5.1-5.2-12.6z" />
    <path d="M15 15l4.4 4.4" />
  </>
)
export const IcReply = make(
  <>
    <path d="M9.4 6.4L4.6 11l4.8 4.6" />
    <path d="M4.6 11h8.6a6 6 0 016 6v1.6" />
  </>
)
export const IcSend = make(
  <>
    <path d="M21 3.6L10.4 14.2" />
    <path d="M21 3.6l-6.6 17.2-3.9-7.2-7.2-3.9L21 3.6z" />
  </>
)
export const IcMoney = make(
  <>
    <circle cx="12" cy="12" r="8.6" />
    <path d="M14.6 9.2a2.8 2.8 0 00-2.6-1.4c-1.6 0-2.6.8-2.6 2s.9 1.7 2.6 2.1c1.9.4 2.8 1 2.8 2.2s-1.1 2.1-2.8 2.1a3 3 0 01-2.8-1.5" />
    <path d="M12 6.4v11.2" />
  </>
)
export const IcTrendDown = make(
  <>
    <path d="M4 8.5l5 5 3.2-3.2L20 17.5" />
    <path d="M15.5 17.5H20V13" />
  </>
)
export const IcArrowUp = make(<path d="M12 19V5M6 11l6-6 6 6" />)
export const IcSidebar = make(
  <>
    <rect x="3" y="4" width="18" height="16" rx="3" />
    <path d="M9.6 4v16" />
  </>
)
export const IcMobile = make(
  <>
    <rect x="7" y="2.8" width="10" height="18.4" rx="2.6" />
    <path d="M10.8 18.4h2.4" />
  </>
)
export const IcDesktop = make(
  <>
    <rect x="2.8" y="4.4" width="18.4" height="12.4" rx="2.6" />
    <path d="M8.6 20.6h6.8M12 16.8v3.8" />
  </>
)
export const IcTag = make(
  <>
    <path d="M11.6 3.4H20v8.4l-8.7 8.7a1.8 1.8 0 01-2.6 0l-5.8-5.8a1.8 1.8 0 010-2.6l8.7-8.7z" />
    <circle cx="16.4" cy="7.6" r="1.4" />
  </>
)
export const IcLink = make(
  <>
    <path d="M10.2 13.8a3.6 3.6 0 005.4.4l2.6-2.6a3.6 3.6 0 00-5.1-5.1l-1.5 1.5" />
    <path d="M13.8 10.2a3.6 3.6 0 00-5.4-.4l-2.6 2.6a3.6 3.6 0 005.1 5.1l1.5-1.5" />
  </>
)
export const IcCalendar = make(
  <>
    <rect x="3.4" y="5" width="17.2" height="15.6" rx="3" />
    <path d="M3.4 9.6h17.2M8.4 3v4M15.6 3v4" />
  </>
)
export const IcBook = make(
  <>
    <path d="M4 5.2A1.8 1.8 0 015.8 3.4H10a2.6 2.6 0 012.6 2.6v14a2 2 0 00-2-2H4V5.2z" />
    <path d="M20 5.2a1.8 1.8 0 00-1.8-1.8H14a2.6 2.6 0 00-2.6 2.6v14a2 2 0 012-2H20V5.2z" />
  </>
)
export const IcLayers = make(
  <>
    <path d="M12 3.4l8.4 4.3-8.4 4.3-8.4-4.3L12 3.4z" />
    <path d="M3.6 12.2l8.4 4.3 8.4-4.3M3.6 16.4l8.4 4.3 8.4-4.3" />
  </>
)
export const IcKey = make(
  <>
    <circle cx="8" cy="8" r="4.2" />
    <path d="M11 11l8 8M16.4 16.4l1.8-1.8M19 19l1.8-1.8" />
  </>
)

/* Direction-aware. `flip` is passed the RTL flag by the caller, so one
   component serves both directions instead of two mirrored glyphs. */
export function IcChevron({ size = 16, dir = 'end', flip = false, ...rest }) {
  const forward = dir === 'end' ? !flip : flip
  return (
    <svg style={box(size)} viewBox="0 0 24 24" {...base} {...rest}>
      <path d={forward ? 'M9 5l7 7-7 7' : 'M15 5l-7 7 7 7'} />
    </svg>
  )
}

export function IcChevronDown({ size = 16, ...rest }) {
  return (
    <svg style={box(size)} viewBox="0 0 24 24" {...base} {...rest}>
      <path d="M6 9.5l6 6 6-6" />
    </svg>
  )
}

export function IcArrow({ size = 16, flip = false, ...rest }) {
  return (
    <svg style={box(size)} viewBox="0 0 24 24" {...base} {...rest}>
      <path d={flip ? 'M19 12H5M11 6l-6 6 6 6' : 'M5 12h14M13 6l6 6-6 6'} />
    </svg>
  )
}
