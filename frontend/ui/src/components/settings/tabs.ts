/**
 * The settings page's tab model, in one place.
 *
 * A `.ts` and not a `.tsx` for the same reason `components/nav.ts` is: it holds
 * no JSX, so `node --test` can import it and assert the order, the keys and the
 * URL parsing without a DOM. The page reads this list; it does not restate it.
 *
 * The order is deliberate: personal settings first (general, translation,
 * reading, appearance, notifications), then the advanced ones (diagnostics,
 * system), and data last because it is the only tab with destructive actions.
 * The groups are rendered as headings in the rail; the keyboard order stays
 * this flat order.
 */
import type { StringKey } from '../../i18n/fa.ts'

export type SettingsTabKey =
  | 'general'
  | 'translation'
  | 'reading'
  | 'appearance'
  | 'notifications'
  | 'diagnostics'
  | 'system'
  | 'data'

export type SettingsIconName = SettingsTabKey
export type SettingsTabGroup = 'personal' | 'advanced'

export interface SettingsTab {
  key: SettingsTabKey
  labelKey: StringKey
  icon: SettingsIconName
  group: SettingsTabGroup
}

export const SETTINGS_TABS: readonly SettingsTab[] = [
  { key: 'general', labelKey: 'settings.tab.general', icon: 'general', group: 'personal' },
  { key: 'translation', labelKey: 'settings.tab.translation', icon: 'translation', group: 'personal' },
  { key: 'reading', labelKey: 'settings.tab.reading', icon: 'reading', group: 'personal' },
  { key: 'appearance', labelKey: 'settings.tab.appearance', icon: 'appearance', group: 'personal' },
  { key: 'notifications', labelKey: 'settings.tab.notifications', icon: 'notifications', group: 'personal' },
  { key: 'diagnostics', labelKey: 'settings.tab.diagnostics', icon: 'diagnostics', group: 'advanced' },
  { key: 'system', labelKey: 'settings.tab.system', icon: 'system', group: 'advanced' },
  { key: 'data', labelKey: 'settings.tab.data', icon: 'data', group: 'advanced' },
]

export const SETTINGS_TAB_STORAGE_KEY = 'kalima-settings-tab'

const KEYS = new Set<string>(SETTINGS_TABS.map((tab) => tab.key))

/**
 * A tab key, or `general` for anything else.
 *
 * A bad `?tab=` is a stale link, not an error: the page opens on the first tab
 * rather than on a blank panel or a 404. `general` is the fallback because it
 * is the tab whose absence would be least surprising.
 */
export function parseSettingsTab(value: string | null | undefined): SettingsTabKey {
  return value && KEYS.has(value) ? (value as SettingsTabKey) : 'general'
}

/**
 * The tab named by a query string.
 *
 * `URLSearchParams` is used rather than a regex so `?tab=reading&x=1` and a
 * repeated parameter both behave the way a browser would make them behave.
 */
export function settingsTabFromSearch(search: string): SettingsTabKey {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search)
  return parseSettingsTab(params.get('tab'))
}

export function settingsTabIndex(key: SettingsTabKey): number {
  return SETTINGS_TABS.findIndex((tab) => tab.key === key)
}

/** The tab `delta` steps away, wrapping at both ends. */
export function nextSettingsTab(key: SettingsTabKey, delta: number): SettingsTabKey {
  const index = settingsTabIndex(key)
  if (index < 0) return SETTINGS_TABS[0]?.key ?? 'general'
  const length = SETTINGS_TABS.length
  return SETTINGS_TABS[(((index + delta) % length) + length) % length]?.key ?? 'general'
}

/** The URL for a tab, so the address bar and a shared link agree. */
export function settingsTabHref(key: SettingsTabKey): string {
  return `/settings?tab=${key}`
}

/** The tab to show when the URL says nothing: the last one used, else general. */
export function storedSettingsTab(): SettingsTabKey {
  try {
    return parseSettingsTab(localStorage.getItem(SETTINGS_TAB_STORAGE_KEY))
  } catch {
    return 'general'
  }
}

export function storeSettingsTab(key: SettingsTabKey): void {
  try {
    localStorage.setItem(SETTINGS_TAB_STORAGE_KEY, key)
  } catch {
    // Private mode: the tab lives for this visit only.
  }
}
