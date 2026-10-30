import { useEffect, useMemo, useRef, useState } from 'react'
import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query'
import { useParams } from 'react-router-dom'
import { api } from '@/lib/api'
import type {
  Bookmark,
  Chapter,
  ChapterBlock,
  ChapterContent,
  ReadingSettings,
  ReadingTheme,
} from '@/lib/api'
import { stripDuplicatedHeading, stripLeadingTitle } from '@/lib/chunks'
import {
  MAX_GLOSS_MARKS,
  findTermAt,
  prepareGlossTerms,
  textFor,
  tipFor,
  type GlossSide,
  type GlossTerm,
} from '@/lib/glossary.ts'
import {
  DIRECTION_OPTIONS,
  LINE_HEIGHT_FALLBACK,
  LINE_HEIGHT_OPTIONS,
  NOTE_MAX,
  READER_MODES,
  READING_THEMES,
  WIDTH_FALLBACK,
  WIDTH_OPTIONS,
  bookmarksFor,
  clampFontSize,
  clampLineHeight,
  clampWidth,
  directionFor,
  hasBookmark,
  isDirection,
  locationKey,
  overallPercent,
  pairedBlocks,
  readKey,
  removeBookmark,
  setBookmarkNote,
  storedChapter,
  syncTop,
  themeForStored,
  themePatch,
  toReaderMode,
  toggleBookmark,
  type ReaderMode,
} from '@/lib/reading.ts'
import { fa } from '@/lib/format'
import { useLanguage } from '@/i18n/useLanguage.ts'
import type { StringKey } from '@/i18n/fa.ts'
import './reader.css'

/**
 * The bilingual reader.
 *
 * Ported from `app/reader/page.py`.
 *
 * ONE RULE DOMINATES THIS FILE: the HTML rendered here is sanitised by the
 * Python `sanitize_html` boundary before it ever reaches this client. Do not
 * add client-side sanitisation, and do not widen what is rendered. The
 * protection is the boundary, and the tests in
 * `D:\J_BookTranslate_V\tests\test_reader_images.py` cover it. Re-implementing
 * it here in TypeScript would create a second, differently-flawed copy of the
 * one thing that keeps a hostile EPUB from running script in this origin.
 *
 * Images arrive as local asset URLs (`/reader/<id>/asset/<path>`) which the
 * backend serves with a sandboxing CSP. That is why the block HTML can be
 * injected whole: there is no remote origin in it.
 */

const MODE_KEY: Record<ReaderMode, StringKey> = {
  translation: 'reader.mode.translation',
  original: 'reader.mode.original',
  bilingual: 'reader.mode.bilingual',
  columns: 'reader.mode.columns',
}

const DIRECTION_KEY: Record<string, StringKey> = {
  auto: 'reader.direction.auto',
  rtl: 'reader.direction.rtl',
  ltr: 'reader.direction.ltr',
}

const THEME_KEY: Record<ReadingTheme, StringKey> = {
  light: 'reader.theme.light',
  sepia: 'reader.theme.sepia',
  night: 'reader.theme.night',
  contrast: 'reader.theme.contrast',
}

/**
 * Local-storage helpers. Reads are total (missing/corrupt → empty), writes
 * never throw (private mode) — a preference that cannot persist must not
 * break the reader.
 */
function readJson(key: string): unknown {
  try {
    const raw = localStorage.getItem(key)
    return raw ? (JSON.parse(raw) as unknown) : null
  } catch {
    return null
  }
}

function writeJson(key: string, value: unknown): void {
  try {
    localStorage.setItem(key, JSON.stringify(value))
  } catch {
    // Private browsing: the preference lives in memory for this visit.
  }
}

function loadReadIds(jobId: string): number[] {
  const raw = readJson(readKey(jobId))
  if (!Array.isArray(raw)) return []
  return raw.filter((value): value is number => typeof value === 'number' && Number.isFinite(value))
}

/** Saved scroll fraction for a chapter, or null when nothing was kept. */
function loadSavedFrac(jobId: string, chapter: number): number | null {
  const raw = readJson(locationKey(jobId))
  if (typeof raw !== 'object' || raw === null) return null
  const record = raw as { chapter?: unknown; frac?: unknown }
  if (record.chapter !== chapter) return null
  if (typeof record.frac !== 'number' || !Number.isFinite(record.frac)) return null
  return Math.min(1, Math.max(0, record.frac))
}
/**
 * DOM helpers for glossary highlighting. They touch `document` and are
 * therefore exercised by hand, not by `node --test` — everything decidable
 * without a DOM lives tested in `lib/glossary.ts`.
 *
 * Mirrors `applyGloss`/`clearGloss` in `app/reader/page.py`: longest-first
 * terms, one mark per (node, term), 200 marks per chapter, marks cleared
 * before every re-apply so toggling mode or chapter never double-wraps.
 */

/** Which language a text node is in, from the nearest marked ancestor. */
function sideOfNode(node: Text, mode: ReaderMode): GlossSide | null {
  const element = node.parentElement
  if (!element) return null
  const marked = element.closest('[data-gloss-side]')
  const side = marked?.getAttribute('data-gloss-side')
  if (side === 'source' || side === 'target') return side
  return mode === 'original' ? 'source' : 'target'
}

