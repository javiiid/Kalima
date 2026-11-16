/**
 * The one place a page says what is unsaved and offers to save it.
 *
 * `aria-live="polite"` is on the status, not on the buttons: a screen reader
 * should hear "two changes not saved" once when it changes, not re-read the
 * buttons on every keystroke. The bar is sticky at the bottom on a phone,
 * because a save button that scrolls away is a save button that gets missed.
 */
interface SaveBarProps {
  dirtyCount: number
  saving: boolean
  savedLabel: string | null
  saveLabel: string
  cancelLabel: string
  onSave: () => void
  onCancel: () => void
  canSave: boolean
}

export function SaveBar({
  dirtyCount,
  saving,
  savedLabel,
  saveLabel,
  cancelLabel,
  onSave,
  onCancel,
  canSave,
}: SaveBarProps) {
  return (
    <div className="save-bar">
      <span className="save-bar-status" aria-live="polite">
        {saving ? '…' : savedLabel ?? `${dirtyCount}`}
      </span>
      <span className="save-bar-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={saving}>
          {cancelLabel}
        </button>
        <button type="button" className="btn btn-primary" onClick={onSave} disabled={!canSave || saving}>
          {saveLabel}
        </button>
      </span>
    </div>
  )
}