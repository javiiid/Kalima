import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { SettingRow } from '@/components/ui/SettingRow'
import { Select } from '@/components/ui/Select'
import { Switch } from '@/components/ui/Switch'
import { useLanguage } from '@/i18n/useLanguage.ts'
import {
  formatDateSample,
  generalSchema,
  type DateFormat,
  type GeneralPreferences,
  type Language,
  type PreferencesMeta,
} from '@/lib/preferences.ts'

interface GeneralTabProps {
  value: GeneralPreferences
  meta: PreferencesMeta
  onChange: (patch: Partial<GeneralPreferences>) => void
  registerValidate: (validate: (() => Promise<boolean>) | null) => void
}

export function GeneralTab({ value, meta, onChange, registerValidate }: GeneralTabProps) {
  const { t } = useLanguage()
  const form = useForm<GeneralPreferences>({
    resolver: zodResolver(generalSchema(t)),
    defaultValues: value,
    mode: 'onBlur',
  })
  const { setValue, watch, formState } = form
  const current = watch()

  useEffect(() => {
    const sub = form.watch((values) => onChange(values as Partial<GeneralPreferences>))
    return () => sub.unsubscribe()
  }, [form, onChange])

  useEffect(() => {
    registerValidate(() => form.trigger())
    return () => registerValidate(null)
  }, [form, registerValidate])

  const zones = meta.options.timezones.includes(current.timezone)
    ? meta.options.timezones
    : [current.timezone, ...meta.options.timezones]

  const dateOptions: Array<{ value: DateFormat; label: string }> = [
    { value: 'jalali', label: t('settings.general.date.jalali') },
    { value: 'gregorian', label: t('settings.general.date.gregorian') },
    { value: 'iso', label: t('settings.general.date.iso') },
  ]

  const languageOptions: Array<{ value: Language; label: string }> = [
    { value: 'fa', label: t('settings.general.language.fa') },
    { value: 'en', label: t('settings.general.language.en') },
  ]

  return (
    <section className="settings-card" aria-labelledby="settings-general-title">
      <h2 id="settings-general-title" className="settings-card-title">
        {t('settings.general.title')}
      </h2>
      <p className="settings-card-hint">{t('settings.general.hint')}</p>

      <SettingRow id="general-language" label={t('settings.general.language')} hint={t('settings.general.languageHint')}>
        {(ids) => (
          <Select
            id="general-language"
            value={current.language}
            describedBy={ids.describedBy}
            options={languageOptions}
            onChange={(next) => setValue('language', next as Language, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="general-timezone"
        label={t('settings.general.timezone')}
        hint={t('settings.general.timezoneHint')}
        error={formState.errors.timezone?.message}
        wide
      >
        {(ids) => (
          <Select
            id="general-timezone"
            value={current.timezone}
            describedBy={ids.describedBy}
            invalid={Boolean(formState.errors.timezone)}
            options={zones.map((zone) => ({ value: zone, label: zone }))}
            onChange={(next) => setValue('timezone', next, { shouldDirty: true, shouldValidate: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="general-date"
        label={t('settings.general.dateFormat')}
        hint={t('settings.general.dateFormatHint', { sample: formatDateSample(new Date(), current.date_format) })}
      >
        {(ids) => (
          <Select
            id="general-date"
            value={current.date_format}
            describedBy={ids.describedBy}
            options={dateOptions}
            onChange={(next) => setValue('date_format', next as DateFormat, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow id="general-resume" label={t('settings.general.resume')} hint={t('settings.general.resumeHint')}>
        {(ids) => (
          <Switch
            checked={current.resume_last_page}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('resume_last_page', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="general-onboarding"
        label={t('settings.general.onboarding')}
        hint={t('settings.general.onboardingHint')}
      >
        {(ids) => (
          <Switch
            checked={current.show_onboarding}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('show_onboarding', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>
    </section>
  )
}
