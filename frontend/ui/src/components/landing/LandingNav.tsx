/**
 * The landing navigation.
 *
 * Sticky, transparent at rest, and it grows a hairline and a blurred ink
 * backdrop once the page has scrolled -- so the brand sits on the hero artwork
 * at the top and on a legible surface the moment there is content behind it.
 *
 * AUTH
 * ----
 * The CTA is auth-aware but does not invent an auth system: it reads the same
 * `api.authMe()` the rest of the app reads, and points at the routes that
 * already exist (`/signup`, `/login`, `/dashboard`). While the check is in
 * flight the CTA shows the signed-out label and the signed-out destination,
 * because a visitor arriving cold is overwhelmingly a signed-out visitor and a
 * spinner in a nav bar is worse than a link that turns out to be right anyway.
 *
 * `Link` from react-router, never a bare anchor: an anchor reloads the whole
 * app, which drops the warm settings query and re-runs the auth check.
 */
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import type { StringKey } from '@/i18n/fa.ts'
import { KalimaMark } from '../AppShell'
import { ArrowRightIcon, CloseIcon, MenuIcon } from './LandingIcons'
import { LandingLanguageSwitch } from './LandingLanguageSwitch'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

export interface NavSection {
  id: string
  label: StringKey
}

interface Props {
  t: T
  loggedIn: boolean | null
  primaryHref: string
  primaryLabel: string
  sections: readonly NavSection[]
}

export function LandingNav({ t, loggedIn, primaryHref, primaryLabel, sections }: Props) {
  const [scrolled, setScrolled] = useState(false)
  const [open, setOpen] = useState(false)

  useEffect(() => {
    const onScroll = () => setScrolled(window.scrollY > 12)
    onScroll()
    window.addEventListener('scroll', onScroll, { passive: true })
    return () => window.removeEventListener('scroll', onScroll)
  }, [])

  // Escape closes the sheet, and the body is locked while it is open so the
  // page behind does not scroll under the menu on a phone.
  useEffect(() => {
    if (!open) return
    const onKey = (event: KeyboardEvent) => {
      if (event.key === 'Escape') setOpen(false)
    }
    document.addEventListener('keydown', onKey)
    const previous = document.body.style.overflow
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = previous
    }
  }, [open])

  return (
    <>
      <header className="k-nav" data-scrolled={scrolled ? 'true' : 'false'}>
        <div className="k-container k-nav-inner">
          <Link to="/landing" className="k-brand" aria-label={t('landing.nav.brand')}>
            <KalimaMark size={30} variant="dark" />
            <span className="k-brand-word">{t('landing.nav.brand')}</span>
            <span className="k-brand-dot" aria-hidden="true" />
          </Link>

          <nav className="k-nav-links" aria-label={t('landing.nav.brand')}>
            {sections.map((section) => (
              <a key={section.id} href={`#${section.id}`} className="k-nav-link">
                {t(section.label)}
              </a>
            ))}
          </nav>

          <div className="k-nav-actions">
            <LandingLanguageSwitch t={t} />
            {loggedIn ? null : (
              <Link to="/login" className="k-nav-signin">
                {/*
                  The label is duplicated as a `data-label` attribute rather than
                  a second DOM node: `::after` paints the emerald copy that wipes
                  in over it, so the accessible name stays one clean string and
                  nothing is announced twice.
                */}
                <span className="k-nav-signin-label" data-label={t('landing.nav.login')}>
                  {t('landing.nav.login')}
                </span>
              </Link>
            )}
            <Link to={primaryHref} className="k-btn k-btn-primary k-nav-cta">
              <span className="k-nav-cta-label">{primaryLabel}</span>
            </Link>
            <button
              type="button"
              className="k-menu-btn"
              aria-expanded={open}
              aria-controls="landing-menu"
              aria-label={open ? t('landing.nav.close') : t('landing.nav.menu')}
              onClick={() => setOpen((value) => !value)}
            >
              {open ? <CloseIcon size={20} /> : <MenuIcon size={20} />}
            </button>
          </div>
        </div>
      </header>

      {open ? (
        <div className="k-nav-sheet" id="landing-menu">
          <nav className="k-mobile-nav" aria-label={t('landing.nav.brand')}>
            {sections.map((section, index) => (
              <a
                key={section.id}
                href={`#${section.id}`}
                className="k-mobile-link"
                onClick={() => setOpen(false)}
              >
                <span className="k-mobile-index" aria-hidden="true">
                  {String(index + 1).padStart(2, '0')}
                </span>
                {t(section.label)}
                <ArrowRightIcon size={16} />
              </a>
            ))}
          </nav>
          <div className="k-mobile-actions">
            <Link to={primaryHref} className="k-btn k-btn-primary" onClick={() => setOpen(false)}>
              {primaryLabel}
            </Link>
            {loggedIn ? null : (
              <Link to="/login" className="k-btn k-btn-ghost" onClick={() => setOpen(false)}>
                {t('landing.nav.login')}
              </Link>
            )}
          </div>
          {/*
            The switch also lives in the sheet. On a narrow bar it is visible
            already, but a visitor who has opened the menu is looking for
            navigation, and language is navigation on this page.
          */}
          <div className="k-mobile-lang">
            <LandingLanguageSwitch t={t} inline />
          </div>
          <p className="k-mobile-note">{t('landing.cta.note')}</p>
        </div>
      ) : null}
    </>
  )
}
