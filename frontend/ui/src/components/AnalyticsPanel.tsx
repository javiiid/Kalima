import { useState } from 'react'
import { useQuery } from '@tanstack/react-query'
import { Link } from 'react-router-dom'
import { api } from '@/lib/api'
import type { AnalyticsRange, AnalyticsTotals } from '@/lib/api'
import { fa, usd } from '@/lib/format'
import { useLanguage } from '@/i18n/useLanguage.ts'
import type { StringKey } from '@/i18n/fa.ts'
import { BarChart } from '@/components/BarChart'

/**
 * Analytics, inside the dashboard.
 *
 * ## Where the numbers come from
 *
 * Every provider call writes one row to the usage ledger, so these figures are
 * measured, not estimated. Chunks and pages come from the pipeline's own
 * progress; tokens, cost, duration, retries and errors come from the ledger.
 *
 * ## What it refuses to show
 *
 * A model with no price in the table records `price_known = 0`. Its cost is
 * shown as part of a warning count, never folded into the total as a silent
 * zero -- a zero reads as "free", which is the one thing a cost figure must
 * never say by accident. EPUB sources have no page count, so the pages tile
 * says so instead of printing 0.
 *
 * ## Why bars and not lines
 *
 * The time series is a cost per day, a count per day. A line would imply
 * continuity between days that the data does not have, and the project already
 * has a hand-built bar chart that matches the palette. No chart library.
 */

const RANGES: AnalyticsRange[] = ['24h', '7d', '30d', '90d', 'all']

type SortKey = 'cost' | 'tokens' | 'duration' | 'recent'

function deltaPercent(current: number, previous: number | undefined): number | null {
  if (previous === undefined || previous === 0) return null
  return ((current - previous) / previous) * 100
}

function Delta({ percent, goodWhenDown }: { percent: number | null; goodWhenDown: boolean }) {
  if (percent === null) return null
  const rounded = Math.round(percent)
  if (rounded === 0) return <span className="analytics-delta is-flat">0%</span>
  const rising = rounded > 0
  const good = goodWhenDown ? !rising : rising
  return (
    <span className={`analytics-delta ${good ? 'is-good' : 'is-bad'}`}>
      {rising ? '↑' : '↓'} {fa(Math.abs(rounded))}%
    </span>
  )
}

function Metric({
  label,
  value,
  hint,
  percent,
  goodWhenDown = false,
}: {
  label: string
  value: string
  hint?: string | undefined
  percent?: number | null | undefined
  goodWhenDown?: boolean
}) {
  return (
    <div className="analytics-metric">
      <span className="analytics-metric-label">{label}</span>
      <strong className="analytics-metric-value">{value}</strong>
      <span className="analytics-metric-foot">
        {hint ? <span className="analytics-metric-hint">{hint}</span> : null}
        {percent === undefined ? null : (
          <Delta percent={percent} goodWhenDown={goodWhenDown} />
        )}
      </span>
    </div>
  )
}

function shortBucket(bucket: string): string {
  // `2026-11-20` -> `11-20`; a week key or anything else passes through.
  return /^\d{4}-\d{2}-\d{2}$/.test(bucket) ? bucket.slice(5) : bucket
}

