/**
 * Kalima landing page — INK / PAPER / EMERALD.
 *
 * The public face of the product, rendered outside `AppShell` (see the
 * standalone branch in `App.tsx`) so it carries no rail and no bottom bar.
 *
 * WHY THE REVEAL LIVES HERE
 * -------------------------
 * One observer for the whole page, armed once on mount, rather than a hook per
 * section. A per-section observer means six IntersectionObservers watching the
 * same viewport and firing in an order nobody controls, which is how scroll
 * reveals end up feeling random instead of sequential.
 *
 * The failure mode is handled explicitly: elements are only hidden once the
 * observer is actually attached (`is-armed`), so if `IntersectionObserver` is
 * missing or throws, nothing is ever hidden and the page is simply static. A
 * reveal system that hides content it cannot later show is worse than no
 * animation at all.
 */
import { useEffect, useRef, useState } from 'react'
import { api } from '@/lib/api'
import { useLanguage } from '@/i18n/useLanguage.ts'
import { LandingNav, type NavSection } from '../components/landing/LandingNav'
import { HeroSection } from '../components/landing/HeroSection'
import { LanguageSection } from '../components/landing/LanguageSection'
import { ShowcaseSection } from '../components/landing/ShowcaseSection'
import { CapabilitiesSection } from '../components/landing/CapabilitiesSection'
import { ReadingSection } from '../components/landing/ReadingSection'
import { WorkflowSection } from '../components/landing/WorkflowSection'
import { DifferentiationSection } from '../components/landing/DifferentiationSection'
import { FinalCtaSection } from '../components/landing/FinalCtaSection'
import { LandingFooter } from '../components/landing/LandingFooter'
import './landing.css'

const SECTIONS: readonly NavSection[] = [
  { id: 'product', label: 'landing.nav.product' },
  { id: 'capabilities', label: 'landing.nav.capabilities' },
  { id: 'reading', label: 'landing.nav.reading' },
  { id: 'workflow', label: 'landing.nav.workflow' },
]

/**
 * Arms and reveals every `[data-reveal]` on the page.
 *
 * Returns the ref the page root must carry. The observer is created once and
 * disconnected on unmount; each element is unobserved as soon as it has been
 * revealed, so scrolling back up does not re-run anything.
 */
function useReveal() {
  const ref = useRef<HTMLDivElement | null>(null)

  useEffect(() => {
    const root = ref.current
    if (!root) return

    const items = Array.from(root.querySelectorAll<HTMLElement>('[data-reveal]'))
    if (items.length === 0) return

    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches
    if (reduced || typeof IntersectionObserver === 'undefined') {
      items.forEach((el) => el.classList.add('is-visible'))
      return
    }

    // Arm first, then observe. If arming threw, nothing would be hidden.
    items.forEach((el) => el.classList.add('is-armed'))

    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (!entry.isIntersecting) return
          entry.target.classList.add('is-visible')
          observer.unobserve(entry.target)
        })
      },
      { threshold: 0.1, rootMargin: '0px 0px -6% 0px' },
    )

    items.forEach((el) => observer.observe(el))
    return () => observer.disconnect()
  }, [])

  return ref
}

/**
 * Whether anyone is signed in.
 *
 * `null` means "not known yet". The nav and the CTAs treat `null` as signed
 * out, because a cold visitor is overwhelmingly signed out and a nav bar that
 * flickers from "Start" to "Dashboard" is worse than one that settles once.
 */
function useAuthState() {
  const [loggedIn, setLoggedIn] = useState<boolean | null>(null)

  useEffect(() => {
    let alive = true
    api
      .authMe()
      .then((res) => {
        if (alive) setLoggedIn(Boolean(res?.user))
      })
      .catch(() => {
        if (alive) setLoggedIn(false)
      })
    return () => {
      alive = false
    }
  }, [])

  return loggedIn
}

export function LandingPage() {
  const { t, lang, dir } = useLanguage()
  const revealRef = useReveal()
  const loggedIn = useAuthState()

  useEffect(() => {
    document.title = 'Kalima \u2014 Every Book. Every Language. Nothing Lost.'
  }, [])

  const primaryHref = loggedIn ? '/dashboard' : '/signup'
  const primaryLabel = loggedIn ? t('landing.nav.ctaLoggedIn') : t('landing.nav.cta')

  return (
    <div ref={revealRef} className="k-landing" lang={lang} dir={dir}>
      <a href="#main" className="k-skip">
        {t('shell.skip')}
      </a>

      <LandingNav
        t={t}
        loggedIn={loggedIn}
        primaryHref={primaryHref}
        primaryLabel={primaryLabel}
        sections={SECTIONS}
      />

      {/*
        `.page` is the shared page contract: it is what tells the responsive
        test that this page does not own a second gutter. `landing.css` zeroes
        its padding and gives the landing its own wider editorial gutter, so the
        class is carried without its usual effect.
      */}
      <main className="page" id="main" tabIndex={-1}>
        <HeroSection t={t} loggedIn={loggedIn} />

        <div className="k-container">
          <div className="k-proof-strip" data-reveal>
            <div className="k-proof-cell">
              <span className="k-proof-cell-value">{t('landing.proof.formats.value')}</span>
              <span className="k-proof-cell-label">{t('landing.proof.formats.label')}</span>
            </div>
            <div className="k-proof-cell">
              <span className="k-proof-cell-value">{t('landing.proof.outputs.value')}</span>
              <span className="k-proof-cell-label">{t('landing.proof.outputs.label')}</span>
            </div>
            <div className="k-proof-cell">
              <span className="k-proof-cell-value">{t('landing.proof.workshop.value')}</span>
              <span className="k-proof-cell-label">{t('landing.proof.workshop.label')}</span>
            </div>
            <div className="k-proof-cell">
              <span className="k-proof-cell-value">{t('landing.proof.reader.value')}</span>
              <span className="k-proof-cell-label">{t('landing.proof.reader.label')}</span>
            </div>
          </div>
        </div>

        <LanguageSection t={t} />

        <div data-reveal>
          <ShowcaseSection t={t} />
        </div>

        <div data-reveal>
          <CapabilitiesSection t={t} />
        </div>

        <div data-reveal>
          <ReadingSection t={t} />
        </div>

        <div data-reveal>
          <WorkflowSection t={t} />
        </div>

        <div data-reveal>
          <DifferentiationSection t={t} />
        </div>

        <div data-reveal>
          <FinalCtaSection t={t} loggedIn={loggedIn} />
        </div>
      </main>

      <LandingFooter t={t} loggedIn={loggedIn} />
    </div>
  )
}
