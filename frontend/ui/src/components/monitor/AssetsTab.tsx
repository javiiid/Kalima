import { useEffect, useState } from 'react'
import type { Job } from '@/lib/api'
import { assetLabel, faBytes } from '@/lib/format'
import { useLanguage } from '@/i18n/useLanguage.ts'

/**
 * Assets tab.
 *
 * Links come from `asset_downloads`, not from `assets`. `assets` is the map of
 * produced file paths; only `asset_downloads` carries a URL the browser can
 * actually fetch, and a path is not a URL. Rendering the wrong one produced
 * dead links in an earlier draft of this page.
 *
 * Each file also has an `asset_previews` entry: the same bytes served inline,
 * so a reader can look at the PDF before deciding to keep it. The preview
 * opens in an overlay rather than a new tab, because the job page is where
 * the decision is made and a new tab loses it.
 */
export function AssetsTab({ job }: { job: Job }) {
  const { t } = useLanguage()
  const downloads = job.asset_downloads ?? {}
  const previews = job.asset_previews ?? {}
  const entries = Object.entries(downloads)
  const assets = job.assets ?? {}
  const [open, setOpen] = useState<{ label: string; href: string; download: string } | null>(null)

  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(null)
    }
    window.addEventListener('keydown', onKey)
    return () => window.removeEventListener('keydown', onKey)
  }, [open])

  if (entries.length === 0) {
    return <div className="surface-card empty">{t('monitor.assets.empty')}</div>
  }

  return (
    <div className="surface-card p-[var(--spacing-5)]">
      <div className="asset-grid">
        {entries.map(([name, href]) => {
          const label = assetLabel(name)
          // The raw value is a size in bytes on some entries and a path on
          // others, so it is only shown when it parses as a number.
          const raw = assets[name]
          const size = raw && /^\d+$/.test(raw) ? faBytes(Number(raw)) : ''
          const preview = previews[name]
          return (
            <div key={name} className="asset">
              <a className="asset-name" href={href} aria-label={t('monitor.assets.downloadAria', { name: label })}>
                {label.toUpperCase()}
              </a>
              <span className="asset-meta">{size || name}</span>
              {preview ? (
                <button
                  type="button"
                  className="asset-preview"
                  onClick={() => setOpen({ label, href: preview, download: href })}
                >
                  {t('monitor.assets.preview')}
                </button>
              ) : null}
            </div>
          )
        })}
      </div>
      {open ? (
        <div className="preview-overlay" role="dialog" aria-modal="true" aria-label={open.label}>
          <div className="preview-panel">
            <div className="preview-head">
              <strong>{open.label}</strong>
              <div className="preview-actions">
                <a className="btn btn-secondary" href={open.download}>
                  {t('monitor.assets.download')}
                </a>
                <button type="button" className="btn btn-secondary" onClick={() => setOpen(null)}>
                  {t('monitor.assets.close')}
                </button>
              </div>
            </div>
            {/* The server decides how each type is shown: a PDF inline, a
                DOCX as a script-free text page. Both arrive with a sandboxed
                CSP, so the frame cannot reach this document. */}
            <iframe className="preview-frame" src={open.href} title={open.label} />
          </div>
        </div>
      ) : null}
    </div>
  )
}
