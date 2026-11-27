/**
 * Product showcase: the four stages of the actual workflow.
 *
 * A tab strip rather than a card grid, because these four things are a
 * sequence, not a feature list. Each panel pairs a short argument with a
 * faithful reconstruction of that stage's real interface.
 *
 * Keyboard: the tab list is a real `role="tablist"` with roving arrow-key
 * focus and Home/End, so it behaves the way a tab strip is expected to and not
 * merely looks like one.
 */
import { useRef, useState } from 'react'
import type { KeyboardEvent } from 'react'
import type { StringKey } from '@/i18n/fa.ts'
import {
  ArrowRightIcon,
  CheckIcon,
  CheckCircleIcon,
  ClockIcon,
  DocIcon,
  FileIcon,
  PulseIcon,
  UploadIcon,
} from './LandingIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
}

interface Stage {
  id: string
  kicker: StringKey
  title: StringKey
  body: StringKey
  point1: StringKey
  point2: StringKey
}

const STAGES: readonly Stage[] = [
  { id: 'stage1', kicker: 'landing.stage1.kicker', title: 'landing.stage1.title', body: 'landing.stage1.body', point1: 'landing.stage1.point1', point2: 'landing.stage1.point2' },
  { id: 'stage2', kicker: 'landing.stage2.kicker', title: 'landing.stage2.title', body: 'landing.stage2.body', point1: 'landing.stage2.point1', point2: 'landing.stage2.point2' },
  { id: 'stage3', kicker: 'landing.stage3.kicker', title: 'landing.stage3.title', body: 'landing.stage3.body', point1: 'landing.stage3.point1', point2: 'landing.stage3.point2' },
  { id: 'stage4', kicker: 'landing.stage4.kicker', title: 'landing.stage4.title', body: 'landing.stage4.body', point1: 'landing.stage4.point1', point2: 'landing.stage4.point2' },
]

export function ShowcaseSection({ t }: Props) {
  const [active, setActive] = useState(0)
  const tabs = useRef<Array<HTMLButtonElement | null>>([])

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>) {
    const last = STAGES.length - 1
    let next: number | null = null
    if (event.key === 'ArrowRight') next = active === last ? 0 : active + 1
    else if (event.key === 'ArrowLeft') next = active === 0 ? last : active - 1
    else if (event.key === 'Home') next = 0
    else if (event.key === 'End') next = last
    if (next === null) return
    event.preventDefault()
    setActive(next)
    tabs.current[next]?.focus()
  }

  const stage = STAGES[active]!

  return (
    <section className="k-section k-product" id="showcase">
      <div className="k-container">
        <div className="k-section-head">
          <div className="k-section-head-copy">
            <p className="k-eyebrow">
              <span className="k-eyebrow-dot" aria-hidden="true" />
              {t('landing.showcase.eyebrow')}
            </p>
            <h2>{t('landing.showcase.title')}</h2>
          </div>
          <p className="k-section-lead">{t('landing.showcase.sub')}</p>
        </div>

        <div className="k-tabs" role="tablist" aria-label={t('landing.showcase.eyebrow')} onKeyDown={onKeyDown}>
          {STAGES.map((item, index) => (
            <button
              key={item.id}
              ref={(node) => {
                tabs.current[index] = node
              }}
              type="button"
              role="tab"
              id={`tab-${item.id}`}
              aria-selected={index === active}
              aria-controls={`panel-${item.id}`}
              tabIndex={index === active ? 0 : -1}
              className="k-tab"
              onClick={() => setActive(index)}
            >
              <span className="k-tab-index">{String(index + 1).padStart(2, '0')}</span>
              {t(item.kicker)}
            </button>
          ))}
        </div>

        <div
          key={stage.id}
          className="k-stage-panel"
          role="tabpanel"
          id={`panel-${stage.id}`}
          aria-labelledby={`tab-${stage.id}`}
          tabIndex={0}
        >
          <div className="k-stage-copy">
            <p className="k-stage-kicker">{t(stage.kicker)}</p>
            <h3>{t(stage.title)}</h3>
            <p className="k-stage-body">{t(stage.body)}</p>
            <ul className="k-stage-points">
              <li>
                <CheckIcon size={14} />
                {t(stage.point1)}
              </li>
              <li>
                <CheckIcon size={14} />
                {t(stage.point2)}
              </li>
            </ul>
          </div>

          <div className="k-stage-art">
            {active === 0 ? <IntakeArt t={t} /> : null}
            {active === 1 ? <CalibrationArt t={t} /> : null}
            {active === 2 ? <MonitorArt t={t} /> : null}
            {active === 3 ? <ReaderArt t={t} /> : null}
          </div>
        </div>
      </div>
    </section>
  )
}

/** Stage 1 — the intake drop zone, as `/workspace` actually presents it. */
function IntakeArt({ t }: { t: T }) {
  return (
    <figure className="k-art-card">
      <div className="k-mini-top">
        <span className="k-mini-tag is-emerald">
          <UploadIcon size={11} />
          {t('landing.ui.workspace')}
        </span>
        <span className="k-mini-tag">{t('landing.ui.intakeOnly')}</span>
      </div>
      <div className="k-drop">
        <span className="k-drop-icon">
          <FileIcon size={18} />
        </span>
        <span className="k-drop-title" dir="ltr">
          the-quiet-cities.epub
        </span>
        <span className="k-drop-meta">2.4 MB · EPUB 3</span>
        <span className="k-drop-state">
          <CheckCircleIcon size={13} />
          {t('landing.ui.structureRead', { n: '18' })}
        </span>
      </div>
      <div className="k-mini-foot">
        <span>{t('landing.ui.nothingCharged')}</span>
        <span className="k-mini-note">{t('landing.ui.nextCalibration')}</span>
      </div>
    </figure>
  )
}

