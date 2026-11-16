import { useCallback, useEffect, useRef, useState } from 'react'
import { useForm } from 'react-hook-form'
import { zodResolver } from '@hookform/resolvers/zod'
import { SettingRow } from '@/components/ui/SettingRow'
import { Select } from '@/components/ui/Select'
import { Slider } from '@/components/ui/Slider'
import { Switch } from '@/components/ui/Switch'
import { SegmentedControl } from '@/components/ui/SegmentedControl'
import { api } from '@/lib/api'
import type { ReadingSettings, ReadingTheme } from '@/lib/api'
import { useLanguage } from '@/i18n/useLanguage.ts'
import {
  READING_FALLBACKS,
  readingSchema,
  type Preferences,
} from '@/lib/preferences.ts'

type ReadingForm = {
  reading_font_size: number
  reading_line_height: number
  reading_width: number
  reading_theme: ReadingTheme
  reading_direction: 'auto' | 'rtl' | 'ltr'
  reading_mode: 'translation' | 'original' | 'bilingual' | 'columns'
  reading_glossary: boolean
}

interface ReadingTabProps {
  value: ReadingSettings
  onSaved: (value: Preferences) => void
}

function formValues(value: ReadingSettings): ReadingForm {
  return {
    reading_font_size: value.reading_font_size,
    reading_line_height: value.reading_line_height,
    reading_width: value.reading_width,
    reading_theme: value.reading_theme,
    reading_direction: value.reading_direction,
    reading_mode: value.reading_mode,
    reading_glossary: value.reading_glossary ?? true,
  }
}

