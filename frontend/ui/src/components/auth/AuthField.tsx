/**
 * The auth form's field primitives.
 *
 * Login, signup and the recovery flow all need the same label, the same
 * bordered input, the same password row with its reveal toggle, and the same
 * strength meter. Writing those three times is how the login field ends up
 * 46px tall and the signup field 40px, so they live here once.
 *
 * ACCESSIBILITY CONTRACT
 * ----------------------
 * Every field is a real `<label for>` plus a real `<input>`. The error for a
 * field is rendered under it and wired with `aria-describedby`, and
 * `aria-invalid` is set so the state is announced rather than only coloured.
 * The reveal toggle is a `button` with `aria-pressed` and an explicit label,
 * never an icon with a title attribute.
 *
 * The strength meter is `aria-hidden` and paired with a text label, because a
 * four-segment bar announces nothing useful; the level name is the accessible
 * content.
 */
import { useId, type ReactNode } from 'react'
import type { StringKey } from '@/i18n/fa.ts'
import { passwordStrength } from '@/lib/password.ts'
import { EyeIcon, EyeOffIcon } from './AuthIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface FieldProps {
  id: string
  label: string
  /** Rendered at the label's inline end: "forgot password", a hint, a counter. */
  aside?: ReactNode
  error?: string | null
  hint?: string
  children: ReactNode
}

/**
 * The label / control / message scaffold. The control is passed in rather
 * than generated, because an email input and a password row are different
 * shapes but share everything around them.
 */
export function AuthField({ id, label, aside, error, hint, children }: FieldProps) {
  return (
    <div className="k-auth-field">
      <div className="k-auth-label">
        <label htmlFor={id}>{label}</label>
        {aside ? <span className="k-auth-label-aside">{aside}</span> : null}
      </div>
      {children}
      {error ? (
        <p className="k-auth-field-error" id={`${id}-error`}>
          {error}
        </p>
      ) : hint ? (
        <p className="k-auth-field-error" id={`${id}-hint`} style={{ color: 'var(--k-faint)' }}>
          {hint}
        </p>
      ) : null}
    </div>
  )
}

interface PasswordFieldProps {
  id: string
  label: string
  value: string
  onChange: (value: string) => void
  t: T
  visible: boolean
  onToggleVisible: () => void
  autoComplete: 'current-password' | 'new-password'
  disabled?: boolean
  error?: string | null
  aside?: ReactNode
  /** Show the four-segment strength meter. Signup only. */
  showStrength?: boolean
  onEnter?: () => void
}

/**
 * A password input with its reveal toggle inside the same border.
 *
 * The value is always `dir="ltr"`: a password is not prose, and in an RTL page
 * an LTR run inside an RTL container puts the caret at the wrong end and
 * reorders a mixed password on screen.
 */
export function AuthPasswordField({
  id,
  label,
  value,
  onChange,
  t,
  visible,
  onToggleVisible,
  autoComplete,
  disabled = false,
  error = null,
  aside = null,
  showStrength = false,
  onEnter,
}: PasswordFieldProps) {
  const strength = passwordStrength(value)
  const describedBy = error ? `${id}-error` : undefined

  return (
    <div className="k-auth-field">
      <div className="k-auth-label">
        <label htmlFor={id}>{label}</label>
        {aside ? <span className="k-auth-label-aside">{aside}</span> : null}
      </div>

      <div className="k-auth-password">
        <input
          id={id}
          className="k-auth-input"
          type={visible ? 'text' : 'password'}
          dir="ltr"
          autoComplete={autoComplete}
          value={value}
          onChange={(event) => onChange(event.target.value)}
          onKeyDown={(event) => {
            if (event.key === 'Enter' && onEnter) onEnter()
          }}
          disabled={disabled}
          aria-invalid={error ? 'true' : undefined}
          aria-describedby={describedBy}
        />
        <button
          type="button"
          className="k-auth-reveal"
          aria-pressed={visible}
          aria-label={visible ? t('auth.hidePassword') : t('auth.showPassword')}
          onClick={onToggleVisible}
          disabled={disabled}
          tabIndex={0}
        >
          {visible ? <EyeOffIcon size={17} /> : <EyeIcon size={17} />}
        </button>
      </div>

      {showStrength && value.length > 0 ? (
        <div className="k-auth-strength" data-level={strength.level}>
          <div className="k-auth-strength-bars" aria-hidden="true">
            <span className="k-auth-strength-bar" />
            <span className="k-auth-strength-bar" />
            <span className="k-auth-strength-bar" />
            <span className="k-auth-strength-bar" />
          </div>
          <p className="k-auth-strength-meta">
            <span>{t('auth.strengthLabel')}</span>
            <span className="k-auth-strength-value">{t(strength.labelKey)}</span>
          </p>
        </div>
      ) : null}

      {error ? (
        <p className="k-auth-field-error" id={`${id}-error`}>
          {error}
        </p>
      ) : showStrength ? (
        <p className="k-auth-field-error" style={{ color: 'var(--k-faint)' }}>
          {t('auth.passwordHint')}
        </p>
      ) : null}
    </div>
  )
}

