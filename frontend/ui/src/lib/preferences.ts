/**
 * The settings page's contract with the backend, as values and decisions.
 *
 * ## Why the decisions are functions here and not in the page
 *
 * `node --test` has no DOM. Anything decidable without one -- what a valid
 * timezone looks like, which fields actually changed, what an imported file is
 * allowed to contain -- lives here so `tests/preferences.test.ts` can drive it
 * directly. The page keeps the rendering and nothing else, which is the same
 * split `lib/reading.ts` and `lib/dashboard.ts` already use.
 *
 * ## Why the schemas are factories
 *
 * The text a user reads for an error is a translated string, and this module
 * cannot call `useLanguage`. Each schema is therefore a factory taking the
 * translator the component already has. A test passes `identityTranslate`; the
 * page passes `t`. Neither has to know about the other.
 */
import { z } from 'zod'
import type { ReadingSettings } from './api.ts'
import type { StringKey } from '../i18n/fa.ts'
import { clampFontSize, clampLineHeight, clampWidth } from './reading.ts'

export type Language = 'fa' | 'en'
export type DateFormat = 'jalali' | 'gregorian' | 'iso'
export type AppearanceTheme = 'light' | 'dark' | 'system'
export type Density = 'comfortable' | 'compact'

export const LANGUAGES: readonly Language[] = ['fa', 'en']
export const DATE_FORMATS: readonly DateFormat[] = ['jalali', 'gregorian', 'iso']
export const APPEARANCE_THEMES: readonly AppearanceTheme[] = ['light', 'dark', 'system']
export const DENSITIES: readonly Density[] = ['comfortable', 'compact']
export const TRANSLATION_MODES: readonly string[] = ['fast']
export const LANGUAGE_CODES: readonly string[] = ['EN', 'FA', 'DE', 'FR', 'AR']
export const NOTIFICATION_EVENTS: readonly string[] = [
  'job.completed',
  'job.failed',
  'job.stopped',
  'quota.warning',
]

export interface GeneralPreferences {
  language: Language
  timezone: string
  date_format: DateFormat
  resume_last_page: boolean
  show_onboarding: boolean
}

export interface TranslationPreferences {
  default_model: string
  mode: string
  style_preset: string
  auto_glossary: boolean
  preserve_voice: boolean
  from_lang: string
  to_lang: string
}

export interface AppearancePreferences {
  theme: AppearanceTheme
  density: Density
  animations: boolean
}

export interface NotificationPreferences {
  email: boolean
  in_app: boolean
  webhook: string
  events: string[]
}

export interface Preferences {
  general: GeneralPreferences
  translation: TranslationPreferences
  reading: ReadingSettings
  appearance: AppearancePreferences
  notifications: NotificationPreferences
}

/** A partial update: only the sections and fields a form actually changed. */
export interface PreferencesPatch {
  general?: Partial<GeneralPreferences>
  translation?: Partial<TranslationPreferences>
  reading?: Partial<ReadingSettings>
  appearance?: Partial<AppearancePreferences>
  notifications?: Partial<NotificationPreferences>
}

export interface PreferencesMeta {
  updated_at: string | null
  is_admin: boolean
  defaults: { 'translation.default_model': string }
  options: {
    style_presets: string[]
    timezones: string[]
    timezone_fallback: boolean
    notification_events: string[]
    translation_modes: string[]
  }
}

/**
 * The client's copy of the server's defaults.
 *
 * Used to render a form before the first response arrives, and to label a field
 * "default (...)". The server's value always wins on load; if the two ever
 * disagree, the server is right and this is the bug.
 */
export const PREFERENCE_DEFAULTS: Omit<Preferences, 'reading'> = {
  general: {
    language: 'fa',
    timezone: 'Asia/Tehran',
    date_format: 'jalali',
    resume_last_page: true,
    show_onboarding: true,
  },
  translation: {
    default_model: '',
    mode: 'fast',
    style_preset: '',
    auto_glossary: false,
    preserve_voice: true,
    from_lang: 'EN',
    to_lang: 'FA',
  },
  appearance: { theme: 'system', density: 'comfortable', animations: true },
  notifications: { email: true, in_app: true, webhook: '', events: ['job.completed', 'job.failed'] },
}

