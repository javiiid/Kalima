/**
 * The footer.
 *
 * Only destinations that exist. Every link here resolves to a real route in
 * `App.tsx`; nothing points at a page that has not been built, because a footer
 * full of dead links is the fastest way to make a finished product look
 * unfinished.
 *
 * `/reader` is deliberately absent: it names no book, so it is a dead end (see
 * `frontend/AGENTS.md`). The library is the honest destination for "go read
 * something".
 */
import { Link } from 'react-router-dom'
import type { StringKey } from '@/i18n/fa.ts'
import { KalimaMark } from '../AppShell'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

interface Props {
  t: T
  loggedIn: boolean | null
}

export function LandingFooter({ t, loggedIn }: Props) {
  const year = new Date().getFullYear()

  return (
    <footer className="k-footer">
      <div className="k-container">
        <div className="k-footer-main">
          <div className="k-footer-brand">
            <Link to="/landing" className="k-brand" aria-label={t('landing.nav.brand')}>
              <KalimaMark size={28} variant="dark" />
              <span className="k-brand-word">{t('landing.nav.brand')}</span>
              <span className="k-brand-dot" aria-hidden="true" />
            </Link>
            <p>{t('landing.footer.blurb')}</p>
          </div>

          <nav className="k-footer-col" aria-labelledby="footer-product">
            <h2 id="footer-product">{t('landing.footer.colProduct')}</h2>
            <a href="#product">{t('landing.nav.product')}</a>
            <a href="#capabilities">{t('landing.nav.capabilities')}</a>
            <a href="#reading">{t('landing.nav.reading')}</a>
            <a href="#workflow">{t('landing.nav.workflow')}</a>
          </nav>

          <nav className="k-footer-col" aria-labelledby="footer-account">
            <h2 id="footer-account">{t('landing.footer.colAccount')}</h2>
            {loggedIn ? (
              <>
                <Link to="/dashboard">{t('landing.nav.dashboard')}</Link>
                <Link to="/workspace">{t('landing.footer.workspace')}</Link>
                <Link to="/library">{t('landing.footer.library')}</Link>
              </>
            ) : (
              <>
                <Link to="/login">{t('landing.footer.signin')}</Link>
                <Link to="/signup">{t('landing.footer.signup')}</Link>
              </>
            )}
          </nav>

          <nav className="k-footer-col" aria-labelledby="footer-resources">
            <h2 id="footer-resources">{t('landing.footer.colResources')}</h2>
            <Link to="/help">{t('landing.footer.help')}</Link>
          </nav>
        </div>

        <div className="k-footer-bottom">
          <span>{t('landing.footer.copyright', { year: String(year) })}</span>
          <span>{t('landing.footer.note')}</span>
        </div>
      </div>
    </footer>
  )
}
