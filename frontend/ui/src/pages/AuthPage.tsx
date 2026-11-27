/**
 * Login, signup and password recovery — the ink surface's front door.
 *
 * WHAT THIS PAGE IS
 * -----------------
 * The landing page establishes an ink-and-emerald world and ends on "Start
 * translating". This is where that click lands, so it carries the same world:
 * one card, lit from behind, standing on the landing page's own ambient field.
 * The card is the only thing asking for input, and it is the only thing that
 * moves.
 *
 * THE AUTH MODEL IS THE SERVER'S, NOT THIS FILE'S
 * -----------------------------------------------
 * `app/auth/` owns every rule, and this page invents none of them:
 *
 *   * The session is an HttpOnly cookie. This page never sees, stores or
 *     forwards a token — it posts a form and navigates on `{user}`.
 *   * Password bounds are 8..200 characters and nothing else. `validPassword`
 *     in `lib/auth.ts` mirrors that exactly, and the strength meter in
 *     `lib/password.ts` only *describes* — it never blocks a password the
 *     server would accept.
 *   * Signup signs you in immediately. There is no email-verification step in
 *     the backend, so there is no "check your inbox" screen here pretending
 *     there is one.
 *   * There is no "remember me": session lifetime is server-owned and a
 *     checkbox that changed nothing would be a lie.
 *   * Password recovery does exist (`request_password_reset` /
 *     `reset_password`), so it is wired up properly rather than faked. The
 *     request step answers identically for a known and an unknown address —
 *     it is not an account oracle — and this page's copy says so.
 *
 * LOGIN AND SIGNUP ARE ONE CARD IN TWO STATES
 * -------------------------------------------
 * The URL is the mode (`/login`, `/signup`), so a refresh, a bookmark and the
 * back button all agree with what is on screen. But the *card* is not
 * remounted between them: the height is measured and animated, and the form
 * body crossfades in under a new key. That is what makes the switch read as a
 * state change rather than a page load. See `useAnimatedHeight`.
 *
 * REDIRECTS
 * ---------
 * `?next=` is honoured but sanitised by `safeNextPath`: one leading slash, no
 * protocol-relative `//`, no backslash, no control characters, and no target
 * that is itself an auth page. An authenticated visitor landing here is sent
 * on rather than shown a form behind a live session.
 */
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { Link, useLocation, useNavigate, useSearchParams } from 'react-router-dom'
import { api, ApiError } from '@/lib/api.ts'
import { validDisplayName, validEmail, validOtpCode, validPassword } from '@/lib/auth.ts'
import type { AuthSession, AuthUser } from '@/lib/auth.ts'
import { safeNextPath } from '@/lib/password.ts'
import { useLanguage } from '@/i18n/useLanguage.ts'
import type { StringKey } from '@/i18n/fa.ts'
import { useAnimatedHeight } from '@/hooks/useAnimatedHeight.ts'
import { LandingLanguageSwitch } from '@/components/landing/LandingLanguageSwitch'
import { AuthCard } from '@/components/auth/AuthCard'
import {
  AuthError,
  AuthField,
  AuthInput,
  AuthNotice,
  AuthPasswordField,
  AuthSubmit,
  useFieldId,
} from '@/components/auth/AuthField'
import { ArrowLeftIcon } from '@/components/auth/AuthIcons'
import './auth.css'

type T = (key: StringKey, vars?: Record<string, string | number>) => string

type Mode = 'login' | 'signup'
/** The form's own view: the credential form, or the two recovery steps. */
type View = 'form' | 'reset-request' | 'reset-confirm'
type Method = 'password' | 'code'

/**
 * Brand marks for the OAuth buttons. Product logos, not UI chrome: the Google
 * "G" keeps its official colours so it stays recognisable, while the Apple mark
 * uses the text colour so it follows the surface. `aria-hidden` — the button
 * label already names the provider.
 */