export function AnalyticsPanel() {
  const { t } = useLanguage()
  const [range, setRange] = useState<AnalyticsRange>('30d')
  const [sort, setSort] = useState<SortKey>('cost')

  const overview = useQuery({
    queryKey: ['analytics', 'overview', range],
    queryFn: () => api.analytics({ since: range }),
    staleTime: 30_000,
    refetchInterval: 30_000,
  })
  const cost = useQuery({
    queryKey: ['analytics', 'cost', range],
    queryFn: () => api.analyticsCost({ since: range }),
    staleTime: 30_000,
    refetchInterval: 30_000,
  })
  const jobs = useQuery({
    queryKey: ['analytics', 'jobs', range, sort],
    queryFn: () => api.analyticsJobs({ since: range, sort, limit: 10 }),
    staleTime: 30_000,
  })

  const totals: AnalyticsTotals | undefined = overview.data?.totals
  const previous = overview.data?.previous ?? undefined
  const hasUsage = (totals?.requests ?? 0) > 0

  const pagesValue =
    totals && totals.pages_total > 0 ? fa(totals.pages) : '—'
  const pagesHint =
    totals && totals.pages_total > 0
      ? t('analytics.pagesOf', { total: fa(totals.pages_total) })
      : t('analytics.pagesNa')

  const costBars = (cost.data?.series ?? []).map((point) => ({
    label: shortBucket(point.bucket),
    value: point.cost_usd,
    title: `${point.bucket} · ${usd(point.cost_usd)} · ${fa(point.calls)} ${t('analytics.calls')}`,
  }))
  const tokenBars = (cost.data?.series ?? []).map((point) => ({
    label: shortBucket(point.bucket),
    value: point.input_tokens + point.output_tokens,
    title: `${point.bucket} · ${fa(point.input_tokens)} + ${fa(point.output_tokens)}`,
  }))
  const modelBars = (cost.data?.by_model ?? []).slice(0, 6).map((row) => ({
    label: row.model,
    value: row.cost_usd,
    title: `${row.model} · ${usd(row.cost_usd)} · ${fa(row.calls)} ${t('analytics.calls')}`,
  }))
  const stageBars = (cost.data?.by_stage ?? []).map((row) => ({
    label: t(`analytics.stage.${row.stage}` as StringKey),
    value: row.cost_usd,
    title: `${t(`analytics.stage.${row.stage}` as StringKey)} · ${usd(row.cost_usd)}`,
  }))

  return (
    <section className="dash-section analytics" aria-labelledby="analytics-heading">
      <div className="dash-section-head analytics-head">
        <div className="min-w-0">
          <h2 id="analytics-heading" className="dash-section-title">
            {t('analytics.title')}
          </h2>
          <span className="dash-section-note">{t('analytics.hint')}</span>
        </div>
        <div className="analytics-range" role="group" aria-label={t('analytics.rangeLabel')}>
          {RANGES.map((option) => (
            <button
              key={option}
              type="button"
              className={`analytics-range-btn${range === option ? ' is-active' : ''}`}
              aria-pressed={range === option}
              onClick={() => setRange(option)}
            >
              {t(`analytics.range.${option}` as StringKey)}
            </button>
          ))}
        </div>
      </div>

      {overview.isError ? (
        <div role="alert" className="alert alert-error analytics-alert">
          <span>{t('analytics.failed')}</span>
          <button type="button" className="btn btn-secondary flex-none" onClick={() => void overview.refetch()}>
            {t('analytics.retry')}
          </button>
        </div>
      ) : null}

      {totals && totals.unknown_price_calls > 0 ? (
        <p className="analytics-note analytics-note-warn" role="status">
          {t('analytics.unknownPrice', { count: fa(totals.unknown_price_calls) })}
        </p>
      ) : null}

      <div className="analytics-grid">
        <Metric
          label={t('analytics.pages')}
          value={overview.isPending ? '…' : overview.isError ? '—' : pagesValue}
          hint={pagesHint}
          percent={totals ? deltaPercent(totals.pages, previous?.pages) : undefined}
        />
        <Metric
          label={t('analytics.chunks')}
          value={overview.isPending ? '…' : overview.isError ? '—' : fa(totals?.chunks)}
          hint={totals ? t('analytics.chunksOf', { total: fa(totals.chunks_total) }) : undefined}
          percent={totals ? deltaPercent(totals.chunks, previous?.chunks) : undefined}
        />
        <Metric
          label={t('analytics.requests')}
          value={overview.isPending ? '…' : overview.isError ? '—' : fa(totals?.requests)}
          percent={totals ? deltaPercent(totals.requests, previous?.requests) : undefined}
        />
        <Metric
          label={t('analytics.inputTokens')}
          value={overview.isPending ? '…' : overview.isError ? '—' : fa(totals?.input_tokens)}
          percent={totals ? deltaPercent(totals.input_tokens, previous?.input_tokens) : undefined}
        />
        <Metric
          label={t('analytics.outputTokens')}
          value={overview.isPending ? '…' : overview.isError ? '—' : fa(totals?.output_tokens)}
          percent={totals ? deltaPercent(totals.output_tokens, previous?.output_tokens) : undefined}
        />
        <Metric
          label={t('analytics.cost')}
          value={overview.isPending ? '…' : overview.isError ? '—' : usd(totals?.cost_usd ?? 0)}
          percent={totals ? deltaPercent(totals.cost_usd, previous?.cost_usd) : undefined}
          goodWhenDown
        />
        <Metric
          label={t('analytics.avgChunk')}
          value={
            overview.isPending
              ? '…'
              : overview.isError
                ? '—'
                : totals?.avg_chunk_ms
                  ? `${fa(Number((totals.avg_chunk_ms / 1000).toFixed(1)))}s`
                  : '—'
          }
          percent={totals ? deltaPercent(totals.avg_chunk_ms, previous?.avg_chunk_ms) : undefined}
          goodWhenDown
        />
        <Metric
          label={t('analytics.retries')}
          value={overview.isPending ? '…' : overview.isError ? '—' : fa(totals?.retries)}
          percent={totals ? deltaPercent(totals.retries, previous?.retries) : undefined}
          goodWhenDown
        />
        <Metric
          label={t('analytics.apiErrors')}
          value={overview.isPending ? '…' : overview.isError ? '—' : fa(totals?.api_errors)}
          percent={totals ? deltaPercent(totals.api_errors, previous?.api_errors) : undefined}
          goodWhenDown
        />
      </div>

      {!overview.isPending && !overview.isError && !hasUsage ? (
        <p className="analytics-note">{t('analytics.empty')}</p>
      ) : null}

      <div className="analytics-charts">
        <figure className="analytics-chart">
          <figcaption className="analytics-chart-title">{t('analytics.costOverTime')}</figcaption>
          <BarChart bars={costBars} caption={t('analytics.chartCostCaption')} />
        </figure>
        <figure className="analytics-chart">
          <figcaption className="analytics-chart-title">{t('analytics.tokensOverTime')}</figcaption>
          <BarChart bars={tokenBars} caption={t('analytics.chartTokensCaption')} />
        </figure>
        <figure className="analytics-chart">
          <figcaption className="analytics-chart-title">{t('analytics.byModel')}</figcaption>
          <BarChart bars={modelBars} caption={t('analytics.chartModelCaption')} />
        </figure>
        <figure className="analytics-chart">
          <figcaption className="analytics-chart-title">{t('analytics.byStage')}</figcaption>
          <BarChart bars={stageBars} caption={t('analytics.chartStageCaption')} />
        </figure>
      </div>

      <div className="analytics-jobs">
        <div className="dash-section-head">
          <h3 className="dash-section-title" style={{ fontSize: 'var(--text-body)' }}>
            {t('analytics.jobsTitle')}
          </h3>
          <div className="analytics-sort" role="group" aria-label={t('analytics.sortLabel')}>
            {(['cost', 'tokens', 'duration', 'recent'] as SortKey[]).map((option) => (
              <button
                key={option}
                type="button"
                className={`analytics-range-btn${sort === option ? ' is-active' : ''}`}
                aria-pressed={sort === option}
                onClick={() => setSort(option)}
              >
                {t(`analytics.sort.${option}` as StringKey)}
              </button>
            ))}
          </div>
        </div>
        {jobs.isError ? (
          <p role="alert" className="alert alert-error">{t('analytics.jobsFailed')}</p>
        ) : jobs.isPending ? (
          <div className="skeleton" style={{ height: 120 }} aria-hidden="true" />
        ) : (jobs.data?.items.length ?? 0) === 0 ? (
          <p className="dash-empty">{t('analytics.jobsEmpty')}</p>
        ) : (
          <div className="table-wrap">
            <table className="analytics-table">
              <caption className="sr-only">{t('analytics.jobsCaption')}</caption>
              <thead>
                <tr>
                  <th scope="col">{t('analytics.col.job')}</th>
                  <th scope="col">{t('analytics.col.chunks')}</th>
                  <th scope="col">{t('analytics.col.tokens')}</th>
                  <th scope="col">{t('analytics.col.cost')}</th>
                  <th scope="col">{t('analytics.col.avg')}</th>
                  <th scope="col">{t('analytics.col.retries')}</th>
                  <th scope="col">{t('analytics.col.errors')}</th>
                </tr>
              </thead>
              <tbody>
                {jobs.data?.items.map((row) => (
                  <tr key={row.job_id}>
                    <td>
                      <Link to={`/jobs/${row.job_id}`} dir="ltr" className="analytics-job-name">
                        {row.filename}
                      </Link>
                      <span className="analytics-job-model" dir="ltr">{row.model}</span>
                    </td>
                    <td className="tabular-nums">
                      {row.chunks_total ? `${fa(row.chunks)}/${fa(row.chunks_total)}` : '—'}
                    </td>
                    <td className="tabular-nums">{fa(row.input_tokens + row.output_tokens)}</td>
                    <td className="tabular-nums">{usd(row.cost_usd)}</td>
                    <td className="tabular-nums">
                      {row.avg_chunk_ms ? `${fa(Number((row.avg_chunk_ms / 1000).toFixed(1)))}s` : '—'}
                    </td>
                    <td className="tabular-nums">{fa(row.retries)}</td>
                    <td className="tabular-nums">{fa(row.api_errors)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
        <p className="analytics-note">{t('analytics.jobsHint')}</p>
      </div>
    </section>
  )
}
