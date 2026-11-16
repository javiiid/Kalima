import { useRef } from 'react'
import type { KeyboardEvent } from 'react'

/**
 * Two to four choices, all visible, one selected.
 *
 * A radiogroup, not a row of buttons: that is what it is, and it is what a
 * screen reader should hear. Arrow keys move the selection and the focus
 * together, `Home`/`End` jump to the ends, and the roving tabindex keeps the
 * group to a single stop in the page's tab order.
 *
 * The direction of the arrow keys follows the document's `dir`, so in the
 * Persian interface Right arrow moves to the previous option -- the option to
 * the *right* of the one you are on.
 */
export interface SegmentOption<T extends string> {
  value: T
  label: string
}

interface SegmentedControlProps<T extends string> {
  name?: string | undefined
  value: T
  options: readonly SegmentOption<T>[]
  onChange: (next: T) => void
  onBlur?: (() => void) | undefined
  labelledBy?: string | undefined
  describedBy?: string | undefined
  disabled?: boolean | undefined
  idBase: string
}

export function SegmentedControl<T extends string>({
  name,
  value,
  options,
  onChange,
  onBlur,
  labelledBy,
  describedBy,
  disabled,
  idBase,
}: SegmentedControlProps<T>) {
  const container = useRef<HTMLDivElement>(null)

  const move = (delta: number) => {
    const index = options.findIndex((option) => option.value === value)
    const next = options[(index + delta + options.length) % options.length]
    if (!next) return
    onChange(next.value)
    const button = container.current?.querySelector<HTMLButtonElement>(
      `#${CSS.escape(`${idBase}-${next.value}`)}`,
    )
    button?.focus()
  }

  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const rtl = getComputedStyle(event.currentTarget).direction === 'rtl'
    switch (event.key) {
      case 'ArrowRight':
        event.preventDefault()
        move(rtl ? -1 : 1)
        break
      case 'ArrowLeft':
        event.preventDefault()
        move(rtl ? 1 : -1)
        break
      case 'ArrowDown':
        event.preventDefault()
        move(1)
        break
      case 'ArrowUp':
        event.preventDefault()
        move(-1)
        break
      case 'Home':
        event.preventDefault()
        move(-options.length + 1)
        break
      case 'End':
        event.preventDefault()
        move(options.length - 1)
        break
      default:
        break
    }
  }

  return (
    <div
      ref={container}
      role="radiogroup"
      className="ui-segmented"
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      onKeyDown={onKeyDown}
    >
      {options.map((option) => {
        const selected = option.value === value
        return (
          <button
            key={option.value}
            id={`${idBase}-${option.value}`}
            type="button"
            role="radio"
            aria-checked={selected}
            tabIndex={selected ? 0 : -1}
            disabled={disabled}
            className="ui-segmented-option"
            onClick={() => onChange(option.value)}
            onBlur={onBlur}
            data-name={name}
          >
            {option.label}
          </button>
        )
      })}
    </div>
  )
}