export function ReadingTab({ value, onSaved }: ReadingTabProps) {
  const { t } = useLanguage()
  const initial = useRef<ReadingForm>(formValues(value))
  const latest = useRef<ReadingForm>(formValues(value))
  const lastSent = useRef(JSON.stringify(formValues(value)))
  const timer = useRef<number | null>(null)
  const [saving, setSaving] = useState(false)
  const [saved, setSaved] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const form = useForm<ReadingForm>({
    resolver: zodResolver(readingSchema()),
    defaultValues: formValues(value),
    mode: 'onBlur',
  })
  const { setValue, watch } = form
  const current = watch()

  const flush = useCallback(() => {
    if (timer.current !== null) {
      window.clearTimeout(timer.current)
      timer.current = null
    }
    const parsed = readingSchema().safeParse(latest.current)
    if (!parsed.success) return
    const serialised = JSON.stringify(parsed.data)
    if (serialised === lastSent.current) return
    lastSent.current = serialised

    const patch: Partial<ReadingSettings> = { ...parsed.data }
    if (parsed.data.reading_theme !== initial.current.reading_theme) {
      patch.study_night_mode = parsed.data.reading_theme === 'night'
    }

    setSaving(true)
    setError(null)
    api
      .updatePreferences({ reading: patch })
      .then((response) => {
        onSaved(response.value)
        setSaved(true)
      })
      .catch((cause: unknown) => {
        setError(cause instanceof Error ? cause.message : t('settings.instantFailed'))
      })
      .finally(() => setSaving(false))
  }, [onSaved, t])

  useEffect(() => {
    const sub = form.watch((values) => {
      latest.current = values as ReadingForm
      if (timer.current !== null) window.clearTimeout(timer.current)
      timer.current = window.setTimeout(flush, 400)
    })
    return () => {
      sub.unsubscribe()
      // Leaving the tab must not drop the last 400ms of a drag.
      flush()
    }
  }, [form, flush])

  const themeOptions: Array<{ value: ReadingTheme; label: string }> = [
    { value: 'light', label: t('settings.reading.theme.light') },
    { value: 'sepia', label: t('settings.reading.theme.sepia') },
    { value: 'night', label: t('settings.reading.theme.night') },
    { value: 'contrast', label: t('settings.reading.theme.contrast') },
  ]

  return (
    <section className="settings-card" aria-labelledby="settings-reading-title">
      <h2 id="settings-reading-title" className="settings-card-title">
        {t('settings.reading.title')}
      </h2>
      <p className="settings-card-hint">{t('settings.reading.hint')}</p>
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
        id="reading-font-size"
        label={t('settings.reading.fontSize')}
        hint={t('settings.reading.fontSizeHint')}
        wide
      >
        {(ids) => (
          <Slider
            id="reading-font-size"
            value={current.reading_font_size}
            min={14}
            max={30}
            step={1}
            valueText={t('settings.reading.unitPx', { value: current.reading_font_size })}
            display={`${current.reading_font_size}`}
            describedBy={ids.describedBy}
            atDefault={current.reading_font_size === READING_FALLBACKS.reading_font_size}
            resetLabel={t('settings.default')}
            onReset={() => setValue('reading_font_size', READING_FALLBACKS.reading_font_size, { shouldDirty: true })}
            onChange={(next) => setValue('reading_font_size', next, { shouldDirty: true })}
            onChangeEnd={flush}
          />
        )}
      </SettingRow>

      <SettingRow
        id="reading-line-height"
        label={t('settings.reading.lineHeight')}
        hint={t('settings.reading.lineHeightHint')}
        wide
      >
        {(ids) => (
          <Slider
            id="reading-line-height"
            value={current.reading_line_height}
            min={1.4}
            max={2.6}
            step={0.1}
            valueText={t('settings.reading.unitX', { value: current.reading_line_height.toFixed(1) })}
            display={current.reading_line_height.toFixed(1)}
            describedBy={ids.describedBy}
            atDefault={current.reading_line_height === READING_FALLBACKS.reading_line_height}
            resetLabel={t('settings.default')}
            onReset={() =>
              setValue('reading_line_height', READING_FALLBACKS.reading_line_height, { shouldDirty: true })
            }
            onChange={(next) => setValue('reading_line_height', next, { shouldDirty: true })}
            onChangeEnd={flush}
          />
        )}
      </SettingRow>

      <SettingRow
        id="reading-width"
        label={t('settings.reading.width')}
        hint={t('settings.reading.widthHint')}
        wide
      >
        {(ids) => (
          <Slider
            id="reading-width"
            value={current.reading_width}
            min={560}
            max={1000}
            step={20}
            valueText={t('settings.reading.unitPx', { value: current.reading_width })}
            display={`${current.reading_width}`}
            describedBy={ids.describedBy}
            atDefault={current.reading_width === READING_FALLBACKS.reading_width}
            resetLabel={t('settings.default')}
            onReset={() => setValue('reading_width', READING_FALLBACKS.reading_width, { shouldDirty: true })}
            onChange={(next) => setValue('reading_width', next, { shouldDirty: true })}
            onChangeEnd={flush}
          />
        )}
      </SettingRow>

      <SettingRow id="reading-theme" label={t('settings.reading.theme')} wide>
        {(ids) => (
          <SegmentedControl
            idBase="reading-theme"
            value={current.reading_theme}
            options={themeOptions}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('reading_theme', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <SettingRow id="reading-direction" label={t('settings.reading.direction')}>
        {(ids) => (
          <Select
            id="reading-direction"
            value={current.reading_direction}
            describedBy={ids.describedBy}
            options={[
              { value: 'auto', label: t('settings.reading.direction.auto') },
              { value: 'rtl', label: t('settings.reading.direction.rtl') },
              { value: 'ltr', label: t('settings.reading.direction.ltr') },
            ]}
            onChange={(next) =>
              setValue('reading_direction', next as ReadingForm['reading_direction'], { shouldDirty: true })
            }
          />
        )}
      </SettingRow>

      <SettingRow id="reading-mode" label={t('settings.reading.mode')}>
        {(ids) => (
          <Select
            id="reading-mode"
            value={current.reading_mode}
            describedBy={ids.describedBy}
            options={[
              { value: 'translation', label: t('settings.reading.mode.translation') },
              { value: 'original', label: t('settings.reading.mode.original') },
              { value: 'bilingual', label: t('settings.reading.mode.bilingual') },
              { value: 'columns', label: t('settings.reading.mode.columns') },
            ]}
            onChange={(next) =>
              setValue('reading_mode', next as ReadingForm['reading_mode'], { shouldDirty: true })
            }
          />
        )}
      </SettingRow>

      <SettingRow
        id="reading-glossary"
        label={t('settings.reading.glossary')}
        hint={t('settings.reading.glossaryHint')}
      >
        {(ids) => (
          <Switch
            checked={current.reading_glossary}
            labelledBy={ids.labelId}
            describedBy={ids.describedBy}
            onChange={(next) => setValue('reading_glossary', next, { shouldDirty: true })}
          />
        )}
      </SettingRow>

      <div className="settings-reading-preview-wrap">
        <h3 className="settings-preview-title">{t('settings.reading.preview')}</h3>
        <div
          className={`settings-reading-preview reader-theme-${current.reading_theme}`}
          dir={current.reading_direction === 'auto' ? 'auto' : current.reading_direction}
          aria-label={t('settings.reading.previewCaption')}
        >
          <div
            className="settings-reading-preview-inner"
            style={{
              maxWidth: current.reading_width,
              fontSize: current.reading_font_size,
              lineHeight: current.reading_line_height,
            }}
          >
            <p lang="en" dir="ltr" className="settings-reading-preview-original">
              {t('settings.reading.previewOriginal')}
            </p>
            <p>{t('settings.reading.previewTranslation')}</p>
          </div>
        </div>
      </div>
    </section>
  )
}
