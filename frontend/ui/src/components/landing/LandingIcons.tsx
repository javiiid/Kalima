/**
 * Landing-only icon set.
 *
 * Drawn on the same 24px grid and 1.6 stroke as the product chrome so the
 * marketing page reads as the same object as the app, without pulling the
 * app's nav icons into a page where their meanings differ. All decorative:
 * the control or heading beside each one carries the accessible name.
 *
 * The path data is Lucide's (lucide-static, ISC licence -- free to use and
 * modify, no attribution required in the UI). Inlined rather than taken
 * through `lucide-react`, for the same reason `NavIcon.tsx` inlines its seven:
 * this project ships zero runtime UI dependencies, and a marketing page is not
 * a good place to start. `package.json` has no icon package, so importing one
 * here would not even resolve.
 */
import type { ReactNode } from 'react'

interface IconProps {
  size?: number | undefined
  className?: string | undefined
}

function Svg({ size = 18, className, children }: IconProps & { children: ReactNode }) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.6}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
      focusable="false"
    >
      {children}
    </svg>
  )
}

export function ArrowRightIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M4 12h15" />
      <path d="m13 6 6 6-6 6" />
    </Svg>
  )
}

export function ArrowLeftIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M20 12H5" />
      <path d="m11 6-6 6 6 6" />
    </Svg>
  )
}

export function ArrowDownIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M12 4v15" />
      <path d="m6 13 6 6 6-6" />
    </Svg>
  )
}

export function ArrowUpRightIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M7 17 17 7" />
      <path d="M8 7h9v9" />
    </Svg>
  )
}

export function CheckIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="m4.5 12.5 4.5 4.5L19.5 6.5" />
    </Svg>
  )
}

export function CheckCircleIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="m8.5 12.5 2.5 2.5 4.5-5" />
    </Svg>
  )
}

export function MenuIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M4 7h16" />
      <path d="M4 12h16" />
      <path d="M4 17h16" />
    </Svg>
  )
}

export function CloseIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M6 6l12 12" />
      <path d="M18 6 6 18" />
    </Svg>
  )
}

export function ChevronDownIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="m6 9 6 6 6-6" />
    </Svg>
  )
}

export function BookIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M4 5.5A2.5 2.5 0 0 1 6.5 3H19v15H6.5A2.5 2.5 0 0 0 4 20.5z" />
      <path d="M4 20.5A2.5 2.5 0 0 1 6.5 18H19v3H6.5" />
    </Svg>
  )
}

export function LayersIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="m12 3 9 5-9 5-9-5z" />
      <path d="m3 13 9 5 9-5" />
    </Svg>
  )
}

export function PulseIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M3 12h4l2.5-6 4 12 2.5-6H21" />
    </Svg>
  )
}

export function LibraryIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M4 4v16" />
      <path d="M8 4v16" />
      <path d="M12 5.5 16 4l4 15-4 1.5z" />
    </Svg>
  )
}

export function ExportIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M12 15V3" />
      <path d="m8 7 4-4 4 4" />
      <path d="M4 15v4a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-4" />
    </Svg>
  )
}

export function UploadIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M12 16V4" />
      <path d="m7 9 5-5 5 5" />
      <path d="M4 16v2a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-2" />
    </Svg>
  )
}

export function DownloadIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M12 4v12" />
      <path d="m7 11 5 5 5-5" />
      <path d="M4 18v1a2 2 0 0 0 2 2h12a2 2 0 0 0 2-2v-1" />
    </Svg>
  )
}

export function FileIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
    </Svg>
  )
}

export function DocIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M14 3H7a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2V8z" />
      <path d="M14 3v5h5" />
      <path d="M9 13h6" />
      <path d="M9 17h4" />
    </Svg>
  )
}

export function GlobeIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M3 12h18" />
      <path d="M12 3a14 14 0 0 1 0 18a14 14 0 0 1 0-18z" />
    </Svg>
  )
}

export function QuoteIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M9 7H5.5A1.5 1.5 0 0 0 4 8.5V12h5V7z" />
      <path d="M9 12c0 3-1.5 4.5-4 5" />
      <path d="M19 7h-3.5A1.5 1.5 0 0 0 14 8.5V12h5V7z" />
      <path d="M19 12c0 3-1.5 4.5-4 5" />
    </Svg>
  )
}

export function ShieldIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M12 3 5 6v6c0 4.5 3 7.5 7 9 4-1.5 7-4.5 7-9V6z" />
      <path d="m9 12 2 2 4-4" />
    </Svg>
  )
}

export function SparkleIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M12 3v4" />
      <path d="M12 17v4" />
      <path d="M3 12h4" />
      <path d="M17 12h4" />
      <path d="m6 6 2.5 2.5" />
      <path d="m15.5 15.5 2.5 2.5" />
      <path d="m18 6-2.5 2.5" />
      <path d="m8.5 15.5-2.5 2.5" />
    </Svg>
  )
}

export function ClockIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <circle cx="12" cy="12" r="9" />
      <path d="M12 7v5l3 2" />
    </Svg>
  )
}

export function SearchIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <circle cx="11" cy="11" r="7" />
      <path d="m16 16 4 4" />
    </Svg>
  )
}

export function PauseIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M9 5v14" />
      <path d="M15 5v14" />
    </Svg>
  )
}

export function PlayIcon({ size, className }: IconProps) {
  return (
    <Svg size={size} className={className}>
      <path d="M7 4.5 19 12 7 19.5z" />
    </Svg>
  )
}
