import { useEffect, useId, useMemo, useRef, useState } from 'react'
import type { FormEvent, ReactNode } from 'react'
import { Link } from 'react-router-dom'
import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'
import {
  api,
  ApiError,
  type AccountPortal,
  type CreatedApiKey,
  type MarketplaceItem,
  type PortalAccount,
  type PortalApiKey,
  type ProviderConfig,
  type ProviderTestResult,
  type PublisherOverview,
} from '@/lib/api'
import { validPassword, type AuthEvent, type AuthSession } from '@/lib/auth.ts'
import { fa, faAgo, faDate, maskSecretLike, serverError } from '@/lib/format'
import { useTheme } from '@/hooks/useTheme'
import { useLanguage } from '@/i18n/useLanguage.ts'
import type { StringKey } from '@/i18n/fa.ts'
import { Glyph, type GlyphName } from '@/components/Glyph'
import {
  fillReadingSeries,
  initials,
  nextAction,
  readinessChecklist,
  readinessPercent,
  type NextActionId,
  type ReadinessId,
  type ReadinessItem,
} from '@/lib/account.ts'
import './account.css'

/**
 * Account and settings.
 *
 * ## What this page is for
 *
 * The earlier version answered "is my setup working?" and "what have I done?"
 * with a stack of equal-weight cards, so the one thing a reader needs next was
 * never at the top. This version is a console: an identity band that states who
 * you are and how complete the account is, one recommendation, then the facts.
 *
 *   1. **Who and how ready.** The band carries the name, plan, credits and a
 *      readiness ring computed from durable facts -- not from a test that
 *      resets on reload.
 *   2. **What to do next.** One action, chosen by priority: a missing key
 *      blocks everything, an empty library is the real next step, running work
 *      outranks reading because it changes on its own.
 *   3. **What is true.** Figures, an editable profile, reading activity, the
 *      provider test, usage, security, keys and packs.
 *
 * ## What it still refuses to show
 *
 * - **Transactions and credit packages.** A table of permanently-pending
 *   orders for a checkout that does not exist teaches distrust. The plan and
 *   the credit balance are facts, so they stay; the catalogue does not.
 * - **Token usage and estimated cost.** The provider layer does not persist
 *   them, so `0` would read as "free". The usage card says so in words.
 * - **A provider test result from a previous visit.** It is a session event,
 *   not a stored fact, so it is never presented as a durable green tick.
 *
 * ## New here
 *
 * - **Editable profile.** `PUT /api/account` already accepted display name,
 *   email, organization and locale; the page only displayed them. Saving the
 *   locale also switches the interface, because the server stores it.
 * - **Readiness checklist** with a ring, and a next-step CTA in the band.
 * - **Reading activity** from `GET /api/reading/stats`: streak, pages, and a
 *   dense 30-day window. The endpoint omits empty days, so the series is
 *   rebuilt from the calendar -- otherwise three days of reading would look
 *   like a month.
 * - **Backup facts** from the portal's `backup` block, shown as counts rather
 *   than as a download button this page cannot honour for non-admins.
 */

/* ------------------------------------------------------------------ */
/* Dictionary maps for values the backend names in Latin               */
/* ------------------------------------------------------------------ */

const KIND_KEY: Record<string, StringKey> = {
  glossary: 'account.packs.kind.glossary',
  preset: 'account.packs.kind.preset',
  style: 'account.packs.kind.style',
  template: 'account.packs.kind.template',
  model: 'account.packs.kind.model',
}

const kindLabel = (t: (key: StringKey) => string, kind: string): string => {
  const key = KIND_KEY[kind]
  return key ? t(key) : kind
}

const SCOPE_KEY: Record<string, StringKey> = {
  'translate:write': 'account.keys.scope.translate_write',
  'jobs:read': 'account.keys.scope.jobs_read',
}

const scopeLabel = (t: (key: StringKey) => string, scope: string): string => {
  const key = SCOPE_KEY[scope]
  return key ? t(key) : scope
}

const EVENT_KEY: Record<string, StringKey> = {
  login: 'account.security.event.login',
  logout: 'account.security.event.logout',
  login_failed: 'account.security.event.login_failed',
  password_changed: 'account.security.event.password_changed',
  session_revoked: 'account.security.event.session_revoked',
  sessions_revoked: 'account.security.event.sessions_revoked',
}

const METHOD_KEY: Record<string, StringKey> = {
  password: 'account.security.method.password',
  'email-code': 'account.security.method.email-code',
  google: 'account.security.method.google',
  apple: 'account.security.method.apple',
}

const eventLabel = (t: (key: StringKey) => string, event: string): string => {
  const key = EVENT_KEY[event]
  return key ? t(key) : event
}

const READINESS_KEY: Record<ReadinessId, { title: StringKey; hint: StringKey }> = {
  provider: { title: 'account.readiness.provider', hint: 'account.readiness.providerHint' },
  book: { title: 'account.readiness.book', hint: 'account.readiness.bookHint' },
  translation: { title: 'account.readiness.translation', hint: 'account.readiness.translationHint' },
  glossary: { title: 'account.readiness.glossary', hint: 'account.readiness.glossaryHint' },
  memory: { title: 'account.readiness.memory', hint: 'account.readiness.memoryHint' },
}

const NEXT_KEY: Record<NextActionId, { cta: StringKey; hint: StringKey }> = {
  provider: { cta: 'account.next.cta.provider', hint: 'account.next.providerHint' },
  upload: { cta: 'account.next.cta.upload', hint: 'account.next.uploadHint' },
  monitor: { cta: 'account.next.cta.monitor', hint: 'account.next.monitorHint' },
  read: { cta: 'account.next.cta.read', hint: 'account.next.readHint' },
}

/** Human line for the audit detail: a method, a closed-session count, or raw. */
function eventDetail(
  t: (key: StringKey, vars?: Record<string, string | number>) => string,
  entry: AuthEvent,
): string {
  if (entry.event === 'login' || entry.event === 'login_failed') {
    const key = METHOD_KEY[entry.detail]
    return key ? t(key) : entry.detail
  }
  if (entry.event === 'sessions_revoked' && /^\d+$/.test(entry.detail)) {
    return t('account.security.sessionsCount', { count: fa(Number(entry.detail)) })
  }
  return entry.detail
}

/* ------------------------------------------------------------------ */
/* Small pieces                                                        */
/* ------------------------------------------------------------------ */

function Section({
  id,
  icon,
  title,
  action,
  note,
  children,
}: {
  id: string
  icon: GlyphName
  title: string
  action?: ReactNode | undefined
  note?: string | undefined
  children: ReactNode
}) {
  return (
    <section id={id} className="surface-card acc-section p-5" aria-labelledby={`${id}-heading`}>
      <div className="acc-section-head">
        <h2 id={`${id}-heading`} className="acc-h2">
          <Glyph name={icon} size={18} />
          {title}
        </h2>
        {action}
      </div>
      {children}
      {note ? <p className="acc-note">{note}</p> : null}
    </section>
  )
}

