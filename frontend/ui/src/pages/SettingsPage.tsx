import { useCallback, useEffect, useRef, useState } from 'react'
import { Link, useSearchParams } from 'react-router-dom'
import { useQuery, useQueryClient } from '@tanstack/react-query'
import { ConfirmDialog } from '@/components/settings/ConfirmDialog'
import { SettingsIcon } from '@/components/settings/SettingsIcon'
import {
  parseSettingsTab,
  SETTINGS_TABS,
  storeSettingsTab,
  storedSettingsTab,
  type SettingsTabKey,
} from '@/components/settings/tabs'
import { SaveBar } from '@/components/ui/SaveBar'
import { Tabs, panelId, tabId } from '@/components/ui/Tabs'
import { api } from '@/lib/api'
import { useLanguage } from '@/i18n/useLanguage.ts'
import {
  countChanges,
  diffPreferences,
  hasChanges,
  type GeneralPreferences,
  type NotificationPreferences,
  type Preferences,
  type PreferencesMeta,
  type TranslationPreferences,
} from '@/lib/preferences.ts'
import { AppearanceTab } from './settings/AppearanceTab'
import { DataTab } from './settings/DataTab'
import { GeneralTab } from './settings/GeneralTab'
import { NotificationsTab } from './settings/NotificationsTab'
import { ReadingTab } from './settings/ReadingTab'
import { TranslationTab } from './settings/TranslationTab'
import './settings/settings.css'

const EXPLICIT_TABS = new Set<SettingsTabKey>(['general', 'translation', 'notifications'])

interface PreferencesResponse {
  value: Preferences
  meta: PreferencesMeta
}

