import { useCallback, useEffect, useState } from 'react'

/**
 * Storage key shared with the Python pages so the theme never resets while
 * both UIs coexist.
 *
 * The product was renamed to KALIMA and this key was deliberately not renamed.
 * It is a preference already written into every existing user's
 * localStorage under the old name; changing it would silently reset their
 * theme to light, and since both UIs read the same key, changing it in one
 * place would desynchronise them. 31 references across the two codebases
 * depend on the exact string.
 *
 * A rename is only safe as a migration: read the old key, write the new one.
 * That is a deliberate task, not a rename.
 */
export const THEME_KEY = 'jbook-study-dark'

/** The resolved theme: what is actually drawn. */
export type Theme = 'light' | 'dark'

/**
 * The stored choice. `system` is a real third state, not the absence of one:
 * it means "follow the operating system", and `useTheme` tracks `matchMedia`
 * while it is selected.
 *
 * The legacy key holds `'1'`/`'0'`; `system` is stored as *no key* so the
 * Python pages, which only understand the two-value key, keep working.
 */
export type ThemeChoice = Theme | 'system'

/** Fired after `setThemeChoice` so every mounted `useTheme` agrees at once. */
export const THEME_EVENT = 'kalima-theme-change'

/**
 * What the operating system asks for.
 *
 * `localStorage` is the wrong default on a phone. A reader who set their
 * handset to dark mode and then opened this app got a white page, because
 * "no stored preference" was read as "light". On a desktop that is a shrug; on
 * a phone it is the app looking broken at 2am.
 *
 * Wrapped because `matchMedia` is absent in some non-browser hosts, and a
 * missing API must not take the theme down.
 */
export function systemPrefersDark(): boolean {
  try {
    return window.matchMedia('(prefers-color-scheme: dark)').matches
  } catch {
    return false
  }
}

/**
 * The stored choice, or `system` when the reader has never chosen.
 *
 * The distinction matters: no key means "follow the system", while `'0'`
 * means "I picked light even though my phone is dark". Collapsing them throws
 * away the second kind of choice on every load.
 */
export function storedThemeChoice(): ThemeChoice {
  try {
    const value = localStorage.getItem(THEME_KEY)
    return value === '1' ? 'dark' : value === '0' ? 'light' : 'system'
  } catch {
    return 'system'
  }
}

function resolve(choice: ThemeChoice): Theme {
  return choice === 'system' ? (systemPrefersDark() ? 'dark' : 'light') : choice
}

/** Applies a choice to `<html>` and returns the resolved theme. */
export function applyThemeChoice(choice: ThemeChoice): Theme {
  const theme = resolve(choice)
  document.documentElement.classList.toggle('dark', theme === 'dark')
  return theme
}

/** Applies the theme before first paint to avoid a light flash on dark mode. */
export function applyStoredTheme(): Theme {
  return applyThemeChoice(storedThemeChoice())
}

/**
 * Writes and applies a choice, then tells every mounted hook.
 *
 * `system` removes the key rather than writing a third value, so the Python
 * pages -- which read `'1'`/`'0'` -- see "no preference" and follow their own
 * system default, exactly as this does.
 */
export function setThemeChoice(choice: ThemeChoice): void {
  try {
    if (choice === 'system') localStorage.removeItem(THEME_KEY)
    else localStorage.setItem(THEME_KEY, choice === 'dark' ? '1' : '0')
  } catch {
    // Private-mode storage failure must not break the toggle in memory.
  }
  applyThemeChoice(choice)
  try {
    window.dispatchEvent(new CustomEvent(THEME_EVENT))
  } catch {
    // No `window` (a test host): the caller still has the applied class.
  }
}

export function useTheme() {
  const [choice, setChoiceState] = useState<ThemeChoice>(storedThemeChoice)
  // Derived rather than stored, so a system change is picked up without a
  // second state variable that could disagree with this one.
  const theme: Theme = resolve(choice)

  useEffect(() => {
    applyThemeChoice(choice)
  }, [choice])

  /* Stay in step with the settings page and with other tabs. The custom event
   * carries an in-page change; `storage` carries a change made in another tab
   * (that event does not fire in the tab that wrote the value). */
  useEffect(() => {
    const sync = () => setChoiceState(storedThemeChoice())
    window.addEventListener(THEME_EVENT, sync)
    window.addEventListener('storage', sync)
    return () => {
      window.removeEventListener(THEME_EVENT, sync)
      window.removeEventListener('storage', sync)
    }
  }, [])

  /* Follow the system while the reader has not chosen.
   *
   * The listener is only attached while `choice` is `system`. Once someone has
   * pressed the toggle the stored value wins, which is what they asked for --
   * and it is also what keeps this UI and the Python pages agreeing, since both
   * read the same key and neither can end up on a theme the other does not
   * know about. */
  useEffect(() => {
    if (choice !== 'system') return
    let query: MediaQueryList
    try {
      query = window.matchMedia('(prefers-color-scheme: dark)')
    } catch {
      return
    }
    const onChange = () => setChoiceState('system')
    query.addEventListener('change', onChange)
    return () => query.removeEventListener('change', onChange)
  }, [choice])

  const setTheme = useCallback((next: Theme) => {
    setChoiceState(next)
    setThemeChoice(next)
  }, [])

  const choose = useCallback((next: ThemeChoice) => {
    setChoiceState(next)
    setThemeChoice(next)
  }, [])

  const toggle = useCallback(() => {
    setTheme(document.documentElement.classList.contains('dark') ? 'light' : 'dark')
  }, [setTheme])

  return {
    theme,
    choice,
    setTheme,
    setThemeChoice: choose,
    toggle,
    followsSystem: choice === 'system',
  }
}
