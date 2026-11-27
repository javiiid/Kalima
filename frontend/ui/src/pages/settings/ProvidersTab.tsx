import { useQuery } from '@tanstack/react-query'
import { SettingRow } from '@/components/ui/SettingRow'
import { api } from '@/lib/api'
import { useLanguage } from '@/i18n/useLanguage.ts'

/**
 * The active translation provider, shown read-only.
 *
 * The provider is a platform-level fact read from `config/config.yaml`, not a
 * per-user setting, so this tab only reports it: base URL, active model,
 * whether a key is stored, and the concurrency ceiling. There is no editing
 * here by design -- changing the provider is a server configuration change.
 *
 * `GET /api/provider-config` never returns the key itself, only `has_api_key`,
 * so this tab can never leak a secret. The key row states presence, not value.
 */
function providerBrand(baseUrl: string): string {
  if (/gapgpt/i.test(baseUrl)) return 'GapGPT'
  try {
    return new URL(baseUrl).host
  } catch {
    return baseUrl
  }
}

export function ProvidersTab() {
  const { t } = useLanguage()
  const query = useQuery({
    queryKey: ['provider-config'],
    queryFn: api.providerConfig,
    staleTime: 30_000,
    refetchOnWindowFocus: false,
  })

  if (query.isPending) {
    return <div className="skeleton" style={{ height: 240 }} />
  }
  if (query.isError || !query.data) {
    return (
      <p role="alert" className="alert alert-error">
        {t('settings.providers.loadError')}
      </p>
    )
  }

  const config = query.data
  const connected = config.has_api_key
  const brand = providerBrand(config.base_url)

  return (
    <div className="settings-providers">
      <section className="settings-card">
        <div className="settings-providers-head">
          <div className="settings-providers-id">
            <span className="settings-providers-mark" aria-hidden="true">
              {brand.slice(0, 1).toUpperCase()}
            </span>
            <div>
              <h2 className="settings-card-title">{brand}</h2>
              <p className="settings-card-hint">{t('settings.providers.kind')}</p>
            </div>
          </div>
          <span className={`badge ${connected ? 'badge-success' : 'badge-warning'}`}>
            {connected
              ? t('settings.providers.status.connected')
              : t('settings.providers.status.missing')}
          </span>
        </div>

        <SettingRow
          id="providers-base-url"
          label={t('settings.providers.baseUrl')}
          hint={t('settings.providers.baseUrlHint')}
        >
          {() => (
            <code className="settings-system-readonly" dir="ltr">
              {config.base_url}
            </code>
          )}
        </SettingRow>

        <SettingRow
          id="providers-model"
          label={t('settings.providers.model')}
          hint={t('settings.providers.modelHint')}
        >
          {() => (
            <code className="settings-system-readonly" dir="ltr">
              {config.default_model}
            </code>
          )}
        </SettingRow>

        <SettingRow
          id="providers-key"
          label={t('settings.providers.key')}
          hint={t('settings.providers.keyHint')}
        >
          {() => (
            <span className={`badge ${connected ? 'badge-success' : 'badge-warning'}`}>
              {connected
                ? t('settings.providers.keyStored')
                : t('settings.providers.keyMissing')}
            </span>
          )}
        </SettingRow>

        <SettingRow
          id="providers-concurrency"
          label={t('settings.providers.concurrency')}
          hint={t('settings.providers.concurrencyHint')}
        >
          {() => (
            <span className="settings-providers-value" dir="ltr">
              {config.max_concurrency}
            </span>
          )}
        </SettingRow>
      </section>

      <p className="settings-card-hint">{t('settings.providers.readonlyNote')}</p>
    </div>
  )
}
