/**
 * The auth page's own icons.
 *
 * Kept separate from `landing/LandingIcons` because these are form chrome
 * (an eye, a lock, an arrow back) and the landing's set is marketing iconography
 * (a book, a pulse, a sparkle). Sharing one file would mean the auth page
 * imports six icons it never draws.
 *
 * All of them are `currentColor` and `aria-hidden`: every one sits inside a
 * control that already has an accessible name, so announcing the glyph too
 * would read the control twice.
 */

interface IconProps {
  size?: number
  className?: string
}

const base = (size: number) => ({
  width: size,
  height: size,
  viewBox: '0 0 24 24',
  fill: 'none' as const,
  stroke: 'currentColor' as const,
  strokeWidth: 1.8,
  strokeLinecap: 'round' as const,
  strokeLinejoin: 'round' as const,
  'aria-hidden': true,
  focusable: 'false' as const,
})

export function EyeIcon({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M2.2 12S5.6 5.5 12 5.5 21.8 12 21.8 12 18.4 18.5 12 18.5 2.2 12 2.2 12Z" />
      <circle cx="12" cy="12" r="3.1" />
    </svg>
  )
}

export function EyeOffIcon({ size = 18, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M9.9 5.8A9.6 9.6 0 0 1 12 5.5c6.4 0 9.8 6.5 9.8 6.5a17 17 0 0 1-2.7 3.6" />
      <path d="M6.4 7.3A16.7 16.7 0 0 0 2.2 12s3.4 6.5 9.8 6.5a9.4 9.4 0 0 0 3.9-.8" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
      <path d="M3.5 3.5l17 17" />
    </svg>
  )
}

export function ArrowLeftIcon({ size = 16, className }: IconProps) {
  return (
    <svg {...base(size)} className={className}>
      <path d="M19 12H5" />
      <path d="m11 18-6-6 6-6" />
    </svg>
  )
}
