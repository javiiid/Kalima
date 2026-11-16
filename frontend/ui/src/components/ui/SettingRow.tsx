import type { ReactNode } from 'react'

/**
 * One setting: its name and explanation on one side, its control on the other.
 *
 * This is the page's whole visual grammar, so it is one component rather than a
 * class repeated in six tabs. The label is a `<span>` with an id, not a
 * `<label for>`: the control is often a `button role="switch"` or a
 * `radiogroup`, and naming those through `aria-labelledby` is unambiguous where
 * `label for` is merely tolerated.
 *
 * `wide` is for controls that need the full width on a phone -- a slider, or a
 * select whose longest option is a timezone name.
 */
export interface RowIds {
  labelId: string
  hintId: string
  errorId: string
  describedBy: string | undefined
}

interface SettingRowProps {
  id: string
  label: string
  hint?: string | undefined
  error?: string | undefined
  wide?: boolean | undefined
  children: (ids: RowIds) => ReactNode
}

export function SettingRow({ id, label, hint, error, wide, children }: SettingRowProps) {
  const labelId = `${id}-label`
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

  return (
    <div className={`setting-row${wide ? ' wide' : ''}`}>
      <div className="setting-row-text">
        <span id={labelId} className="setting-row-label">
          {label}
        </span>
        {hint ? (
          <p id={hintId} className="setting-row-hint">
            {hint}
          </p>
        ) : null}
        {error ? (
          <p id={errorId} className="setting-row-error" role="alert">
            {error}
          </p>
        ) : null}
      </div>
      <div className="setting-row-control">{children({ labelId, hintId, errorId, describedBy })}</div>
    </div>
  )
}