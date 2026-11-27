/**
 * The hero.
 *
 * The tagline is approved and final: "Every Book. Every Language. Nothing
 * Lost." It is set as three lines with three different jobs -- the subject in
 * full ink, the promise with the accent on the word that carries the product,
 * and the resolution softer so the sentence ends instead of stopping.
 *
 * The <h1> carries the whole sentence as its accessible name; the three spans
 * are presentational. That split is why the accent can sit on one word without
 * the screen reader hearing the sentence in fragments.
 *
 * The visual is not a screenshot and not a laptop mockup. It is a faithful
 * reconstruction of the calibration workshop's working pane -- a sealed profile
 * translating a real passage -- because that pane is the most distinctive thing
 * the product does. It is labelled as illustrative, not live.
 */
import { Link } from 'react-router-dom'
import type { StringKey } from '@/i18n/fa.ts'
import { LanguageDemo } from './LanguageDemo'
import { ArrowRightIcon, CheckIcon, FileIcon, ShieldIcon } from './LandingIcons'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
  loggedIn: boolean | null
}

export function HeroSection({ t, loggedIn }: Props) {
  const primaryHref = loggedIn ? '/dashboard' : '/signup'
  const primaryLabel = loggedIn ? t('landing.hero.ctaLoggedIn') : t('landing.hero.cta')

  return (
    <section className="k-hero" id="product">
      <div className="k-hero-bg" aria-hidden="true">
        <div className="k-hero-glow k-hero-glow--a" />
        <div className="k-hero-grid" />
      </div>

      <div className="k-container k-hero-inner">
        <div className="k-hero-copy">
          <p className="k-eyebrow">
            <span className="k-eyebrow-dot" aria-hidden="true" />
            {t('landing.hero.eyebrow')}
          </p>

          {/*
            The accessible name is assembled from the same three translated
            parts as the visible text. It used to be `landing.hero.tagline`,
            which is deliberately the English sentence in both dictionaries --
            so a Persian page announced an English headline to a screen reader.
          */}
          <h1
            className="k-tagline"
            aria-label={`${t('landing.tagline.book')} ${t('landing.tagline.language')} ${t(
              'landing.tagline.lost',
            )}`}
          >
            <span className="k-tagline-part k-tagline-part--book" aria-hidden="true">
              {t('landing.tagline.book')}
            </span>
            <span className="k-tagline-part k-tagline-part--language" aria-hidden="true">
              {t('landing.tagline.languagePre')}
              <span className="k-tagline-accent">{t('landing.tagline.languageAccent')}</span>
              <span className="k-tagline-stop">.</span>
            </span>
            <span className="k-tagline-part k-tagline-part--lost" aria-hidden="true">
              {t('landing.tagline.lost')}
            </span>
          </h1>

          <p className="k-hero-lead">{t('landing.hero.lead')}</p>

          <div className="k-hero-actions">
            <Link to={primaryHref} className="k-btn k-btn-primary k-btn-lg">
              {primaryLabel}
              <ArrowRightIcon size={17} />
            </Link>
            <a href="#workflow" className="k-btn k-btn-ghost k-btn-lg">
              {t('landing.hero.ctaSecondary')}
            </a>
          </div>

          <ul className="k-hero-facts">
            <li>
              <CheckIcon size={14} />
              {t('landing.hero.trust1')}
            </li>
            <li>
              <CheckIcon size={14} />
              {t('landing.hero.trust2')}
            </li>
            <li>
              <CheckIcon size={14} />
              {t('landing.hero.trust3')}
            </li>
          </ul>
        </div>

        <div className="k-hero-visual">
          <HeroWindow t={t} />
        </div>
      </div>
    </section>
  )
}

/**
 * The product window.
 *
 * Reconstructed from the calibration workshop: a source file in the bar, the
 * sealed-profile state, and the live translation of a real passage. Every label
 * is a real term from the product -- "sealed", "glossary locked" -- because a
 * plausible-looking fake is worse than an honest diagram.
 *
 * The chapter names and the word count are illustrative content, not claims
 * about a real user's book; the figure note under the window says so.
 */
function HeroWindow({ t }: { t: T }) {
  return (
    <div className="k-hero-figure">
      <div className="k-window k-window-hero">
        <div className="k-window-bar">
          <div className="k-window-file">
            <span className="k-window-dots" aria-hidden="true">
              <span />
              <span />
              <span />
            </span>
            <span className="k-file-badge">EPUB</span>
            <span className="k-window-file-text">
              <strong className="k-window-title" dir="ltr">
                the-quiet-cities.epub
              </strong>
              <span className="k-window-sub" dir="ltr">
                18 chapters · 214,806 words
              </span>
            </span>
          </div>
          <span className="k-live-pill">
            <span className="k-live-dot" aria-hidden="true" />
            {t('landing.cta.seal')}
          </span>
        </div>

        <div className="k-window-main">
          <div className="k-hero-rail">
            <span className="k-ui-label">{t('landing.ui.chapters')}</span>
            <div className="k-chapter-list">
              <div className="k-chapter is-done">
                <CheckIcon size={12} />
                <span>Arrival</span>
                <span className="k-chapter-num">01</span>
              </div>
              <div className="k-chapter is-done">
                <CheckIcon size={12} />
                <span>The Long Road</span>
                <span className="k-chapter-num">02</span>
              </div>
              <div className="k-chapter is-active">
                <span aria-hidden="true" />
                <span>Dusk</span>
                <span className="k-chapter-num">03</span>
              </div>
              <div className="k-chapter">
                <span aria-hidden="true" />
                <span>Bread and Rain</span>
                <span className="k-chapter-num">04</span>
              </div>
            </div>

            <span className="k-ui-label k-ui-label-spaced">{t('landing.ui.glossary')}</span>
            <div className="k-term-list">
              <div className="k-term">
                <span dir="ltr">dusk</span>
                <b dir="rtl">غروب</b>
              </div>
              <div className="k-term">
                <span dir="ltr">certainty</span>
                <b dir="rtl">یقین</b>
              </div>
            </div>
          </div>

          <div className="k-hero-page">
            <div className="k-page-meta">
              <span>{t('landing.ui.chapter', { n: '03' })}</span>
            </div>
            <LanguageDemo t={t} variant="compact" showRail={false} showPair />
          </div>
        </div>

        <div className="k-window-foot">
          <span className="k-foot-progress">
            <span className="k-foot-count" dir="ltr">3 / 18</span>
            <span className="k-progress-track">
              <span className="k-progress-fill" style={{ width: '17%' }} />
            </span>
          </span>
          <span className="k-foot-saved">
            <ShieldIcon size={12} />
            {t('landing.cta.seal')}
          </span>
        </div>
      </div>

      <p className="k-figure-note">
        <FileIcon size={12} />
        <span>{t('landing.hero.note')}</span>
      </p>
    </div>
  )
}
