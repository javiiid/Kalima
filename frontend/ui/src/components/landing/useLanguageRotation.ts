/**
 * The six-language rotation.
 *
 * WHY A HOOK AND NOT CSS
 * ----------------------
 * The text genuinely changes, and with it the `dir` attribute, the font family
 * and the alignment. A CSS-only crossfade can only swap two pre-rendered
 * layers, which caps the rotation at two languages and leaves the direction
 * fixed -- exactly the English-to-Persian-only demo this replaces.
 *
 * BEHAVIOUR
 * ---------
 * - Advances on an interval, wrapping through all six.
 * - Pauses on hover and on focus within, because a visitor reading a German
 *   sentence should not have it pulled away mid-clause.
 * - A pill press jumps to that language and holds it. Pressing again resumes.
 * - Stops entirely under `prefers-reduced-motion`, starting on English so the
 *   page is still a complete demonstration rather than a frozen one.
 * - Never runs when the tab is hidden: a background interval that keeps
 *   re-rendering is pure waste, and it desynchronises the progress bar.
 */
import { useCallback, useEffect, useRef, useState } from 'react'
import { DEMO_INTERVAL_MS, DEMO_LANGUAGES, nextDemoIndex } from './languages.ts'

export interface LanguageRotation {
  /** Index into `DEMO_LANGUAGES`. */
  index: number
  /** The language currently on the stage. */
  current: (typeof DEMO_LANGUAGES)[number]
  /** True when the rotation is holding on a chosen language. */
  paused: boolean
  /** Jump to a language and hold it. */
  select: (index: number) => void
  /** Resume the automatic rotation. */
  resume: () => void
  /** Hover/focus pause, without changing the visitor's explicit choice. */
  setHovering: (hovering: boolean) => void
  /** Remount key for the stage, so the crossfade replays on every change. */
  stageKey: number
}

export function useLanguageRotation(): LanguageRotation {
  const [index, setIndex] = useState(0)
  const [paused, setPaused] = useState(false)
  const [hovering, setHovering] = useState(false)
  const [stageKey, setStageKey] = useState(0)
  const reduced = useRef(false)

  useEffect(() => {
    reduced.current = window.matchMedia('(prefers-reduced-motion: reduce)').matches
  }, [])

  const advance = useCallback(() => {
    setIndex((current) => nextDemoIndex(current))
    setStageKey((key) => key + 1)
  }, [])

  const select = useCallback((next: number) => {
    setIndex(next)
    setStageKey((key) => key + 1)
    setPaused(true)
  }, [])

  const resume = useCallback(() => {
    setPaused(false)
    setStageKey((key) => key + 1)
  }, [])

  useEffect(() => {
    // Reduced motion: hold on the first language. The rail still works, so the
    // demonstration stays complete and every language is reachable by hand.
    if (reduced.current) return
    if (paused || hovering) return

    let timer = window.setInterval(advance, DEMO_INTERVAL_MS)

    const onVisibility = () => {
      window.clearInterval(timer)
      if (!document.hidden) timer = window.setInterval(advance, DEMO_INTERVAL_MS)
    }
    document.addEventListener('visibilitychange', onVisibility)

    return () => {
      window.clearInterval(timer)
      document.removeEventListener('visibilitychange', onVisibility)
    }
  }, [advance, paused, hovering])

  return {
    index,
    current: DEMO_LANGUAGES[index] ?? DEMO_LANGUAGES[0]!,
    paused,
    select,
    resume,
    setHovering,
    stageKey,
  }
}