/** Reading fallbacks, mirroring `READING_DEFAULTS` in the backend. */
export const READING_FALLBACKS: ReadingSettings = {
  study_night_mode: false,
  reading_theme: 'light',
  reading_mode: 'bilingual',
  reading_font_size: 18,
  reading_line_height: 1.9,
  reading_width: 760,
  reading_direction: 'auto',
  reading_last_location: null,
  reading_bookmarks: [],
  reading_glossary: true,
}

/**
 * A structural clone that does not need `structuredClone`.
 *
 * `structuredClone` is present in the browsers this app supports, but not
 * guaranteed in every runtime a `node --test` file might run under, and a
 * settings default is plain JSON. `JSON.parse(JSON.stringify(...))` is the
 * honest size of that job.
 */
function clone<T>(value: T): T {
  return JSON.parse(JSON.stringify(value)) as T
}

export function readEmptyPreferences(): Preferences {
  return { ...clone(PREFERENCE_DEFAULTS), reading: { ...READING_FALLBACKS } }
}

/* ------------------------------------------------------------------ */
/* Schemas                                                             */
/* ------------------------------------------------------------------ */

type Translate = (key: StringKey) => string

/** The translation used by tests, and by code with no language context. */
export const identityTranslate: Translate = (key) => key

function isHttpUrl(value: string): boolean {
  try {
    const parsed = new URL(value)
    return parsed.protocol === 'http:' || parsed.protocol === 'https:'
  } catch {
    return false
  }
}

const LOOPBACK_HOSTS = new Set(['127.0.0.1', 'localhost', '::1', '[::1]'])

/**
 * The webhook rule, mirrored from `_clean_webhook` in the backend.
 *
 * Plain `http` is accepted only for a loopback host, because a local receiver
 * is exactly what the local build is for; the exception is loopback-justified
 * and dies at launch, where only https is accepted. The server enforces this
 * too — this copy exists so the field can show the error before the round trip.
 */
export function isAcceptableWebhook(value: string): boolean {
  const trimmed = value.trim()
  if (!trimmed) return true
  if (!isHttpUrl(trimmed)) return false
  const parsed = new URL(trimmed)
  if (parsed.protocol === 'https:') return true
  return LOOPBACK_HOSTS.has(parsed.hostname.toLowerCase())
}

export function generalSchema(t: Translate) {
  return z.object({
    language: z.enum(['fa', 'en']),
    timezone: z
      .string()
      .trim()
      .min(1, t('settings.error.timezone'))
      .max(64, t('settings.error.timezone')),
    date_format: z.enum(['jalali', 'gregorian', 'iso']),
    resume_last_page: z.boolean(),
    show_onboarding: z.boolean(),
  })
}

export function translationSchema() {
  return z.object({
    default_model: z.string(),
    mode: z.enum(['fast']),
    style_preset: z.string(),
    auto_glossary: z.boolean(),
    preserve_voice: z.boolean(),
    from_lang: z.string().min(2).max(8),
    to_lang: z.string().min(2).max(8),
  })
}

export function appearanceSchema() {
  return z.object({
    theme: z.enum(['light', 'dark', 'system']),
    density: z.enum(['comfortable', 'compact']),
    animations: z.boolean(),
  })
}

export function notificationsSchema(t: Translate) {
  return z
    .object({
      email: z.boolean(),
      in_app: z.boolean(),
      webhook: z.string().max(500, t('settings.error.webhook')),
      events: z.array(z.string()),
    })
    .refine((value) => isAcceptableWebhook(value.webhook), {
      message: t('settings.error.webhook'),
      path: ['webhook'],
    })
    .refine((value) => !value.webhook.trim() || value.events.length > 0, {
      message: t('settings.error.events'),
      path: ['events'],
    })
}

export function readingSchema() {
  return z.object({
    reading_font_size: z.number(),
    reading_line_height: z.number(),
    reading_width: z.number(),
    reading_theme: z.enum(['light', 'sepia', 'night', 'contrast']),
    reading_direction: z.enum(['auto', 'rtl', 'ltr']),
    reading_mode: z.enum(['translation', 'original', 'bilingual', 'columns']),
    reading_glossary: z.boolean(),
  })
}

/* ------------------------------------------------------------------ */
/* Diffing and clamping                                                */
/* ------------------------------------------------------------------ */

