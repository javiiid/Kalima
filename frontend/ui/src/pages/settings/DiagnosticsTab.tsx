import { useDeferredValue, useMemo, useState } from 'react'
import { useInfiniteQuery, useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { Select } from '@/components/ui/Select'
import { Switch } from '@/components/ui/Switch'
import { api, type JobEvent, type LogQuery } from '@/lib/api'
import { faDate } from '@/lib/format'
import type { StringKey } from '@/i18n/fa.ts'
import { useLanguage } from '@/i18n/useLanguage.ts'

const LEVELS = ['', 'ERROR', 'WARNING', 'INFO'] as const
const CATEGORIES = ['', 'api', 'pdf', 'epub', 'crash', 'retry', 'job'] as const
const WINDOWS = ['24h', '7d', '30d', ''] as const

type Level = (typeof LEVELS)[number]
type Category = (typeof CATEGORIES)[number]
type Window = (typeof WINDOWS)[number]

const LEVEL_LABELS: Record<Exclude<Level, ''>, StringKey> = {
  ERROR: 'settings.diagnostics.level.error',
  WARNING: 'settings.diagnostics.level.warning',
  INFO: 'settings.diagnostics.level.info',
}

const CATEGORY_LABELS: Record<Exclude<Category, ''>, StringKey> = {
  api: 'settings.diagnostics.category.api',
  pdf: 'settings.diagnostics.category.pdf',
  epub: 'settings.diagnostics.category.epub',
  crash: 'settings.diagnostics.category.crash',
  retry: 'settings.diagnostics.category.retry',
  job: 'settings.diagnostics.category.job',
}

const WINDOW_LABELS: Record<Exclude<Window, ''>, StringKey> = {
  '24h': 'settings.diagnostics.window.24h',
  '7d': 'settings.diagnostics.window.7d',
  '30d': 'settings.diagnostics.window.30d',
}

function toneFor(level: string): string {
  switch (level.toUpperCase()) {
    case 'ERROR':
    case 'CRITICAL':
      return 'badge badge-error'
    case 'WARNING':
      return 'badge badge-warning'
    default:
      return 'badge'
  }
}

export function DiagnosticsTab({ isAdmin }: { isAdmin: boolean }) {
  const { t } = useLanguage()
  const [level, setLevel] = useState<Level>('')
  const [category, setCategory] = useState<Category>('')
  const [window, setWindow] = useState<Window>('24h')
  const [jobId, setJobId] = useState('')
  const [query, setQuery] = useState('')
  const [scope, setScope] = useState<'mine' | 'all'>('mine')
  const [auto, setAuto] = useState(false)
  const [expanded, setExpanded] = useState<Set<number>>(new Set())
  const deferredQuery = useDeferredValue(query)
  const deferredJob = useDeferredValue(jobId)

  const filters = useMemo<LogQuery>(() => {
    const next: LogQuery = { limit: 100 }
    if (level) next.level = level
    if (category) next.category = category
    if (window) next.since = window
    if (deferredJob.trim()) next.job_id = deferredJob.trim()
    if (deferredQuery.trim()) next.q = deferredQuery.trim()
    if (isAdmin && scope === 'all') next.scope = 'all'
    return next
  }, [category, deferredJob, deferredQuery, isAdmin, level, scope, window])

  const list = useInfiniteQuery({
    queryKey: ['diagnostics', filters],
    queryFn: ({ pageParam }) =>
      api.logs(pageParam === undefined ? filters : { ...filters, before_id: pageParam }),
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => (last.has_more ? last.next_before_id ?? undefined : undefined),
    refetchInterval: auto ? 15_000 : false,
    refetchOnWindowFocus: false,
  })

  const summary = useQuery({
    queryKey: ['diagnostics-summary', filters.since, filters.job_id, filters.scope],
    queryFn: () => {
      const params: Pick<LogQuery, 'since' | 'job_id' | 'scope'> = {}
      if (filters.since) params.since = filters.since
      if (filters.job_id) params.job_id = filters.job_id
      if (filters.scope) params.scope = filters.scope
      return api.logSummary(params)
    },
    refetchInterval: auto ? 15_000 : false,
    refetchOnWindowFocus: false,
  })

  const events = list.data?.pages.flatMap((page) => page.items) ?? []

  const toggleExpanded = (id: number | undefined) => {
    if (id === undefined) return
    setExpanded((current) => {
      const next = new Set(current)
      if (next.has(id)) next.delete(id)
      else next.add(id)
      return next
    })
  }

  const levelOptions = LEVELS.map((value) => ({
    value,
    label: value ? t(LEVEL_LABELS[value]) : t('settings.diagnostics.level.all'),
  }))
  const categoryOptions = CATEGORIES.map((value) => ({
    value,
    label: value ? t(CATEGORY_LABELS[value]) : t('settings.diagnostics.category.all'),
  }))
  const windowOptions = WINDOWS.map((value) => ({
    value,
    label: value ? t(WINDOW_LABELS[value]) : t('settings.diagnostics.window.all'),
  }))

  const counts = summary.data
  const errorCount = (counts?.by_level.ERROR ?? 0) + (counts?.by_level.CRITICAL ?? 0)

  return (
    <div className="settings-diagnostics">
      <section className="settings-card" aria-labelledby="diagnostics-title">
        <div className="settings-diagnostics-head">
          <div>
            <h2 id="diagnostics-title" className="settings-card-title">
              {t('settings.diagnostics.title')}
            </h2>
            <p className="settings-card-hint">{t('settings.diagnostics.hint')}</p>
          </div>
          <div className="settings-diagnostics-actions">
            <button
              type="button"
              className="btn btn-secondary"
              onClick={() => {
                void list.refetch()
                void summary.refetch()
              }}
            >
              {t('settings.diagnostics.refresh')}
            </button>
          </div>
        </div>

        <div className="settings-diagnostics-summary" aria-live="polite">
          <div className="settings-diagnostics-stat">
            <strong>{counts?.total ?? '—'}</strong>
            <span>{t('settings.diagnostics.stat.total')}</span>
          </div>
          <div className="settings-diagnostics-stat is-error">
            <strong>{errorCount}</strong>
            <span>{t('settings.diagnostics.stat.errors')}</span>
          </div>
          <div className="settings-diagnostics-stat is-warning">
            <strong>{counts?.by_level.WARNING ?? 0}</strong>
            <span>{t('settings.diagnostics.stat.warnings')}</span>
          </div>
          <div className="settings-diagnostics-stat">
            <strong>{counts?.by_category.retry ?? 0}</strong>
            <span>{t('settings.diagnostics.stat.retries')}</span>
          </div>
          <div className="settings-diagnostics-stat">
            <strong>{counts?.by_category.crash ?? 0}</strong>
            <span>{t('settings.diagnostics.stat.crashes')}</span>
          </div>
        </div>

        <div className="settings-diagnostics-filters">
          <label className="settings-diagnostics-field">
            <span>{t('settings.diagnostics.level')}</span>
            <Select
              id="diagnostics-level"
              value={level}
              options={levelOptions}
              onChange={(next) => setLevel(next as Level)}
            />
          </label>
          <label className="settings-diagnostics-field">
            <span>{t('settings.diagnostics.category')}</span>
            <Select
              id="diagnostics-category"
              value={category}
              options={categoryOptions}
              onChange={(next) => setCategory(next as Category)}
            />
          </label>
          <label className="settings-diagnostics-field">
            <span>{t('settings.diagnostics.windowLabel')}</span>
            <Select
              id="diagnostics-window"
              value={window}
              options={windowOptions}
              onChange={(next) => setWindow(next as Window)}
            />
          </label>
          <label className="settings-diagnostics-field">
            <span>{t('settings.diagnostics.job')}</span>
            <input
              className="field"
              value={jobId}
              placeholder={t('settings.diagnostics.jobPlaceholder')}
              onChange={(event) => setJobId(event.target.value)}
            />
          </label>
          <label className="settings-diagnostics-field is-wide">
            <span>{t('settings.diagnostics.search')}</span>
            <input
              className="field"
              value={query}
              placeholder={t('settings.diagnostics.searchPlaceholder')}
              onChange={(event) => setQuery(event.target.value)}
            />
          </label>
          <div className="settings-diagnostics-field">
            <span id="diagnostics-auto-label">{t('settings.diagnostics.autoRefresh')}</span>
            <Switch
              checked={auto}
              labelledBy="diagnostics-auto-label"
              onChange={setAuto}
            />
          </div>
          {isAdmin ? (
            <label className="settings-checkbox settings-diagnostics-scope">
              <input
                type="checkbox"
                checked={scope === 'all'}
                onChange={(event) => setScope(event.target.checked ? 'all' : 'mine')}
              />
              {t('settings.diagnostics.allUsers')}
            </label>
          ) : null}
        </div>
      </section>

      {list.isError ? (
        <p role="alert" className="alert alert-error">
          {t('settings.diagnostics.loadError')}
        </p>
      ) : null}

      {list.isPending ? (
        <div className="skeleton" style={{ height: 280 }} />
      ) : events.length === 0 ? (
        <div className="surface-card empty">{t('settings.diagnostics.empty')}</div>
      ) : (
        <div className="settings-card settings-diagnostics-table-wrap">
          <table className="settings-diagnostics-table">
            <thead>
              <tr>
                <th>{t('settings.diagnostics.columns.time')}</th>
                <th>{t('settings.diagnostics.columns.level')}</th>
                <th>{t('settings.diagnostics.columns.category')}</th>
                <th>{t('settings.diagnostics.columns.event')}</th>
                <th>{t('settings.diagnostics.columns.message')}</th>
                <th>{t('settings.diagnostics.columns.job')}</th>
                <th>{t('settings.diagnostics.columns.recoverable')}</th>
              </tr>
            </thead>
            <tbody>
              {events.map((event, index) => {
                const key = event.id ?? `${event.timestamp}-${index}`
                const open = event.id !== undefined && expanded.has(event.id)
                return (
                  <DiagnosticsRow
                    key={key}
                    event={event}
                    open={open}
                    onToggle={() => toggleExpanded(event.id)}
                  />
                )
              })}
            </tbody>
          </table>
          {list.hasNextPage ? (
            <button
              type="button"
              className="btn btn-secondary settings-diagnostics-more"
              disabled={list.isFetchingNextPage}
              onClick={() => void list.fetchNextPage()}
            >
              {list.isFetchingNextPage
                ? t('settings.diagnostics.loadingMore')
                : t('settings.diagnostics.loadMore')}
            </button>
          ) : null}
        </div>
      )}
    </div>
  )
}

function DiagnosticsRow({
  event,
  open,
  onToggle,
}: {
  event: JobEvent
  open: boolean
  onToggle: () => void
}) {
  const { t } = useLanguage()
  return (
    <>
      <tr className={open ? 'is-open' : undefined}>
        <td className="settings-diagnostics-time">{faDate(event.timestamp)}</td>
        <td>
          <span className={toneFor(event.level)}>{event.level}</span>
        </td>
        <td>
          <span className="badge">{event.category ?? 'job'}</span>
        </td>
        <td>
          <button type="button" className="settings-diagnostics-event" onClick={onToggle}>
            {event.event}
          </button>
        </td>
        <td className="settings-diagnostics-message">{event.message}</td>
        <td>
          {event.job_id ? (
            <Link to={`/jobs/${event.job_id}`} className="settings-diagnostics-job">
              {event.job?.filename ?? event.job_id}
            </Link>
          ) : (
            '—'
          )}
        </td>
        <td>{event.recoverable === false || event.recoverable === 0 ? t('settings.diagnostics.no') : t('settings.diagnostics.yes')}</td>
      </tr>
      {open ? (
        <tr className="settings-diagnostics-detail">
          <td colSpan={7}>
            <pre>{JSON.stringify(event.data ?? {}, null, 2)}</pre>
          </td>
        </tr>
      ) : null}
    </>
  )
}
