/**
 * Pure helpers for the account page.
 *
 * The page asks three questions -- "is my setup ready?", "what should I do
 * next?" and "have I actually used this?" -- and each answer is a decision
 * rather than a rendering detail. Keeping those decisions here means they can
 * be asserted by `node --test` without a DOM, which is the same reason
 * `dashboard.ts` and `library.ts` exist.
 *
 * Nothing here invents a number. Every input comes from a real endpoint; a
 * missing provider answer stays `null` (unknown) rather than being read as
 * "not configured", because those are different facts.
 */

export type ReadinessId = 'provider' | 'book' | 'translation' | 'glossary' | 'memory'

export interface ReadinessItem {
  id: ReadinessId
  done: boolean
  /** Where the reader goes to finish this step. */
  to: string
}

export interface ReadinessInput {
  /** `null` means the provider query has not answered yet. */
  hasKey: boolean | null
  books: number
  completedJobs: number
  glossaries: number
  memoryEntries: number
}

/**
 * The five durable facts that make a first translation possible.
 *
 * A provider test is deliberately not one of them: it is a session event, not
 * a stored fact, so counting it would make the checklist reset on every
 * reload.
 */
export function readinessChecklist(input: ReadinessInput): ReadinessItem[] {
  return [
    { id: 'provider', done: input.hasKey === true, to: '/settings' },
    { id: 'book', done: input.books > 0, to: '/workspace' },
    { id: 'translation', done: input.completedJobs > 0, to: '/jobs' },
    { id: 'glossary', done: input.glossaries > 0, to: '/library' },
    { id: 'memory', done: input.memoryEntries > 0, to: '/library' },
  ]
}

export function readinessPercent(items: ReadinessItem[]): number {
  if (items.length === 0) return 0
  const done = items.filter((item) => item.done).length
  return Math.round((done / items.length) * 100)
}

export type NextActionId = 'provider' | 'upload' | 'monitor' | 'read'

export interface NextAction {
  id: NextActionId
  to: string
}

/**
 * One recommendation, in priority order.
 *
 * A missing key blocks everything, so it wins. Otherwise an empty library is
 * the real next step even if old jobs exist, and running work outranks reading
 * because it is the only state that changes on its own.
 */
export function nextAction(input: {
  hasKey: boolean | null
  books: number
  activeProjects: number
  completedJobs: number
}): NextAction {
  if (input.hasKey === false) return { id: 'provider', to: '/settings' }
  if (input.books === 0) return { id: 'upload', to: '/workspace' }
  if (input.activeProjects > 0) return { id: 'monitor', to: '/jobs' }
  if (input.completedJobs > 0) return { id: 'read', to: '/library' }
  return { id: 'upload', to: '/workspace' }
}

/**
 * A one- or two-letter monogram.
 *
 * `Array.from` rather than `name[0]`: a name that starts with an emoji or an
 * astral character would otherwise be cut in half and render as a replacement
 * box. Persian and Latin both take the first letter of the first and last
 * words, which reads as initials in either script.
 */
export function initials(name: string, fallback = 'K'): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  if (words.length === 0) return fallback
  const first = Array.from(words[0] ?? '')[0] ?? ''
  const last = words.length > 1 ? Array.from(words[words.length - 1] ?? '')[0] ?? '' : ''
  const value = (first + last).toUpperCase()
  return value || fallback
}

export interface ReadingDay {
  day: string
  pages: number
}

/**
 * A dense, oldest-first window ending on `todayISO`.
 *
 * `GET /api/reading/stats` returns only days that have events, so plotting it
 * directly would compress the gaps and make a three-day streak look like a
 * month of reading. The window is rebuilt from the calendar instead, and a day
 * with no events is a real zero.
 */
export function fillReadingSeries(
  perDay: ReadingDay[],
  days: number,
  todayISO: string,
): ReadingDay[] {
  const count = Math.max(1, Math.trunc(days))
  const byDay = new Map(perDay.map((entry) => [entry.day, entry.pages]))
  const end = Date.parse(`${todayISO}T00:00:00Z`)
  if (Number.isNaN(end)) return []
  const series: ReadingDay[] = []
  for (let offset = count - 1; offset >= 0; offset -= 1) {
    const day = new Date(end - offset * 86_400_000).toISOString().slice(0, 10)
    series.push({ day, pages: byDay.get(day) ?? 0 })
  }
  return series
}