function GoogleMark(): React.JSX.Element {
  return (
    <svg width={17} height={17} viewBox="0 0 24 24" aria-hidden="true" focusable="false">
      <path
        fill="#4285F4"
        d="M23.5 12.3c0-.9-.1-1.5-.3-2.3H12v4.5h6.5c-.1 1.1-.8 2.7-2.4 3.8l-.1.1 3.5 2.7.2.1c2.2-2 3.8-5 3.8-8.9z"
      />
      <path
        fill="#34A853"
        d="M12 24c3.2 0 5.9-1.1 7.9-2.9l-3.8-2.9c-1 .7-2.4 1.2-4.1 1.2-3.1 0-5.8-2.1-6.8-5l-.1.1-3.6 2.8v.1C3.5 21.3 7.4 24 12 24z"
      />
      <path
        fill="#FBBC05"
        d="M5.2 14.4c-.2-.7-.4-1.5-.4-2.4s.1-1.7.4-2.4l-.1-.1-3.6-2.8-.1.1C.5 8.6 0 10.2 0 12s.5 3.4 1.4 4.9l3.8-2.5z"
      />
      <path
        fill="#EA4335"
        d="M12 4.7c1.8 0 3 .8 3.7 1.4l3.3-3.2C17.9 1.1 15.2 0 12 0 7.4 0 3.5 2.7 1.4 6.7l3.8 2.9c1-2.9 3.7-4.9 6.8-4.9z"
      />
    </svg>
  )
}

function AppleMark(): React.JSX.Element {
  return (
    <svg width={17} height={17} viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" focusable="false">
      <path d="M17.05 12.54c0-2.4 1.96-3.55 2.05-3.6-1.12-1.64-2.86-1.86-3.48-1.89-1.48-.15-2.89.87-3.64.87-.75 0-1.9-.85-3.13-.83-1.61.02-3.1.94-3.93 2.38-1.68 2.9-.43 7.2 1.2 9.56.8 1.15 1.75 2.45 3 2.4 1.2-.05 1.66-.78 3.12-.78s1.87.78 3.14.75c1.3-.02 2.12-1.17 2.91-2.33.92-1.34 1.3-2.64 1.32-2.71-.03-.01-2.54-.97-2.56-3.82zM14.65 5.4c.66-.8 1.1-1.9 1.1-3.1-1.07.04-2.37.71-3.14 1.51-.69.8-1.3 1.9-1.13 3.1 1.19.09 2.4-.6 3.17-1.51z" />
    </svg>
  )
}

/**
 * The card's masthead: the Kalima mark and wordmark.
 *
 * The mark is the same asset the landing nav and the brand half use, so the
 * product is named by one file rather than three drawings of a logo. It is
 * `alt=""` because the wordmark beside it is the accessible name; announcing
 * both would read the brand twice.
 */
function CardBrand(): React.JSX.Element {
  return (
    <div className="k-auth-card-brand">
      <img src="/brand/kalima-mark-dark.svg" alt="" width={34} height={34} />
      <span className="k-auth-card-word">KALIMA</span>
    </div>
  )
}

