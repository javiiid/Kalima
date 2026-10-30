/**
 * Reading-setting decisions, asserted without a DOM.
 *
 * The bounds below mirror the server validation on
 * `PUT /api/reader/settings` (`app/web.py`), so the settings controls can
 * clamp instantly instead of waiting for the round trip. The server remains
 * authoritative and re-clamps everything; these only keep the slider and the
 * selects from ever offering a value the server would refuse.
 *
 * `node --test` has no DOM, so the decisions live here as plain functions
 * and `tests/reading.test.ts` drives them directly. The page keeps the
 * rendering and nothing else.
 */

import type { Bookmark, ReadingSettings, ReadingTheme } from './api.ts'

/** Display modes the reader port implements. */
export type ReaderMode = 'translation' | 'original' | 'bilingual' | 'columns'

/**
 * The mode for a stored value.
 *
 * Unknown values fall back to `bilingual` rather than the server's
 * `translation` default: this port opens on the paired view, and a mode the
 * client does not know must render something rather than nothing.
 */
export function toReaderMode(value: string | undefined): ReaderMode {
  return value === 'translation' ||
    value === 'original' ||
    value === 'bilingual' ||
    value === 'columns'
    ? value
    : 'bilingual'
}

/** The mode buttons, in the order the Python settings sheet lists them. */
export const READER_MODES: readonly ReaderMode[] = [
  'translation',
  'original',
  'bilingual',
  'columns',
]

/**
 * Reader surface themes, in the Python swatch order
 * (`app/reader/page.py`: روشن / گرم / شب / کنتراست).
 */
export const READING_THEMES: readonly ReadingTheme[] = ['light', 'sepia', 'night', 'contrast']

/**
 * The theme for a stored value, mirroring `theme()` in the Python reader:
 * an unknown value is `light` (the Python fallback), never a blank surface.
 */
export function toReadingTheme(value: string | null | undefined): ReadingTheme {
  return value === 'light' || value === 'sepia' || value === 'night' || value === 'contrast'
    ? value
    : 'light'
}

/**
 * The theme to render for a stored settings row, mirroring `theme()` in
 * `app/reader/page.py`: a recognised `reading_theme` wins, otherwise the
 * legacy `study_night_mode` flag decides, and the fallback is the light
 * surface. Rows written before `reading_theme` existed only carry the flag.
 */
export function themeForStored(
  stored: { reading_theme?: string; study_night_mode?: boolean } | undefined,
): ReadingTheme {
  const value = stored?.reading_theme
  if (value === 'light' || value === 'sepia' || value === 'night' || value === 'contrast') {
    return value
  }
  return stored?.study_night_mode ? 'night' : 'light'
}

/**
 * The patch a theme swatch writes. `save()` in `app/reader/page.py` keeps the
 * legacy `study_night_mode` flag in step with the theme, so an older client
 * that only knows the night toggle still follows the choice.
 */
export function themePatch(
  theme: ReadingTheme,
): Pick<ReadingSettings, 'reading_theme' | 'study_night_mode'> {
  return { reading_theme: theme, study_night_mode: theme === 'night' }
}

/** Font sizes the Python sheet offers. The slider admits more; the server clamps to 14–30. */
export const FONT_SIZE_MIN = 14
export const FONT_SIZE_MAX = 30
export const FONT_SIZE_FALLBACK = 18

/** Line heights the Python sheet offers. The server clamps to 1.4–2.6. */
export const LINE_HEIGHT_OPTIONS: readonly number[] = [1.7, 1.9, 2.1]
export const LINE_HEIGHT_FALLBACK = 1.9

/** Content widths the Python sheet offers. The server clamps to 560–1000. */
export const WIDTH_OPTIONS: readonly number[] = [640, 760, 880]
export const WIDTH_FALLBACK = 760

/** Reading directions the Python sheet offers. */
export const DIRECTION_OPTIONS: readonly NonNullable<
  ReadingSettings['reading_direction']
>[] = ['auto', 'rtl', 'ltr']