/** Unwrap every highlight mark, restoring the original text nodes. */
function clearGlossMarks(root: Element): void {
  for (const mark of Array.from(root.querySelectorAll('mark.gloss'))) {
    mark.replaceWith(...Array.from(mark.childNodes))
  }
  root.normalize()
}

/** Collect highlightable text nodes before mutating, so the walk sees a stable list. */
function glossTextNodes(root: Element): Text[] {
  const nodes: Text[] = []
  const walker = document.createTreeWalker(root, NodeFilter.SHOW_TEXT, {
    acceptNode(node: Node): number {
      if (!node.nodeValue?.trim()) return NodeFilter.FILTER_REJECT
      const element = (node as Text).parentElement
      if (!element || element.closest('mark.gloss, script, style')) {
        return NodeFilter.FILTER_REJECT
      }
      return NodeFilter.FILTER_ACCEPT
    },
  })
  let current = walker.nextNode()
  while (current) {
    nodes.push(current as Text)
    current = walker.nextNode()
  }
  return nodes
}

function applyGlossMarks(
  root: Element,
  terms: readonly GlossTerm[],
  mode: ReaderMode,
  label: string,
): number {
  let count = 0
  for (const textNode of glossTextNodes(root)) {
    let node: Text | null = textNode
    for (const term of terms) {
      if (!node || count >= MAX_GLOSS_MARKS) return count
      const side = sideOfNode(node, mode)
      if (!side) continue
      const match = findTermAt(node.nodeValue ?? '', textFor(term, side))
      if (!match) continue
      const middle = node.splitText(match.index)
      const after = middle.splitText(match.length)
      const mark = document.createElement('mark')
      mark.className = 'gloss'
      mark.tabIndex = 0
      mark.dataset.tip = tipFor(term, side)
      mark.setAttribute('aria-label', label)
      mark.appendChild(middle)
      node.parentNode?.insertBefore(mark, after)
      node = after
      count++
    }
  }
  return count
}

/**
 * DOM helpers for marks and read-aloud. They touch `document` (measurement,
 * `speechSynthesis`) and are therefore exercised by hand, like the glossary
 * walk above; the persistable decisions live tested in `lib/reading.ts`.
 *
 * Mirrors `blockTargets()` / `currentBlockIndex()` in `app/reader/page.py`:
 * the translation column in columns mode, the paired blocks in bilingual
 * mode, else the top-level nodes of the single-language body.
 */
function blockTargets(root: HTMLElement, mode: ReaderMode): HTMLElement[] {
  if (mode === 'columns') {
    const column = root.querySelectorAll<HTMLElement>('[data-col="translation"] [data-block-index]')
    if (column.length) return Array.from(column)
  }
  const paired = root.querySelectorAll<HTMLElement>('[data-block-index]')
  if (paired.length) return Array.from(paired)
  return Array.from(root.querySelectorAll<HTMLElement>('[data-reader-body] > *')).filter((element) =>
    Boolean(element.textContent?.trim()),
  )
}

/**
 * The block nearest the top of the viewport, mirroring `currentBlockIndex()`:
 * the first target that has not scrolled past, else the last one.
 */
function currentBlockIndex(root: HTMLElement, mode: ReaderMode): number {
  const elements = blockTargets(root, mode)
  for (let index = 0; index < elements.length; index++) {
    if ((elements[index] as HTMLElement).getBoundingClientRect().top >= 0) return index
  }
  return Math.max(0, elements.length - 1)
}

/**
 * The Persian voice, or null. Mirrors `faVoice()` in the Python reader:
 * a voice whose language starts with `fa` (`fa`, `fa-IR`), never a fallback
 * voice that would read Persian text with English phonemes.
 */
function faVoice(): SpeechSynthesisVoice | null {
  try {
    const voices = window.speechSynthesis?.getVoices() ?? []
    return voices.find((voice) => voice.lang.toLowerCase().startsWith('fa')) ?? null
  } catch {
    return null
  }
}

/** A transient note, matching the monitor page's toast. */
function Toast({ message, onDone }: { message: string; onDone: () => void }) {
  useEffect(() => {
    const timer = window.setTimeout(onDone, 3000)
    return () => window.clearTimeout(timer)
  }, [message, onDone])
  return (
    <div role="status" aria-live="polite" className="toast toast-ok">
      {message}
    </div>
  )
}