export function AuthPage(): React.JSX.Element {
  const { t, dir, lang } = useLanguage()
  const { pathname, search } = useLocation()
  const navigate = useNavigate()
  const [searchParams, setSearchParams] = useSearchParams()

  const mode: Mode = pathname.startsWith('/signup') ? 'signup' : 'login'
  /** Where to go after a successful sign-in. Sanitised once, used everywhere. */
  const nextPath = useMemo(() => safeNextPath(searchParams.get('next')), [searchParams])

  const [view, setView] = useState<View>('form')
  const [method, setMethod] = useState<Method>('password')

  const [email, setEmail] = useState('')
  const [password, setPassword] = useState('')
  const [confirm, setConfirm] = useState('')
  const [displayName, setDisplayName] = useState('')
  const [showPassword, setShowPassword] = useState(false)
  const [code, setCode] = useState('')
  const [codeSent, setCodeSent] = useState(false)
  const [resetCode, setResetCode] = useState('')
  const [newPassword, setNewPassword] = useState('')

  /* null = still checking; neither button renders until the server says which
     providers are actually configured. */
  const [providers, setProviders] = useState<{ google: boolean; apple: boolean } | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [notice, setNotice] = useState<string | null>(null)
  const [busy, setBusy] = useState(false)
  const [sessions, setSessions] = useState<AuthSession[] | null>(null)
  /* undefined = still checking; null = no session; a user = signed in. */
  const [session, setSession] = useState<AuthUser | null | undefined>(undefined)

  const emailId = useFieldId('auth-email-')
  const nameId = useFieldId('auth-name-')
  const passwordId = useFieldId('auth-password-')
  const confirmId = useFieldId('auth-confirm-')
  const codeId = useFieldId('auth-code-')
  const resetCodeId = useFieldId('auth-reset-code-')
  const newPasswordId = useFieldId('auth-new-password-')

  /* The element whose height is animated when the card changes shape. */
  const bodyRef = useRef<HTMLDivElement>(null)
  const shape = `${mode}:${view}:${method}:${session === null ? 'anon' : 'known'}:${codeSent ? 'code' : 'nocode'}`
  useAnimatedHeight(bodyRef, shape)

  /* An OAuth failure lands back here as ?auth_error=: the backend owns the
     truth, so its message is shown once and cleared from the URL. */
  useEffect(() => {
    const failure = searchParams.get('auth_error')
    if (failure) {
      setError(failure)
      const rest = new URLSearchParams(searchParams)
      rest.delete('auth_error')
      setSearchParams(rest, { replace: true })
    }
  }, [searchParams, setSearchParams])

  /* Who is signed in. An active session does not get a login form: a form
     behind a live session is how "am I in or out?" confusion starts. It gets
     the session panel instead, with the way forward. */
  useEffect(() => {
    let cancelled = false
    void api
      .authMe()
      .then((me) => {
        if (!cancelled) setSession(me.user)
      })
      .catch(() => {
        if (!cancelled) setSession(null)
      })
    return () => {
      cancelled = true
    }
  }, [])

  useEffect(() => {
    if (session === undefined || session === null) {
      setSessions(null)
      return
    }
    let cancelled = false
    void api
      .authSessions()
      .then((response) => {
        if (!cancelled) setSessions(response.items)
      })
      .catch(() => {
        if (!cancelled) setSessions([])
      })
    return () => {
      cancelled = true
    }
  }, [session])

  /* Which social buttons may render. Unconfigured providers stay hidden: a
     button that can only fail is worse than none. Fail-closed to hidden when
     the status call itself fails. */
  useEffect(() => {
    if (session !== null) return
    let cancelled = false
    void api
      .authOAuthStatus()
      .then((status) => {
        if (!cancelled) setProviders({ google: status.google, apple: status.apple })
      })
      .catch(() => {
        if (!cancelled) setProviders({ google: false, apple: false })
      })
    return () => {
      cancelled = true
    }
  }, [session])

  const fail = useCallback(
    (failure: unknown) => {
      setError(failure instanceof ApiError ? failure.message : t('auth.serverError'))
    },
    [t],
  )

  /** Clear the banners whenever the user changes what they are doing. */
  function resetBanners(): void {
    setError(null)
    setNotice(null)
  }

  /**
   * Switch between login and signup by navigating, not by swapping local
   * state: the URL is the mode, so a refresh, a bookmark and the back button
   * all agree with what is on screen. `next` and the language survive.
   */
  function switchMode(target: Mode): void {
    if (target === mode) return
    resetBanners()
    setMethod('password')
    setView('form')
    const params = new URLSearchParams(search)
    params.delete('auth_error')
    const query = params.toString()
    navigate(`/${target}${query ? `?${query}` : ''}`, { replace: true })
  }

  function goAfterAuth(): void {
    navigate(nextPath ?? '/', { replace: true })
  }

  async function submit(event: React.FormEvent): Promise<void> {
    event.preventDefault()
    if (busy) return
    if (!validEmail(email)) {
      setError(t('auth.badEmail'))
      return
    }
    if (!validPassword(password)) {
      setError(t('auth.badPassword'))
      return
    }
    if (mode === 'signup') {
      if (!validDisplayName(displayName)) {
        setError(t('auth.badName'))
        return
      }
      if (password !== confirm) {
        setError(t('auth.mismatch'))
        return
      }
    }
    resetBanners()
    setBusy(true)
    try {
      const trimmed = email.trim()
      const response =
        mode === 'signup'
          ? await api.authSignup({ email: trimmed, password, display_name: displayName.trim() })
          : await api.authLogin({ email: trimmed, password })
      setSession(response.user)
      goAfterAuth()
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }

  async function sendCode(event: React.FormEvent): Promise<void> {
    event.preventDefault()
    if (busy) return
    if (!validEmail(email)) {
      setError(t('auth.badEmail'))
      return
    }
    resetBanners()
    setBusy(true)
    try {
      await api.authRequestEmailCode({ email: email.trim() })
      setCodeSent(true)
      setNotice(t('auth.codeSent'))
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }

  async function verifyCode(event: React.FormEvent): Promise<void> {
    event.preventDefault()
    if (busy) return
    if (!validEmail(email) || !validOtpCode(code)) {
      setError(!validEmail(email) ? t('auth.badEmail') : t('auth.badCode'))
      return
    }
    resetBanners()
    setBusy(true)
    try {
      const response = await api.authVerifyEmailCode({ email: email.trim(), code: code.trim() })
      setSession(response.user)
      goAfterAuth()
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }

  async function requestReset(event: React.FormEvent): Promise<void> {
    event.preventDefault()
    if (busy) return
    if (!validEmail(email)) {
      setError(t('auth.badEmail'))
      return
    }
    resetBanners()
    setBusy(true)
    try {
      await api.authRequestPasswordReset({ email: email.trim() })
      setView('reset-confirm')
      setNotice(t('auth.resetSent'))
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }

  async function confirmReset(event: React.FormEvent): Promise<void> {
    event.preventDefault()
    if (busy) return
    if (!validOtpCode(resetCode)) {
      setError(t('auth.resetBadCode'))
      return
    }
    if (!validPassword(newPassword)) {
      setError(t('auth.badPassword'))
      return
    }
    resetBanners()
    setBusy(true)
    try {
      await api.authResetPassword({
        email: email.trim(),
        code: resetCode.trim(),
        new_password: newPassword,
      })
      setView('form')
      setPassword('')
      setMethod('password')
      setNotice(t('auth.resetDone'))
    } catch (failure) {
      /* A wrong or expired code is the common case and the server's message
         for it is specific; anything else falls through to the generic path. */
      if (failure instanceof ApiError && failure.status === 401) {
        setError(t('auth.resetFailed'))
      } else {
        fail(failure)
      }
    } finally {
      setBusy(false)
    }
  }

  async function startOAuth(provider: 'google' | 'apple'): Promise<void> {
    if (busy) return
    resetBanners()
    setBusy(true)
    try {
      const started = await api.authOAuthStart(provider)
      window.location.href = started.auth_url
    } catch (failure) {
      if (failure instanceof ApiError && failure.status === 422) {
        setError(t('auth.oauthUnavailable'))
      } else {
        fail(failure)
      }
      setBusy(false)
    }
  }

  async function logout(): Promise<void> {
    setBusy(true)
    try {
      await api.authLogout()
    } catch {
      /* The cookie is cleared server-side on success; a network failure leaves
         it, and the next me-check reports the truth either way. */
    } finally {
      setSession(null)
      setSessions(null)
      setBusy(false)
    }
  }

  async function revokeOne(id: string): Promise<void> {
    if (busy) return
    resetBanners()
    setBusy(true)
    try {
      await api.authRevokeSession({ session_id: id })
      setSessions((items) => (items ?? []).filter((item) => item.id !== id))
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }

  async function revokeOthers(): Promise<void> {
    if (busy) return
    resetBanners()
    setBusy(true)
    try {
      const response = await api.authRevokeAll()
      setSessions((items) => (items ?? []).filter((item) => item.current))
      setNotice(t('auth.revokedClosed', { count: response.closed }))
    } catch (failure) {
      fail(failure)
    } finally {
      setBusy(false)
    }
  }

  /* ---- derived copy ------------------------------------------------- */

  const heading =
    view === 'reset-request'
      ? t('auth.resetTitle')
      : view === 'reset-confirm'
        ? t('auth.resetTitle')
        : method === 'code'
          ? t('auth.codeTitle')
          : mode === 'signup'
            ? t('auth.signupTitle')
            : t('auth.loginTitle')

  const subheading =
    view === 'reset-request' || view === 'reset-confirm'
      ? t('auth.resetSub')
      : method === 'code'
        ? t('auth.codeSub')
        : mode === 'signup'
          ? t('auth.signupSub')
          : t('auth.loginSub')

  const oauthCount = providers ? Number(providers.google) + Number(providers.apple) : 0

  /* The key that drives the form body's crossfade. It changes on every state
     the card can be in, so React swaps the subtree and the entrance animation
     runs once per change — which is the "two states of one card" transition. */
  const bodyKey = `${mode}:${view}:${method}:${codeSent ? 'sent' : 'idle'}`

  return (
    <div className="k-auth" lang={lang} dir={dir}>
      <main className="page k-auth-page">
        <div className="k-auth-utility">
          <Link to="/landing" className="k-auth-home">
            <ArrowLeftIcon size={15} />
            {t('auth.backHome')}
          </Link>
          <LandingLanguageSwitch t={t} />
        </div>

        <AuthCard>
          <div className="k-auth-card-inner" ref={bodyRef}>
            {session === undefined ? (
              /* Still asking the server who this is. A skeleton rather than a
                 form, because rendering a form to someone already signed in
                 and then replacing it is the flash this page exists to avoid. */
              <div
                className="k-auth-enter"
                role="status"
                aria-label={t('auth.checking')}
                style={{ height: 300 }}
              />
            ) : session !== null ? (
              <SessionPanel
                t={t}
                session={session}
                sessions={sessions}
                busy={busy}
                error={error}
                notice={notice}
                onLogout={() => void logout()}
                onRevokeOne={(id) => void revokeOne(id)}
                onRevokeOthers={() => void revokeOthers()}
                nextPath={nextPath}
              />
            ) : (
              <>
                <header className="k-auth-head">
                  <CardBrand />
                  <h1 className="k-auth-title">{heading}</h1>
                  <p className="k-auth-sub">{subheading}</p>
                </header>

                <div className="k-auth-body" key={bodyKey}>
                  {error !== null ? <AuthError message={error} /> : null}
                  {notice !== null ? <AuthNotice message={notice} /> : null}

                  {view === 'reset-request' ? (
                    <form className="k-auth-form" onSubmit={(event) => void requestReset(event)} noValidate>
                      <AuthField id={emailId} label={t('auth.email')} hint={t('auth.emailHint')}>
                        <AuthInput
                          id={emailId}
                          type="email"
                          dir="ltr"
                          inputMode="email"
                          autoComplete="email"
                          placeholder={t('auth.emailPh')}
                          value={email}
                          onChange={setEmail}
                          disabled={busy}
                        />
                      </AuthField>
                      <AuthSubmit
                        label={t('auth.resetSend')}
                        busy={busy}
                        busyLabel={t('auth.sending')}
                      />
                      <button
                        type="button"
                        className="k-auth-back"
                        onClick={() => {
                          resetBanners()
                          setView('form')
                        }}
                      >
                        <ArrowLeftIcon size={14} />
                        {t('auth.resetBack')}
                      </button>
                    </form>
                  ) : view === 'reset-confirm' ? (
                    <form className="k-auth-form" onSubmit={(event) => void confirmReset(event)} noValidate>
                      <AuthField id={resetCodeId} label={t('auth.resetCode')}>
                        <AuthInput
                          id={resetCodeId}
                          type="text"
                          dir="ltr"
                          inputMode="numeric"
                          autoComplete="one-time-code"
                          placeholder={t('auth.resetCodePh')}
                          value={resetCode}
                          onChange={setResetCode}
                          disabled={busy}
                        />
                      </AuthField>
                      <AuthPasswordField
                        id={newPasswordId}
                        label={t('auth.newPassword')}
                        value={newPassword}
                        onChange={setNewPassword}
                        t={t}
                        visible={showPassword}
                        onToggleVisible={() => setShowPassword((value) => !value)}
                        autoComplete="new-password"
                        disabled={busy}
                        showStrength
                      />
                      <AuthSubmit
                        label={t('auth.resetConfirm')}
                        busy={busy}
                        busyLabel={t('auth.sending')}
                      />
                      <button
                        type="button"
                        className="k-auth-back"
                        onClick={() => {
                          resetBanners()
                          setView('form')
                        }}
                      >
                        <ArrowLeftIcon size={14} />
                        {t('auth.resetBack')}
                      </button>
                    </form>
                  ) : method === 'password' ? (
                    <form className="k-auth-form" onSubmit={(event) => void submit(event)} noValidate>
                      <AuthField id={emailId} label={t('auth.email')}>
                        <AuthInput
                          id={emailId}
                          type="email"
                          dir="ltr"
                          inputMode="email"
                          autoComplete={mode === 'signup' ? 'email' : 'username'}
                          placeholder={t('auth.emailPh')}
                          value={email}
                          onChange={setEmail}
                          disabled={busy}
                        />
                      </AuthField>

                      {mode === 'signup' ? (
                        <AuthField id={nameId} label={t('auth.displayName')}>
                          <AuthInput
                            id={nameId}
                            type="text"
                            autoComplete="nickname"
                            placeholder={t('auth.namePh')}
                            value={displayName}
                            onChange={setDisplayName}
                            disabled={busy}
                          />
                        </AuthField>
                      ) : null}

                      <AuthPasswordField
                        id={passwordId}
                        label={t('auth.password')}
                        value={password}
                        onChange={setPassword}
                        t={t}
                        visible={showPassword}
                        onToggleVisible={() => setShowPassword((value) => !value)}
                        autoComplete={mode === 'signup' ? 'new-password' : 'current-password'}
                        disabled={busy}
                        showStrength={mode === 'signup'}
                        aside={
                          mode === 'login' ? (
                            <button
                              type="button"
                              onClick={() => {
                                resetBanners()
                                setView('reset-request')
                              }}
                            >
                              {t('auth.forgotPassword')}
                            </button>
                          ) : null
                        }
                      />

                      {mode === 'signup' ? (
                        <AuthPasswordField
                          id={confirmId}
                          label={t('auth.confirmPassword')}
                          value={confirm}
                          onChange={setConfirm}
                          t={t}
                          visible={showPassword}
                          onToggleVisible={() => setShowPassword((value) => !value)}
                          autoComplete="new-password"
                          disabled={busy}
                          error={
                            confirm.length > 0 && confirm !== password ? t('auth.mismatch') : null
                          }
                        />
                      ) : null}

                      <AuthSubmit
                        label={mode === 'signup' ? t('auth.submitSignup') : t('auth.submitLogin')}
                        busy={busy}
                        busyLabel={t('auth.sending')}
                      />
                    </form>
                  ) : (
                    <>
                      <form className="k-auth-form" onSubmit={(event) => void sendCode(event)} noValidate>
                        <AuthField id={emailId} label={t('auth.email')}>
                          <AuthInput
                            id={emailId}
                            type="email"
                            dir="ltr"
                            inputMode="email"
                            autoComplete="email"
                            placeholder={t('auth.emailPh')}
                            value={email}
                            onChange={setEmail}
                            disabled={busy}
                          />
                        </AuthField>
                        <AuthSubmit
                          label={t('auth.sendCode')}
                          busy={busy}
                          busyLabel={t('auth.sending')}
                        />
                      </form>
                      {codeSent ? (
                        <form
                          className="k-auth-form"
                          style={{ marginTop: '1.1rem' }}
                          onSubmit={(event) => void verifyCode(event)}
                          noValidate
                        >
                          <AuthField id={codeId} label={t('auth.code')}>
                            <AuthInput
                              id={codeId}
                              type="text"
                              dir="ltr"
                              inputMode="numeric"
                              autoComplete="one-time-code"
                              placeholder={t('auth.codePh')}
                              value={code}
                              onChange={setCode}
                              disabled={busy}
                            />
                          </AuthField>
                          <AuthSubmit
                            label={t('auth.verifyCode')}
                            busy={busy}
                            busyLabel={t('auth.sending')}
                          />
                        </form>
                      ) : null}
                    </>
                  )}

                  {/* OAuth and the method switch are for the credential form
                      only: offering "continue with Google" beside a reset code
                      field would be a different flow wearing the same panel. */}
                  {view === 'form' ? (
                    <>
                      {providers !== null && oauthCount > 0 ? (
                        <>
                          <p className="k-auth-divider">{t('auth.orDivider')}</p>
                          <div className="k-auth-oauth" data-count={oauthCount}>
                            {providers.google ? (
                              <button
                                type="button"
                                className="k-auth-oauth-btn"
                                disabled={busy}
                                onClick={() => void startOAuth('google')}
                              >
                                <GoogleMark />
                                {t('auth.google')}
                              </button>
                            ) : null}
                            {providers.apple ? (
                              <button
                                type="button"
                                className="k-auth-oauth-btn"
                                disabled={busy}
                                onClick={() => void startOAuth('apple')}
                              >
                                <AppleMark />
                                {t('auth.apple')}
                              </button>
                            ) : null}
                          </div>
                        </>
                      ) : null}

                      <p className="k-auth-alt">
                        {method === 'password' ? (
                          <>
                            {mode === 'signup' ? t('auth.haveAccount') : t('auth.noAccount')}{' '}
                            <button
                              type="button"
                              onClick={() => switchMode(mode === 'signup' ? 'login' : 'signup')}
                            >
                              {mode === 'signup' ? t('auth.loginTab') : t('auth.signupTab')}
                            </button>
                          </>
                        ) : (
                          <button
                            type="button"
                            onClick={() => {
                              resetBanners()
                              setMethod('password')
                              setCodeSent(false)
                            }}
                          >
                            {t('auth.passwordTab')}
                          </button>
                        )}
                      </p>

                      {method === 'password' ? (
                        <p className="k-auth-alt k-auth-alt-tight">
                          <button
                            type="button"
                            onClick={() => {
                              resetBanners()
                              setMethod('code')
                              setCodeSent(false)
                            }}
                          >
                            {t('auth.codeTab')}
                          </button>
                        </p>
                      ) : null}

                      {mode === 'signup' ? (
                        <p className="k-auth-terms">{t('auth.termsNote')}</p>
                      ) : null}
                    </>
                  ) : null}
                </div>
              </>
            )}
          </div>
        </AuthCard>

        <p className="k-auth-tagline">{t('auth.brandFoot')}</p>
      </main>
    </div>
  )
}

/**
 * The already-signed-in panel.
 *
 * Reached by landing on /login or /signup with a live cookie — a stale
 * bookmark, the back button, or a link from an email. It shows who is signed
 * in, the way forward, and the signed-in devices with revoke, because that is
 * the leaked-cookie recovery path and this is where someone looks for it.
 */
function SessionPanel({
  t,
  session,
  sessions,
  busy,
  error,
  notice,
  onLogout,
  onRevokeOne,
  onRevokeOthers,
  nextPath,
}: {
  t: T
  session: AuthUser
  sessions: AuthSession[] | null
  busy: boolean
  error: string | null
  notice: string | null
  onLogout: () => void
  onRevokeOne: (id: string) => void
  onRevokeOthers: () => void
  nextPath: string | null
}): React.JSX.Element {
  return (
    <div className="k-auth-session k-auth-enter">
      <header className="k-auth-head">
        <CardBrand />
        <h1 className="k-auth-title">{t('auth.sessionTitle')}</h1>
        <p className="k-auth-sub">{t('auth.sessionsSub')}</p>
      </header>

      {error !== null ? <AuthError message={error} /> : null}
      {notice !== null ? <AuthNotice message={notice} /> : null}

      <div className="k-auth-session-card">
        <div className="k-auth-session-who">
          <span className="k-auth-session-name">{session.display_name}</span>
          <span className="k-auth-session-email" dir="ltr">
            {session.email}
          </span>
        </div>
      </div>

      <div className="k-auth-actions">
        <Link to={nextPath ?? '/'} className="k-auth-submit k-auth-submit-inline">
          {t('auth.dashboard')}
        </Link>
        <button type="button" className="k-auth-btn-secondary" disabled={busy} onClick={onLogout}>
          {t('auth.logout')}
        </button>
      </div>

      <div>
        <h2 className="k-auth-label k-auth-label-block">{t('auth.sessionsTitle')}</h2>
        {sessions === null ? (
          <div role="status" aria-label={t('auth.checking')} style={{ height: 56 }} />
        ) : sessions.length === 0 ? null : (
          <ul className="k-auth-session-list">
            {sessions.map((item) => (
              <li key={item.id} className="k-auth-session-row">
                <span className="k-auth-session-id" dir="ltr">
                  {item.id}
                </span>
                {item.current ? (
                  <span className="k-auth-session-current">{t('auth.currentDevice')}</span>
                ) : (
                  <button
                    type="button"
                    className="k-auth-btn-secondary k-auth-btn-compact"
                    disabled={busy}
                    onClick={() => onRevokeOne(item.id)}
                  >
                    {t('auth.revoke')}
                  </button>
                )}
              </li>
            ))}
          </ul>
        )}
        <button
          type="button"
          className="k-auth-btn-secondary k-auth-revoke-all"
          disabled={busy}
          onClick={onRevokeOthers}
        >
          {t('auth.revokeAll')}
        </button>
      </div>
    </div>
  )
}
