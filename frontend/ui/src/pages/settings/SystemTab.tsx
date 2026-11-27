import { useEffect, useMemo, useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { SettingRow } from '@/components/ui/SettingRow'
import { Switch } from '@/components/ui/Switch'
import { api, type SystemSettingItem } from '@/lib/api'
import type { StringKey } from '@/i18n/fa.ts'
import { useLanguage } from '@/i18n/useLanguage.ts'

const SECTION_LABELS: Record<string, StringKey> = {
  provider: 'settings.system.section.provider',
  translation: 'settings.system.section.translation',
  jobs: 'settings.system.section.jobs',
  limits: 'settings.system.section.limits',
  storage: 'settings.system.section.storage',
}

const ITEM_LABELS: Record<string, { label: StringKey; hint: StringKey }> = {
  'openai.base_url': { label: 'settings.system.baseUrl', hint: 'settings.system.baseUrlHint' },
  'openai.has_api_key': { label: 'settings.system.hasApiKey', hint: 'settings.system.hasApiKeyHint' },
  'translation.default_model': { label: 'settings.system.defaultModel', hint: 'settings.system.defaultModelHint' },
  'translation.max_concurrency': { label: 'settings.system.maxConcurrency', hint: 'settings.system.maxConcurrencyHint' },
  'translation.max_parallel_jobs': { label: 'settings.system.maxParallelJobs', hint: 'settings.system.maxParallelJobsHint' },
  'translation.max_jobs_per_user': { label: 'settings.system.maxJobsPerUser', hint: 'settings.system.maxJobsPerUserHint' },
  'translation.max_retries': { label: 'settings.system.maxRetries', hint: 'settings.system.maxRetriesHint' },
  'translation.retry_delay': { label: 'settings.system.retryDelay', hint: 'settings.system.retryDelayHint' },
  'translation.max_retry_delay': { label: 'settings.system.maxRetryDelay', hint: 'settings.system.maxRetryDelayHint' },
  'limits.max_upload_mb': { label: 'settings.system.maxUpload', hint: 'settings.system.maxUploadHint' },
  'storage.auto_cleanup': { label: 'settings.system.autoCleanup', hint: 'settings.system.autoCleanupHint' },
  'storage.output_dir': { label: 'settings.system.outputDir', hint: 'settings.system.outputDirHint' },
  'storage.temp_dir': { label: 'settings.system.tempDir', hint: 'settings.system.tempDirHint' },
}

type DraftValue = string | boolean

function draftValue(item: SystemSettingItem): DraftValue {
  return item.type === 'bool' ? Boolean(item.value) : String(item.value ?? '')
}

export function SystemTab({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useLanguage()
  const query = useQuery({
    queryKey: ['system-settings'],
    queryFn: api.systemSettings,
    staleTime: 15_000,
    refetchOnWindowFocus: false,
  })
  const [draft, setDraft] = useState<Record<string, DraftValue>>({})
  const [saving, setSaving] = useState(false)
  const [status, setStatus] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    // A backend that predates the typed settings service answers `/api/settings`
    // with a raw key/value dump (`{items: [...]}`), not `{sections, meta}`.
    // Guard the shape so a stale server shows an error instead of throwing on
    // `sections.flatMap` and blanking the whole page.
    if (!query.data || !Array.isArray(query.data.sections)) return
    const next: Record<string, DraftValue> = {}
    for (const section of query.data.sections) {
      for (const item of section.items) next[item.key] = draftValue(item)
    }
    setDraft(next)
  }, [query.data])

  const items = useMemo(
    () =>
      Array.isArray(query.data?.sections)
        ? query.data.sections.flatMap((section) => section.items)
        : [],
    [query.data],
  )

  const dirty = useMemo(
    () =>
      items
        .filter((item) => item.editable && String(draft[item.key]) !== String(draftValue(item)))
        .map((item) => item.key),
    [draft, items],
  )

  const save = async () => {
    if (!dirty.length || saving) return
    const patch: Record<string, string | number | boolean> = {}
    for (const item of items) {
      if (!dirty.includes(item.key)) continue
      const value = draft[item.key]
      if (item.type === 'bool') patch[item.key] = Boolean(value)
      else if (item.type === 'int') patch[item.key] = Number(value)
      else if (item.type === 'float') patch[item.key] = Number(value)
      else patch[item.key] = String(value ?? '')
    }
    setSaving(true)
    setError(null)
    setStatus(null)
    try {
      const response = await api.updateSystemSettings(patch)
      const next: Record<string, DraftValue> = {}
      for (const section of response.sections) {
        for (const item of section.items) next[item.key] = draftValue(item)
      }
      setDraft(next)
      setStatus(t('settings.system.saved'))
      window.setTimeout(() => setStatus(null), 2500)
      await query.refetch()
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : t('settings.system.saveFailed'))
    } finally {
      setSaving(false)
    }
  }

  if (query.isPending) {
    return <div className="skeleton" style={{ height: 320 }} />
  }
  if (query.isError || !query.data) {
    return (
      <p role="alert" className="alert alert-error">
        {t('settings.system.loadError')}
      </p>
    )
  }
  if (!Array.isArray(query.data.sections) || !query.data.meta) {
    return (
      <p role="alert" className="alert alert-error">
        {t('settings.system.staleBackend')}
      </p>
    )
  }

  const meta = query.data.meta
  const writable = isAdmin && meta.is_admin

  return (
    <div className="settings-system">
      {!writable ? (
        <p className="alert alert-info" role="status">
          {t('settings.system.readOnly')}
        </p>
      ) : null}
      {meta.hosted ? (
        <p className="alert alert-info" role="status">
          {t('settings.system.hosted')}
        </p>
      ) : null}
      {meta.env_overrides.length ? (
        <p className="settings-card-hint">
          {t('settings.system.envLocked', { vars: meta.env_overrides.join(', ') })}
        </p>
      ) : null}

      {query.data.sections.map((section) => (
        <section key={section.key} className="settings-card" aria-labelledby={`system-${section.key}-title`}>
          <h2 id={`system-${section.key}-title`} className="settings-card-title">
            {t(SECTION_LABELS[section.key] ?? 'settings.system.section.other')}
          </h2>
          {section.items.map((item) => {
            const labels = ITEM_LABELS[item.key]
            const label = labels ? t(labels.label) : item.key
            const hint = labels ? t(labels.hint) : undefined
            return (
              <SettingRow key={item.key} id={`system-${item.key.replaceAll('.', '-')}`} label={label} hint={hint}>
                {(ids) => (
                  <div className="settings-system-control">
                    {item.type === 'bool' ? (
                      <Switch
                        checked={Boolean(draft[item.key])}
                        labelledBy={ids.labelId}
                        describedBy={ids.describedBy}
                        disabled={!item.editable}
                        onChange={(next) =>
                          setDraft((current) => ({ ...current, [item.key]: next }))
                        }
                      />
                    ) : item.read_only ? (
                      <code className="settings-system-readonly">{String(item.value)}</code>
                    ) : (
                      <input
                        className="field settings-system-input"
                        type={item.type === 'int' || item.type === 'float' ? 'number' : 'text'}
                        value={String(draft[item.key] ?? '')}
                        min={item.min ?? undefined}
                        max={item.max ?? undefined}
                        step={item.type === 'float' ? 0.5 : undefined}
                        disabled={!item.editable}
                        aria-describedby={ids.describedBy}
                        onChange={(event) =>
                          setDraft((current) => ({ ...current, [item.key]: event.target.value }))
                        }
                      />
                    )}
                    <span className="settings-system-badges">
                      <span className="badge">{t(`settings.system.source.${item.source}` as StringKey)}</span>
                      {item.restart_required ? (
                        <span className="badge badge-warning">{t('settings.system.restart')}</span>
                      ) : null}
                      {item.env ? <span className="badge">{item.env}</span> : null}
                    </span>
                    {item.effective ? (
                      <span className="settings-system-effective">
                        {t('settings.system.effective', { model: item.effective })}
                      </span>
                    ) : null}
                  </div>
                )}
              </SettingRow>
            )
          })}
        </section>
      ))}

      {writable ? (
        <div className="settings-system-save">
          <button
            type="button"
            className="btn btn-primary"
            disabled={!dirty.length || saving}
            onClick={() => void save()}
          >
            {saving ? t('settings.system.saving') : t('settings.system.save')}
          </button>
          {dirty.length ? (
            <span className="settings-card-hint">
              {t('settings.system.dirty', { count: dirty.length })}
            </span>
          ) : null}
          {status ? <span className="settings-inline-status">{status}</span> : null}
          {error ? (
            <span role="alert" className="field-error">
              {error}
            </span>
          ) : null}
        </div>
      ) : null}
    </div>
  )
}