function finiteOr(value: number, fallback: number): number {
  return Number.isFinite(value) ? value : fallback
}

/** Mirror of the server's `int()` clamp for `reading_font_size`. */
export function clampFontSize(value: number): number {
  const truncated = Math.trunc(finiteOr(value, FONT_SIZE_FALLBACK))
  return Math.min(FONT_SIZE_MAX, Math.max(FONT_SIZE_MIN, truncated))
}

/** Mirror of the server's `float()` clamp for `reading_line_height`. */
export function clampLineHeight(value: number): number {
  return Math.min(2.6, Math.max(1.4, finiteOr(value, LINE_HEIGHT_FALLBACK)))
}

/** Mirror of the server's `int()` clamp for `reading_width`. */
export function clampWidth(value: number): number {
  const truncated = Math.trunc(finiteOr(value, WIDTH_FALLBACK))
  return Math.min(1000, Math.max(560, truncated))
}

/**
 * Whether a direction value may be sent to the server.
 *
 * Anything else is a 400-shaped refusal folded into `auto` server-side, so
 * the select is built from `DIRECTION_OPTIONS` rather than free text.
 */
export function isDirection(
  value: string,
): value is NonNullable<ReadingSettings['reading_direction']> {
  return value === 'auto' || value === 'rtl' || value === 'ltr'
}

/* ------------------------------------------------------------------ */
/* Paragraph pairing and reading progress                               */
/* ------------------------------------------------------------------ */

/**
 * Local storage keys, shared with the Python reader (`app/reader/page.py`):
 * a location survives switching between the two readers because both read
 * and write the same keys.
 */
export function locationKey(jobId: string): string {
  return `jbook:loc:${jobId}`
}

export function readKey(jobId: string): string {
  return `jbook:read:${jobId}`
}

/**
 * Content direction for one side, mirroring `directionFor()` in
 * `app/reader/page.py`: an explicit setting wins, otherwise any Arabic-
 * script character (U+0600–U+06FF) makes it RTL. Unknown settings fall
 * through to detection rather than rendering nothing.
 */
export function directionFor(html: string, direction: string): 'rtl' | 'ltr' {
  if (direction === 'rtl' || direction === 'ltr') return direction
  return /[\u0600-\u06FF]/.test(html) ? 'rtl' : 'ltr'
}

/**
 * Overall reading progress in whole percent: the fraction through the
 * current chapter added to the chapters before it. Clamped, never NaN —
 * an empty book reports 0 rather than dividing by zero.
 */
export function overallPercent(index: number, frac: number, total: number): number {
  if (!Number.isFinite(index) || !Number.isFinite(frac) || !(total > 0)) return 0
  const clamped = Math.min(1, Math.max(0, frac))
  return Math.min(100, Math.max(0, Math.round(((index + clamped) / total) * 100)))
}

/**
 * The chapter the server remembers, or `null` when it remembers nothing
 * usable. The stored shape is `{job_id, chapter}` (written by the Python
 * reader and by this port); anything else — the default `null`, a stray
 * string from an older build — is "no memory", not an error.
 */
export function lastLocationOf(value: unknown): { chapter: number } | null {
  if (typeof value !== 'object' || value === null) return null
  const chapter = (value as { chapter?: unknown }).chapter
  if (typeof chapter !== 'number' || !Number.isFinite(chapter) || chapter < 0) {
    return null
  }
  return { chapter: Math.trunc(chapter) }
}

/**
 * Which chapter to open: an explicit choice first, then the locally
 * remembered chapter when it still exists, then the server memory, else
 * nothing (the caller falls back to the first chapter).
 */
export function storedChapter(
  validIds: ReadonlyArray<number>,
  selected: number | null,
  local: unknown,
  server: unknown,
): number | null {
  if (selected !== null && validIds.includes(selected)) return selected
  const localChapter = lastLocationOf(local)
  if (localChapter !== null && validIds.includes(localChapter.chapter)) {
    return localChapter.chapter
  }
  const serverChapter = lastLocationOf(server)
  if (serverChapter !== null && validIds.includes(serverChapter.chapter)) {
    return serverChapter.chapter
  }
  return null
}

