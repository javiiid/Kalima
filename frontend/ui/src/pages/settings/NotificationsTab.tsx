import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { Field } from '@/components/ui/Field'
import { SettingRow } from '@/components/ui/SettingRow'
import { Switch } from '@/components/ui/Switch'
import { useLanguage } from '@/i18n/useLanguage.ts'
import type { StringKey } from '@/i18n/fa.ts'
import {
  notificationsSchema,
  type NotificationPreferences,
  type PreferencesMeta,
} from '@/lib/preferences.ts'

interface NotificationsTabProps {
  value: NotificationPreferences
  meta: PreferencesMeta
  onChange: (patch: Partial<NotificationPreferences>) => void
  registerValidate: (validate: (() => Promise<boolean>) | null) => void
}

const EVENT_KEYS: Record<string, StringKey> = {
  'job.completed': 'settings.notifications.event.job.completed',
  'job.failed': 'settings.notifications.event.job.failed',
  'job.stopped': 'settings.notifications.event.job.stopped',
  'quota.warning': 'settings.notifications.event.quota.warning',
}

export function NotificationsTab({
  value,
  meta,
  onChange,
  registerValidate,
}: NotificationsTabProps) {
  const { t } = useLanguage()
  const form = useForm<NotificationPreferences>({
    resolver: zodResolver(notificationsSchema(t)),
    defaultValues: value,
    mode: 'onBlur',
  })
  const { setValue, watch, formState } = form
  const current = watch()

  useEffect(() => {
    const sub = form.watch((values) => onChange(values as Partial<NotificationPreferences>))
    return () => sub.unsubscribe()
  }, [form, onChange])

  useEffect(() => {
    registerValidate(() => form.trigger())
    return () => registerValidate(null)
  }, [form, registerValidate])

  const events = meta.options.notification_events.length
    ? meta.options.notification_events
    : Object.keys(EVENT_KEYS)

  const toggleEvent = (event: string, checked: boolean) => {
    const next = checked
      ? events.filter((item) => item === event || current.events.includes(item))
      : current.events.filter((item) => item !== event)
    setValue('events', next, { shouldDirty: true, shouldValidate: true })
  }

  return (
    <section className="settings-card" aria-labelledby="settings-notifications-title">
      <h2 id="settings-notifications-title" className="settings-card-title">
        {t('settings.notifications.title')}
      </h2>
      <p className="settings-card-hint">{t('settings.notifications.hint')}</p>

      <SettingRow
        id="notifications-email"
        label={t('settings.notifications.email')}
        hint={t('settings.notifications.emailHint')}
      >
        {(ids) => (
          <Switch
            checked={current.email}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('email', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="notifications-in-app"
        label={t('settings.notifications.inApp')}
        hint={t('settings.notifications.inAppHint')}
      >
        {(ids) => (
          <Switch
            checked={current.in_app}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('in_app', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <div className="settings-field-block">
        <Field
          id="notifications-webhook"
          label={t('settings.notifications.webhook')}
          hint={t('settings.notifications.webhookHint')}
          error={formState.errors.webhook?.message}
        >
          {(ids) => (
            <input
              id="notifications-webhook"
              type="url"
              inputMode="url"
              className="field"
              dir="ltr"
              placeholder={t('settings.notifications.webhookPlaceholder')}
              value={current.webhook}
              aria-describedby={ids.describedBy}
              aria-invalid={formState.errors.webhook ? true : undefined}
              onChange={(event) =>
                setValue('webhook', event.target.value, { shouldDirty: true, shouldValidate: false })
              }
              onBlur={() => {
                void form.trigger('webhook')
              }}
            />
          )}
        </Field>
      </div>

      <fieldset className="settings-field-block settings-events">
        <legend className="label">{t('settings.notifications.events')}</legend>
        <p className="field-hint">{t('settings.notifications.eventsHint')}</p>
        <div className="settings-events-grid">
          {events.map((event) => {
            const key = EVENT_KEYS[event]
            const checked = current.events.includes(event)
            return (
              <label key={event} className="settings-checkbox">
                <input
                  type="checkbox"
                  checked={checked}
                  onChange={(change) => toggleEvent(event, change.target.checked)}
                />
                <span>{key ? t(key) : event}</span>
              </label>
            )
          })}
        </div>
        {formState.errors.events?.message ? (
          <p className="field-error" role="alert">
            {formState.errors.events.message}
          </p>
        ) : null}
      </fieldset>
    </section>
  )
}