export function SettingsPage() {
  const { t } = useLanguage()
  const client = useQueryClient()
  const [searchParams, setSearchParams] = useSearchParams()

  const query = useQuery<PreferencesResponse>({
    queryKey: ['preferences'],
    queryFn: api.preferences,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  const [server, setServer] = useState<Preferences | null>(null)
  const [draft, setDraft] = useState<Preferences | null>(null)
  const [revision, setRevision] = useState(0)
  const [saving, setSaving] = useState(false)
  const [savedLabel, setSavedLabel] = useState<string | null>(null)
  const [saveError, setSaveError] = useState<string | null>(null)
  const [pendingTab, setPendingTab] = useState<SettingsTabKey | null>(null)
  const initialised = useRef(false)
  const validateRef = useRef<(() => Promise<boolean>) | null>(null)

  useEffect(() => {
    if (!query.data || initialised.current) return
    initialised.current = true
    setServer(query.data.value)
    setDraft(query.data.value)
  }, [query.data])

  const applyValue = useCallback(
    (value: Preferences, remount: boolean) => {
      setServer(value)
      setDraft(value)
      if (remount) setRevision((current) => current + 1)
      client.setQueryData<PreferencesResponse>(['preferences'], (old) =>
        old ? { ...old, value } : old,
      )
    },
    [client],
  )

  const onReadingSaved = useCallback(
    (value: Preferences) => {
      setServer((prev) => (prev ? { ...prev, reading: value.reading } : prev))
      setDraft((prev) => (prev ? { ...prev, reading: value.reading } : prev))
      client.setQueryData<PreferencesResponse>(['preferences'], (old) =>
        old ? { ...old, value: { ...old.value, reading: value.reading } } : old,
      )
    },
    [client],
  )

  const onAppearanceSaved = useCallback(
    (value: Preferences) => {
      setServer((prev) => (prev ? { ...prev, appearance: value.appearance } : prev))
      setDraft((prev) => (prev ? { ...prev, appearance: value.appearance } : prev))
      client.setQueryData<PreferencesResponse>(['preferences'], (old) =>
        old ? { ...old, value: { ...old.value, appearance: value.appearance } } : old,
      )
    },
    [client],
  )

  const updateGeneral = useCallback((patch: Partial<GeneralPreferences>) => {
    setDraft((prev) => (prev ? { ...prev, general: { ...prev.general, ...patch } } : prev))
  }, [])

  const updateTranslation = useCallback((patch: Partial<TranslationPreferences>) => {
    setDraft((prev) =>
      prev ? { ...prev, translation: { ...prev.translation, ...patch } } : prev,
    )
  }, [])

  const updateNotifications = useCallback((patch: Partial<NotificationPreferences>) => {
    setDraft((prev) =>
      prev ? { ...prev, notifications: { ...prev.notifications, ...patch } } : prev,
    )
  }, [])

  const registerValidate = useCallback((validate: (() => Promise<boolean>) | null) => {
    validateRef.current = validate
  }, [])

  const changes = server && draft ? diffPreferences(server, draft) : {}
  const dirtyCount = countChanges(changes)

  const save = useCallback(async (): Promise<boolean> => {
    if (!server || !draft) return false
    if (validateRef.current) {
      const valid = await validateRef.current()
      if (!valid) return false
    }
    const patch = diffPreferences(server, draft)
    if (!hasChanges(patch)) return true
    setSaving(true)
    setSaveError(null)
    try {
      const response = await api.updatePreferences(patch)
      applyValue(response.value, true)
      setSavedLabel(t('settings.saved'))
      window.setTimeout(() => setSavedLabel(null), 2500)
      return true
    } catch (cause) {
      const message = cause instanceof Error ? cause.message : ''
      setSaveError(t('settings.saveFailed', { message }))
      return false
    } finally {
      setSaving(false)
    }
  }, [applyValue, draft, server, t])

  const discard = useCallback(() => {
    if (!server) return
    setDraft(server)
    setRevision((current) => current + 1)
    setSavedLabel(null)
    setSaveError(null)
  }, [server])

  const tabParam = searchParams.get('tab')
  const active = tabParam ? parseSettingsTab(tabParam) : storedSettingsTab()

  const go = useCallback(
    (next: SettingsTabKey) => {
      storeSettingsTab(next)
      setSearchParams({ tab: next }, { replace: true })
      setPendingTab(null)
    },
    [setSearchParams],
  )

  const requestTab = (next: SettingsTabKey) => {
    if (next === active) return
    if (dirtyCount > 0) setPendingTab(next)
    else go(next)
  }

  useEffect(() => {
    if (dirtyCount === 0) return
    const handler = (event: BeforeUnloadEvent) => {
      event.preventDefault()
      event.returnValue = ''
    }
    window.addEventListener('beforeunload', handler)
    return () => window.removeEventListener('beforeunload', handler)
  }, [dirtyCount])

  if (query.isPending) {
    return (
      <main className="page settings-page" aria-busy="true">
        <p className="settings-loading">{t('settings.loading')}</p>
        <div className="skeleton" style={{ height: 48, marginBottom: 16 }} />
        <div className="skeleton" style={{ height: 320 }} />
      </main>
    )
  }

  if (query.isError && !server) {
    return (
      <main className="page settings-page">
        <p role="alert" className="alert alert-error">
          {t('settings.loadError')}
        </p>
        <button type="button" className="btn btn-primary" onClick={() => void query.refetch()}>
          {t('settings.retry')}
        </button>
      </main>
    )
  }

  const meta = query.data?.meta
  if (!server || !draft || !meta) {
    return (
      <main className="page settings-page" aria-busy="true">
        <p className="settings-loading">{t('settings.loading')}</p>
      </main>
    )
  }

  const items = SETTINGS_TABS.map((tab) => ({
    key: tab.key,
    label: t(tab.labelKey),
    icon: <SettingsIcon name={tab.icon} size={18} />,
  }))

  const explicit = EXPLICIT_TABS.has(active)

  const panel = (() => {
    switch (active) {
      case 'general':
        return (
          <GeneralTab
            key={`general-${revision}`}
            value={draft.general}
            meta={meta}
            onChange={updateGeneral}
            registerValidate={registerValidate}
          />
        )
      case 'translation':
        return (
          <TranslationTab
            key={`translation-${revision}`}
            value={draft.translation}
            meta={meta}
            onChange={updateTranslation}
            registerValidate={registerValidate}
          />
        )
      case 'reading':
        return (
          <ReadingTab
            key={`reading-${revision}`}
            value={draft.reading}
            onSaved={onReadingSaved}
          />
        )
      case 'appearance':
        return (
          <AppearanceTab
            key={`appearance-${revision}`}
            value={draft.appearance}
            onSaved={onAppearanceSaved}
          />
        )
      case 'notifications':
        return (
          <NotificationsTab
            key={`notifications-${revision}`}
            value={draft.notifications}
            meta={meta}
            onChange={updateNotifications}
            registerValidate={registerValidate}
          />
        )
      case 'data':
        return <DataTab preferences={server} onApplied={(value) => applyValue(value, true)} />
      default:
        return null
    }
  })()

  return (
    <main className="page settings-page">
      <header className="settings-header">
        <div>
          <h1 className="settings-title">{t('settings.title')}</h1>
          <p className="settings-subtitle">{t('settings.subtitle')}</p>
        </div>
        <Link to="/account" className="btn btn-ghost">
          {t('settings.backToAccount')}
        </Link>
      </header>

      {query.isError ? (
        <p className="alert alert-error" role="alert">
          {t('settings.offline')}
        </p>
      ) : null}

      <div className="settings-layout">
        <div className="settings-nav">
          <Tabs idBase="settings" items={items} active={active} onChange={requestTab} label={t('settings.tabsLabel')} />
        </div>

        <section
          role="tabpanel"
          id={panelId('settings', active)}
          aria-labelledby={tabId('settings', active)}
          tabIndex={0}
          className="settings-panel"
        >
          {panel}

          {saveError ? (
            <p className="alert alert-error" role="alert">
              {saveError}
            </p>
          ) : null}

          {explicit && (dirtyCount > 0 || saving || savedLabel) ? (
            <SaveBar
              dirtyCount={dirtyCount}
              saving={saving}
              savedLabel={savedLabel ?? (dirtyCount > 0 ? t('settings.dirty', { count: dirtyCount }) : null)}
              saveLabel={t('settings.save')}
              cancelLabel={t('settings.cancel')}
              canSave={!saving}
              onSave={() => {
                void save()
              }}
              onCancel={discard}
            />
          ) : null}
        </section>
      </div>

      <ConfirmDialog
        open={pendingTab !== null}
        title={t('settings.dialog.saveTitle')}
        confirmLabel={t('settings.dialog.save')}
        cancelLabel={t('settings.dialog.stay')}
        busy={saving}
        onConfirm={() => {
          void (async () => {
            const saved = await save()
            if (saved && pendingTab) go(pendingTab)
          })()
        }}
        onCancel={() => setPendingTab(null)}
      >
        <p>{t('settings.dialog.saveBody')}</p>
        <button
          type="button"
          className="btn btn-ghost"
          onClick={() => {
            discard()
            if (pendingTab) go(pendingTab)
          }}
        >
          {t('settings.dialog.discard')}
        </button>
      </ConfirmDialog>
    </main>
  )
}
