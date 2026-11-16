import { useEffect, useId, useRef } from 'react'
import type { ReactNode } from 'react'

/**
 * A native `<dialog>` for the two destructive confirmations.
 *
 * Native rather than a div overlay because the browser already owns the focus
 * trap, the `Esc` key and the inert background. The page owns the copy and the
 * action; this owns only the mechanics.
 */
interface ConfirmDialogProps {
  open: boolean
  title: string
  children: ReactNode
  confirmLabel: string
  cancelLabel: string
  onConfirm: () => void
  onCancel: () => void
  danger?: boolean | undefined
  confirmDisabled?: boolean | undefined
  busy?: boolean | undefined
}

export function ConfirmDialog({
  open,
  title,
  children,
  confirmLabel,
  cancelLabel,
  onConfirm,
  onCancel,
  danger,
  confirmDisabled,
  busy,
}: ConfirmDialogProps) {
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  return (
    <dialog
      ref={ref}
      className="settings-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        onCancel()
      }}
      onClose={() => {
        if (open) onCancel()
      }}
    >
      <h2 id={titleId} className="settings-dialog-title">
        {title}
      </h2>
      <div className="settings-dialog-body">{children}</div>
      <div className="settings-dialog-actions">
        <button type="button" className="btn btn-ghost" onClick={onCancel} disabled={busy}>
          {cancelLabel}
        </button>
        <button
          type="button"
          className={danger ? 'btn btn-danger' : 'btn btn-primary'}
          onClick={onConfirm}
          disabled={confirmDisabled || busy}
        >
          {confirmLabel}
        </button>
      </div>
    </dialog>
  )
}
