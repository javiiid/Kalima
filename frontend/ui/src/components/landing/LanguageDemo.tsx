/**
 * The six-language demonstration.
 *
 * The signature element of the landing page: one editorial sentence, carried
 * across English, Persian, Arabic, Spanish, French and German on a rotation a
 * visitor can watch, pause, or steer.
 *
 * DIRECTION IS DATA, NOT A LANGUAGE CHECK
 * ---------------------------------------
 * Every string is rendered with its own `lang` and `dir`, taken from the
 * language record. Nothing in this file tests for `'fa'` or `'ar'` to decide
 * alignment, so the layout cannot drift out of step with the content, and a
 * seventh language cannot forget to set a direction.
 *
 * The stage has a fixed minimum height. Without it the German sentence (the
 * longest) would push the footer down on every cycle, and a demonstration that
 * makes the page jump is worse than no demonstration.
 */
import type { CSSProperties } from 'react'
import type { StringKey } from '@/i18n/fa.ts'
import { CheckCircleIcon, PauseIcon, PlayIcon } from './LandingIcons'
import { DEMO_LANGUAGES, DEMO_INTERVAL_MS } from './languages.ts'
import { useLanguageRotation } from './useLanguageRotation.ts'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
  /** `compact` is the hero pane; the default is the full section. */
  variant?: 'full' | 'compact'
  /** Hides the language rail where space is tight. */
  showRail?: boolean
  /**
   * Renders the "EN -> XX" pair for the language currently on the stage.
   *
   * The hero window used to hardcode "EN -> FA" in its chrome while the demo
   * inside rotated through six languages, so the label contradicted the text
   * beside it. The pair has to come from the same state as the text or it is
   * only ever right one sixth of the time.
   */
  showPair?: boolean
}

export function LanguageDemo({ t, variant = 'full', showRail = true, showPair = false }: Props) {
  const rotation = useLanguageRotation()
  const { current } = rotation
  const compact = variant === 'compact'

  return (
    <div
      className={`k-lang-demo${compact ? ' k-lang-demo--compact' : ''}`}
      style={{ '--k-lang-interval': `${DEMO_INTERVAL_MS}ms` } as CSSProperties}
      onMouseEnter={() => rotation.setHovering(true)}
      onMouseLeave={() => rotation.setHovering(false)}
      onFocusCapture={() => rotation.setHovering(true)}
      onBlurCapture={() => rotation.setHovering(false)}
    >
      <div className="k-lang-demo-head">
        <p className="k-lang-demo-source">
          {t('landing.demo.source')}
          <b dir="ltr">{t('landing.demo.sourceTitle')}</b>
        </p>
        {showRail ? (
          <div className="k-lang-rail" role="group" aria-label={t('landing.demo.label')}>
            {DEMO_LANGUAGES.map((language, index) => {
              const active = index === rotation.index
              return (
                <button
                  key={language.code}
                  type="button"
                  className="k-lang-pill"
                  aria-pressed={active}
                  aria-label={t('landing.demo.jumpTo', { language: language.english })}
                  onClick={() => (active && rotation.paused ? rotation.resume() : rotation.select(index))}
                >
                  <span className="k-lang-pill-code">{language.short}</span>
                  <span className="k-lang-pill-name" lang={language.code}>
                    {language.native}
                  </span>
                </button>
              )
            })}
          </div>
        ) : null}
      </div>

      {/*
        The stage is keyed on the rotation counter, so React remounts the line
        and the CSS entrance animation replays. Changing the text in place would
        leave the animation spent and the swap would be a hard cut.
      */}
      <div className="k-lang-stage">
        <p
          key={rotation.stageKey}
          className="k-lang-line"
          lang={current.code}
          dir={current.dir}
        >
          {current.text}
        </p>
      </div>

      <div className="k-lang-foot">
        <span className="k-lang-foot-note">
          <CheckCircleIcon size={14} />
          {t('landing.demo.note')}
        </span>
        <span className="k-lang-timer" aria-hidden="true">
          <span
            key={rotation.stageKey}
            className="k-lang-timer-fill"
            data-paused={rotation.paused || undefined}
          />
        </span>
        <span className="k-lang-foot-dir">
          {current.dir === 'rtl' ? t('landing.demo.rtl') : t('landing.demo.ltr')}
        </span>
        {showPair ? (
          // The target language named in its own script, not "EN -> EN" when
          // English is the one on stage. `dir` is pinned to ltr so the pair
          // itself never reorders, while the name inside keeps its own script.
          <span className="k-lang-foot-dir" dir="ltr">
            {current.code === 'en' ? 'EN' : `EN → ${current.native}`}
          </span>
        ) : null}
        {!compact ? (
          <button
            type="button"
            className="k-lang-pill"
            onClick={() => (rotation.paused ? rotation.resume() : rotation.select(rotation.index))}
            aria-label={rotation.paused ? t('landing.demo.play') : t('landing.demo.pause')}
          >
            {rotation.paused ? <PlayIcon size={12} /> : <PauseIcon size={12} />}
          </button>
        ) : null}
      </div>
    </div>
  )
}