/**
 * Structural equality for the values a preference can hold.
 *
 * `!==` is enough for strings, numbers and booleans, but not for the two
 * arrays in the contract (`notifications.events`, `reading_bookmarks`) or the
 * `reading_last_location` object: a freshly parsed server response and the
 * client's copy are equal in meaning and different in identity. Comparing by
 * reference would mark a tab dirty the moment it loaded.
 */
function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true
  if (Array.isArray(a) && Array.isArray(b)) {
    return a.length === b.length && a.every((value, index) => sameValue(value, b[index]))
  }
  if (a && b && typeof a === 'object' && typeof b === 'object') {
    const left = a as Record<string, unknown>
    const right = b as Record<string, unknown>
    const keys = Object.keys(left)
    return keys.length === Object.keys(right).length && keys.every((key) => sameValue(left[key], right[key]))
  }
  return false
}

function changedFields<T extends object>(current: T, next: T): Partial<T> | undefined {
  const patch: Partial<T> = {}
  let any = false
  for (const key of Object.keys(next) as (keyof T)[]) {
    if (!sameValue(current[key], next[key])) {
      patch[key] = next[key]
      any = true
    }
  }
  return any ? patch : undefined
}

/**
 * Only what changed, section by section.
 *
 * Sending the whole object would rewrite every row on every save, so two tabs
 * open on two devices would fight over fields neither of them touched. A
 * section with no change is left out entirely, and a patch with nothing in it
 * is empty — which is what the SaveBar and the unsaved-changes guard read.
 */
export function diffPreferences(current: Preferences, next: Preferences): PreferencesPatch {
  const patch: PreferencesPatch = {}
  const general = changedFields(current.general, next.general)
  if (general) patch.general = general
  const translation = changedFields(current.translation, next.translation)
  if (translation) patch.translation = translation
  const appearance = changedFields(current.appearance, next.appearance)
  if (appearance) patch.appearance = appearance
  const notifications = changedFields(current.notifications, next.notifications)
  if (notifications) patch.notifications = notifications
  const reading = changedFields(current.reading, next.reading)
  if (reading) patch.reading = reading
  return patch
}

export function hasChanges(patch: PreferencesPatch): boolean {
  return Object.values(patch).some((section) => section && Object.keys(section).length > 0)
}

export function countChanges(patch: PreferencesPatch): number {
  return Object.values(patch).reduce(
    (total, section) => total + (section ? Object.keys(section).length : 0),
    0,
  )
}

/** A full preferences object with a partial patch applied, section by section. */
export function applyPreferencesPatch(current: Preferences, patch: PreferencesPatch): Preferences {
  return {
    general: { ...current.general, ...patch.general },
    translation: { ...current.translation, ...patch.translation },
    reading: { ...current.reading, ...patch.reading },
    appearance: { ...current.appearance, ...patch.appearance },
    notifications: { ...current.notifications, ...patch.notifications },
  }
}

/** The reader's own clamps, applied before a value is previewed or sent. */
export function clampReadingSettings(patch: Partial<ReadingSettings>): Partial<ReadingSettings> {
  const clamped: Partial<ReadingSettings> = { ...patch }
  if (typeof clamped.reading_font_size === 'number') {
    clamped.reading_font_size = clampFontSize(clamped.reading_font_size)
  }
  if (typeof clamped.reading_line_height === 'number') {
    clamped.reading_line_height = clampLineHeight(clamped.reading_line_height)
  }
  if (typeof clamped.reading_width === 'number') {
    clamped.reading_width = clampWidth(clamped.reading_width)
  }
  return clamped
}

/* ------------------------------------------------------------------ */
/* Export / import                                                     */
/* ------------------------------------------------------------------ */

export const EXPORT_KIND = 'kalima.settings'
export const EXPORT_VERSION = 1
/** A settings file is a few kilobytes; this is the ceiling for a bad one. */
export const MAX_IMPORT_BYTES = 64 * 1024

export interface ExportedSettings {
  kind: typeof EXPORT_KIND
  version: number
  exported_at: string
  preferences: PreferencesPatch
}

/**
 * The exported document.
 *
 * The reading section is included minus the two position keys: where a reader
 * was in a book, and what they bookmarked, are not settings and must not travel
 * between accounts inside a preferences file.
 */
