/**
 * A styled native `<select>`.
 *
 * The element stays native on purpose. A listbox built from divs has to
 * reimplement type-ahead, the phone's own picker, `option` semantics and the
 * magnifier behaviour of a long list -- and gets all four subtly wrong. The
 * wrapper exists only to draw the chevron and the invalid border.
 *
 * `options` always starts with the "default" entry the caller supplies: a
 * preference that resolves to something else must say what it resolves to,
 * rather than showing an empty first row.
 */
export interface SelectOption {
  value: string
  label: string
  disabled?: boolean | undefined
}

interface SelectProps {
  id: string
  name?: string | undefined
  value: string
  options: readonly SelectOption[]
  onChange: (next: string) => void
  onBlur?: (() => void) | undefined
  describedBy?: string | undefined
  invalid?: boolean | undefined
  disabled?: boolean | undefined
  title?: string | undefined
}

function Chevron() {
  return (
    <svg
      className="ui-select-chevron"
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
      <path d="m6 9 6 6 6-6" />
    </svg>
  )
}

export function Select({
  id,
  name,
  value,
  options,
  onChange,
  onBlur,
  describedBy,
  invalid,
  disabled,
  title,
}: SelectProps) {
  return (
    <span className="ui-select" data-invalid={invalid ? 'true' : undefined}>
      <select
        id={id}
        name={name}
        className="field"
        value={value}
        title={title}
        disabled={disabled}
        aria-describedby={describedBy}
        aria-invalid={invalid ? true : undefined}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value} disabled={option.disabled}>
            {option.label}
          </option>
        ))}
      </select>
      <Chevron />
    </span>
  )
}