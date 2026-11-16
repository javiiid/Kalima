/**
 * A range input with the value always in view.
 *
 * The badge is not decoration: a slider whose number appears only while you are
 * holding it asks the reader to remember what they saw. `aria-valuetext` gives
 * the same number a unit, because "18" alone is not an answer to "18 what?".
 *
 * The optional reset button is how "default" stays reachable for a value that
 * has no room for a "default" entry in a list.
 */
interface SliderProps {
  id: string
  name?: string | undefined
  value: number
  min: number
  max: number
  step: number
  /** What a screen reader reads, unit included ("18 pixels"). */
  valueText: string
  /** What the badge shows ("18x", "760"). */
  display: string
  onChange: (next: number) => void
  onChangeEnd?: (() => void) | undefined
  onBlur?: (() => void) | undefined
  onReset?: (() => void) | undefined
  resetLabel?: string | undefined
  describedBy?: string | undefined
  disabled?: boolean | undefined
  /** True while the value already equals the server's default. */
  atDefault?: boolean | undefined
}

function ResetIcon() {
  return (
    <svg
      width={16}
      height={16}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth={1.75}
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
      focusable="false"
    >
      <path d="M3 12a9 9 0 1 0 3-6.7" />
      <path d="M3 4v5h5" />
    </svg>
  )
}

export function Slider({
  id,
  name,
  value,
  min,
  max,
  step,
  valueText,
  display,
  onChange,
  onChangeEnd,
  onBlur,
  onReset,
  resetLabel,
  describedBy,
  disabled,
  atDefault,
}: SliderProps) {
  return (
    <div className="ui-slider">
      <input
        id={id}
        name={name}
        type="range"
        min={min}
        max={max}
        step={step}
        value={Number.isFinite(value) ? value : min}
        disabled={disabled}
        aria-describedby={describedBy}
        aria-valuetext={valueText}
        onChange={(event) => onChange(Number(event.target.value))}
        onPointerUp={() => onChangeEnd?.()}
        onKeyUp={() => onChangeEnd?.()}
        onBlur={onBlur}
      />
      <output className="ui-slider-value" htmlFor={id}>
        {display}
      </output>
      {onReset ? (
        <button
          type="button"
          className="ui-slider-reset"
          onClick={onReset}
          disabled={disabled || atDefault}
          aria-label={resetLabel}
          title={resetLabel}
        >
          <ResetIcon />
        </button>
      ) : null}
    </div>
  )
}