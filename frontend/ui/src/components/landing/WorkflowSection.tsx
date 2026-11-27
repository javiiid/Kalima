/**
 * Workflow — the four real steps, as a numbered ledger.
 *
 * A sticky intro column beside a list of rows, rather than four cards or a
 * horizontal stepper. The sequence matters and the rows are read top to bottom,
 * which is what a stepper drawn sideways quietly discourages.
 *
 * Each row carries a small artefact of that step on the right. The artefacts
 * are the same reconstructions the showcase uses, at a smaller size, so the two
 * sections reinforce each other instead of repeating themselves in different
 * visual languages.
 */
import type { StringKey } from '@/i18n/fa.ts'
import {
  CheckCircleIcon,
  FileIcon,
  PulseIcon,
} from './LandingIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
}

const STEPS = [
  { n: '01', kicker: 'landing.flow1.kicker', title: 'landing.flow1.title', body: 'landing.flow1.body', tags: ['landing.flow1.tag1', 'landing.flow1.tag2', 'landing.flow1.tag3', 'landing.flow1.tag4'] },
  { n: '02', kicker: 'landing.flow2.kicker', title: 'landing.flow2.title', body: 'landing.flow2.body', tags: ['landing.flow2.tag1', 'landing.flow2.tag2', 'landing.flow2.tag3', 'landing.flow2.tag4'] },
  { n: '03', kicker: 'landing.flow3.kicker', title: 'landing.flow3.title', body: 'landing.flow3.body', tags: ['landing.flow3.tag1', 'landing.flow3.tag2', 'landing.flow3.tag3'] },
  { n: '04', kicker: 'landing.flow4.kicker', title: 'landing.flow4.title', body: 'landing.flow4.body', tags: ['landing.flow4.tag1', 'landing.flow4.tag2', 'landing.flow4.tag3', 'landing.flow4.tag4'] },
] as const satisfies readonly { n: string; kicker: StringKey; title: StringKey; body: StringKey; tags: readonly StringKey[] }[]

export function WorkflowSection({ t }: Props) {
  return (
    <section className="k-section k-workflow" id="workflow">
      <div className="k-container k-workflow-grid">
        <div className="k-workflow-intro">
          <p className="k-eyebrow">
            <span className="k-eyebrow-dot" aria-hidden="true" />
            {t('landing.workflow.eyebrow')}
          </p>
          <h2>{t('landing.workflow.title')}</h2>
          <p className="k-lead">{t('landing.workflow.sub')}</p>
        </div>

        <div className="k-flow">
          {STEPS.map((step, index) => (
            <div className="k-flow-row" key={step.n}>
              <span className="k-flow-number">{step.n}</span>
              <div className="k-flow-copy">
                <span className="k-flow-kicker">{t(step.kicker)}</span>
                <h3>{t(step.title)}</h3>
                <p>{t(step.body)}</p>
                <div className="k-flow-tags">
                  {step.tags.map((tag) => (
                    <span key={tag}>{t(tag)}</span>
                  ))}
                </div>
              </div>
              <div className="k-flow-art">{index === 0 ? <IntakeMini t={t} /> : null}{index === 1 ? <CalibrationMini t={t} /> : null}{index === 2 ? <RunMini t={t} /> : null}{index === 3 ? <ReadMini t={t} /> : null}</div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}

function IntakeMini({ t }: { t: T }) {
  return (
    <>
      <span className="k-flow-file">EPUB</span>
      <span className="k-flow-file-copy">
        <strong dir="ltr">the-quiet-cities.epub</strong>
        <span>{t('landing.ui.structureRead', { n: '18' })}</span>
      </span>
      <span className="k-flow-art-check">
        <CheckCircleIcon size={14} />
      </span>
    </>
  )
}

function CalibrationMini({ t }: { t: T }) {
  return (
    <div className="k-flow-samples">
      <div className="k-flow-sample">
        <span>{t('landing.ui.sampleOf', { n: '1', total: '3' })}</span>
        <CheckCircleIcon size={12} />
      </div>
      <div className="k-flow-sample">
        <span>{t('landing.ui.sampleOf', { n: '2', total: '3' })}</span>
        <CheckCircleIcon size={12} />
      </div>
      <div className="k-flow-sample">
        <span>{t('landing.ui.sampleOf', { n: '3', total: '3' })}</span>
        <CheckCircleIcon size={12} />
      </div>
    </div>
  )
}

function RunMini({ t }: { t: T }) {
  return (
    <div className="k-flow-progress">
      <div className="k-flow-progress-top">
        <span>{t('landing.ui.chapters')}</span>
        <b dir="ltr">13 / 18</b>
      </div>
      <span className="k-progress-track">
        <span className="k-progress-fill" style={{ width: '72%' }} />
      </span>
      <span className="k-flow-progress-meta">
        <PulseIcon size={11} /> {t('landing.ui.resumeSafe')}
      </span>
    </div>
  )
}

function ReadMini({ t }: { t: T }) {
  return (
    <div className="k-flow-read">
      <span className="k-flow-read-label">{t('landing.ui.chapter', { n: '03' })}</span>
      <p dir="rtl" lang="fa">
        غروب‌هنگام رسیدیم، وقتی شهر آغاز کرده بود به نجوا کردن.
      </p>
      <span className="k-flow-read-meta">
        <FileIcon size={11} /> DOCX · PDF · EPUB
      </span>
    </div>
  )
}