/** Stage 2 — the workshop's step rail and a real sample pair. */
function CalibrationArt({ t }: { t: T }) {
  return (
    <figure className="k-art-card">
      <div className="k-mini-top">
        <span className="k-mini-tag is-emerald">{t('landing.cap.cal.kicker')}</span>
        <span className="k-mini-tag">{t('landing.ui.sampleOf', { n: '1', total: '3' })}</span>
      </div>
      <div className="k-wizard-steps">
        <div className="k-wizard-step is-done">
          <span>
            <CheckIcon size={10} />
          </span>
          {t('landing.ui.tone')}
        </div>
        <div className="k-wizard-step is-active">
          <span>2</span>
          {t('landing.ui.models')}
        </div>
        <div className="k-wizard-step">
          <span>3</span>
          {t('landing.ui.glossary')}
        </div>
        <div className="k-wizard-step">
          <span>4</span>
          {t('landing.ui.review')}
        </div>
      </div>
      <div className="k-sample">
        <p className="k-sample-source" dir="ltr">
          We arrived at dusk, when the city had begun to whisper instead of shout.
        </p>
        <p className="k-sample-target" dir="rtl" lang="fa">
          غروب‌هنگام رسیدیم، وقتی شهر به‌جای فریاد کشیدن، آغاز کرده بود به نجوا کردن.
        </p>
      </div>
      <div className="k-term-row">
        <span className="k-chip">
          <CheckIcon size={11} />
          dusk <b dir="rtl">غروب</b>
        </span>
        <span className="k-chip">
          <CheckIcon size={11} />
          whisper <b dir="rtl">نجوا</b>
        </span>
        <span className="k-chip is-muted">{t('landing.ui.rejected', { n: '2' })}</span>
      </div>
      <div className="k-seal-row">
        <span className="k-seal-ok">
          <CheckCircleIcon size={13} />
          {t('landing.ui.allApproved')}
        </span>
        <span className="k-mini-tag is-emerald">{t('landing.ui.sealProfile')}</span>
      </div>
    </figure>
  )
}

/** Stage 3 — the monitor: per-chunk status and a resumable progress bar. */
function MonitorArt({ t }: { t: T }) {
  const rows = [
    { id: 'ch-011', name: 'Chapter 11 · The Harbour', status: 'done', label: t('landing.ui.done') },
    { id: 'ch-012', name: 'Chapter 12 · Bread and Rain', status: 'done', label: t('landing.ui.done') },
    { id: 'ch-013', name: 'Chapter 13 · Dusk', status: 'running', label: t('landing.ui.running') },
    { id: 'ch-014', name: 'Chapter 14 · The Long Road', status: 'queued', label: t('landing.ui.queued') },
  ]
  return (
    <figure className="k-art-card">
      <div className="k-mini-top">
        <span className="k-mini-tag is-live">
          <PulseIcon size={11} />
          {t('landing.ui.running')}
        </span>
        <span className="k-mini-tag">
          <ClockIcon size={11} />
          {t('landing.ui.concurrent', { n: '12' })}
        </span>
      </div>
      <div className="k-monitor-progress">
        <div className="k-monitor-progress-top">
          <span>{t('landing.ui.chaptersTranslated')}</span>
          <b dir="ltr">13 / 18</b>
        </div>
        <span className="k-progress-track">
          <span className="k-progress-fill" style={{ width: '72%' }} />
        </span>
      </div>
      <div className="k-chunk-list">
        {rows.map((row) => (
          <div className="k-chunk-row" key={row.id}>
            <span className="k-chunk-id">{row.id}</span>
            <span className="k-chunk-name" dir="ltr">
              {row.name}
            </span>
            <span className={`k-status is-${row.status}`}>{row.label}</span>
          </div>
        ))}
      </div>
      <div className="k-mini-foot">
        <span>{t('landing.ui.stopKeeps')}</span>
        <span className="k-mini-note">{t('landing.ui.resumeSafe')}</span>
      </div>
    </figure>
  )
}

/** Stage 4 — the reader, with pairing and a paper surface. */
function ReaderArt({ t }: { t: T }) {
  return (
    <figure className="k-art-card">
      <div className="k-mini-top">
        <span className="k-mini-tag is-emerald">
          <DocIcon size={11} />
          {t('landing.ui.reader')}
        </span>
        <span className="k-mini-tag">{t('landing.ui.paired')}</span>
      </div>
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
          <span className="k-swatch is-active">
            <span />
          </span>
          <span className="k-swatch mini">
            <span />
          </span>
          <span className="k-swatch mini">
            <span />
          </span>
        </div>
      </div>
      <div className="k-mini-foot">
        <span>{t('landing.ui.fourThemes')}</span>
        <span className="k-mini-note">
          <ArrowRightIcon size={11} /> {t('landing.ui.export')}
        </span>
      </div>
    </figure>
  )
}
