/**
 * Pointer-driven 3D tilt for the authentication card.
 *
 * WHY A HOOK AND NOT A LIBRARY
 * ----------------------------
 * The card needs one thing: the pointer's position inside it, turned into a
 * small rotation on two axes, eased back to flat when the pointer leaves. That
 * is a `pointermove` listener and two CSS custom properties. A motion library
 * would add a dependency to a bundle that deliberately hand-rolls its
 * animation (see the motion notes at the top of `auth.css`), and the repo's
 * reduced-motion contract would still have to be honoured by hand.
 *
 * WHAT IT WRITES
 * --------------
 * It never sets `transform` itself. It writes `--tilt-x` and `--tilt-y` (in
 * degrees) onto the element, and the stylesheet composes them with the
 * entrance and hover transforms. That keeps one owner for the transform: a
 * hook that also wrote `transform` would fight the CSS the moment either side
 * changed.
 *
 * WHEN IT DOES NOTHING
 * --------------------
 *   * Coarse pointers (touch). A tilt that follows a finger is a tilt that
 *     fights the scroll, and the card is the scroll target on a phone.
 *   * `prefers-reduced-motion: reduce`. Rotation is exactly the kind of
 *     vestibular motion that setting exists to stop.
 *   * Keyboard-only focus: there is no pointer, so the card simply stays flat.
 *
 * The listener is attached to the *stage* (the element with perspective), not
 * the card, so the pointer is still tracked while the card is rotated out from
 * under the cursor. Attaching to the card makes the edge flicker: the card
 * rotates away, the pointer leaves it, the card snaps back, the pointer is
 * inside it again.
 */
import { useEffect, type RefObject } from 'react'

/** Degrees of rotation at the card's edge. Small on purpose: past ~8deg the
 *  text starts to shear and the form reads as a novelty. */
const MAX_TILT = 6
/** How far the pointer may travel before the tilt is at maximum, as a fraction
 *  of the card's half-size. Below 1 the edges saturate early, which feels
 *  responsive without making the centre feel dead. */
const SATURATION = 0.85

export function useCardTilt(
  stageRef: RefObject<HTMLElement | null>,
  cardRef: RefObject<HTMLElement | null>,
): void {
  useEffect(() => {
    const stage = stageRef.current
    const card = cardRef.current
    if (!stage || !card) return

    // Touch and reduced-motion users get the flat card. `matchMedia` is read
    // once at mount rather than per event: the query does not change mid-gesture,
    // and reading it inside a pointermove handler is a layout query per frame.
    const coarse = window.matchMedia('(pointer: coarse)')
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)')
    if (coarse.matches || reduced.matches) return

    let frame = 0
    let pendingX = 0
    let pendingY = 0
    let active = false

    const apply = () => {
      frame = 0
      card.style.setProperty('--tilt-x', `${pendingX.toFixed(3)}deg`)
      card.style.setProperty('--tilt-y', `${pendingY.toFixed(3)}deg`)
    }

    const onMove = (event: PointerEvent) => {
      const rect = card.getBoundingClientRect()
      if (rect.width === 0 || rect.height === 0) return
      // -1..1 from the centre, then clamped by the saturation factor.
      const nx = ((event.clientX - rect.left) / rect.width - 0.5) * 2
      const ny = ((event.clientY - rect.top) / rect.height - 0.5) * 2
      const clampedX = Math.max(-1, Math.min(1, nx / SATURATION))
      const clampedY = Math.max(-1, Math.min(1, ny / SATURATION))

      // Rotating around Y follows the horizontal pointer; around X follows the
      // vertical one, inverted so the near edge dips toward the reader.
      pendingY = clampedX * MAX_TILT
      pendingX = -clampedY * MAX_TILT

      if (!active) {
        active = true
        card.dataset.tilting = 'true'
      }
      // One write per frame. A pointermove can fire several times per frame and
      // each write invalidates style; coalescing keeps it at the frame rate.
      if (frame === 0) frame = requestAnimationFrame(apply)
    }

    const onLeave = () => {
      if (frame !== 0) {
        cancelAnimationFrame(frame)
        frame = 0
      }
      active = false
      delete card.dataset.tilting
      // Clearing the properties hands the transform back to the stylesheet's
      // resting value, which is what makes the return ease rather than snap.
      card.style.removeProperty('--tilt-x')
      card.style.removeProperty('--tilt-y')
    }

    stage.addEventListener('pointermove', onMove)
    stage.addEventListener('pointerleave', onLeave)
    // A pointer that leaves the window never fires pointerleave on the stage.
    window.addEventListener('blur', onLeave)

    return () => {
      if (frame !== 0) cancelAnimationFrame(frame)
      stage.removeEventListener('pointermove', onMove)
      stage.removeEventListener('pointerleave', onLeave)
      window.removeEventListener('blur', onLeave)
      card.style.removeProperty('--tilt-x')
      card.style.removeProperty('--tilt-y')
      delete card.dataset.tilting
    }
  }, [stageRef, cardRef])
}
