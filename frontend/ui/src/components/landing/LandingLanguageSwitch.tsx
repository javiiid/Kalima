/**
 * The landing language switcher.
 *
 * Closed, it is the globe alone: one compact control in a bar that already has
 * a logo, four links, a login and a CTA. The two-segment EN/FA toggle it used
 * to be spent 80px of header on two words a visitor can read in the menu.
 *
 * Open, it is a short list of language *names* -- "English" and "فارسی" -- each
 * written in its own script, so the control is legible whichever side you are
 * on. No flags, no country codes, no abbreviations: a flag is a country and a
 * language is not, and "EN"/"FA" are ISO tags, not names.
 *
 * It is built on the existing `useLanguage` context, so it shares one source of
 * truth with the rest of the app: `setLang` writes `localStorage['jbook-language']`
 * and sets `<html lang>` and `<html dir>`, and the landing reads `dir` from the
 * same place. There is no second language system here and no local state that
 * could disagree with the provider -- the only local state is whether the menu
 * is open, which is not language state.
 *
 * The menu is always mounted and toggled with `data-open`, so it can animate
 * out as well as in; `visibility` is what keeps it out of the tab order while
 * closed, and its transition delay is what lets the exit finish first.
 */
import { useCallback, useEffect, useId, useRef, useState } from 'react'
import { useLanguage } from '@/i18n/useLanguage.ts'
import type { StringKey } from '@/i18n/fa.ts'
import type { Language } from '@/i18n/lang.ts'
import { GlobeIcon } from './LandingIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
  /**
   * Render the list inline and always open, with no globe button. Used inside
   * the mobile sheet, where a popup would be clipped by the sheet's own scroll
   * container and a button that opens an already-visible list is a dead
   * control. The language state is the same context either way.
   */
  inline?: boolean
}

/**
 * The name of each language in its own script. Deliberately not translated
 * through `t`: a language picker that renames the languages when you switch is
 * a picker you cannot use to switch back.
 */
const OPTIONS: ReadonlyArray<{ lang: Language; label: string; aria: StringKey }> = [
  { lang: 'en', label: 'English', aria: 'shell.languageToEn' },
  { lang: 'fa', label: 'فارسی', aria: 'shell.languageToFa' },
]

export function LandingLanguageSwitch({ t, inline = false }: Props) {
  const { lang, setLang } = useLanguage()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement | null>(null)
  const buttonRef = useRef<HTMLButtonElement | null>(null)
  const menuRef = useRef<HTMLDivElement | null>(null)
  const menuId = useId()
  // Inline is always open; the popup follows its own state.
  const shown = inline || open

  const close = useCallback((returnFocus: boolean) => {
    setOpen(false)
    if (returnFocus) buttonRef.current?.focus()
  }, [])

  // Escape closes from anywhere inside the control and hands focus back to the
  // globe, so a keyboard user is never left with focus on a hidden option.
  useEffect(() => {
    if (!shown || inline) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') {
        event.stopPropagation()
        close(true)
      }
    }
    document.addEventListener('keydown', onKey)
    return () => document.removeEventListener('keydown', onKey)
  }, [shown, inline, close])

  // A pointer press anywhere outside the control closes it. `pointerdown`
  // rather than `click` so the menu is gone before the page behind reacts.
  useEffect(() => {
    if (!shown || inline) return
    const onDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onDown)
    return () => document.removeEventListener('pointerdown', onDown)
  }, [shown, inline])

  // Opening moves focus to the selected option, so the next key press is
  // already on the list rather than on the globe.
  useEffect(() => {
    if (!open || inline) return
    const active = menuRef.current?.querySelector<HTMLElement>('[aria-selected="true"]')
    active?.focus()
  }, [open, inline])

  const choose = (next: Language) => {
    // No-op when already active: re-setting the same language would still
    // write storage and re-render the whole page for nothing.
    if (next !== lang) setLang(next)
    if (!inline) close(true)
  }

  return (
    <div
      className="k-lang"
      ref={rootRef}
      data-open={shown ? 'true' : 'false'}
    >
      {inline ? null : (
        <button
          ref={buttonRef}
          type="button"
          className="k-lang-btn"
          aria-haspopup="listbox"
          aria-expanded={open}
          aria-controls={menuId}
          aria-label={t('shell.language')}
          onClick={() => setOpen((value) => !value)}
          onKeyDown={(event) => {
            // ArrowDown opens onto the list, the way a select does.
            if (event.key === 'ArrowDown' && !open) {
              event.preventDefault()
              setOpen(true)
            }
          }}
        >
          <GlobeIcon size={16} className="k-lang-globe" />
        </button>
      )}

      <div
        ref={menuRef}
        id={menuId}
        className="k-lang-menu"
        role="listbox"
        aria-label={t('shell.language')}
      >
        {OPTIONS.map((option) => {
          const active = lang === option.lang
          return (
            <button
              key={option.lang}
              type="button"
              role="option"
              aria-selected={active}
              aria-label={t(option.aria)}
              className="k-lang-option"
              lang={option.lang}
              tabIndex={shown ? 0 : -1}
              onClick={() => choose(option.lang)}
            >
              <span className="k-lang-option-name">{option.label}</span>
              {/* The tick is the active marker; `aria-selected` is what a
                  screen reader reads, so the glyph itself is decorative. */}
              <span className="k-lang-option-tick" aria-hidden="true">
                <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2.2} strokeLinecap="round" strokeLinejoin="round">
                  <path d="m5 12.5 4.5 4.5L19 7" />
                </svg>
              </span>
            </button>
          )
        })}
      </div>
    </div>
  )
}