export function exportPreferences(preferences: Preferences, now: Date): ExportedSettings {
  const { reading_last_location: _location, reading_bookmarks: _bookmarks, ...reading } =
    preferences.reading
  return {
    kind: EXPORT_KIND,
    version: EXPORT_VERSION,
    exported_at: now.toISOString(),
    preferences: {
      general: preferences.general,
      translation: preferences.translation,
      appearance: preferences.appearance,
      notifications: preferences.notifications,
      reading,
    },
  }
}

export function serialiseExport(payload: ExportedSettings): string {
  return `${JSON.stringify(payload, null, 2)}\n`
}

export type ImportErrorCode = 'too-large' | 'not-json' | 'wrong-kind' | 'too-new' | 'invalid'

/**
 * Parse an imported settings file, or say exactly what is wrong with it.
 *
 * A file from a newer version is refused rather than partially applied: a field
 * this build does not know about would be dropped silently, and the user would
 * be told their settings had been imported.
 */
export function parseImportedPreferences(
  text: string,
  t: Translate = identityTranslate,
): PreferencesPatch {
  if (text.length > MAX_IMPORT_BYTES) throw new ImportError('too-large')
  let parsed: unknown
  try {
    parsed = JSON.parse(text)
  } catch {
    throw new ImportError('not-json')
  }
  if (!parsed || typeof parsed !== 'object') throw new ImportError('not-json')
  const document_ = parsed as Partial<ExportedSettings>
  if (document_.kind !== EXPORT_KIND) throw new ImportError('wrong-kind')
  const version = Number(document_.version)
  if (!Number.isFinite(version) || version < 1) throw new ImportError('invalid')
  if (version > EXPORT_VERSION) throw new ImportError('too-new')

  const source = (document_.preferences ?? {}) as Record<string, unknown>
  const patch: PreferencesPatch = {}
  const take = <K extends keyof PreferencesPatch>(key: K, schema: z.ZodType) => {
    if (source[key] === undefined) return
    const result = schema.safeParse(source[key])
    if (!result.success) throw new ImportError('invalid')
    patch[key] = result.data as PreferencesPatch[K]
  }
  take('general', generalSchema(t))
  take('translation', translationSchema())
  take('appearance', appearanceSchema())
  take('notifications', notificationsSchema(t))
  take('reading', readingSchema())
  return patch
}

export class ImportError extends Error {
  readonly code: ImportErrorCode

  constructor(code: ImportErrorCode) {
    super(code)
    this.name = 'ImportError'
    this.code = code
  }
}

export function importErrorMessageKey(code: ImportErrorCode): StringKey {
  switch (code) {
    case 'too-large':
      return 'settings.data.import.tooLarge'
    case 'not-json':
      return 'settings.data.import.notJson'
    case 'wrong-kind':
      return 'settings.data.import.wrongKind'
    case 'too-new':
      return 'settings.data.import.tooNew'
    default:
      return 'settings.data.import.invalid'
  }
}

/* ------------------------------------------------------------------ */
/* Display helpers                                                     */
/* ------------------------------------------------------------------ */

/**
 * A date shown in the chosen calendar, for the live sample beside the picker.
 *
 * `Intl` supplies the Persian calendar rather than a hand-rolled conversion,
 * because a hand-rolled one is where leap years go wrong. The locale is pinned
 * and the digits are latn: this previews a *format*, not a locale, so the
 * sample does not change shape when the interface language does.
 */
export function formatDateSample(date: Date, format: DateFormat): string {
  if (format === 'iso') {
    const month = String(date.getMonth() + 1).padStart(2, '0')
    const day = String(date.getDate()).padStart(2, '0')
    return `${date.getFullYear()}-${month}-${day}`
  }
  const calendar = format === 'jalali' ? 'persian' : 'gregory'
  try {
    const parts = new Intl.DateTimeFormat(`en-u-ca-${calendar}-nu-latn`, {
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
      timeZone: 'UTC',
    }).formatToParts(date)
    const part = (type: Intl.DateTimeFormatPartTypes) =>
      parts.find((item) => item.type === type)?.value ?? ''
    // Assembled in a fixed order rather than the locale's: the sample previews
    // the *format*, and `en` would otherwise print Jalali as `08/17/1405 AP`.
    return `${part('year')}/${part('month')}/${part('day')}`
  } catch {
    return date.toISOString().slice(0, 10)
  }
}
