/**
 * Capabilities — the bento.
 *
 * Four cards plus one wide strip. The cards are not interchangeable: each one
 * carries a small reconstruction of the surface it describes, so the section
 * argues with evidence rather than with adjectives. The fifth idea (outputs)
 * does not fit a card, so it spans the grid as a strip -- which also breaks the
 * 2x2 rhythm that makes a bento look like a template.
 */
import type { StringKey } from '@/i18n/fa.ts'
import {
  CheckIcon,
  CheckCircleIcon,
  ExportIcon,
  LayersIcon,
  LibraryIcon,
  PulseIcon,
} from './LandingIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
}

export function CapabilitiesSection({ t }: Props) {
  return (
    <section className="k-section k-capabilities" id="capabilities">
      <div className="k-container">
        <div className="k-section-head">
          <div className="k-section-head-copy">
            <p className="k-eyebrow">
              <span className="k-eyebrow-dot" aria-hidden="true" />
              {t('landing.capabilities.eyebrow')}
            </p>
            <h2>{t('landing.capabilities.title')}</h2>
          </div>
          <p className="k-section-lead">{t('landing.capabilities.sub')}</p>
        </div>

        <div className="k-bento">
          <article className="k-card k-card-cal">
            <div className="k-card-head">
              <span className="k-card-icon">
                <LayersIcon size={16} />
              </span>
              <span className="k-card-kicker">{t('landing.cap.cal.kicker')}</span>
            </div>
            <h3>{t('landing.cap.cal.title')}</h3>
            <p>{t('landing.cap.cal.body')}</p>
            <div className="k-card-art">
              <div className="k-cal-art">
                <div className="k-cal-rail">
                  <div className="k-cal-step is-done">
                    <span>1</span>
                    <span>{t('landing.ui.tone')}</span>
                    <CheckIcon size={11} />
                  </div>
                  <div className="k-cal-step is-done">
                    <span>2</span>
                    <span>{t('landing.ui.models')}</span>
                    <CheckIcon size={11} />
                  </div>
                  <div className="k-cal-step is-active">
                    <span>3</span>
                    <span>{t('landing.ui.glossary')}</span>
                    <span aria-hidden="true" />
                  </div>
                  <div className="k-cal-step">
                    <span>4</span>
                    <span>{t('landing.ui.review')}</span>
                    <span aria-hidden="true" />
                  </div>
                </div>
                <div className="k-cal-slip">
                  <p className="k-cal-source" dir="ltr">
                    ...the city had begun to whisper instead of shout.
                  </p>
                  <div className="k-cal-terms">
                    <span className="k-chip">
                      <CheckIcon size={10} />
                      whisper <b dir="rtl">نجوا</b>
                    </span>
                    <span className="k-chip">
                      <CheckIcon size={10} />
                      dusk <b dir="rtl">غروب</b>
                    </span>
                  </div>
                  <span className="k-cal-sealed">
                    <CheckCircleIcon size={12} />
                    {t('landing.ui.sealProfile')}
                  </span>
                </div>
              </div>
            </div>
          </article>

          <article className="k-card k-card-monitor">
            <div className="k-card-head">
              <span className="k-card-icon">
                <PulseIcon size={16} />
              </span>
              <span className="k-card-kicker">{t('landing.cap.monitor.kicker')}</span>
            </div>
            <h3>{t('landing.cap.monitor.title')}</h3>
            <p>{t('landing.cap.monitor.body')}</p>
            <div className="k-card-art">
              <div className="k-monitor-art">
                <div className="k-monitor-row">
                  <span className="k-monitor-name" dir="ltr">
                    the-quiet-cities.epub
                  </span>
                  <span className="k-status is-running">{t('landing.ui.running')}</span>
                </div>
                <div className="k-monitor-bar-row">
                  <b dir="ltr">72%</b>
                  <span className="k-progress-track">
                    <span className="k-progress-fill" style={{ width: '72%' }} />
                  </span>
                </div>
                <div className="k-monitor-meta-row">
                  <span dir="ltr">13 / 18</span>
                  <span>{t('landing.ui.chapters')}</span>
                </div>
                <div className="k-monitor-tiny">
                  <span className="k-status is-done">{t('landing.ui.done')} 11</span>
                  <span className="k-status is-done">{t('landing.ui.done')} 12</span>
                  <span className="k-status is-running">{t('landing.ui.running')} 13</span>
                </div>
              </div>
            </div>
          </article>

          <article className="k-card k-card-library">
            <div className="k-card-head">
              <span className="k-card-icon">
                <LibraryIcon size={16} />
              </span>
              <span className="k-card-kicker">{t('landing.cap.library.kicker')}</span>
            </div>
            <h3>{t('landing.cap.library.title')}</h3>
            <p>{t('landing.cap.library.body')}</p>
            <div className="k-card-art">
              <div className="k-library-art">
                <div className="k-shelf-row">
                  <span className="k-spine k-spine-a" aria-hidden="true" />
                  <span className="k-shelf-copy">
                    <strong dir="ltr">the-quiet-cities</strong>
                    <span>{t('landing.ui.chapters')} · 18</span>
                  </span>
                  <span className="k-status is-done">{t('landing.ui.done')}</span>
                </div>
                <div className="k-shelf-row">
                  <span className="k-spine k-spine-b" aria-hidden="true" />
                  <span className="k-shelf-copy">
                    <strong dir="ltr">harbour-lights</strong>
                    <span>{t('landing.ui.chapters')} · 24</span>
                  </span>
                  <span className="k-status is-done">{t('landing.ui.done')}</span>
                </div>
                <div className="k-shelf-row">
                  <span className="k-spine k-spine-c" aria-hidden="true" />
                  <span className="k-shelf-copy">
                    <strong dir="ltr">the-long-road</strong>
                    <span>{t('landing.ui.chapters')} · 12</span>
                  </span>
                  <span className="k-status">{t('landing.ui.queued')}</span>
                </div>
              </div>
            </div>
          </article>

          <article className="k-card k-card-reader">
            <div className="k-card-head">
              <span className="k-card-icon">
                <ExportIcon size={16} />
              </span>
              <span className="k-card-kicker">{t('landing.cap.reader.kicker')}</span>
            </div>
            <h3>{t('landing.cap.reader.title')}</h3>
            <p>{t('landing.cap.reader.body')}</p>
            <div className="k-card-art">
              <div className="k-reader-art">
                <div className="k-reader-art-page">
                  <span className="k-reader-art-label">{t('landing.ui.chapter', { n: '03' })}</span>
                  <p className="k-reader-art-source" dir="ltr">
                    We arrived at dusk, when the city had begun to whisper instead of shout.
                  </p>
                  <p className="k-reader-art-target" dir="rtl" lang="fa">
                    غروب‌هنگام رسیدیم، وقتی شهر به‌جای فریاد کشیدن، آغاز کرده بود به نجوا کردن.
                  </p>
                </div>
                <div className="k-reader-art-swatches">
                  {/* Each swatch carries the reader's own theme scope so it
                      paints itself from the real tokens. */}
                  <span className="k-swatch reader-theme-light is-active">
                    <span />
                  </span>
                  <span className="k-swatch mini reader-theme-sepia">
                    <span />
                  </span>
                  <span className="k-swatch mini reader-theme-night">
                    <span />
                  </span>
                </div>
              </div>
            </div>
          </article>

          <article className="k-card k-card-outputs">
            <div>
              <div className="k-card-head">
                <span className="k-card-icon">
                  <ExportIcon size={16} />
                </span>
                <span className="k-card-kicker">{t('landing.cap.outputs.kicker')}</span>
              </div>
              <h3>{t('landing.cap.outputs.title')}</h3>
              <p>{t('landing.cap.outputs.body')}</p>
            </div>
            <div className="k-export-art">
              <span className="k-format-chip">DOCX</span>
              <span className="k-format-chip">PDF · A4</span>
              <span className="k-format-chip">PDF · mobile</span>
              <span className="k-format-chip">PDF · bilingual</span>
              <span className="k-format-chip">EPUB</span>
              <span className="k-format-chip">Markdown</span>
              <span className="k-format-chip">TXT</span>
            </div>
          </article>
        </div>
      </div>
    </section>
  )
}
