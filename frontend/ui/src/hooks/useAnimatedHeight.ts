/**
 * Height transition for a container whose content changes size.
 *
 * WHY THIS EXISTS
 * ---------------
 * Login and signup are the same card with a different number of fields. Swapping
 * them without measuring snaps the card's height, which yanks everything below
 * it and reads as a page reload rather than a state change. `height: auto` is
 * not animatable, so the height has to be measured, pinned, and released.
 *
 * THE SEQUENCE
 * ------------
 *   1. measure the current height and pin it (so the browser has a start value)
 *   2. let React render the new content (the caller changes its children)
 *   3. measure the new height and animate to it
 *   4. on transition end, release to `auto` so the card can still grow for a
 *      validation message or a wrapped label without being stuck at a stale
 *      pixel value
 *
 * Step 4 is the one that is usually skipped, and it is the one that breaks: a
 * card left pinned at 412px clips the "the two passwords do not match" line that
 * appears under the confirm field.
 *
 * REDUCED MOTION
 * --------------
 * The transition duration is zero, so the height still changes but arrives at
 * once. The hook does not skip the work: a container left at a stale height is
 * a layout bug, not a motion preference.
 */
import { useCallback, useEffect, useLayoutEffect, useRef, useState, type RefObject } from 'react'

/** Matches the `--k-card-ease` duration used by the card's own transitions. */
const DURATION_MS = 320

export function useAnimatedHeight<T extends HTMLElement>(
  ref: RefObject<T | null>,
  /** Changing this value triggers the re-measure. Usually the mode or view. */
  dependency: string,
): { locked: boolean } {
  const [locked, setLocked] = useState(false)
  const previous = useRef<number | null>(null)
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null)
  const firstRun = useRef(true)

  const clearTimer = useCallback(() => {
    if (timer.current !== null) {
      clearTimeout(timer.current)
      timer.current = null
    }
  }, [])

  // Runs before paint, so the pinned start height is in place before the new
  // content is ever painted at its natural size. Doing this in an effect would
  // show one frame of the new height and then animate from it.
  useLayoutEffect(() => {
    const node = ref.current
    if (!node) return

    // The very first render is the entrance, not a transition: the card should
    // appear at its natural height, not grow into it from zero.
    if (firstRun.current) {
      firstRun.current = false
      previous.current = node.getBoundingClientRect().height
      return
    }

    const from = previous.current
    // `getBoundingClientRect` rather than `offsetHeight`: the latter rounds to
    // an integer, and a card that measures 596.4px pinned to 596px leaves a
    // sub-pixel gap the content reflows into.
    const to = node.getBoundingClientRect().height
    previous.current = to

    if (from === null || from === to) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced) return

    clearTimer()
    setLocked(true)
    node.style.height = `${from}px`
    node.style.overflow = 'hidden'

    // Force the pinned height to be committed before the target is set,
    // otherwise both writes collapse into one style recalculation and there is
    // no start value to animate from.
    void node.offsetHeight
    node.style.height = `${to}px`

    timer.current = setTimeout(() => {
      node.style.height = ''
      node.style.overflow = ''
      setLocked(false)
      timer.current = null
    }, DURATION_MS)
  }, [ref, dependency, clearTimer])

  useEffect(() => clearTimer, [clearTimer])

  return { locked }
}
