/**
 * The account page's decisions, asserted without a DOM.
 *
 * The page itself is mostly layout; the parts that can be wrong are the
 * readiness arithmetic, the priority order of the next-step recommendation,
 * the monogram, and the reading window. Each of those is a pure function in
 * `lib/account.ts` precisely so it can be checked here.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  fillReadingSeries,
  initials,
  nextAction,
  readinessChecklist,
  readinessPercent,
} from '../src/lib/account.ts'

describe('readiness checklist', () => {
  it('treats an unknown provider answer as not done, not as configured', () => {
    const items = readinessChecklist({
      hasKey: null,
      books: 0,
      completedJobs: 0,
      glossaries: 0,
      memoryEntries: 0,
    })
    assert.equal(items.every((item) => !item.done), true)
    assert.equal(readinessPercent(items), 0)
  })

  it('counts each durable fact once and keeps a stable order', () => {
    const items = readinessChecklist({
      hasKey: true,
      books: 2,
      completedJobs: 1,
      glossaries: 0,
      memoryEntries: 0,
    })
    assert.deepEqual(
      items.map((item) => item.id),
      ['provider', 'book', 'translation', 'glossary', 'memory'],
    )
    assert.equal(items.filter((item) => item.done).length, 3)
    assert.equal(readinessPercent(items), 60)
  })

  it('never divides by zero', () => {
    assert.equal(readinessPercent([]), 0)
  })
})

describe('next action', () => {
  it('puts a missing key first, even with work already done', () => {
    assert.deepEqual(
      nextAction({ hasKey: false, books: 4, activeProjects: 2, completedJobs: 9 }),
      { id: 'provider', to: '/settings' },
    )
  })

  it('prefers an empty library over old completed work', () => {
    assert.deepEqual(
      nextAction({ hasKey: true, books: 0, activeProjects: 0, completedJobs: 9 }),
      { id: 'upload', to: '/workspace' },
    )
  })

  it('prefers running work over reading', () => {
    assert.deepEqual(
      nextAction({ hasKey: true, books: 3, activeProjects: 1, completedJobs: 9 }),
      { id: 'monitor', to: '/jobs' },
    )
  })

  it('falls back to reading when nothing is running', () => {
    assert.deepEqual(
      nextAction({ hasKey: true, books: 3, activeProjects: 0, completedJobs: 1 }),
      { id: 'read', to: '/library' },
    )
  })

  it('does not treat an unknown provider answer as a blocker', () => {
    assert.equal(
      nextAction({ hasKey: null, books: 1, activeProjects: 0, completedJobs: 0 }).id,
      'upload',
    )
  })
})

describe('initials', () => {
  it('uses the first and last words for Latin names', () => {
    assert.equal(initials('Sara Ahmadi'), 'SA')
  })

  it('uses the first and last words for Persian names', () => {
    assert.equal(initials('سارا احمدی'), 'سا')
  })

  it('falls back for an empty name', () => {
    assert.equal(initials('   '), 'K')
  })

  it('does not split an astral character in half', () => {
    assert.equal(initials('😀 Book'), '😀B')
  })
})

describe('reading series', () => {
  it('fills missing days with zeros and ends on today', () => {
    const series = fillReadingSeries([{ day: '2026-11-26', pages: 5 }], 3, '2026-11-27')
    assert.deepEqual(series, [
      { day: '2026-11-25', pages: 0 },
      { day: '2026-11-26', pages: 5 },
      { day: '2026-11-27', pages: 0 },
    ])
  })

  it('returns exactly the requested number of days', () => {
    assert.equal(fillReadingSeries([], 30, '2026-11-27').length, 30)
  })

  it('returns an empty series for an invalid date', () => {
    assert.deepEqual(fillReadingSeries([], 7, 'not-a-date'), [])
  })
})
