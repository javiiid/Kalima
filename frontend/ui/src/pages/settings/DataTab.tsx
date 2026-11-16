import { useRef, useState, type ChangeEvent } from 'react'
import { useQueryClient } from '@tanstack/react-query'
import { ConfirmDialog } from '@/components/settings/ConfirmDialog'
import { SETTINGS_TAB_STORAGE_KEY } from '@/components/settings/tabs'
import { api } from '@/lib/api'
import { LANGUAGE_KEY } from '@/i18n/lang.ts'
import { useLanguage } from '@/i18n/useLanguage.ts'
import {
  applyStoredAppearance,
  DENSITY_KEY,
  MOTION_KEY,
  useDensity,
  useMotion,
} from '@/hooks/useDensity'
import { applyStoredTheme, setThemeChoice, THEME_KEY } from '@/hooks/useTheme'
import {
  applyPreferencesPatch,
  countChanges,
  diffPreferences,
  exportPreferences,
  ImportError,
  importErrorMessageKey,
  MAX_IMPORT_BYTES,
  parseImportedPreferences,
  serialiseExport,
  type AppearancePreferences,
  type Preferences,
  type PreferencesPatch,
} from '@/lib/preferences.ts'

interface DataTabProps {
  preferences: Preferences
  onApplied: (value: Preferences) => void
}

function exportFilename(now: Date): string {
  const stamp = now.toISOString().slice(0, 10).replaceAll('-', '')
  return `kalima-settings-${stamp}.json`
}