function Readout({ label, value }: { label: string; value: string }) {
  return (
    <div className="acc-readout">
      <span className="data-label">{label}</span>
      {/* `break-all` rather than truncate: a base URL or a token prefix that
          gets ellipsised is worse than one that wraps, because the reader cannot
          tell how much is missing. */}
      <strong className="data-value break-all" title={value}>
        {value}
      </strong>
    </div>
  )
}

function ReadinessRing({ percent, caption }: { percent: number; caption: string }) {
  const { t } = useLanguage()
  const radius = 38
  const circumference = 2 * Math.PI * radius
  const offset = circumference * (1 - Math.min(100, Math.max(0, percent)) / 100)
  return (
    <div className="acc-ring-wrap">
      <svg
        className="acc-ring"
        viewBox="0 0 96 96"
        role="img"
        aria-label={t('account.readiness.aria', { percent: fa(percent) })}
      >
        <circle className="acc-ring-track" cx="48" cy="48" r={radius} fill="none" strokeWidth="7" />
        <circle
          className="acc-ring-value"
          cx="48"
          cy="48"
          r={radius}
          fill="none"
          strokeWidth="7"
          strokeLinecap="round"
          strokeDasharray={circumference}
          strokeDashoffset={offset}
          transform="rotate(-90 48 48)"
        />
        <text className="acc-ring-label" x="48" y="54">
          {t('account.ring.percent', { percent: fa(percent) })}
        </text>
      </svg>
      <span className="acc-ring-caption">{caption}</span>
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Identity band                                                       */
/* ------------------------------------------------------------------ */

function Hero({
  portal,
  readiness,
  hasKey,
}: {
  portal: AccountPortal
  readiness: ReadinessItem[]
  hasKey: boolean | null
}) {
  const { t, lang } = useLanguage()
  const { account, plan } = portal.overview
  const name = account.display_name || t('account.work.localUser')
  const percent = readinessPercent(readiness)
  const action = nextAction({
    hasKey,
    books: portal.overview.counts.books,
    activeProjects: portal.publisher?.active_projects ?? 0,
    completedJobs: portal.overview.counts.completed_jobs,
  })

  return (
    <section id="acc-top" className="acc-hero acc-section" aria-labelledby="acc-hero-name">
      <div className="acc-hero-main">
        <div className="acc-avatar" aria-hidden="true">
          {initials(name)}
        </div>
        <div className="min-w-0">
          <p className="acc-hero-eyebrow">{t('account.hero.greeting', { name })}</p>
          <h1 id="acc-hero-name" className="acc-hero-name">
            {name}
          </h1>
          <p className="acc-hero-meta">{account.email || t('account.hero.noEmail')}</p>
          <div className="acc-hero-badges">
            <span className="badge">{lang === 'fa' ? plan.name_fa : plan.name_en}</span>
            <span className="badge">
              {t('account.hero.memberSince', { date: faDate(account.created_at) })}
            </span>
            <span className="badge">
              {t('account.hero.credits', { count: fa(account.credit_balance) })}
            </span>
          </div>
        </div>
      </div>
      <div className="acc-hero-side">
        <ReadinessRing percent={percent} caption={t('account.readiness.short')} />
        <div className="acc-hero-cta">
          <div className="acc-hero-actions">
            <Link to={action.to} className="btn acc-hero-primary">
              {t(NEXT_KEY[action.id].cta)}
              <Glyph name="arrow" size={16} className="acc-arrow" />
            </Link>
            <Link to="/settings" className="btn btn-secondary">
              {t('account.hero.settings')}
            </Link>
          </div>
          <p className="acc-hero-hint">{t(NEXT_KEY[action.id].hint)}</p>
        </div>
      </div>
    </section>
  )
}

const JUMP: ReadonlyArray<{ id: string; key: StringKey }> = [
  { id: 'acc-top', key: 'account.jump.overview' },
  { id: 'readiness', key: 'account.jump.readiness' },
  { id: 'profile', key: 'account.jump.profile' },
  { id: 'activity', key: 'account.jump.activity' },
  { id: 'security', key: 'account.jump.security' },
  { id: 'keys', key: 'account.jump.keys' },
  { id: 'packs', key: 'account.jump.packs' },
  { id: 'publisher', key: 'account.jump.publisher' },
  { id: 'appearance', key: 'account.jump.appearance' },
]

function JumpNav({ available }: { available: ReadonlySet<string> }) {
  const { t } = useLanguage()
  return (
    <nav className="acc-jump" aria-label={t('account.jump.label')}>
      {JUMP.filter((item) => available.has(item.id)).map((item) => (
        <a key={item.id} href={`#${item.id}`}>
          {t(item.key)}
        </a>
      ))}
    </nav>
  )
}

/* ------------------------------------------------------------------ */
/* Readiness                                                           */
/* ------------------------------------------------------------------ */

function ReadinessPanel({ items }: { items: ReadinessItem[] }) {
  const { t } = useLanguage()
  const done = items.filter((item) => item.done).length
  return (
    <Section
      id="readiness"
      icon="spark"
      title={t('account.readiness.title')}
      action={
        <span className="badge">
          {t('account.readiness.percent', { done: fa(done), total: fa(items.length) })}
        </span>
      }
      note={t('account.readiness.note')}
    >
      <div className="acc-readiness">
        <ReadinessRing percent={readinessPercent(items)} caption={t('account.readiness.short')} />
        <ul className="acc-check">
          {items.map((item) => {
            const keys = READINESS_KEY[item.id]
            return (
              <li key={item.id} className="acc-check-item" data-done={item.done}>
                <span className="acc-check-mark" aria-hidden="true">
                  {item.done ? <Glyph name="check" size={14} /> : null}
                </span>
                <div className="acc-check-body">
                  <span className="acc-check-title">{t(keys.title)}</span>
                  <span className="acc-check-hint">{t(keys.hint)}</span>
                </div>
                {item.done ? (
                  <span className="badge badge-success">{t('account.readiness.done')}</span>
                ) : (
                  <Link to={item.to} className="btn btn-ghost">
                    {t('account.readiness.do')}
                  </Link>
                )}
              </li>
            )
          })}
        </ul>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Figures                                                             */
/* ------------------------------------------------------------------ */

function Tile({
  to,
  label,
  value,
  hint,
}: {
  to: string
  label: string
  value: number
  hint: string
}) {
  return (
    <Link to={to} className="acc-tile">
      <span className="acc-tile-edge" aria-hidden="true" />
      <span className="acc-tile-label">{label}</span>
      <strong className="acc-tile-value">{fa(value)}</strong>
      <span className="acc-tile-hint">{hint}</span>
    </Link>
  )
}

function Tiles({ portal }: { portal: AccountPortal }) {
  const { t } = useLanguage()
  const { counts } = portal.overview
  return (
    <div className="acc-tiles">
      <Tile
        to="/library"
        label={t('account.work.books')}
        value={counts.books}
        hint={t('account.tiles.booksHint')}
      />
      <Tile
        to="/jobs"
        label={t('account.work.jobs')}
        value={counts.jobs}
        hint={t('account.tiles.jobsHint')}
      />
      <Tile
        to="/jobs"
        label={t('account.work.done')}
        value={counts.completed_jobs}
        hint={t('account.tiles.doneHint')}
      />
      <Tile
        to="/library"
        label={t('account.work.glossaries')}
        value={counts.glossaries}
        hint={t('account.tiles.glossariesHint')}
      />
    </div>
  )
}

/* ------------------------------------------------------------------ */
/* Profile                                                             */
/* ------------------------------------------------------------------ */

function ProfilePanel({ account }: { account: PortalAccount }) {
  const { t, setLang } = useLanguage()
  const cache = useQueryClient()
  const [displayName, setDisplayName] = useState(account.display_name)
  const [email, setEmail] = useState(account.email)
  const [organization, setOrganization] = useState(account.organization)
  const [locale, setLocale] = useState<'fa' | 'en'>(account.locale === 'en' ? 'en' : 'fa')
  const [formError, setFormError] = useState<string | null>(null)

  // The server is the source of truth: after a save the portal refetches, and
  // the form follows the stored row rather than keeping a stale local copy.
  useEffect(() => {
    setDisplayName(account.display_name)
    setEmail(account.email)
    setOrganization(account.organization)
    setLocale(account.locale === 'en' ? 'en' : 'fa')
  }, [account.display_name, account.email, account.organization, account.locale])

  const save = useMutation({
    mutationFn: () =>
      api.updateAccount({
        display_name: displayName.trim(),
        email: email.trim(),
        organization: organization.trim(),
        locale,
      }),
    onSuccess: (next) => {
      setFormError(null)
      setLang(next.locale === 'en' ? 'en' : 'fa')
      void cache.invalidateQueries({ queryKey: ['portal'] })
    },
  })

  function submit(event: FormEvent): void {
    event.preventDefault()
    if (save.isPending) return
    if (!displayName.trim()) {
      setFormError(t('account.profile.nameRequired'))
      return
    }
    setFormError(null)
    save.mutate()
  }

  return (
    <Section
      id="profile"
      icon="user"
      title={t('account.profile.title')}
      note={t('account.profile.note')}
    >
      <form className="acc-form-grid" onSubmit={submit}>
        <label className="acc-field">
          <span className="label">{t('account.profile.name')}</span>
          <input
            className="field"
            value={displayName}
            onChange={(event) => setDisplayName(event.target.value)}
            autoComplete="name"
            maxLength={100}
          />
        </label>
        <label className="acc-field">
          <span className="label">{t('account.profile.email')}</span>
          <input
            className="field"
            type="email"
            dir="ltr"
            value={email}
            onChange={(event) => setEmail(event.target.value)}
            autoComplete="email"
            maxLength={180}
          />
        </label>
        <label className="acc-field">
          <span className="label">{t('account.profile.organization')}</span>
          <input
            className="field"
            value={organization}
            onChange={(event) => setOrganization(event.target.value)}
            autoComplete="organization"
            maxLength={160}
          />
        </label>
        <label className="acc-field">
          <span className="label">{t('account.profile.locale')}</span>
          <select
            className="field"
            value={locale}
            onChange={(event) => setLocale(event.target.value === 'en' ? 'en' : 'fa')}
          >
            <option value="fa">{t('account.profile.localeFa')}</option>
            <option value="en">{t('account.profile.localeEn')}</option>
          </select>
        </label>
        <div className="acc-field-wide acc-form-actions">
          <button type="submit" className="btn btn-primary" disabled={save.isPending}>
            {save.isPending ? t('account.profile.saving') : t('account.profile.save')}
          </button>
          {formError ? (
            <p role="alert" className="alert alert-error">
              {formError}
            </p>
          ) : null}
          {save.isError ? (
            <p role="alert" className="alert alert-error">
              {save.error instanceof Error ? save.error.message : t('account.profile.failed')}
            </p>
          ) : null}
          {save.isSuccess ? (
            <p role="status" className="alert alert-success">
              {t('account.profile.saved')}
            </p>
          ) : null}
        </div>
      </form>
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Reading activity                                                    */
/* ------------------------------------------------------------------ */

/**
 * A daily reading goal, stored in this browser.
 *
 * There is no per-user settings row for a reader goal yet, so this is a client
 * preference (`localStorage`), not a server fact -- and it is labelled as such
 * rather than pretending to sync. `today` is the last point of the 30-day
 * series, so the bar reflects real pages read today.
 */
const READING_GOAL_KEY = 'kalima-reading-goal'

function readStoredGoal(): number {
  try {
    const value = Number(localStorage.getItem(READING_GOAL_KEY))
    return Number.isFinite(value) && value > 0 ? Math.round(value) : 0
  } catch {
    return 0
  }
}

function ReadingGoal({ today }: { today: number }) {
  const { t } = useLanguage()
  const [goal, setGoal] = useState<number>(readStoredGoal)
  const [draft, setDraft] = useState<string>(() => {
    const stored = readStoredGoal()
    return stored > 0 ? String(stored) : ''
  })

  function save(event: FormEvent): void {
    event.preventDefault()
    const value = Math.max(0, Math.round(Number(draft) || 0))
    setGoal(value)
    try {
      if (value > 0) localStorage.setItem(READING_GOAL_KEY, String(value))
      else localStorage.removeItem(READING_GOAL_KEY)
    } catch {
      /* Private mode: the goal simply will not persist; the bar still works. */
    }
  }

  const pct = goal > 0 ? Math.min(100, Math.round((today / goal) * 100)) : 0

  return (
    <form className="acc-goal" onSubmit={save}>
      <div className="acc-goal-head">
        <span className="acc-goal-label">{t('account.goal.label')}</span>
        {goal > 0 ? (
          <span className="acc-goal-count" dir="ltr">
            {fa(today)} / {fa(goal)}
          </span>
        ) : null}
      </div>
      {goal > 0 ? (
        <div
          className="acc-goal-track"
          role="progressbar"
          aria-valuemin={0}
          aria-valuemax={goal}
          aria-valuenow={Math.min(today, goal)}
          aria-label={t('account.goal.aria')}
        >
          <span className="acc-goal-fill" style={{ width: `${pct}%` }} data-done={today >= goal} />
        </div>
      ) : (
        <p className="acc-goal-hint">{t('account.goal.hint')}</p>
      )}
      <div className="acc-goal-form">
        <label className="sr-only" htmlFor="reading-goal-input">
          {t('account.goal.input')}
        </label>
        <input
          id="reading-goal-input"
          className="field"
          type="number"
          min={0}
          inputMode="numeric"
          value={draft}
          onChange={(event) => setDraft(event.target.value)}
          placeholder={t('account.goal.placeholder')}
        />
        <button type="submit" className="btn btn-secondary">
          {t('account.goal.save')}
        </button>
      </div>
    </form>
  )
}

function ActivityPanel() {
  const { t } = useLanguage()
  const stats = useQuery({
    queryKey: ['reading-stats', 30],
    queryFn: () => api.readingStats(30),
    staleTime: 60_000,
  })

  const series = useMemo(() => {
    const today = new Date().toISOString().slice(0, 10)
    return fillReadingSeries(stats.data?.per_day ?? [], 30, today)
  }, [stats.data])

  if (stats.isPending) {
    return (
      <Section id="activity" icon="activity" title={t('account.activity.title')}>
        <div className="skeleton" style={{ height: 96 }} />
      </Section>
    )
  }

  if (stats.isError) {
    return (
      <Section id="activity" icon="activity" title={t('account.activity.title')}>
        <p role="alert" className="alert alert-error">
          {stats.error instanceof Error ? stats.error.message : t('account.activity.failed')}
        </p>
      </Section>
    )
  }

  const data = stats.data
  if (!data) return null
  const max = Math.max(1, ...series.map((entry) => entry.pages))
  const activeDays = series.filter((entry) => entry.pages > 0)

  return (
    <Section
      id="activity"
      icon="activity"
      title={t('account.activity.title')}
      action={
        <span className="badge badge-accent">
          <Glyph name="flame" size={13} />
          {t('account.activity.streak', { count: fa(data.streak_days) })}
        </span>
      }
    >
      <div className="acc-activity-top">
        <div className="acc-activity-figure">
          <strong>{fa(data.total_pages)}</strong>
          <span>{t('account.activity.pages', { days: fa(30) })}</span>
        </div>
        <div className="acc-activity-figure">
          <strong>{fa(data.avg_per_day)}</strong>
          <span>{t('account.activity.avg')}</span>
        </div>
      </div>

      <ReadingGoal today={series[series.length - 1]?.pages ?? 0} />

      {data.total_pages === 0 ? (
        <p className="empty">{t('account.activity.empty')}</p>
      ) : (
        <>
          <div
            className="acc-spark"
            role="img"
            aria-label={t('account.activity.aria', {
              days: fa(30),
              total: fa(data.total_pages),
            })}
          >
            {series.map((entry) => (
              <span
                key={entry.day}
                className="acc-spark-bar"
                data-active={entry.pages > 0}
                style={{ height: `${Math.round((entry.pages / max) * 100)}%` }}
                aria-hidden="true"
              />
            ))}
          </div>
          <details className="acc-details">
            <summary>{t('account.activity.details')}</summary>
            <table className="acc-table">
              <thead>
                <tr>
                  <th scope="col">{t('account.activity.day')}</th>
                  <th scope="col">{t('account.activity.pagesCol')}</th>
                </tr>
              </thead>
              <tbody>
                {activeDays.map((entry) => (
                  <tr key={entry.day}>
                    <td dir="ltr" className="chunk-id">
                      {entry.day}
                    </td>
                    <td>{fa(entry.pages)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </details>
        </>
      )}
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Setup                                                               */
/* ------------------------------------------------------------------ */

function ProviderTest({ config }: { config: ProviderConfig | undefined }) {
  const { t } = useLanguage()
  const test = useMutation<ProviderTestResult>({
    mutationFn: () => api.testProvider(),
  })

  const result = test.data
  const failed = test.isError

  return (
    <div className="mt-4 flex flex-wrap items-center gap-3">
      <button
        type="button"
        className="btn btn-secondary"
        onClick={() => test.mutate()}
        disabled={test.isPending || !config?.has_api_key}
        aria-describedby="provider-test-result"
      >
        {test.isPending ? t('account.test.running') : t('account.test.run')}
      </button>

      {test.isPending ? <span className="skeleton h-5 w-40" aria-hidden="true" /> : null}

      {result && !failed ? (
        <p
          id="provider-test-result"
          role="status"
          className={result.model_available === false ? 'alert alert-warning' : 'alert alert-success'}
        >
          {serverError(result.message)}
          {result.model_available === false
            ? t('account.test.modelMissing', { model: result.selected_model })
            : ''}
        </p>
      ) : null}

      {failed ? (
        <p id="provider-test-result" role="alert" className="alert alert-error">
          {test.error instanceof Error ? test.error.message : t('account.test.failed')}
        </p>
      ) : null}
    </div>
  )
}

function SetupPanel({ config }: { config: ProviderConfig | undefined }) {
  const { t } = useLanguage()
  const hasKey = config?.has_api_key ?? false

  return (
    <Section
      id="setup"
      icon="settings"
      title={t('account.setup.title')}
      action={
        config ? (
          <span className={hasKey ? 'badge badge-success' : 'badge badge-warning'}>
            {hasKey ? t('account.setup.keySet') : t('account.setup.keyUnset')}
          </span>
        ) : null
      }
      note={hasKey ? t('account.setup.note') : undefined}
    >
      <div className="acc-readouts">
        <Readout label={t('account.setup.baseUrl')} value={config?.base_url ?? '—'} />
        <Readout label={t('account.setup.model')} value={config?.default_model ?? '—'} />
        <Readout
          label={t('account.setup.apiKey')}
          value={hasKey ? t('account.setup.keySet') : t('account.setup.keyUnset')}
        />
        <Readout
          label={t('account.setup.concurrency')}
          value={config ? fa(config.max_concurrency) : '—'}
        />
      </div>

      {hasKey ? (
        <ProviderTest config={config} />
      ) : (
        <p className="alert alert-warning mt-4">
          {t('account.setup.noKey', { file: 'config/config.yaml' })}
        </p>
      )}
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Usage                                                               */
/* ------------------------------------------------------------------ */

function UsagePanel({ counts }: { counts: AccountPortal['overview']['counts'] }) {
  const { t } = useLanguage()
  const analytics = useQuery({
    queryKey: ['analytics'],
    queryFn: api.analytics,
    staleTime: 60_000,
  })

  // Never a silent `null`: an empty panel while loading or failed reads as
  // "there is no usage section", not as "it is still coming".
  if (analytics.isPending) {
    return (
      <Section id="usage" icon="chart" title={t('account.usage.title')}>
        <div className="skeleton" style={{ height: 72 }} />
      </Section>
    )
  }

  if (analytics.isError) {
    return (
      <Section id="usage" icon="chart" title={t('account.usage.title')}>
        <p role="alert" className="alert alert-error">
          {analytics.error instanceof Error ? analytics.error.message : t('account.usage.failed')}
        </p>
      </Section>
    )
  }

  const data = analytics.data
  // Unreachable while the query is enabled (pending and error return above),
  // kept so the type stays honest instead of asserting non-null.
  if (!data) return null

  return (
    <Section id="usage" icon="chart" title={t('account.usage.title')}>
      <div className="acc-readouts">
        <Readout label={t('account.usage.chunks')} value={fa(data.completed_chunks)} />
        <Readout label={t('account.usage.retries')} value={fa(data.retries)} />
        <Readout label={t('account.usage.memory')} value={fa(counts.memory_entries)} />
        <Readout label={t('account.usage.apiKeys')} value={fa(counts.api_keys)} />
      </div>
      <p className="acc-note">{t('account.usage.note')}</p>
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Publisher overview                                                  */
/* ------------------------------------------------------------------ */

function PublisherPanel({ publisher }: { publisher: PublisherOverview | undefined }) {
  const { t } = useLanguage()
  if (!publisher) return null
  const languages = (publisher.languages ?? []).slice(0, 4)
  return (
    <Section
      id="publisher"
      icon="building"
      title={t('account.publisher.title')}
      note={t('account.publisher.note')}
    >
      <div className="acc-readouts">
        <Readout label={t('account.publisher.books')} value={fa(publisher.books)} />
        <Readout label={t('account.publisher.active')} value={fa(publisher.active_projects)} />
        <Readout label={t('account.publisher.delivered')} value={fa(publisher.delivered)} />
        <Readout
          label={t('account.publisher.spend')}
          value={`$${publisher.estimated_spend.toFixed(2)}`}
        />
      </div>
      {languages.length > 0 ? (
        <div className="acc-langs">
          <span className="data-label">{t('account.publisher.languages')}</span>
          <ul className="acc-lang-list">
            {languages.map((entry) => (
              <li key={entry.language || 'unknown'} className="acc-lang">
                <span dir="ltr" className="chunk-id">
                  {entry.language || '—'}
                </span>
                <span className="acc-lang-count">{fa(entry.jobs)}</span>
              </li>
            ))}
          </ul>
        </div>
      ) : null}
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Appearance                                                          */
/* ------------------------------------------------------------------ */

function AppearancePanel() {
  const { t } = useLanguage()
  const { theme, setTheme, followsSystem } = useTheme()
  return (
    <Section id="appearance" icon="sun" title={t('account.theme.title')}>
      <fieldset className="grid gap-2">
        <legend className="sr-only">{t('account.theme.legend')}</legend>
        {(
          [
            ['light', t('account.theme.light'), 'sun'],
            ['dark', t('account.theme.dark'), 'moon'],
          ] as const
        ).map(([value, label, icon]) => (
          <label
            key={value}
            className="flex items-center justify-between gap-3 rounded-[var(--radius-control)] border p-[var(--spacing-3)] text-[length:var(--text-label)]"
            style={{
              borderColor: theme === value ? 'var(--color-primary)' : 'var(--color-border)',
              background: theme === value ? 'var(--color-primary-subtle)' : 'transparent',
            }}
          >
            <span className="flex items-center gap-2">
              <input
                type="radio"
                name="theme"
                checked={theme === value}
                onChange={() => setTheme(value)}
              />
              <Glyph name={icon} size={16} />
              {label}
            </span>
            {theme === value ? (
              <span className="text-[length:var(--text-caption)]">{t('account.theme.selected')}</span>
            ) : null}
          </label>
        ))}
      </fieldset>
      <p className="acc-note">{followsSystem ? t('account.theme.auto') : t('account.theme.manual')}</p>
      <Link to="/settings" className="btn btn-secondary mt-3">
        {t('account.theme.more')}
      </Link>
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Security                                                            */
/* ------------------------------------------------------------------ */

/**
 * Leaked-cookie recovery path, on /account where people look for it.
 *
 * The backend already owns the truth (`app/auth/service.py`: change-password
 * proves the current one and kills other sessions, revoke-all keeps only the
 * caller, per-session revoke by id prefix) and /auth already surfaces it —
 * but nobody hunts for account recovery on the login page. So it lives here
 * too: change the password, see the signed-in devices, leave them all.
 */
function SecurityPanel() {
  const { t } = useLanguage()
  const cache = useQueryClient()
  const [currentPassword, setCurrentPassword] = useState('')
  const [newPassword, setNewPassword] = useState('')
  const [formError, setFormError] = useState<string | null>(null)

  const sessions = useQuery({
    queryKey: ['sessions'],
    queryFn: api.authSessions,
    staleTime: 30_000,
    retry: false,
  })
  const events = useQuery({
    queryKey: ['auth-events'],
    queryFn: api.authEvents,
    staleTime: 30_000,
    retry: false,
  })

  function refreshSecurity(): void {
    void cache.invalidateQueries({ queryKey: ['sessions'] })
    void cache.invalidateQueries({ queryKey: ['auth-events'] })
  }

  const change = useMutation({
    mutationFn: (body: { current_password: string; new_password: string }) =>
      api.authChangePassword(body),
    onSuccess: () => {
      setCurrentPassword('')
      setNewPassword('')
      setFormError(null)
      refreshSecurity()
    },
  })

  const revokeOne = useMutation({
    mutationFn: (id: string) => api.authRevokeSession({ session_id: id }),
    onSuccess: () => refreshSecurity(),
  })

  const revokeAll = useMutation({
    mutationFn: () => api.authRevokeAll(),
    onSuccess: () => refreshSecurity(),
  })

  /* The portal itself loads without a login, so a visitor meets this panel
     logged out: offer the login, not an error box. */
  if (sessions.error instanceof ApiError && sessions.error.status === 401) {
    return (
      <Section id="security" icon="shield" title={t('account.security.title')}>
        <p className="empty">
          {t('account.security.loginPrompt')}{' '}
          <Link to="/login">{t('account.security.login')}</Link>.
        </p>
      </Section>
    )
  }

  const items: AuthSession[] = sessions.data?.items ?? []
  const log: AuthEvent[] = events.data?.items ?? []
  const busy = change.isPending || revokeOne.isPending || revokeAll.isPending

  function submitPassword(event: FormEvent): void {
    event.preventDefault()
    if (change.isPending) return
    if (!validPassword(currentPassword) || !validPassword(newPassword)) {
      setFormError(t('account.security.weak'))
      return
    }
    setFormError(null)
    change.mutate({
      current_password: currentPassword,
      new_password: newPassword,
    })
  }

  return (
    <Section
      id="security"
      icon="shield"
      title={t('account.security.title')}
      action={
        <span className="badge">
          {t('account.security.deviceCount', { count: fa(items.length) })}
        </span>
      }
      note={t('account.security.note')}
    >
      <form
        className="grid gap-3 sm:grid-cols-[minmax(0,1fr)_minmax(0,1fr)_auto] sm:items-end"
        onSubmit={submitPassword}
      >
        <label className="acc-field">
          <span className="label">{t('account.security.current')}</span>
          <input
            type="password"
            autoComplete="current-password"
            className="field min-w-0"
            value={currentPassword}
            onChange={(event) => setCurrentPassword(event.target.value)}
          />
        </label>
        <label className="acc-field">
          <span className="label">{t('account.security.new')}</span>
          <input
            type="password"
            autoComplete="new-password"
            className="field min-w-0"
            value={newPassword}
            onChange={(event) => setNewPassword(event.target.value)}
          />
        </label>
        <button type="submit" className="btn btn-secondary" disabled={change.isPending}>
          {change.isPending ? t('account.security.changing') : t('account.security.change')}
        </button>
      </form>

      {formError ? (
        <p role="alert" className="alert alert-error mt-3">
          {formError}
        </p>
      ) : null}
      {change.isError ? (
        <p role="alert" className="alert alert-error mt-3">
          {change.error instanceof Error
            ? change.error.message
            : t('account.security.changeFailed')}
        </p>
      ) : null}
      {change.isSuccess ? (
        <p role="status" className="alert alert-success mt-3">
          {t('account.security.changed')}
        </p>
      ) : null}

      <h3 className="mt-5 text-[length:var(--text-small)] font-extrabold">
        {t('account.security.devices')}
      </h3>
      {sessions.isPending ? (
        <div className="skeleton mt-2" style={{ height: 64 }} />
      ) : sessions.isError ? (
        <p role="alert" className="alert alert-error mt-2">
          {t('account.security.sessionsFailed')}
        </p>
      ) : items.length === 0 ? (
        <p className="empty mt-2">{t('account.security.noSessions')}</p>
      ) : (
        <ul className="acc-list mt-2">
          {items.map((item) => (
            <li key={item.id} className="acc-row">
              <div className="acc-row-body">
                {/* dir="ltr" on the truncating element itself: in an RTL line
                    the ellipsis would otherwise cut the identifying head. */}
                <span dir="ltr" className="chunk-id block truncate text-right">
                  {item.id}…
                </span>
                <span className="acc-row-meta">
                  {t('account.security.sessionLine', {
                    created: faDate(item.created_at),
                    seen: faAgo(item.last_seen_at) || faDate(item.last_seen_at),
                  })}
                </span>
              </div>
              {item.current ? (
                <span className="badge badge-success">{t('account.security.thisDevice')}</span>
              ) : (
                <button
                  type="button"
                  className="btn btn-ghost"
                  onClick={() => revokeOne.mutate(item.id)}
                  disabled={busy}
                >
                  {t('account.security.revoke')}
                </button>
              )}
            </li>
          ))}
        </ul>
      )}

      <div className="mt-4 flex flex-wrap items-center gap-3">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => revokeAll.mutate()}
          disabled={busy || items.filter((item) => !item.current).length === 0}
        >
          {revokeAll.isPending ? t('account.security.revoking') : t('account.security.revokeAll')}
        </button>
        {revokeAll.isSuccess ? (
          <p role="status" className="alert alert-success">
            {t('account.security.revokedAll', { count: fa(revokeAll.data.closed) })}
          </p>
        ) : null}
        {revokeAll.isError ? (
          <p role="alert" className="alert alert-error">
            {t('account.security.revokeFailed')}
          </p>
        ) : null}
      </div>

      <h3 className="mt-5 text-[length:var(--text-small)] font-extrabold">
        {t('account.security.events')}
      </h3>
      {events.isPending ? (
        <div className="skeleton mt-2" style={{ height: 64 }} />
      ) : events.isError ? (
        <p role="alert" className="alert alert-error mt-2">
          {t('account.security.eventsFailed')}
        </p>
      ) : log.length === 0 ? (
        <p className="empty mt-2">{t('account.security.noEvents')}</p>
      ) : (
        <ul className="acc-list mt-2">
          {log.slice(0, 20).map((entry) => (
            <li key={entry.id} className="acc-row">
              <div className="acc-row-body">
                <strong className="acc-row-title">{eventLabel(t, entry.event)}</strong>
                <span className="acc-row-meta">
                  {eventDetail(t, entry)}
                  {entry.ip ? ` · ${entry.ip}` : ''}
                  {' · '}
                  {faAgo(entry.created_at) || faDate(entry.created_at)}
                </span>
              </div>
            </li>
          ))}
        </ul>
      )}

      <div className="acc-links">
        <div className="acc-link-row">
          <div className="acc-link-text">
            <strong>{t('account.security.twoFactorTitle')}</strong>
            <span className="acc-row-meta">{t('account.security.twoFactorNote')}</span>
          </div>
          <span className="badge badge-neutral">{t('account.security.twoFactorBadge')}</span>
        </div>
        <Link to="/settings?tab=notifications" className="acc-link-row acc-link-action">
          <div className="acc-link-text">
            <strong>{t('account.security.notificationsTitle')}</strong>
            <span className="acc-row-meta">{t('account.security.notificationsNote')}</span>
          </div>
          <Glyph name="arrow" size={16} className="acc-arrow" />
        </Link>
      </div>
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* API keys                                                            */
/* ------------------------------------------------------------------ */

const KEY_SCOPES: ReadonlyArray<{ id: string; labelKey: StringKey }> = [
  { id: 'translate:write', labelKey: 'account.keys.scope.translate_write' },
  { id: 'jobs:read', labelKey: 'account.keys.scope.jobs_read' },
]

/**
 * Mint an API key. A native `<dialog>` for the same reasons `ConfirmDialog`
 * uses one: the browser owns the focus trap, `Esc`, and the inert backdrop.
 *
 * The plaintext token exists only in this response. After creation the dialog
 * swaps to a one-time reveal with a copy button and a warning, so the value is
 * never silently lost and never re-fetchable.
 */
function CreateKeyDialog({
  open,
  onClose,
  onCreated,
}: {
  open: boolean
  onClose: () => void
  onCreated: () => void
}) {
  const { t } = useLanguage()
  const ref = useRef<HTMLDialogElement>(null)
  const titleId = useId()
  const [name, setName] = useState('')
  const [scopes, setScopes] = useState<string[]>(['translate:write', 'jobs:read'])
  const [created, setCreated] = useState<CreatedApiKey | null>(null)
  const [copied, setCopied] = useState(false)

  useEffect(() => {
    const dialog = ref.current
    if (!dialog) return
    if (open && !dialog.open) dialog.showModal()
    if (!open && dialog.open) dialog.close()
  }, [open])

  // A fresh open always starts a fresh form, never the last token.
  useEffect(() => {
    if (!open) return
    setName('')
    setScopes(['translate:write', 'jobs:read'])
    setCreated(null)
    setCopied(false)
  }, [open])

  const create = useMutation({
    mutationFn: () => api.createApiKey({ name: name.trim(), scopes: scopes.join(' ') }),
    onSuccess: (result) => {
      setCreated(result)
      onCreated()
    },
  })

  function toggle(scope: string): void {
    setScopes((current) =>
      current.includes(scope) ? current.filter((item) => item !== scope) : [...current, scope],
    )
  }

  async function copy(): Promise<void> {
    if (!created) return
    try {
      await navigator.clipboard.writeText(created.token)
      setCopied(true)
    } catch {
      setCopied(false)
    }
  }

  function submit(event: FormEvent): void {
    event.preventDefault()
    if (create.isPending || created || !name.trim() || scopes.length === 0) return
    create.mutate()
  }

  return (
    <dialog
      ref={ref}
      className="acc-dialog"
      aria-labelledby={titleId}
      onCancel={(event) => {
        event.preventDefault()
        onClose()
      }}
      onClose={() => {
        if (open) onClose()
      }}
    >
      <h2 id={titleId} className="acc-dialog-title">
        {created ? t('account.keys.createdTitle') : t('account.keys.createTitle')}
      </h2>
      {created ? (
        <div className="acc-dialog-body">
          <p>{t('account.keys.createdNote')}</p>
          <div className="acc-token">
            <code className="acc-token-value" dir="ltr">
              {created.token}
            </code>
            <button type="button" className="btn btn-secondary" onClick={() => void copy()}>
              {copied ? t('account.keys.copied') : t('account.keys.copy')}
            </button>
          </div>
          <p className="acc-dialog-warn">{t('account.keys.createdWarn')}</p>
        </div>
      ) : (
        <form className="acc-dialog-body" onSubmit={submit}>
          <label className="acc-field">
            <span className="label">{t('account.keys.name')}</span>
            <input
              className="field"
              value={name}
              onChange={(event) => setName(event.target.value)}
              maxLength={80}
              placeholder={t('account.keys.namePlaceholder')}
            />
          </label>
          <fieldset className="acc-scopes">
            <legend className="label">{t('account.keys.scopes')}</legend>
            {KEY_SCOPES.map((scope) => (
              <label key={scope.id} className="acc-scope-check">
                <input
                  type="checkbox"
                  checked={scopes.includes(scope.id)}
                  onChange={() => toggle(scope.id)}
                />
                <span>{t(scope.labelKey)}</span>
              </label>
            ))}
          </fieldset>
          {create.isError ? (
            <p role="alert" className="alert alert-error">
              {create.error instanceof Error ? create.error.message : t('account.keys.createFailed')}
            </p>
          ) : null}
        </form>
      )}
      <div className="acc-dialog-actions">
        {created ? (
          <button type="button" className="btn btn-primary" onClick={onClose}>
            {t('account.keys.done')}
          </button>
        ) : (
          <>
            <button type="button" className="btn btn-ghost" onClick={onClose}>
              {t('account.keys.cancel')}
            </button>
            <button
              type="button"
              className="btn btn-primary"
              onClick={() => {
                if (name.trim() && scopes.length > 0) create.mutate()
              }}
              disabled={create.isPending || !name.trim() || scopes.length === 0}
            >
              {create.isPending ? t('account.keys.creating') : t('account.keys.create')}
            </button>
          </>
        )}
      </div>
    </dialog>
  )
}

function KeysPanel({ keys }: { keys: PortalApiKey[] }) {
  const { t } = useLanguage()
  const cache = useQueryClient()
  const [creating, setCreating] = useState(false)
  const revoke = useMutation({
    mutationFn: (id: number) => api.revokeApiKey(id),
    onSuccess: () => cache.invalidateQueries({ queryKey: ['portal'] }),
  })

  return (
    <Section
      id="keys"
      icon="key"
      title={t('account.keys.title')}
      action={
        <div className="acc-section-actions">
          <span
            className="text-[length:var(--text-caption)] tabular-nums"
            style={{ color: 'var(--color-text-muted)' }}
          >
            {fa(keys.length)}
          </span>
          <button type="button" className="btn btn-secondary" onClick={() => setCreating(true)}>
            <Glyph name="plus" size={16} />
            {t('account.keys.create')}
          </button>
        </div>
      }
    >
      {keys.length === 0 ? (
        <p className="empty">{t('account.keys.empty')}</p>
      ) : (
        <ul className="acc-list">
          {keys.map((key) => {
            const revoked = Boolean(key.revoked_at)
            return (
              <li key={key.id} className="acc-row">
                <div className="acc-row-body">
                  {/* Masked. The endpoint returns this column verbatim and it is
                      user data, so anything shaped like a credential is not
                      printed. See `maskSecretLike`. */}
                  <strong className="acc-row-title">{maskSecretLike(key.name)}</strong>
                  <span className="chunk-id block">
                    {key.token_prefix}… · {key.created_at.slice(0, 10)}
                  </span>
                  <span className="acc-row-meta">
                    {key.scopes
                      .split(/\s+/)
                      .filter(Boolean)
                      .map((scope) => scopeLabel(t, scope))
                      .join(t('account.listSep'))}
                    {key.last_used_at
                      ? t('account.keys.lastUsed', { date: faDate(key.last_used_at) })
                      : t('account.keys.neverUsed')}
                  </span>
                </div>
                {revoked ? (
                  <span className="badge badge-neutral">{t('account.keys.revoked')}</span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-ghost"
                    onClick={() => revoke.mutate(key.id)}
                    disabled={revoke.isPending}
                  >
                    {t('account.keys.revoke')}
                  </button>
                )}
              </li>
            )
          })}
        </ul>
      )}
      <CreateKeyDialog
        open={creating}
        onClose={() => setCreating(false)}
        onCreated={() => void cache.invalidateQueries({ queryKey: ['portal'] })}
      />
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Glossary packs                                                      */
/* ------------------------------------------------------------------ */

const PACK_KINDS: ReadonlyArray<{ id: string; labelKey: StringKey }> = [
  { id: '', labelKey: 'account.packs.filter.all' },
  { id: 'glossary', labelKey: 'account.packs.kind.glossary' },
  { id: 'preset', labelKey: 'account.packs.kind.preset' },
  { id: 'style', labelKey: 'account.packs.kind.style' },
  { id: 'template', labelKey: 'account.packs.kind.template' },
]

function PacksPanel({ fallback }: { fallback: MarketplaceItem[] }) {
  const { t, lang } = useLanguage()
  const cache = useQueryClient()
  const [kind, setKind] = useState('')
  // "All" reuses the list the portal already shipped; a specific kind asks the
  // server, which is what the `?kind=` filter exists for.
  const filtered = useQuery({
    queryKey: ['marketplace', kind],
    queryFn: () => api.accountMarketplace(kind),
    enabled: kind !== '',
    staleTime: 60_000,
  })
  const install = useMutation({
    mutationFn: (id: string) => api.installMarketplaceItem(id),
    onSuccess: () => {
      void cache.invalidateQueries({ queryKey: ['marketplace'] })
      void cache.invalidateQueries({ queryKey: ['portal'] })
    },
  })

  const items = kind === '' ? fallback : (filtered.data ?? [])

  // Nothing at all to show: keep the section out of the page entirely.
  if (kind === '' && fallback.length === 0) return null

  return (
    <Section
      id="packs"
      icon="book"
      title={t('account.packs.title')}
      note={t('account.packs.note')}
      action={
        <div className="acc-chips" role="group" aria-label={t('account.packs.filter.label')}>
          {PACK_KINDS.map((option) => (
            <button
              key={option.id || 'all'}
              type="button"
              className="acc-chip"
              aria-pressed={kind === option.id}
              onClick={() => setKind(option.id)}
            >
              {t(option.labelKey)}
            </button>
          ))}
        </div>
      }
    >
      {filtered.isError ? (
        <p role="alert" className="alert alert-error">
          {filtered.error instanceof Error ? filtered.error.message : t('account.packs.failed')}
        </p>
      ) : filtered.isPending && kind !== '' ? (
        <div className="skeleton" style={{ height: 120 }} />
      ) : items.length === 0 ? (
        <p className="empty">{t('account.packs.empty')}</p>
      ) : (
      <ul className="acc-list md:grid-cols-2">
        {items.map((item) => {
          const done = Boolean(item.installed)
          return (
            <li key={item.id} className="acc-readout flex flex-col gap-2">
              <div className="flex items-baseline justify-between gap-2">
                <strong className="text-[length:var(--text-body)]">
                  {lang === 'fa' ? item.title_fa : item.title_en}
                </strong>
                <span
                  className="text-[length:var(--text-caption)] tabular-nums"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  ★ {item.rating.toFixed(1)} ·{' '}
                  {t('account.packs.installs', { count: fa(item.installs) })}
                </span>
              </div>
              <p
                className="text-[length:var(--text-small)]"
                style={{ color: 'var(--color-text-secondary)' }}
              >
                {lang === 'fa' ? item.description_fa : item.description_en}
              </p>
              <div className="mt-auto flex items-center justify-between gap-2 pt-1">
                <span
                  className="text-[length:var(--text-caption)]"
                  style={{ color: 'var(--color-text-muted)' }}
                >
                  {kindLabel(t, item.kind)} · {item.language_pair} · ${item.price_usd.toFixed(0)}
                </span>
                {done ? (
                  <span className="badge badge-success">{t('account.packs.installed')}</span>
                ) : (
                  <button
                    type="button"
                    className="btn btn-secondary"
                    onClick={() => install.mutate(item.id)}
                    disabled={install.isPending}
                  >
                    {t('account.packs.install')}
                  </button>
                )}
              </div>
            </li>
          )
        })}
      </ul>
      )}
      {install.isError ? (
        <p role="alert" className="alert alert-error mt-3">
          {install.error instanceof Error ? install.error.message : t('account.packs.failed')}
        </p>
      ) : null}
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Data and backup                                                     */
/* ------------------------------------------------------------------ */

function DataPanel({ portal }: { portal: AccountPortal }) {
  const { t } = useLanguage()
  const [exported, setExported] = useState(false)
  const backup = portal.overview.backup
  const count = backup?.count ?? 0
  const latest = backup?.latest ?? null

  // A real export of this user's translation memory, as JSON. The endpoint
  // returns the rows; the browser turns them into a file so nothing is
  // assembled on the server or left on disk.
  const exportMemory = useMutation({
    mutationFn: api.exportMemory,
    onSuccess: (data) => {
      const blob = new Blob([JSON.stringify(data.items, null, 2)], {
        type: 'application/json',
      })
      const url = URL.createObjectURL(blob)
      const anchor = document.createElement('a')
      anchor.href = url
      anchor.download = `kalima-memory-${new Date().toISOString().slice(0, 10)}.json`
      document.body.appendChild(anchor)
      anchor.click()
      anchor.remove()
      URL.revokeObjectURL(url)
      setExported(true)
    },
  })

  return (
    <Section id="data" icon="layers" title={t('account.data.title')} note={t('account.data.note')}>
      <div className="acc-readouts">
        <Readout label={t('account.data.backups')} value={fa(count)} />
        <Readout label={t('account.data.latest')} value={latest ?? t('account.data.none')} />
      </div>
      {latest ? (
        <p className="acc-note">{t('account.data.latestAt', { date: faDate(backup?.latest_at) })}</p>
      ) : null}
      <div className="acc-data-actions">
        <button
          type="button"
          className="btn btn-secondary"
          onClick={() => exportMemory.mutate()}
          disabled={exportMemory.isPending}
        >
          <Glyph name="download" size={16} />
          {exportMemory.isPending ? t('account.data.exporting') : t('account.data.exportMemory')}
        </button>
        <Link to="/settings?tab=data" className="btn btn-ghost">
          {t('account.data.settings')}
          <Glyph name="arrow" size={16} className="acc-arrow" />
        </Link>
      </div>
      {exported ? (
        <p role="status" className="alert alert-success mt-3">
          {t('account.data.exportDone')}
        </p>
      ) : null}
      {exportMemory.isError ? (
        <p role="alert" className="alert alert-error mt-3">
          {exportMemory.error instanceof Error
            ? exportMemory.error.message
            : t('account.data.exportFailed')}
        </p>
      ) : null}
    </Section>
  )
}

/* ------------------------------------------------------------------ */
/* Page                                                                */
/* ------------------------------------------------------------------ */

export function AccountPage() {
  const { t, dir } = useLanguage()
  const portal = useQuery({ queryKey: ['portal'], queryFn: api.accountPortal })
  const config = useQuery({
    queryKey: ['provider-config'],
    queryFn: api.providerConfig,
    staleTime: 60_000,
  })

  if (portal.isPending) {
    return (
      <main className="page" dir={dir}>
        <div className="grid gap-4">
          <div className="skeleton" style={{ height: 160 }} />
          <div className="skeleton" style={{ height: 220 }} />
        </div>
      </main>
    )
  }

  if (portal.isError) {
    return (
      <main className="page" dir={dir}>
        <p role="alert" className="alert alert-error">
          {t('account.loadFailed')}
        </p>
      </main>
    )
  }

  const data = portal.data
  const keys = (data.api_keys ?? []) as PortalApiKey[]
  const packs = (data.marketplace ?? []) as MarketplaceItem[]
  const counts = data.overview.counts
  const hasKey = config.data?.has_api_key ?? null
  const readiness = readinessChecklist({
    hasKey,
    books: counts.books,
    completedJobs: counts.completed_jobs,
    glossaries: counts.glossaries,
    memoryEntries: counts.memory_entries,
  })
  const available = new Set<string>([
    'acc-top',
    'readiness',
    'profile',
    'activity',
    'security',
    'keys',
    'appearance',
  ])
  if (packs.length > 0) available.add('packs')
  if (data.publisher) available.add('publisher')

  return (
    <main className="page" dir={dir}>
      <Hero portal={data} readiness={readiness} hasKey={hasKey} />
      <JumpNav available={available} />

      <div className="mb-4">
        <ReadinessPanel items={readiness} />
      </div>

      <div className="mb-4">
        <Tiles portal={data} />
      </div>

      <div className="acc-grid">
        <div className="acc-main">
          <ProfilePanel account={data.overview.account} />
          <ActivityPanel />
          <SecurityPanel />
          <KeysPanel keys={keys} />
          <PacksPanel fallback={packs} />
        </div>
        <div className="acc-side">
          <SetupPanel config={config.data} />
          <UsagePanel counts={counts} />
          <PublisherPanel publisher={data.publisher} />
          <AppearancePanel />
          <DataPanel portal={data} />
        </div>
      </div>
    </main>
  )
}
