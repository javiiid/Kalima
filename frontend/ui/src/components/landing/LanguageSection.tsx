/**
 * The language demonstration section.
 *
 * The hero carries a compact version of this inside the product window, where
 * space is tight and the rail would crowd the chrome. This is the full one: the
 * signature element of the page, given its own band, its own scale and the
 * language rail in plain sight so a visitor can steer it.
 *
 * It sits directly under the hero because it is the fastest possible answer to
 * "what does this actually do" -- one sentence, six scripts, no scrolling
 * required to believe it.
 */
import type { StringKey } from '@/i18n/fa.ts'
import { LanguageDemo } from './LanguageDemo'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
}

export function LanguageSection({ t }: Props) {
  return (
    <section className="k-section k-lang-section" id="languages">
      <div className="k-container">
        <div className="k-section-head">
          <div className="k-section-head-copy">
            <p className="k-eyebrow">
              <span className="k-eyebrow-dot" aria-hidden="true" />
              {t('landing.demo.label')}
            </p>
            <h2>{t('landing.capabilities.title')}</h2>
          </div>
          <p className="k-section-lead">{t('landing.capabilities.sub')}</p>
        </div>

        <div data-reveal>
          <LanguageDemo t={t} />
        </div>
      </div>
    </section>
  )
}