export function ReaderPage() {
  const { id = '' } = useParams()
  const { t, dir } = useLanguage()
  const client = useQueryClient()
  const [selectedId, setSelectedId] = useState<number | null>(null)
  // Local overrides until the next server round-trip. `null` means "follow
  // the server": the settings query is the source of truth, so a change made
  // in the Python reader (or another tab) is picked up instead of being
  // overwritten by this page's hardcoded defaults.
  const [modeOverride, setModeOverride] = useState<ReaderMode | null>(null)
  const [fontOverride, setFontOverride] = useState<number | null>(null)
  const [leadingOverride, setLeadingOverride] = useState<number | null>(null)
  const [widthOverride, setWidthOverride] = useState<number | null>(null)
  const [directionOverride, setDirectionOverride] = useState<string | null>(null)
  const [glossOverride, setGlossOverride] = useState<boolean | null>(null)
  const [themeOverride, setThemeOverride] = useState<ReadingTheme | null>(null)
  // The whole list (every book), so a save sends back what it kept; the marks
  // shown are filtered to this book by `bookmarksFor`.
  const [marksOverride, setMarksOverride] = useState<Bookmark[] | null>(null)
  const [speaking, setSpeaking] = useState(false)
  const [toast, setToast] = useState<string | null>(null)
  const [jumpTo, setJumpTo] = useState<{ chapter: number; block: number } | null>(null)
  const speakRef = useRef(false)
  const scrollRef = useRef<HTMLDivElement | null>(null)

  const settings = useQuery({
    queryKey: ['reader-settings'],
    queryFn: () => api.readerSettings(),
    staleTime: 300_000,
  })

  const server = settings.data?.value
  const mode = modeOverride ?? toReaderMode(server?.reading_mode)
  const fontSize = fontOverride ?? server?.reading_font_size ?? 18
  const lineHeight = leadingOverride ?? server?.reading_line_height ?? LINE_HEIGHT_FALLBACK
  const width = widthOverride ?? server?.reading_width ?? WIDTH_FALLBACK
  const direction = directionOverride ?? server?.reading_direction ?? 'auto'
  // The toggle is persisted from this step on; highlighting itself lands
  // with the glossary step, which reads this same value.
  const glossary = glossOverride ?? server?.reading_glossary ?? true
  // The reader surface theme, separate from the app's day/dark mode.
  const theme = themeOverride ?? themeForStored(server)
  const allMarks = marksOverride ?? server?.reading_bookmarks ?? []
  const marks = useMemo(() => bookmarksFor(allMarks, id), [allMarks, id])

  const chapters = useQuery({
    queryKey: ['reader-chapters', id],
    queryFn: () => api.readerChapters(id),
    enabled: Boolean(id),
  })

  // Read chapters per book (not per chapter): opening a new chapter marks
  // it read here and in localStorage, so the ticks survive a reload.
  const [readByBook, setReadByBook] = useState<Record<string, number[]>>({})
  const readIds = readByBook[id] ?? loadReadIds(id)
  // Scroll fraction per book+chapter: keyed, so switching books never shows
  // the other book's progress and no reset effect is needed.
  const [fracByKey, setFracByKey] = useState<Record<string, number>>({})
  const fracTimer = useRef<number>(0)

  // Derived, not stored in state via an effect. An effect that sets the chapter
  // on first load costs an extra render, and if it re-runs on a refetch it
  // silently yanks the reader back to chapter one. An explicit choice wins,
  // then the locally remembered chapter, then the server memory, then the
  // first chapter — all derived, so nothing can go stale.
  const chapterItems = chapters.data?.items ?? []
  const firstChapterId = chapterItems[0]?.id ?? null
  const validIds = chapterItems.map((chapter) => chapter.id)
  const localLoc = useMemo(() => readJson(locationKey(id)), [id])
  const chapterId = storedChapter(validIds, selectedId, localLoc, server?.reading_last_location)
    ?? firstChapterId
  const fracKey = `${id}:${chapterId ?? 'none'}`
  const frac = fracByKey[fracKey] ?? 0
  const chapterIndex = chapterId === null
    ? 0
    : Math.max(0, chapterItems.findIndex((chapter) => chapter.id === chapterId))
  const percent = overallPercent(chapterIndex, frac, chapterItems.length)

  const content = useQuery({
    queryKey: ['reader-chapter', id, chapterId],
    queryFn: () => api.readerChapter(id, chapterId as number),
    enabled: Boolean(id) && chapterId !== null,
  })

  const blocks = useQuery({
    queryKey: ['reader-blocks', id, chapterId],
    queryFn: () => api.readerBlocks(id, chapterId as number),
    enabled: (mode === 'bilingual' || mode === 'columns') && Boolean(id) && chapterId !== null,
  })

  // A partial, FLAT patch: the backend keeps only keys in READING_DEFAULTS,
  // so this merges server-side instead of clobbering untouched settings.
  const save = useMutation({
    mutationFn: (next: Partial<ReadingSettings>) => api.updateReaderSettings(next),
    onSuccess: () => void client.invalidateQueries({ queryKey: ['reader-settings'] }),
  })

  const glossTerms = useQuery({
    queryKey: ['reader-glossary', id],
    queryFn: () => api.readerGlossary(id),
    // The snapshot never changes mid-read: fetch once per book and reuse it
    // across chapters, like the Python `glossReady` flag.
    enabled: Boolean(id) && glossary,
    staleTime: 300_000,
  })
  const terms = useMemo(
    () => prepareGlossTerms(glossTerms.data?.items),
    [glossTerms.data],
  )

  // One way to open a chapter: reset the view, remember the spot locally
  // (chapter + read tick + frac) and on the server (chapter), all
  // fire-and-forget — a failed persist must never block reading.
  const openChapter = (next: number) => {
    setSelectedId(next)
    if (scrollRef.current) scrollRef.current.scrollTop = 0
    const read = readIds.includes(next) ? readIds : [...readIds, next]
    setReadByBook((previous) => ({ ...previous, [id]: read }))
    writeJson(readKey(id), read)
    writeJson(locationKey(id), { chapter: next, frac: 0 })
    void save.mutate({ reading_last_location: { job_id: id, chapter: next } })
  }

  /** Persist the whole mark list (the server re-clamps and caps it). */
  const saveMarks = (next: Bookmark[]) => {
    setMarksOverride(next)
    void save.mutate({ reading_bookmarks: next })
  }

  /**
   * Toggle a mark on the block at the top of the viewport, mirroring the
   * Python `#mark-btn`: the same spot removes it, anywhere else adds it.
   */
  const toggleMark = () => {
    const root = scrollRef.current
    if (!root || chapterId === null) return
    const block = currentBlockIndex(root, mode)
    const entry: Bookmark = {
      chapter: chapterId,
      block,
      note: '',
      created: new Date().toISOString(),
      job: id,
    }
    const wasMarked = hasBookmark(allMarks, id, chapterId, block)
    saveMarks(toggleBookmark(allMarks, entry))
    setToast(wasMarked ? t('reader.mark.removed') : t('reader.mark.saved'))
  }

  /** Jump to a mark, switching chapter first when it lives in another one. */
  const jumpMark = (mark: Bookmark) => {
    if (mark.chapter !== chapterId) openChapter(mark.chapter)
    setJumpTo({ chapter: mark.chapter, block: mark.block })
  }

  /** Update a mark's note locally (persisted on blur, like the Python change). */
  const editNote = (mark: Bookmark, note: string) => {
    setMarksOverride(setBookmarkNote(allMarks, id, mark.chapter, mark.block, note))
  }

  const commitNote = (mark: Bookmark, note: string) => {
    saveMarks(setBookmarkNote(allMarks, id, mark.chapter, mark.block, note))
  }

  const deleteMark = (mark: Bookmark) => {
    saveMarks(removeBookmark(allMarks, id, mark.chapter, mark.block))
    setToast(t('reader.mark.removed'))
  }

  /** Stop read-aloud and clear the highlight, mirroring `stopSpeak()`. */
  const stopSpeech = () => {
    speakRef.current = false
    setSpeaking(false)
    try {
      window.speechSynthesis?.cancel()
    } catch {
      // A browser without speech support has nothing to cancel.
    }
    scrollRef.current
      ?.querySelectorAll('.speaking')
      .forEach((element) => element.classList.remove('speaking'))
  }

  /**
   * Read one block, resolving when it finishes. Mirrors `speakOne()`: the
   * Persian voice, `onend`/`onerror` both resolve so a failed block never
   * wedges the queue.
   */
  const speakOne = (element: HTMLElement, text: string) =>
    new Promise<void>((resolve) => {
      const utterance = new SpeechSynthesisUtterance(text)
      const voice = faVoice()
      if (voice) {
        utterance.voice = voice
        utterance.lang = voice.lang
      } else {
        utterance.lang = 'fa-IR'
      }
      utterance.onend = () => resolve()
      utterance.onerror = () => resolve()
      element.classList.add('speaking')
      window.speechSynthesis.speak(utterance)
    }).then(() => {
      element.classList.remove('speaking')
    })

  /**
   * Read the chapter aloud, block by block from the current position. Mirrors
   * `toggleSpeak()`: nothing is read when the browser has no speech or no
   * Persian voice, rather than reading Persian in an English voice.
   */
  const toggleSpeech = async () => {
    if (speakRef.current) {
      stopSpeech()
      return
    }
    if (!('speechSynthesis' in window)) {
      setToast(t('reader.speak.unsupported'))
      return
    }
    if (!faVoice()) {
      setToast(t('reader.speak.noVoice'))
      return
    }
    const root = scrollRef.current
    if (!root) return
    const elements = blockTargets(root, mode)
    if (elements.length === 0) return
    const start = currentBlockIndex(root, mode)
    speakRef.current = true
    setSpeaking(true)
    for (let index = start; index < elements.length && speakRef.current; index++) {
      const element = elements[index] as HTMLElement
      const sides = element.querySelectorAll('.parallel-side')
      const raw = sides.length
        ? (sides[sides.length - 1] as HTMLElement).textContent
        : element.textContent
      const text = String(raw ?? '')
        .trim()
        .replace(/\s+/g, ' ')
        .slice(0, 600)
      if (!text) continue
      element.scrollIntoView({ block: 'center' })
      await speakOne(element, text)
    }
    stopSpeech()
  }

  // Track the scroll fraction (rAF-throttled) and persist it debounced,
  // mirroring the Python reader's 500ms saveLoc.
  useEffect(() => {
    const element = scrollRef.current
    if (!element || chapterId === null) return
    let raf = 0
    const key = `${id}:${chapterId}`
    const onScroll = () => {
      cancelAnimationFrame(raf)
      raf = requestAnimationFrame(() => {
        const max = element.scrollHeight - element.clientHeight
        const current = max > 0 ? element.scrollTop / max : 0
        setFracByKey((previous) => ({ ...previous, [key]: current }))
        window.clearTimeout(fracTimer.current)
        fracTimer.current = window.setTimeout(() => {
          writeJson(locationKey(id), { chapter: chapterId, frac: current })
        }, 500)
      })
    }
    element.addEventListener('scroll', onScroll, { passive: true })
    return () => {
      element.removeEventListener('scroll', onScroll)
      cancelAnimationFrame(raf)
      window.clearTimeout(fracTimer.current)
    }
  }, [id, chapterId])

  // Restore the remembered scroll position once the chapter DOM exists.
  // Only the scroll is set imperatively; the progress state follows from
  // the scroll event it fires, so no state is set inside this effect.
  useEffect(() => {
    const element = scrollRef.current
    if (!element || !content.data || chapterId === null) return
    const saved = loadSavedFrac(id, chapterId)
    if (saved === null || saved <= 0) return
    const timer = window.setTimeout(() => {
      const max = element.scrollHeight - element.clientHeight
      if (max > 0) element.scrollTop = saved * max
    }, 150)
    return () => window.clearTimeout(timer)
  }, [id, chapterId, content.data])

  // Highlight after every render that replaces the chapter DOM. Clearing
  // first keeps mode/chapter switches from double-wrapping; toggling the
  // switch off clears without re-marking.
  useEffect(() => {
    const root = scrollRef.current
    if (!root) return
    clearGlossMarks(root)
    if (!glossary || terms.length === 0) return
    applyGlossMarks(root, terms, mode, t('reader.glossary'))
  }, [content.data, blocks.data, mode, chapterId, terms, glossary, t])

  // Scroll a jumped-to mark into view once its chapter has rendered. The
  // chapter switch and the scroll are one intent, so the pending target is
  // left alone until the right chapter's DOM exists.
  useEffect(() => {
    if (!jumpTo || chapterId !== jumpTo.chapter || !content.data) return
    const root = scrollRef.current
    if (!root) return
    const timer = window.setTimeout(() => {
      const elements = blockTargets(root, mode)
      const element = elements[Math.min(jumpTo.block, elements.length - 1)]
      element?.scrollIntoView({ block: 'center' })
      setJumpTo(null)
    }, 150)
    return () => window.clearTimeout(timer)
  }, [jumpTo, chapterId, content.data, mode])

  // Read-aloud is per chapter: switching chapters stops it, mirroring
  // `stopSpeak()` at the top of the Python `loadChapter`.
  useEffect(() => {
    speakRef.current = false
    setSpeaking(false)
    try {
      window.speechSynthesis?.cancel()
    } catch {
      // Nothing to cancel on a browser without speech support.
    }
  }, [chapterId])

  // Leaving the page must not keep reading.
  useEffect(
    () => () => {
      speakRef.current = false
      try {
        window.speechSynthesis?.cancel()
      } catch {
        // Nothing to cancel on a browser without speech support.
      }
    },
    [],
  )

  const items = chapterItems
  // A book the server cannot serve (missing translation, or one that is not
  // ours) fails on the chapter list, which disables the chapter query -- so
  // without this branch the body would sit on a skeleton forever. The server
  // explains itself in English (its wording is not localized), so show the
  // reader's own sentence instead of leaking that into a Persian page.
  const bookError = t('reader.unavailable')

  return (
    // The main carries `.page` literally (the gutter owner); the reader theme
    // scope sits on the wrapper so only this page's subtree is restyled.
    <main className="page" dir={dir}>
      <div className={`reader-theme-${theme}`}>
        <header className="mb-5">
          <h1 className="text-[length:var(--text-h1)] font-extrabold tracking-tight">
            {chapters.data?.book ?? t('reader.read')}
          </h1>
        </header>

        <div className="grid gap-5 lg:grid-cols-[260px_minmax(0,1fr)]">
        {/* ---- chapter list ---- */}
        <nav className="surface-card h-fit p-3" aria-label={t('reader.chapters')}>
          <h2 className="px-2 py-1 text-[length:var(--text-label)] font-bold">{t('reader.chapters')}</h2>
          {chapters.isError ? null : chapters.isPending ? (
            <div className="skeleton" style={{ height: 120 }} />
          ) : items.length === 0 ? (
            <p className="empty">{t('reader.noChapters')}</p>
          ) : (
            <ul className="grid gap-0.5" style={{ maxHeight: '65vh', overflow: 'auto' }}>
              {items.map((chapter: Chapter) => (
                <li key={chapter.id}>
                  <button
                    type="button"
                    className="w-full rounded-[var(--radius-control)] px-3 py-2 text-start text-[length:var(--text-small)]"
                    style={{
                      background: chapter.id === chapterId ? 'var(--color-primary-subtle)' : 'transparent',
                      color:
                        chapter.id === chapterId
                          ? 'var(--color-text-brand)'
                          : 'var(--color-text-secondary)',
                    }}
                    onClick={() => openChapter(chapter.id)}
                  >
                    {chapter.title}
                    {readIds.includes(chapter.id) ? (
                      <span aria-hidden="true"> ✓</span>
                    ) : null}
                    {readIds.includes(chapter.id) ? (
                      <span className="sr-only">{t('reader.readTick')}</span>
                    ) : null}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </nav>

        {/* ---- reader ---- */}
        <section className="grid gap-3">
          <div className="surface-card flex flex-wrap items-center gap-3 p-3">
            <div className="flex gap-1" role="group" aria-label={t('reader.mode.label')}>
              {READER_MODES.map((value) => (
                <button
                  key={value}
                  type="button"
                  className="btn btn-ghost"
                  aria-pressed={mode === value}
                  style={
                    mode === value
                      ? { background: 'var(--color-primary-subtle)', color: 'var(--color-text-brand)' }
                      : undefined
                  }
                  onClick={() => {
                    setModeOverride(value)
                    void save.mutate({ reading_mode: value })
                  }}
                >
                  {t(MODE_KEY[value])}
                </button>
              ))}
            </div>

            <label className="ms-auto flex items-center gap-2">
              <span className="label">{t('reader.fontSize')}</span>
              <input
                type="range"
                min={13}
                max={26}
                value={fontSize}
                onChange={(event) => {
                  const value = clampFontSize(Number(event.target.value))
                  setFontOverride(value)
                  void save.mutate({ reading_font_size: value })
                }}
                aria-label={t('reader.fontSize')}
              />
            </label>

            <label className="flex items-center gap-2">
              <span className="label">{t('reader.lineHeight')}</span>
              <select
                className="field"
                value={lineHeight}
                onChange={(event) => {
                  const value = clampLineHeight(Number(event.target.value))
                  setLeadingOverride(value)
                  void save.mutate({ reading_line_height: value })
                }}
                aria-label={t('reader.lineHeight')}
              >
                {LINE_HEIGHT_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-2">
              <span className="label">{t('reader.width')}</span>
              <select
                className="field"
                value={width}
                onChange={(event) => {
                  const value = clampWidth(Number(event.target.value))
                  setWidthOverride(value)
                  void save.mutate({ reading_width: value })
                }}
                aria-label={t('reader.width')}
              >
                {WIDTH_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {option}
                  </option>
                ))}
              </select>
            </label>

            <label className="flex items-center gap-2">
              <span className="label">{t('reader.direction')}</span>
              <select
                className="field"
                value={direction}
                onChange={(event) => {
                  const value = event.target.value
                  if (!isDirection(value)) return
                  setDirectionOverride(value)
                  void save.mutate({ reading_direction: value })
                }}
                aria-label={t('reader.direction')}
              >
                {DIRECTION_OPTIONS.map((option) => (
                  <option key={option} value={option}>
                    {t(DIRECTION_KEY[option] ?? 'reader.direction.auto')}
                  </option>
                ))}
              </select>
            </label>

            <button
              type="button"
              className="btn btn-ghost"
              aria-pressed={glossary}
              onClick={() => {
                setGlossOverride(!glossary)
                void save.mutate({ reading_glossary: !glossary })
              }}
            >
              {t('reader.glossary')}: {glossary ? t('reader.glossary.on') : t('reader.glossary.off')}
            </button>

            {/* The reader surface theme. Each swatch carries its own theme
                scope so it previews its palette; the page carries the chosen
                one. */}
            <div className="flex items-center gap-2">
              <span className="label">{t('reader.theme')}</span>
              <div className="flex gap-1" role="group" aria-label={t('reader.theme')}>
                {READING_THEMES.map((value) => (
                  <button
                    key={value}
                    type="button"
                    className={`reader-swatch reader-theme-${value}`}
                    aria-pressed={theme === value}
                    aria-label={t(THEME_KEY[value])}
                    title={t(THEME_KEY[value])}
                    onClick={() => {
                      setThemeOverride(value)
                      void save.mutate(themePatch(value))
                    }}
                  />
                ))}
              </div>
            </div>

            <button type="button" className="btn btn-ghost" onClick={toggleMark}>
              {t('reader.mark.add')}
            </button>

            <button
              type="button"
              className="btn btn-ghost"
              aria-pressed={speaking}
              onClick={() => void toggleSpeech()}
            >
              {speaking ? t('reader.speak.stop') : t('reader.speak')}
            </button>
          </div>

          {/* Bookmarks and their notes, mirroring the Python `#marks-list`.
              Marks are stored per user but shown per book, so a mark made in
              another book never lands on the same paragraph number here. */}
          <section className="surface-card p-3" aria-label={t('reader.marks.title')}>
            <h2 className="px-1 pb-2 text-[length:var(--text-label)] font-bold">
              {t('reader.marks.title')}
            </h2>
            {marks.length === 0 ? (
              <p className="empty">{t('reader.marks.empty')}</p>
            ) : (
              <ul className="grid gap-1">
                {marks.map((mark) => {
                  const chapter = items.find((item) => item.id === mark.chapter)
                  const label =
                    chapter?.title ??
                    t('reader.chapterFallback', { index: fa(mark.chapter + 1) })
                  return (
                    <li
                      key={`${mark.chapter}:${mark.block}`}
                      className="flex flex-wrap items-center gap-2"
                    >
                      <button
                        type="button"
                        className="btn btn-ghost min-w-0 flex-none"
                        title={t('reader.mark.goto')}
                        onClick={() => jumpMark(mark)}
                      >
                        {/* Wrap rather than truncate: an RTL title truncated by
                            `text-overflow` loses its opening words, which are
                            the ones that identify the chapter. */}
                        <span className="block max-w-[14rem] break-words text-start">{label}</span>
                      </button>
                      <input
                        className="field min-w-0 flex-1"
                        maxLength={NOTE_MAX}
                        placeholder={t('reader.mark.note')}
                        value={mark.note}
                        aria-label={t('reader.mark.noteLabel', { label })}
                        onChange={(event) => editNote(mark, event.target.value)}
                        onBlur={(event) => commitNote(mark, event.target.value)}
                      />
                      <button
                        type="button"
                        className="btn btn-ghost"
                        aria-label={t('reader.mark.delete')}
                        title={t('reader.mark.delete')}
                        onClick={() => deleteMark(mark)}
                      >
                        ✕
                      </button>
                    </li>
                  )
                })}
              </ul>
            )}
          </section>

          {/* Overall progress: the fraction through this chapter added to the
              chapters before it, mirroring the Python `#progress-fill`. */}
          <div
            role="progressbar"
            aria-valuenow={percent}
            aria-valuemin={0}
            aria-valuemax={100}
            aria-label={t('reader.progress', {
              index: fa(chapterIndex + 1),
              total: fa(items.length),
              percent: fa(percent),
            })}
            className="h-1.5 w-full overflow-hidden rounded-full"
            style={{ background: 'var(--color-surface-sunken)' }}
          >
            <div
              className="h-full rounded-full"
              style={{ width: `${percent}%`, background: 'var(--color-primary)' }}
            />
          </div>

          <article
            ref={scrollRef}
            className="surface-card mx-auto w-full p-6"
            style={{ maxHeight: '70vh', overflow: 'auto', fontSize, lineHeight, maxWidth: width }}
          >
            {chapters.isError ? (
              <p role="alert" className="alert alert-error">
                {bookError}
              </p>
            ) : content.isPending ? (
              <div className="skeleton" style={{ height: 320 }} />
            ) : content.isError ? (
              <p role="alert" className="alert alert-error">
                {t('reader.loadError')}
              </p>
            ) : (
              <ChapterBody
                content={content.data}
                mode={mode}
                direction={direction}
                blocks={blocks.data?.items ?? []}
                blocksPending={blocks.isPending}
              />
            )}
          </article>

          {items.length > 1 && chapterId !== null ? (
            <div className="flex items-center justify-between gap-3">
              <button
                type="button"
                className="btn btn-secondary"
                disabled={chapterId <= items[0]!.id}
                onClick={() => {
                  const index = items.findIndex((item) => item.id === chapterId)
                  const previous = items[Math.max(0, index - 1)]
                  if (previous) openChapter(previous.id)
                }}
              >
                {t('reader.prev')}
              </button>
              <span
                className="text-[length:var(--text-label)] tabular-nums"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {t('reader.progress', {
                  index: fa(chapterIndex + 1),
                  total: fa(items.length),
                  percent: fa(percent),
                })}
              </span>
              <button
                type="button"
                className="btn btn-secondary"
                disabled={chapterId >= items[items.length - 1]!.id}
                onClick={() => {
                  const index = items.findIndex((item) => item.id === chapterId)
                  const next = items[Math.min(items.length - 1, index + 1)]
                  if (next) openChapter(next.id)
                }}
              >
                {t('reader.next')}
              </button>
            </div>
          ) : null}
        </section>
        </div>

        {toast ? <Toast message={toast} onDone={() => setToast(null)} /> : null}
      </div>
    </main>
  )
}

function ColumnSide({
  label,
  glossSide,
  col,
  tone,
  htmlOf,
  blocks,
  direction,
  setRef,
}: {
  label: string
  glossSide: GlossSide
  col: 'original' | 'translation'
  tone: string
  htmlOf: (block: ChapterBlock) => string
  blocks: ChapterBlock[]
  direction: string
  setRef: (element: HTMLElement | null) => void
}) {
  return (
    <section ref={setRef} className="reader-col" data-col={col} aria-label={label}>
      <h3 className="reader-col-head">{label}</h3>
      {blocks.map((block, index) => {
        const html = htmlOf(block)
        return (
          <div
            key={block.id}
            data-block-index={index}
            dir={directionFor(html, direction)}
            data-gloss-side={glossSide}
            className="reader-col-block leading-8"
            style={{ color: tone }}
            dangerouslySetInnerHTML={{ __html: stripDuplicatedHeading(html) }}
          />
        )
      })}
    </section>
  )
}

/**
 * Two continuous, independently scrolling columns with proportional scroll
 * sync and a swap control. Ports `renderColumns` plus the sync script in
 * `app/reader/page.py`: sync is proportional because the columns differ in
 * height, feedback-guarded by a lock, and disabled on narrow screens where
 * the CSS stacks the columns instead.
 */
function ColumnsView({
  blocks,
  direction,
  pending,
}: {
  blocks: ChapterBlock[]
  direction: string
  pending: boolean
}) {
  const { t } = useLanguage()
  const [swapped, setSwapped] = useState(false)
  const firstRef = useRef<HTMLElement | null>(null)
  const secondRef = useRef<HTMLElement | null>(null)
  const lock = useRef(false)

  useEffect(() => {
    const first = firstRef.current
    const second = secondRef.current
    if (!first || !second) return
    const narrow = () => window.matchMedia('(max-width: 759px)').matches
    const link = (from: HTMLElement, to: HTMLElement) => {
      const onScroll = () => {
        if (lock.current || narrow()) return
        lock.current = true
        to.scrollTop = syncTop(
          from.scrollTop,
          from.scrollHeight - from.clientHeight,
          to.scrollHeight - to.clientHeight,
        )
        requestAnimationFrame(() => {
          lock.current = false
        })
      }
      from.addEventListener('scroll', onScroll, { passive: true })
      return () => from.removeEventListener('scroll', onScroll)
    }
    const unlinkFirst = link(first, second)
    const unlinkSecond = link(second, first)
    return () => {
      unlinkFirst()
      unlinkSecond()
    }
  }, [blocks])

  if (pending) return <div className="skeleton" style={{ height: 320 }} />
  if (blocks.length === 0) {
    return (
      <p className="empty">
        {t('reader.noBilingual')}
      </p>
    )
  }

  const original = {
    label: t('reader.side.original'),
    glossSide: 'source' as const,
    col: 'original' as const,
    tone: 'var(--color-text-secondary)',
    htmlOf: (block: ChapterBlock) => block.original_html,
  }
  const translation = {
    label: t('reader.side.translation'),
    glossSide: 'target' as const,
    col: 'translation' as const,
    tone: 'var(--color-text-primary)',
    htmlOf: (block: ChapterBlock) => block.translation_html,
  }
  const [first, second] = swapped ? [translation, original] : [original, translation]

  return (
    <div className="reader-columns">
      <div className="reader-columns-toolbar">
        <button
          type="button"
          className="btn btn-ghost"
          aria-pressed={swapped}
          onClick={() => setSwapped((value) => !value)}
        >
          {t('reader.columns.swap')}
        </button>
      </div>
      <div className="reader-columns-grid">
        <ColumnSide
          label={first.label}
          glossSide={first.glossSide}
          col={first.col}
          tone={first.tone}
          htmlOf={first.htmlOf}
          blocks={blocks}
          direction={direction}
          setRef={(element) => {
            firstRef.current = element
          }}
        />
        <ColumnSide
          label={second.label}
          glossSide={second.glossSide}
          col={second.col}
          tone={second.tone}
          htmlOf={second.htmlOf}
          blocks={blocks}
          direction={direction}
          setRef={(element) => {
            secondRef.current = element
          }}
        />
      </div>
    </div>
  )
}

function ChapterBody({
  content,
  mode,
  direction,
  blocks,
  blocksPending,
}: {
  content: ChapterContent
  mode: ReaderMode
  direction: string
  blocks: ChapterBlock[]
  blocksPending: boolean
}) {
  const { t } = useLanguage()
  // Bilingual uses the block list so source and translation sit side by side.
  // The single-language modes use the chapter HTML directly, which is already
  // sanitised on the Python side.
  if (mode === 'columns') {
    return <ColumnsView blocks={pairedBlocks(blocks)} direction={direction} pending={blocksPending} />
  }
  if (mode === 'bilingual') {
    if (blocksPending) return <div className="skeleton" style={{ height: 320 }} />
    if (blocks.length === 0) {
      return (
        <p className="empty">
          {t('reader.noBilingual')}
        </p>
      )
    }
    return (
      <div className="grid gap-5">
        {blocks.map((block, index) => (
          <div
            key={block.id}
            data-block-index={index}
            className="grid gap-3 md:grid-cols-2"
          >
            {/* Both are sanitised server-side. See the note at the top. Both
                also repeat the title as loose text and again in an <h1>, so
                each side is stripped on its own: the original and the
                translation carry different titles. `data-gloss-side` tells
                the highlighter which language each side is in; the direction
                of each side is detected from its own text. */}
            <div className="grid min-w-0 gap-1">
              <span
                className="block text-[length:var(--text-caption)]"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {t('reader.side.original')}
              </span>
              <div
                dir={directionFor(block.original_html, direction)}
                data-gloss-side="source"
                className="parallel-side leading-8"
                style={{ color: 'var(--color-text-secondary)' }}
                dangerouslySetInnerHTML={{ __html: stripDuplicatedHeading(block.original_html) }}
              />
            </div>
            <div className="grid min-w-0 gap-1">
              <span
                className="block text-[length:var(--text-caption)]"
                style={{ color: 'var(--color-text-muted)' }}
              >
                {t('reader.side.translation')}
              </span>
              <div
                dir={directionFor(block.translation_html, direction)}
                data-gloss-side="target"
                className="parallel-side leading-8"
                style={{ color: 'var(--color-text-primary)' }}
                dangerouslySetInnerHTML={{ __html: stripDuplicatedHeading(block.translation_html) }}
              />
            </div>
          </div>
        ))}
      </div>
    )
  }

  return (
    <div
      data-reader-body
      dir={directionFor(content.html, direction)}
      className="leading-8"
      style={{ color: 'var(--color-text-primary)' }}
      /* The chapter HTML repeats the title as loose text before the <h1>, so
         it renders twice. The page header already shows the title. */
      dangerouslySetInnerHTML={{
        __html: stripLeadingTitle(stripDuplicatedHeading(content.html), content.title),
      }}
    />
  )
}
