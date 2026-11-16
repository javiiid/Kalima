import type { ReactNode } from 'react'

/**
 * A labelled form control, with its hint and its error in the right places.
 *
 * The ids are handed to the caller rather than guessed, because `aria-
 * describedby` has to name the hint and the error by id, and a control that
 * forgets it is a control whose error is invisible to a screen reader. The
 * render prop is the smallest way to make forgetting impossible.
 *
 * The error is also `role="alert"`, so it is announced when it appears rather
 * than only when the field is revisited.
 */
export interface FieldIds {
  labelId: string
  hintId: string
  errorId: string
  describedBy: string | undefined
}

interface FieldProps {
  id: string
  label: string
  hint?: string | undefined
  error?: string | undefined
  children: (ids: FieldIds) => ReactNode
}

export function Field({ id, label, hint, error, children }: FieldProps) {
  const labelId = `${id}-label`
  const hintId = `${id}-hint`
  const errorId = `${id}-error`
  const describedBy =
    [hint ? hintId : null, error ? errorId : null].filter(Boolean).join(' ') || undefined

  return (
    <div className="field-group">
      <label id={labelId} className="label" htmlFor={id}>
        {label}
      </label>
      {children({ labelId, hintId, errorId, describedBy })}
      {hint ? (
        <p id={hintId} className="field-hint">
          {hint}
        </p>
      ) : null}
      {error ? (
        <p id={errorId} className="field-error" role="alert">
          {error}
        </p>
      ) : null}
    </div>
  )
}