export function DataTab({ preferences, onApplied }: DataTabProps) {
  const { t, setLang } = useLanguage()
  const client = useQueryClient()
  const { setDensity } = useDensity()
  const { setAnimations } = useMotion()
  const fileInput = useRef<HTMLInputElement>(null)

  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [importPatch, setImportPatch] = useState<PreferencesPatch | null>(null)
  const [importCount, setImportCount] = useState(0)
  const [confirmClear, setConfirmClear] = useState(false)
  const [confirmReset, setConfirmReset] = useState(false)
  const [resetWord, setResetWord] = useState('')

  const applyAppearance = (appearance: AppearancePreferences) => {
    setThemeChoice(appearance.theme)
    setDensity(appearance.density)
    setAnimations(appearance.animations)
  }

  const download = () => {
    const now = new Date()
    const text = serialiseExport(exportPreferences(preferences, now))
    const blob = new Blob([text], { type: 'application/json' })
    const url = URL.createObjectURL(blob)
    const anchor = document.createElement('a')
    anchor.href = url
    anchor.download = exportFilename(now)
    document.body.appendChild(anchor)
    anchor.click()
    anchor.remove()
    URL.revokeObjectURL(url)
    setStatus(t('settings.data.exportDone'))
    setError(null)
  }

  const chooseImport = () => {
    setStatus(null)
    setError(null)
    fileInput.current?.click()
  }

  const readImport = async (event: ChangeEvent<HTMLInputElement>) => {
    const file = event.target.files?.[0]
    event.target.value = ''
    if (!file) return
    setStatus(null)
    setError(null)
    try {
      if (file.size > MAX_IMPORT_BYTES) throw new ImportError('too-large')
      const patch = parseImportedPreferences(await file.text(), t)
      const changed = countChanges(
        diffPreferences(preferences, applyPreferencesPatch(preferences, patch)),
      )
      if (changed === 0) {
        setStatus(t('settings.data.importNoChange'))
        return
      }
      setImportCount(changed)
      setImportPatch(patch)
    } catch (cause) {
      if (cause instanceof ImportError) setError(t(importErrorMessageKey(cause.code)))
      else setError(t('settings.data.importFailed'))
    }
  }

  const applyImport = async () => {
    if (!importPatch) return
    setBusy(true)
    try {
      const response = await api.updatePreferences(importPatch)
      onApplied(response.value)
      applyAppearance(response.value.appearance)
      setLang(response.value.general.language)
      setStatus(t('settings.data.importDone'))
      setError(null)
      setImportPatch(null)
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.data.importFailed'))
    } finally {
      setBusy(false)
    }
  }

  const clearCache = () => {
    for (const key of [THEME_KEY, LANGUAGE_KEY, DENSITY_KEY, MOTION_KEY, SETTINGS_TAB_STORAGE_KEY]) {
      try {
        localStorage.removeItem(key)
      } catch {
        // Private mode: nothing was stored to clear.
      }
    }
    client.clear()
    applyStoredTheme()
    applyStoredAppearance()
    setLang('fa')
    setConfirmClear(false)
    setStatus(t('settings.data.clearCacheDone'))
    setError(null)
  }

  const requiredWord = t('settings.data.resetWord')
  const resetMatches =
    resetWord.trim().toLocaleLowerCase() === requiredWord.trim().toLocaleLowerCase()

  const reset = async () => {
    if (!resetMatches) return
    setBusy(true)
    try {
      const response = await api.resetPreferences()
      onApplied(response.value)
      applyAppearance(response.value.appearance)
      setLang(response.value.general.language)
      setStatus(t('settings.data.resetDone'))
      setError(null)
      setConfirmReset(false)
      setResetWord('')
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.data.resetFailed'))
    } finally {
      setBusy(false)
    }
  }

  return (
    <section className="settings-card" aria-labelledby="settings-data-title">
      <h2 id="settings-data-title" className="settings-card-title">
        {t('settings.data.title')}
      </h2>
      <p className="settings-card-hint">{t('settings.data.hint')}</p>

      {status ? (
        <p className="settings-inline-status" role="status">
          {status}
        </p>
      ) : null}
      {error ? (
        <p className="alert alert-error" role="alert">
          {error}
        </p>
      ) : null}

      <div className="settings-data-grid">
        <div className="settings-data-action">
          <h3 className="settings-data-action-title">{t('settings.data.export')}</h3>
          <p className="settings-card-hint">{t('settings.data.exportHint')}</p>
          <button type="button" className="btn btn-secondary" onClick={download}>
            {t('settings.data.exportAction')}
          </button>
        </div>

        <div className="settings-data-action">
          <h3 className="settings-data-action-title">{t('settings.data.import')}</h3>
          <p className="settings-card-hint">{t('settings.data.importHint')}</p>
          <input
            ref={fileInput}
            type="file"
            accept="application/json,.json"
            className="sr-only"
            onChange={(event) => {
              void readImport(event)
            }}
          />
          <button type="button" className="btn btn-secondary" onClick={chooseImport}>
            {t('settings.data.importAction')}
          </button>
        </div>
      </div>

      <div className="settings-danger-zone">
        <div className="settings-data-action">
          <h3 className="settings-data-action-title">{t('settings.data.clearCache')}</h3>
          <p className="settings-card-hint">{t('settings.data.clearCacheHint')}</p>
          <button type="button" className="btn btn-ghost" onClick={() => setConfirmClear(true)}>
            {t('settings.data.clearCacheAction')}
          </button>
        </div>

        <div className="settings-data-action">
          <h3 className="settings-data-action-title">{t('settings.data.reset')}</h3>
          <p className="settings-card-hint">{t('settings.data.resetHint')}</p>
          <button type="button" className="btn btn-danger" onClick={() => setConfirmReset(true)}>
            {t('settings.data.resetAction')}
          </button>
        </div>
      </div>

      <ConfirmDialog
        open={importPatch !== null}
        title={t('settings.data.importConfirmTitle')}
        confirmLabel={t('settings.dialog.confirm')}
        cancelLabel={t('settings.dialog.cancel')}
        busy={busy}
        onConfirm={() => {
          void applyImport()
        }}
        onCancel={() => setImportPatch(null)}
      >
        <p>{t('settings.data.importConfirmBody', { count: importCount })}</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={confirmClear}
        title={t('settings.data.clearCacheConfirmTitle')}
        confirmLabel={t('settings.data.clearCacheAction')}
        cancelLabel={t('settings.dialog.cancel')}
        danger
        onConfirm={clearCache}
        onCancel={() => setConfirmClear(false)}
      >
        <p>{t('settings.data.clearCacheConfirmBody')}</p>
      </ConfirmDialog>

      <ConfirmDialog
        open={confirmReset}
        title={t('settings.data.resetConfirmTitle')}
        confirmLabel={t('settings.data.resetAction')}
        cancelLabel={t('settings.dialog.cancel')}
        danger
        busy={busy}
        confirmDisabled={!resetMatches}
        onConfirm={() => {
          void reset()
        }}
        onCancel={() => {
          setConfirmReset(false)
          setResetWord('')
        }}
      >
        <p>{t('settings.data.resetConfirmBody', { word: requiredWord })}</p>
        <input
          className="field"
          value={resetWord}
          aria-label={t('settings.data.resetConfirmBody', { word: requiredWord })}
          onChange={(event) => setResetWord(event.target.value)}
        />
        {resetWord && !resetMatches ? (
          <p className="field-error" role="alert">
            {t('settings.data.resetMismatch')}
          </p>
        ) : null}
      </ConfirmDialog>
    </section>
  )
}
