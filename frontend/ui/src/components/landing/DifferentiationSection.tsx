/**
 * Differentiation — why this is not a translation box.
 *
 * Three principles as a numbered ledger beside a sticky statement. No
 * competitor is named and no comparison table is drawn: the section argues from
 * what Kalima does, not from what someone else does not, which is both more
 * honest and more durable.
 */
import type { StringKey } from '@/i18n/fa.ts'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
}

const PRINCIPLES = [
  { n: '01', title: 'landing.diff.principle1.title', body: 'landing.diff.principle1.body' },
  { n: '02', title: 'landing.diff.principle2.title', body: 'landing.diff.principle2.body' },
  { n: '03', title: 'landing.diff.principle3.title', body: 'landing.diff.principle3.body' },
] as const satisfies readonly { n: string; title: StringKey; body: StringKey }[]

export function DifferentiationSection({ t }: Props) {
  return (
    <section className="k-section k-why" id="why">
      <div className="k-container k-why-grid">
        <div className="k-why-intro">
          <p className="k-eyebrow">
            <span className="k-eyebrow-dot" aria-hidden="true" />
            {t('landing.diff.eyebrow')}
          </p>
          <h2>{t('landing.diff.title')}</h2>
          <p className="k-lead">{t('landing.diff.sub')}</p>
          <p className="k-why-statement">{t('landing.diff.statement')}</p>
        </div>

        <div className="k-principles">
          {PRINCIPLES.map((principle) => (
            <div className="k-principle" key={principle.n}>
              <span className="k-principle-number">{principle.n}</span>
              <div>
                <h3>{t(principle.title)}</h3>
                <p>{t(principle.body)}</p>
              </div>
            </div>
          ))}
        </div>
      </div>
    </section>
  )
}