/** A plain text/email input, sharing the same border and focus treatment. */
export function AuthInput({
  id,
  type,
  value,
  onChange,
  autoComplete,
  placeholder,
  disabled = false,
  error = null,
  dir,
  inputMode,
  onEnter,
}: {
  id: string
  type: 'text' | 'email'
  value: string
  onChange: (value: string) => void
  autoComplete: string
  placeholder?: string
  disabled?: boolean
  error?: string | null
  dir?: 'ltr'
  inputMode?: 'email' | 'numeric'
  onEnter?: () => void
}) {
  return (
    <input
      id={id}
      className="k-auth-input"
      type={type}
      dir={dir}
      inputMode={inputMode}
      autoComplete={autoComplete}
      placeholder={placeholder}
      value={value}
      onChange={(event) => onChange(event.target.value)}
      onKeyDown={(event) => {
        if (event.key === 'Enter' && onEnter) onEnter()
      }}
      disabled={disabled}
      aria-invalid={error ? 'true' : undefined}
      aria-describedby={error ? `${id}-error` : undefined}
    />
  )
}

/**
 * The error banner.
 *
 * `role="alert"` so it is announced when it appears, and `key` on the message
 * is the caller's job -- a banner that is already mounted and only changes its
 * text is not re-announced by every screen reader.
 */
export function AuthError({ message }: { message: string }) {
  return (
    <p className="k-auth-error" role="alert">
      <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="M12 8v5M12 16.5v.01" strokeLinecap="round" />
      </svg>
      {message}
    </p>
  )
}

/** The success / informational banner. `role="status"` is the polite channel. */
export function AuthNotice({ message }: { message: string }) {
  return (
    <p className="k-auth-notice" role="status">
      <svg width={15} height={15} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={2} aria-hidden="true">
        <circle cx="12" cy="12" r="9" />
        <path d="m8.5 12.2 2.4 2.4 4.6-4.9" strokeLinecap="round" strokeLinejoin="round" />
      </svg>
      {message}
    </p>
  )
}

/** The primary submit, with its in-place loading state. */
export function AuthSubmit({
  label,
  busy,
  busyLabel,
  disabled = false,
}: {
  label: string
  busy: boolean
  busyLabel: string
  disabled?: boolean
}) {
  return (
    <button
      type="submit"
      className="k-auth-submit"
      data-busy={busy ? 'true' : 'false'}
      disabled={busy || disabled}
      aria-busy={busy}
    >
      {busy ? (
        <>
          <span className="k-auth-spinner" aria-hidden="true" />
          {busyLabel}
        </>
      ) : (
        label
      )}
    </button>
  )
}

/**
 * A stable id for a field, prefixed so two forms on one page cannot collide.
 * React's `useId` already guarantees uniqueness; the prefix only makes the
 * generated ids readable in the DOM.
 */
export function useFieldId(prefix: string): string {
  const raw = useId()
  return `${prefix}${raw.replace(/:/g, '')}`
}