/* ------------------------------------------------------------------ */
/* Columns mode                                                         */
/* ------------------------------------------------------------------ */

/**
 * Blocks with a translation to show. Mirrors the columns filter in
 * `app/reader/page.py` (`renderColumns` drops blocks whose translation is
 * empty): an untranslated block has no pair, so the columns would lay a
 * source beside a gap.
 */
export function pairedBlocks<T extends { translation_html: string }>(
  blocks: ReadonlyArray<T>,
): T[] {
  return blocks.filter((block) => Boolean(block.translation_html))
}

/**
 * Proportional scroll position for the other column, mirroring the Python
 * sync script: `other.scrollTop = (scrollTop / max) * otherMax`. Clamped
 * and zero-safe — an unmeasured column (max 0) holds still instead of
 * producing NaN and flinging the view.
 */
export function syncTop(sourceTop: number, sourceMax: number, targetMax: number): number {
  if (!Number.isFinite(sourceTop) || !(sourceMax > 0) || !(targetMax > 0)) return 0
  const ratio = Math.min(1, Math.max(0, sourceTop / sourceMax))
  return ratio * targetMax
}

/* ------------------------------------------------------------------ */
/* In-text bookmarks with a note                                        */
/* ------------------------------------------------------------------ */

/** The server caps a note at 500 characters (`clean_bookmarks`). */
export const NOTE_MAX = 500

/** The server keeps the newest 50 marks (`clean_bookmarks`). */
export const BOOKMARK_MAX = 50

/**
 * Marks that belong to one book.
 *
 * Mark rows are stored per user, but chapter/block numbers repeat across
 * books; a row with a different (or empty) `job` is not this book's and is
 * hidden rather than shown over an unrelated paragraph.
 */
export function bookmarksFor(
  bookmarks: readonly Bookmark[] | undefined,
  jobId: string,
): Bookmark[] {
  return (bookmarks ?? []).filter((mark) => mark.job === jobId)
}

/** Whether this chapter + block already carries a mark for this book. */
export function hasBookmark(
  bookmarks: readonly Bookmark[] | undefined,
  jobId: string,
  chapter: number,
  block: number,
): boolean {
  return bookmarksFor(bookmarks, jobId).some(
    (mark) => mark.chapter === chapter && mark.block === block,
  )
}

/**
 * Toggle one mark, mirroring the Python `#mark-btn`: the same spot removes
 * it, anywhere else adds it. The whole list (every book) is returned so the
 * caller can persist it, newest-capped at `BOOKMARK_MAX` like the server.
 */
export function toggleBookmark(
  bookmarks: readonly Bookmark[] | undefined,
  entry: Bookmark,
): Bookmark[] {
  const all = bookmarks ?? []
  const index = all.findIndex(
    (mark) =>
      mark.job === entry.job && mark.chapter === entry.chapter && mark.block === entry.block,
  )
  if (index !== -1) return all.filter((_, position) => position !== index)
  return [...all, { ...entry, note: noteSliced(entry.note) }].slice(-BOOKMARK_MAX)
}

/** Replace the note on one mark; other marks and other books are untouched. */
export function setBookmarkNote(
  bookmarks: readonly Bookmark[] | undefined,
  jobId: string,
  chapter: number,
  block: number,
  note: string,
): Bookmark[] {
  const text = noteSliced(note)
  return (bookmarks ?? []).map((mark) =>
    mark.job === jobId && mark.chapter === chapter && mark.block === block
      ? { ...mark, note: text }
      : mark,
  )
}

/** Remove one mark, returning the full list to persist. */
export function removeBookmark(
  bookmarks: readonly Bookmark[] | undefined,
  jobId: string,
  chapter: number,
  block: number,
): Bookmark[] {
  return (bookmarks ?? []).filter(
    (mark) => !(mark.job === jobId && mark.chapter === chapter && mark.block === block),
  )
}

function noteSliced(note: string): string {
  return String(note ?? '').slice(0, NOTE_MAX)
}
