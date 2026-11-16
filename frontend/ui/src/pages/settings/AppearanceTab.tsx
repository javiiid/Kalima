import { useCallback, useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { SettingRow } from '@/components/ui/SettingRow'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { Switch } from '@/components/ui/Switch'
import { api } from '@/lib/api'
import { useDensity, useMotion } from '@/hooks/useDensity'
import { setThemeChoice } from '@/hooks/useTheme'
import { useLanguage } from '@/i18n/useLanguage.ts'
import {
  appearanceSchema,
  type AppearancePreferences,
  type AppearanceTheme,
  type Density,
  type Preferences,
} from '@/lib/preferences.ts'

interface AppearanceTabProps {
  value: AppearancePreferences
  onSaved: (value: Preferences) => void
}

export function AppearanceTab({ value, onSaved }: AppearanceTabProps) {
  const { t } = useLanguage()
  const { setDensity } = useDensity()
  const { setAnimations } = useMotion()
  const lastSent = useRef(JSON.stringify(value))
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const form = useForm<AppearancePreferences>({
    resolver: zodResolver(appearanceSchema()),
    defaultValues: value,
    mode: 'onBlur',
  })
  const { setValue, watch } = form
  const current = watch()

  // The server is the cross-device source for appearance; apply its values on
  // open so the controls and the page agree, then apply each change instantly.
  useEffect(() => {
    setThemeChoice(value.theme)
    setDensity(value.density)
    setAnimations(value.animations)
  }, [setDensity, setAnimations, value.animations, value.density, value.theme])

  const save = useCallback(
    (next: AppearancePreferences) => {
      const serialised = JSON.stringify(next)
      if (serialised === lastSent.current) return
      lastSent.current = serialised
      setSaving(true)
      setError(null)
      api
        .updatePreferences({ appearance: next })
        .then((response) => {
          onSaved(response.value)
          setSaved(true)
        })
        .catch((cause: unknown) => {
          setError(cause instanceof Error ? cause.message : t('settings.instantFailed'))
        })
        .finally(() => setSaving(false))
    },
    [onSaved, t],
  )

  useEffect(() => {
    const sub = form.watch((values) => {
      const next = values as AppearancePreferences
      setThemeChoice(next.theme)
      setDensity(next.density)
      setAnimations(next.animations)
      save(next)
    })
    return () => sub.unsubscribe()
  }, [form, save, setDensity, setAnimations])

  const themeOptions: Array<{ value: AppearanceTheme; label: string }> = [
    { value: 'light', label: t('settings.appearance.theme.light') },
    { value: 'dark', label: t('settings.appearance.theme.dark') },
    { value: 'system', label: t('settings.appearance.theme.system') },
  ]

  const densityOptions: Array<{ value: Density; label: string }> = [
    { value: 'comfortable', label: t('settings.appearance.density.comfortable') },
    { value: 'compact', label: t('settings.appearance.density.compact') },
  ]

  return (
    <section className="settings-card" aria-labelledby="settings-appearance-title">
      <h2 id="settings-appearance-title" className="settings-card-title">
        {t('settings.appearance.title')}
      </h2>
      <p className="settings-card-hint">{t('settings.appearance.hint')}</p>
      <p className="settings-inline-status" aria-live="polite">
        {saving
          ? t('settings.instantSaving')
          : error
            ? `${t('settings.instantFailed')}: ${error}`
            : saved
              ? t('settings.instantSaved')
              : ''}
      </p>

      <SettingRow
        id="appearance-theme"
        label={t('settings.appearance.theme')}
        hint={t('settings.appearance.themeHint')}
        wide
      >
        {(ids) => (
          <SegmentedControl
            idBase="appearance-theme"
            value={current.theme}
            options={themeOptions}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('theme', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="appearance-density"
        label={t('settings.appearance.density')}
        hint={t('settings.appearance.densityHint')}
        wide
      >
        {(ids) => (
          <SegmentedControl
            idBase="appearance-density"
            value={current.density}
            options={densityOptions}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('density', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow
        id="appearance-animations"
        label={t('settings.appearance.animations')}
        hint={t('settings.appearance.animationsHint')}
      >
        {(ids) => (
          <Switch
            checked={current.animations}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('animations', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>
    </section>
  )
}
