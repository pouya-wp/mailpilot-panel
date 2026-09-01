/* Icon sizes are DESIGN pixels, on the same 2000 x 1500 frame the
   stylesheets use — where 1rem = 10 design px (see base.css).

   Emitting rem rather than a raw pixel number is what keeps an icon in
   proportion to the control around it. With a bare `width={16}` the glyph
   held its size while every button, gap and radius around it scaled with the
   viewport, so on a laptop the small round buttons ended up with icons larger
   than the buttons themselves. */
const box = (size) => ({ width: `${size / 10}rem`, height: `${size / 10}rem` })

const base = {
  fill: 'none',
  stroke: 'currentColor',
  strokeWidth: 1.6,
  strokeLinecap: 'round',
  strokeLinejoin: 'round',
}

export const Logo = ({ size = 22 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" fill="none">
    <path
      d="M12 2.6l2.2 5.3 5.3 2.2-5.3 2.2L12 17.6l-2.2-5.3L4.5 10.1l5.3-2.2L12 2.6z"
      fill="currentColor"
      opacity="0.95"
    />
    <path d="M18.4 15.4l.9 2.1 2.1.9-2.1.9-.9 2.1-.9-2.1-2.1-.9 2.1-.9.9-2.1z" fill="currentColor" opacity="0.6" />
  </svg>
)

export const ChevronDown = ({ size = 13 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M6 9l6 6 6-6" />
  </svg>
)

export const ChevronLeft = ({ size = 13 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M15 5l-7 7 7 7" />
  </svg>
)

export const ChevronRight = ({ size = 13 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M9 5l7 7-7 7" />
  </svg>
)

export const Switch = ({ size = 14 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M7 4v14M7 18l-3-3M17 20V6M17 6l3 3" />
  </svg>
)

export const Mail = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <rect x="3" y="5" width="18" height="14" rx="3" />
    <path d="M3.5 7.5l7.3 5a2 2 0 002.4 0l7.3-5" />
  </svg>
)

export const Rocket = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M13.5 3.5c3.5-.6 6.6 2.5 6 6-.5 3-3.4 6.2-7 8.5l-4-4c2.3-3.6 5.5-6.5 8.5-7z" />
    <path d="M8.5 14l-3 3M6.8 11.2L4 12l1 2M12.8 17.2L12 20l2 1" />
    <circle cx="14.8" cy="9.2" r="1.5" />
  </svg>
)

export const Target = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <circle cx="12" cy="12" r="8.5" />
    <circle cx="12" cy="12" r="4.5" />
    <circle cx="12" cy="12" r="1" fill="currentColor" />
  </svg>
)

export const Percent = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M19 5L5 19" />
    <circle cx="7.5" cy="7.5" r="2.5" />
    <circle cx="16.5" cy="16.5" r="2.5" />
  </svg>
)

export const Users = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <circle cx="9" cy="8.5" r="3.2" />
    <path d="M3.5 19c.6-3.1 2.8-4.8 5.5-4.8s4.9 1.7 5.5 4.8" />
    <path d="M16 5.6a3 3 0 010 5.8M17.6 14.6c2 .6 3.3 2.1 3.7 4.4" />
  </svg>
)

export const Clock = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 7.5V12l3 1.8" />
  </svg>
)

export const Bolt = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M13 3L5.5 13.2h5.2L10 21l7.6-10.4h-5.2L13 3z" />
  </svg>
)

export const TrendUp = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M4 15.5l5-5 3.2 3.2L20 6.5" />
    <path d="M15.5 6.5H20V11" />
  </svg>
)

export const Cursor = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M5.5 4.2l13.3 6.4-5.6 1.6-2.2 5.4-5.5-13.4z" />
  </svg>
)

export const Info = ({ size = 12 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <circle cx="12" cy="12" r="8.5" />
    <path d="M12 11v5M12 8h.01" />
  </svg>
)

export const Check = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M5 12.5l4.5 4.5L19 7" />
  </svg>
)

export const Flame = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M12 3.2c3 3.1 5.6 5.4 5.6 9a5.6 5.6 0 11-11.2 0c0-1.6.6-2.9 1.6-4.2.5 1 1.2 1.6 2 1.9-.4-2.6.3-4.9 2-6.7z" />
  </svg>
)

export const XSocial = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" fill="currentColor">
    <path d="M17.5 3h3l-6.6 7.5L21.8 21h-6l-4.7-6.1L5.6 21h-3l7-8-6.9-10h6.1l4.3 5.6L17.5 3zm-1 16.2h1.7L8 4.7H6.2l10.3 14.5z" />
  </svg>
)

export const Discord = ({ size = 16 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" fill="currentColor">
    <path d="M19.3 5.6A16 16 0 0015.4 4l-.2.5c1.3.3 2.4.8 3.4 1.5-1.7-.8-3.4-1.3-5.6-1.3s-3.9.5-5.6 1.3c1-.7 2.2-1.2 3.4-1.5L10.6 4a16 16 0 00-3.9 1.6C4.3 9.2 3.7 12.7 4 16.2A15 15 0 008.5 18l.9-1.4c-.8-.3-1.5-.7-2.1-1.1l.5-.4c2 .9 4 1.4 6.2 1.4s4.2-.5 6.2-1.4l.5.4c-.6.4-1.3.8-2.1 1.1l.9 1.4a15 15 0 004.5-1.8c.4-4.1-.6-7.6-2.7-10.6zM9.7 14c-.9 0-1.6-.8-1.6-1.8s.7-1.8 1.6-1.8 1.6.8 1.6 1.8-.7 1.8-1.6 1.8zm4.6 0c-.9 0-1.6-.8-1.6-1.8s.7-1.8 1.6-1.8 1.6.8 1.6 1.8-.7 1.8-1.6 1.8z" />
  </svg>
)

export const Telegram = ({ size = 16 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" fill="currentColor">
    <path d="M21.3 4.3L2.9 11.4c-1.1.4-1.1 1.1-.2 1.4l4.6 1.4 1.8 5.4c.2.6.4.8 1 .8.4 0 .6-.2.9-.5l2.2-2.2 4.6 3.4c.8.5 1.4.2 1.6-.8l3-14c.3-1.2-.5-1.8-1.1-1zM7.9 13.5l9.9-6.2c.4-.3.8-.1.5.2l-8.4 7.6-.3 3.3-1.7-4.9z" />
  </svg>
)

export const Headset = ({ size = 17 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M4.5 14v-2a7.5 7.5 0 0115 0v2" />
    <rect x="2.8" y="13.4" width="3.6" height="5.4" rx="1.6" />
    <rect x="17.6" y="13.4" width="3.6" height="5.4" rx="1.6" />
    <path d="M19.4 18.8c0 1.5-1.4 2.4-3.2 2.5" />
  </svg>
)

export const Trophy = ({ size = 15 }) => (
  <svg style={box(size)} viewBox="0 0 24 24" {...base}>
    <path d="M7.5 4h9v4.6a4.5 4.5 0 11-9 0V4z" />
    <path d="M7.5 5.6H5A2.4 2.4 0 007.5 9M16.5 5.6H19A2.4 2.4 0 0116.5 9" />
    <path d="M10 13.2V16h4v-2.8M8.5 20h7" />
  </svg>
)
