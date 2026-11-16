import type { SettingsIconName } from './tabs'

/**
 * The six tab glyphs, on the same 24px / 1.75 stroke as `NavIcon`.
 *
 * Inlined rather than taken from an icon package: the project ships no runtime
 * UI dependency for six outlines, and the tab list already names them in
 * `tabs.ts`. Every icon is `aria-hidden`; the tab label beside it is the
 * accessible name.
 */
interface SettingsIconProps {
  name: SettingsIconName
  size?: number | undefined
}

export function SettingsIcon({ name, size = 18 }: SettingsIconProps) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      {name === 'general' ? (
        <>
          <path d="M4 6h10" />
          <path d="M18 6h2" />
          <circle cx="16" cy="6" r="2" />
          <path d="M4 12h2" />
          <path d="M10 12h10" />
          <circle cx="8" cy="12" r="2" />
          <path d="M4 18h10" />
          <path d="M18 18h2" />
          <circle cx="16" cy="18" r="2" />
        </>
      ) : null}
      {name === 'translation' ? (
        <>
          <path d="M2 5h12" />
          <path d="M7 2v3" />
          <path d="m4 14 6-6 2-3" />
          <path d="m5 8 6 6" />
          <path d="m22 22-5-10-5 10" />
          <path d="M14 18h6" />
        </>
      ) : null}
      {name === 'reading' ? (
        <>
          <path d="M12 7v14" />
          <path d="M3 18a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1h5a4 4 0 0 1 4 4 4 4 0 0 1 4-4h5a1 1 0 0 1 1 1v13a1 1 0 0 1-1 1h-6a3 3 0 0 0-3 3 3 3 0 0 0-3-3z" />
        </>
      ) : null}
      {name === 'appearance' ? (
        <>
          <path d="M12 22a10 10 0 1 1 10-10c0 2-2 3-4 3h-1a2 2 0 0 0 0 4c0 2-2 3-5 3z" />
          <circle cx="7.5" cy="10.5" r="1" />
          <circle cx="12" cy="7.5" r="1" />
          <circle cx="16.5" cy="10.5" r="1" />
        </>
      ) : null}
      {name === 'notifications' ? (
        <>
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </>
      ) : null}
      {name === 'data' ? (
        <>
          <ellipse cx="12" cy="5" rx="9" ry="3" />
          <path d="M3 5v14a9 3 0 0 0 18 0V5" />
          <path d="M3 12a9 3 0 0 0 18 0" />
        </>
      ) : null}
    </svg>
  )
}
