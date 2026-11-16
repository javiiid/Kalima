/**
 * A switch, for a setting that takes effect on its own.
 *
 * `role="switch"` + `aria-checked`, not a checkbox: the platform's own switch
 * semantics are what a screen reader announces, and the state is carried by
 * the attribute rather than by the colour of an 8px knob. The visible label is
 * owned by `SettingRow`, so the control is named through `labelledBy` (an
 * `aria-labelledby` id) instead of duplicating the text here.
 *
 * The whole row is clickable because `SettingRow` renders the label as part of
 * the same row; this button is the only focusable part, which is deliberate --
 * one tab stop per setting.
 */
interface SwitchProps {
  checked: boolean
  onChange: (next: boolean) => void
  onBlur?: (() => void) | undefined
  labelledBy: string
  describedBy?: string | undefined
  disabled?: boolean | undefined
  /** A save is in flight. Shown, never used to disable the control. */
  pending?: boolean | undefined
}

export function Switch({
  checked,
  onChange,
  onBlur,
  labelledBy,
  describedBy,
  disabled,
  pending,
}: SwitchProps) {
  return (
    <button
      type="button"
      role="switch"
      aria-checked={checked}
      aria-labelledby={labelledBy}
      aria-describedby={describedBy}
      disabled={disabled}
      data-pending={pending ? 'true' : undefined}
      className="ui-switch"
      onClick={() => onChange(!checked)}
      onBlur={onBlur}
    >
      <span className="ui-switch-knob" aria-hidden="true" />
    </button>
  )
}