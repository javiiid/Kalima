/**
 * The final call to action.
 *
 * One headline, one line of support, one primary action, and a secondary sign-in
 * link for the visitor who already has an account. It reinforces the argument
 * the page has already made rather than introducing a new claim -- which is the
 * only thing a closing section is for.
 *
 * The visual is a stack of paper sheets with the translated page on top: the
 * same object the reader section showed, at the moment it becomes a finished
 * edition. It is decorative and marked `aria-hidden`; the copy carries the
 * meaning.
 */
import { Link } from 'react-router-dom'
import type { StringKey } from '@/i18n/fa.ts'
import { ArrowRightIcon, CheckCircleIcon } from './LandingIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
  loggedIn: boolean | null
}

export function FinalCtaSection({ t, loggedIn }: Props) {
  const primaryHref = loggedIn ? '/dashboard' : '/signup'
  const primaryLabel = loggedIn ? t('landing.cta.primaryLoggedIn') : t('landing.cta.primary')

  return (
    <section className="k-final" id="start">
      <div className="k-container">
        <div className="k-cta-panel">
          <div className="k-cta-copy">
            <h2>{t('landing.cta.title')}</h2>
            <p className="k-lead">{t('landing.cta.lead')}</p>
            <div className="k-cta-actions">
              <Link to={primaryHref} className="k-btn k-btn-primary k-btn-lg">
                {primaryLabel}
                <ArrowRightIcon size={17} />
              </Link>
              {loggedIn ? null : (
                <Link to="/login" className="k-btn k-btn-ghost k-btn-lg">
                  {t('landing.nav.login')}
                </Link>
              )}
            </div>
            <p className="k-cta-note">
              <CheckCircleIcon size={13} />
              {t('landing.cta.note')}
            </p>
          </div>

          <div className="k-cta-visual" aria-hidden="true">
            <span className="k-cta-sheet k-cta-sheet-back" />
            <span className="k-cta-sheet k-cta-sheet-mid" />
            <div className="k-cta-sheet k-cta-sheet-front">
              <span className="k-cta-sheet-label">{t('landing.cta.sheetLabel')}</span>
              <p dir="rtl" lang="fa">
                غروب‌هنگام رسیدیم، وقتی شهر آغاز کرده بود به نجوا کردن.
              </p>
              <span className="k-cta-sheet-meta">{t('landing.cta.sheetMeta')}</span>
              <span className="k-cta-seal">
                <CheckCircleIcon size={12} />
                {t('landing.cta.seal')}
              </span>
            </div>
          </div>
        </div>
      </div>
    </section>
  )
}
