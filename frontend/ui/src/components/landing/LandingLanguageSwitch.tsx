/**
 * The landing language switcher.
 *
 * A two-segment control rather than the app's single toggle button. On the
 * landing the language is part of the pitch -- the page is about translation --
 * so both options are shown and the current one is marked, instead of a button
 * that only names the language you are not in.
 *
 * It is built on the existing `useLanguage` context, so it shares one source of
 * truth with the rest of the app: `setLang` writes `localStorage['jbook-language']`
 * and sets `<html lang>` and `<html dir>`, and the landing reads `dir` from the
 * same place. There is no second language system here and no local state that
 * could disagree with the provider.
 *
 * Each option names its own language in its own script, so the control is
 * readable whichever side you are on, and each carries `lang` so a screen
 * reader pronounces it correctly rather than in the surrounding language.
 */
import { useLanguage } from '@/i18n/useLanguage.ts'
import type { StringKey } from '@/i18n/fa.ts'
import type { Language } from '@/i18n/lang.ts'
import { GlobeIcon } from './LandingIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
}

const OPTIONS: ReadonlyArray<{ lang: Language; label: string; aria: StringKey }> = [
  { lang: 'en', label: 'EN', aria: 'shell.languageToEn' },
  { lang: 'fa', label: 'فا', aria: 'shell.languageToFa' },
]

export function LandingLanguageSwitch({ t }: Props) {
  const { lang, setLang } = useLanguage()

  return (
    <div
      className="k-lang-switch"
      role="group"
      aria-label={t('shell.language')}
    >
      <GlobeIcon size={14} className="k-lang-switch-icon" />
      {OPTIONS.map((option) => {
        const active = lang === option.lang
        return (
          <button
            key={option.lang}
            type="button"
            className="k-lang-switch-btn"
            lang={option.lang}
            aria-pressed={active}
            aria-label={t(option.aria)}
            onClick={() => {
              // No-op when already active: re-setting the same language would
              // still write storage and re-render the whole page for nothing.
              if (!active) setLang(option.lang)
            }}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}
