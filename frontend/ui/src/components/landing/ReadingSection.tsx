/**
 * Reading — the single paper band.
 *
 * The page is ink from top to bottom except here. That is the argument: the
 * reading surface is a different kind of surface from the workshop, and the one
 * place the page goes light is the one place the product goes light. It is also
 * why this section is not a card on a dark background -- a paper card on ink
 * would say "preview", and the point is that this is where you actually read.
 *
 * The controls are real controls, not decoration: the mode buttons and the
 * swatches switch the demo below them. Nothing here claims to be the reader
 * route (that is `/reader/:id`, and it needs a book id), so the section does not
 * link to it -- it demonstrates the surface instead.
 */
import { useState } from 'react'
import type { StringKey } from '@/i18n/fa.ts'
import { CheckIcon } from './LandingIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
}

type Mode = 'paired' | 'columns'

const SURFACES = [
  { key: 'landing.ui.surfaceLight', theme: 'light' },
  { key: 'landing.ui.surfaceSepia', theme: 'sepia' },
  { key: 'landing.ui.surfaceNight', theme: 'night' },
  { key: 'landing.ui.surfaceContrast', theme: 'contrast' },
] as const satisfies readonly { key: StringKey; theme: string }[]

const SOURCE =
  'We arrived at dusk, when the city had begun to whisper instead of shout. The streets smelled of bread and rain.'

const TARGET_FA =
  'غروب‌هنگام رسیدیم، وقتی شهر به‌جای فریاد کشیدن، آغاز کرده بود به نجوا کردن. کوچه‌ها بوی نان و باران می‌داد.'

export function ReadingSection({ t }: Props) {
  const [mode, setMode] = useState<Mode>('paired')
  const [surface, setSurface] = useState(0)

  return (
    <section className="k-reader-section k-paper k-band--paper" id="reading">
      <div className="k-container k-reader-grid">
        <div className="k-reader-copy">
          <p className="k-eyebrow k-eyebrow-paper">
            <span className="k-eyebrow-dot" aria-hidden="true" />
            {t('landing.reading.eyebrow')}
          </p>
          <h2>{t('landing.reading.title')}</h2>
          <p className="k-lead k-lead-paper">{t('landing.reading.sub')}</p>

          <ul className="k-reader-features">
            <li>
              <h3>{t('landing.reading.point1.title')}</h3>
              <p>{t('landing.reading.point1.body')}</p>
            </li>
            <li>
              <h3>{t('landing.reading.point2.title')}</h3>
              <p>{t('landing.reading.point2.body')}</p>
            </li>
            <li>
              <h3>{t('landing.reading.point3.title')}</h3>
              <p>{t('landing.reading.point3.body')}</p>
            </li>
          </ul>
        </div>

        <div className="k-reader-visual k-reader-demo">
          <div className="k-reader-controls">
            <div className="k-control-group">
              <span className="k-control-label">{t('landing.ui.layout')}</span>
              <div className="k-control-buttons">
                <button
                  type="button"
                  className="k-mode-btn"
                  aria-pressed={mode === 'paired'}
                  onClick={() => setMode('paired')}
                >
                  {t('landing.ui.modePaired')}
                </button>
                <button
                  type="button"
                  className="k-mode-btn"
                  aria-pressed={mode === 'columns'}
                  onClick={() => setMode('columns')}
                >
                  {t('landing.ui.modeColumns')}
                </button>
              </div>
            </div>

            <div className="k-control-group">
              <span className="k-control-label">{t('landing.ui.surface')}</span>
              <div className="k-control-buttons">
                {SURFACES.map((item, index) => (
                  <button
                    key={item.theme}
                    type="button"
                    className="k-swatch-btn"
                    aria-pressed={surface === index}
                    onClick={() => setSurface(index)}
                  >
                    {/*
                      The swatch carries the reader's own theme scope, so it
                      paints itself from the real tokens rather than from a
                      hand-picked colour. A swatch that does not match the
                      surface it selects is a lie the eye catches immediately.
                    */}
                    <span
                      className={`k-swatch mini reader-theme-${item.theme}${
                        surface === index ? ' is-active' : ''
                      }`}
                    >
                      <span />
                    </span>
                    <span className="k-swatch-label">{t(item.key)}</span>
                  </button>
                ))}
              </div>
            </div>
          </div>

          <div className={`k-reader-frame reader-theme-${SURFACES[surface]!.theme}`}>
            <div className="k-reader-chrome">
              <span className="k-reader-book" dir="ltr">
                the-quiet-cities
              </span>
              <span className="k-reader-chapter">{t('landing.ui.chapter', { n: '03' })}</span>
              <span className="k-reader-aa" aria-hidden="true">
                Aa
              </span>
            </div>

            <div className="k-reader-page">
              {mode === 'paired' ? (
                <>
                  <div className="k-reader-pair">
                    <p className="k-reader-source" dir="ltr">
                      {SOURCE}
                    </p>
                    <p className="k-reader-target" dir="rtl" lang="fa">
                      {TARGET_FA}
                    </p>
                  </div>
                  <div className="k-reader-pair">
                    <p className="k-reader-source" dir="ltr">
                      For the first time in months I felt the quiet certainty that I had come to the
                      right place.
                    </p>
                    <p className="k-reader-target" dir="rtl" lang="fa">
                      برای نخستین بار در ماه‌ها، آرامش یقینی را احساس کردم که به جای درست آمده‌ام.
                    </p>
                  </div>
                  <div className="k-reader-gloss">
                    <span>dusk</span>
                    <b dir="rtl">غروب</b>
                    <span className="k-reader-gloss-state">
                      <CheckIcon size={11} /> {t('landing.cta.seal')}
                    </span>
                  </div>
                </>
              ) : (
                <div className="k-reader-columns">
                  <div className="k-reader-column">
                    <span className="k-reader-column-label">{t('landing.ui.english')}</span>
                    <p className="k-reader-source" dir="ltr">
                      {SOURCE}
                    </p>
                  </div>
                  <div className="k-reader-column">
                    <span className="k-reader-column-label">فارسی</span>
                    <p className="k-reader-target" dir="rtl" lang="fa">
                      {TARGET_FA}
                    </p>
                  </div>
                </div>
              )}
            </div>

            <div className="k-reader-footer">
              <span>{t('landing.ui.chapterOf', { n: '03', total: '18' })}</span>
              <span dir="ltr">72%</span>
            </div>
          </div>

          <p className="k-figure-note">{t('landing.ui.illustrative')}</p>
        </div>
      </div>
    </section>
  )
}
