/**
 * The authentication card: the 3D stage, the traveling border light, the glow,
 * and the ambient background field.
 *
 * WHAT THIS COMPONENT OWNS
 * ------------------------
 * Structure and the two effects that cannot be done in CSS alone:
 *
 *   * the **stage** that supplies `perspective`, so the card rotates in depth
 *     rather than being skewed flat;
 *   * the **tilt** itself, delegated to `useCardTilt` (pointer position ->
 *     two custom properties);
 *   * the **traveling light**, which is four separate beams animated around the
 *     border by CSS keyframes. It is a sibling of the card's content, not a
 *     `::before`, because it needs four independently-timed elements and a
 *     pseudo-element can only be one.
 *
 * WHAT IT DELIBERATELY DOES NOT OWN
 * ---------------------------------
 * Colour, radius, easing and every other value come from the `--k-*` roles in
 * `styles/ink.css` and the `--k-card-*` roles in `auth.css`. There is no hex
 * literal in this file: the emerald is the landing page's emerald, and it is
 * defined once.
 *
 * THE LIGHT IS DECORATIVE
 * -----------------------
 * Every beam, the glow and the background field are `aria-hidden`. They carry
 * no information, so they must not appear in the accessibility tree, and the
 * card's content must be fully readable with all of them switched off (which
 * is what `prefers-reduced-motion` and `forced-colors` do).
 */
import { useRef, type ReactNode } from 'react'
import { useCardTilt } from '@/hooks/useCardTilt'

interface Props {
  children: ReactNode
  /** Extra class on the card itself, for a per-view modifier. */
  className?: string
}

/**
 * The four beams, in the order they fire: top edge, right edge, bottom edge,
 * left edge. Each is one absolutely-positioned gradient strip; the keyframes in
 * `auth.css` translate it along its own edge and fade it at both ends so the
 * light appears to run into a corner and out the other side.
 *
 * The names are positional, not directional, so an RTL card does not need a
 * second set: the beams travel around the border, and "around" is the same
 * gesture in both directions.
 */
const BEAMS = ['top', 'right', 'bottom', 'left'] as const

export function AuthCard({ children, className }: Props) {
  const stageRef = useRef<HTMLDivElement>(null)
  const cardRef = useRef<HTMLDivElement>(null)

  useCardTilt(stageRef, cardRef)

  return (
    <div className="k-auth-stage" ref={stageRef}>
      {/* The ambient field behind the card. Two soft emerald pools and the
          landing page's hairline grid, at the same 4.5rem pitch the brand half
          uses, so the two halves are lit by the same room. */}
      <div className="k-auth-ambient" aria-hidden="true">
        <div className="k-auth-ambient-grid" />
        <div className="k-auth-ambient-pool k-auth-ambient-pool-a" />
        <div className="k-auth-ambient-pool k-auth-ambient-pool-b" />
      </div>

      <div className={`k-auth-card${className ? ` ${className}` : ''}`} ref={cardRef}>
        {/* Border light: a static hairline and four traveling beams. */}
        <div className="k-auth-card-light" aria-hidden="true">
          <span className="k-auth-card-edge" />
          {BEAMS.map((edge) => (
            <span key={edge} className="k-auth-card-beam" data-edge={edge} />
          ))}
        </div>

        {/* The surface. Kept separate from the light layer so the beams can sit
            above the border but below the content without a z-index argument
            between them. */}
        <div className="k-auth-card-body">{children}</div>
      </div>
    </div>
  )
}
