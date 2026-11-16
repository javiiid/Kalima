import { useEffect } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { useQuery } from '@tanstack/react-query'
import { SettingRow } from '@/components/ui/SettingRow'
import { Select } from '@/components/ui/Select'
import { Switch } from '@/components/ui/Switch'
import { api } from '@/lib/api'
import { useLanguage } from '@/i18n/useLanguage.ts'
import type { StringKey } from '@/i18n/fa.ts'
import {
  translationSchema,
  type PreferencesMeta,
  type TranslationPreferences,
} from '@/lib/preferences.ts'

interface TranslationTabProps {
  value: TranslationPreferences
  meta: PreferencesMeta
  onChange: (patch: Partial<TranslationPreferences>) => void
  registerValidate: (validate: (() => Promise<boolean>) | null) => void
}

const STYLE_KEYS: Record<string, StringKey> = {
  literary: 'settings.style.literary',
  technical: 'settings.style.technical',
  conversational: 'settings.style.conversational',
  formal: 'settings.style.formal',
}

type TranslationForm = Omit<TranslationPreferences, 'mode'> & { mode: 'fast' }

export function TranslationTab({ value, meta, onChange, registerValidate }: TranslationTabProps) {
  const { t } = useLanguage()
  const models = useQuery({ queryKey: ['models'], queryFn: api.models, staleTime: 60_000 })
  const languages = useQuery({ queryKey: ['languages'], queryFn: api.languages, staleTime: 300_000 })

  const form = useForm<TranslationForm>({
    resolver: zodResolver(translationSchema()),
    defaultValues: { ...value, mode: 'fast' },
    mode: 'onBlur',
  })
  const { setValue, watch, formState } = form
  const current = watch()

  useEffect(() => {
    const sub = form.watch((values) => onChange(values as Partial<TranslationPreferences>))
    return () => sub.unsubscribe()
  }, [form, onChange])

  useEffect(() => {
    registerValidate(() => form.trigger())
    return () => registerValidate(null)
  }, [form, registerValidate])

  const defaultModel = meta.defaults['translation.default_model']
  const modelItems = models.data?.items ?? []
  const modelValues = new Set(modelItems.map((model) => model.id))
  const modelOptions = [
    {
      value: '',
      label: defaultModel
        ? t('settings.defaultValue', { value: defaultModel })
        : t('settings.default'),
    },
    ...(current.default_model && !modelValues.has(current.default_model)
      ? [{ value: current.default_model, label: current.default_model, disabled: false }]
      : []),
    ...modelItems.map((model) => ({
      value: model.id,
      label: model.available ? model.id : `${model.id} (${model.provider})`,
      disabled: !model.available,
    })),
  ]

  const languageItems = languages.data?.items ?? []
  const languageValues = new Set(languageItems.map((language) => language.code))
  const fallbackCodes = ['EN', 'FA', 'DE', 'FR', 'AR']
  const languageOptionsFor = (code: string) => {
    const options = new Map<string, string>()
    if (!languageValues.has(code)) options.set(code, code)
    for (const language of languageItems) {
      options.set(language.code, `${language.name} (${language.code})`)
    }
    if (!languageItems.length) {
      for (const fallback of fallbackCodes) options.set(fallback, fallback)
    }
    return [...options].map(([value, label]) => ({ value, label }))
  }
  const languageOptions = languageOptionsFor(current.from_lang)
  const targetOptions = languageOptionsFor(current.to_lang)

  const styleOptions = [
    { value: '', label: t('settings.translation.style.none') },
    ...meta.options.style_presets.map((preset) => ({
      value: preset,
      label: STYLE_KEYS[preset] ? t(STYLE_KEYS[preset] as StringKey) : preset,
    })),
  ]

  return (
    <section className="settings-card" aria-labelledby="settings-translation-title">
      <h2 id="settings-translation-title" className="settings-card-title">
        {t('settings.translation.title')}
      </h2>
      <p className="settings-card-hint">{t('settings.translation.hint')}</p>

      <SettingRow
        id="translation-model"
        label={t('settings.translation.model')}
        hint={models.isError ? t('settings.translation.modelsFailed') : t('settings.translation.modelHint')}
        wide
      >
        {(ids) => (
          <Select
            id="translation-model"
            value={current.default_model}
            describedBy={ids.describedBy}
            options={modelOptions}
            onChange={(next) => setValue('default_model', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow id="translation-mode" label={t('settings.translation.mode')} hint={t('settings.translation.modeHint')}>
        {(ids) => (
          <Select
            id="translation-mode"
            value={current.mode}
            describedBy={ids.describedBy}
            options={[
              { value: 'fast', label: 'fast' },
              {
                value: 'pdfbilingual',
                label: t('settings.translation.mode.pdfBilingual'),
                disabled: true,
              },
            ]}
            onChange={(next) => setValue('mode', next as 'fast', { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="translation-style"
        label={t('settings.translation.style')}
        hint={t('settings.translation.styleHint')}
      >
        {(ids) => (
          <Select
            id="translation-style"
            value={current.style_preset}
            describedBy={ids.describedBy}
            options={styleOptions}
            onChange={(next) => setValue('style_preset', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="translation-glossary"
        label={t('settings.translation.autoGlossary')}
        hint={t('settings.translation.autoGlossaryHint')}
      >
        {(ids) => (
          <Switch
            checked={current.auto_glossary}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('auto_glossary', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="translation-voice"
        label={t('settings.translation.preserveVoice')}
        hint={t('settings.translation.preserveVoiceHint')}
      >
        {(ids) => (
          <Switch
            checked={current.preserve_voice}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('preserve_voice', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="translation-from"
        label={t('settings.translation.from')}
        hint={languages.isError ? t('settings.translation.languagesFailed') : undefined}
        error={formState.errors.from_lang?.message}
      >
        {(ids) => (
          <Select
            id="translation-from"
            value={current.from_lang}
            describedBy={ids.describedBy}
            options={languageOptions}
            onChange={(next) => setValue('from_lang', next, { shouldDirty: true, shouldValidate: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="translation-to"
        label={t('settings.translation.to')}
        error={formState.errors.to_lang?.message}
      >
        {(ids) => (
          <Select
            id="translation-to"
            value={current.to_lang}
            describedBy={ids.describedBy}
            options={targetOptions}
            onChange={(next) => setValue('to_lang', next, { shouldDirty: true, shouldValidate: true })}
          />
        )}
      </SettingRow>
    </section>
  )
}
