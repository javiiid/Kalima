/**
 * The settings page's decisions, asserted without a DOM.
 *
 * These are the parts of `lib/preferences.ts` that a wrong answer would make
 * visible only after a round trip: which fields changed, what a clamped slider
 * sends, and what an imported file is allowed to contain.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  applyPreferencesPatch,
  clampReadingSettings,
  countChanges,
  diffPreferences,
  EXPORT_KIND,
  EXPORT_VERSION,
  exportPreferences,
  formatDateSample,
  hasChanges,
  ImportError,
  importErrorMessageKey,
  isAcceptableWebhook,
  MAX_IMPORT_BYTES,
  parseImportedPreferences,
  readEmptyPreferences,
  serialiseExport,
} from '../src/lib/preferences.ts'

function fixture() {
  const prefs = readEmptyPreferences()
  prefs.general.timezone = 'Europe/Berlin'
  prefs.translation.default_model = 'gpt-test'
  prefs.appearance.theme = 'dark'
  prefs.notifications.webhook = 'https://example.com/hook'
  prefs.notifications.events = ['job.completed']
  prefs.reading.reading_font_size = 22
  prefs.reading.reading_last_location = { job_id: 'abc', chapter: 3 }
  prefs.reading.reading_bookmarks = [
    { chapter: 1, block: 2, note: 'note', created: '2026-01-01T00:00:00Z', job: 'abc' },
  ]
  return prefs
}

describe('diffPreferences', () => {
  it('returns only the sections and fields that changed', () => {
    const current = readEmptyPreferences()
    const next = readEmptyPreferences()
    next.general.timezone = 'UTC'
    next.notifications.events = ['job.failed']

    const patch = diffPreferences(current, next)
    assert.deepEqual(patch, {
      general: { timezone: 'UTC' },
      notifications: { events: ['job.failed'] },
    })
    assert.equal(hasChanges(patch), true)
    assert.equal(countChanges(patch), 2)
  })

  it('is empty when nothing changed', () => {
    const current = readEmptyPreferences()
    const patch = diffPreferences(current, readEmptyPreferences())
    assert.deepEqual(patch, {})
    assert.equal(hasChanges(patch), false)
    assert.equal(countChanges(patch), 0)
  })
})

describe('applyPreferencesPatch', () => {
  it('merges a partial patch without dropping untouched fields', () => {
    const current = fixture()
    const next = applyPreferencesPatch(current, {
      general: { language: 'en' },
      reading: { reading_font_size: 26 },
    })
    assert.equal(next.general.language, 'en')
    assert.equal(next.general.timezone, 'Europe/Berlin')
    assert.equal(next.reading.reading_font_size, 26)
    assert.deepEqual(next.reading.reading_bookmarks, current.reading.reading_bookmarks)
  })
})

describe('reading clamps', () => {
  it('clamps every number to the server bounds', () => {
    assert.deepEqual(
      clampReadingSettings({
        reading_font_size: 99,
        reading_line_height: 0.2,
        reading_width: 10,
      }),
      { reading_font_size: 30, reading_line_height: 1.4, reading_width: 560 },
    )
  })
})

describe('webhook rule', () => {
  it('accepts https, loopback http and empty', () => {
    assert.equal(isAcceptableWebhook(''), true)
    assert.equal(isAcceptableWebhook('https://example.com/hook'), true)
    assert.equal(isAcceptableWebhook('http://127.0.0.1:9000/hook'), true)
    assert.equal(isAcceptableWebhook('http://localhost/hook'), true)
  })

  it('rejects plain http off loopback and non-URLs', () => {
    assert.equal(isAcceptableWebhook('http://example.com/hook'), false)
    assert.equal(isAcceptableWebhook('example.com'), false)
    assert.equal(isAcceptableWebhook('ftp://example.com'), false)
  })
})

describe('export and import', () => {
  it('round-trips every setting except the reader position', () => {
    const prefs = fixture()
    const document = exportPreferences(prefs, new Date('2026-11-08T10:00:00Z'))
    assert.equal(document.kind, EXPORT_KIND)
    assert.equal(document.version, EXPORT_VERSION)

    const patch = parseImportedPreferences(serialiseExport(document))
    const restored = applyPreferencesPatch(readEmptyPreferences(), patch)

    assert.deepEqual(restored.general, prefs.general)
    assert.deepEqual(restored.translation, prefs.translation)
    assert.deepEqual(restored.appearance, prefs.appearance)
    assert.deepEqual(restored.notifications, prefs.notifications)
    assert.equal(restored.reading.reading_font_size, 22)
    assert.equal(restored.reading.reading_last_location, null)
    assert.deepEqual(restored.reading.reading_bookmarks, [])
  })

  it('refuses a file that is too large', () => {
    assert.throws(
      () => parseImportedPreferences('x'.repeat(MAX_IMPORT_BYTES + 1)),
      (error: unknown) => error instanceof ImportError && error.code === 'too-large',
    )
  })

  it('refuses text that is not JSON', () => {
    assert.throws(
      () => parseImportedPreferences('{nope'),
      (error: unknown) => error instanceof ImportError && error.code === 'not-json',
    )
  })

  it('refuses a JSON file that is not a settings export', () => {
    assert.throws(
      () => parseImportedPreferences(JSON.stringify({ hello: 'world' })),
      (error: unknown) => error instanceof ImportError && error.code === 'wrong-kind',
    )
  })

  it('refuses a file from a newer version', () => {
    assert.throws(
      () =>
        parseImportedPreferences(
          JSON.stringify({ kind: EXPORT_KIND, version: EXPORT_VERSION + 1, preferences: {} }),
        ),
      (error: unknown) => error instanceof ImportError && error.code === 'too-new',
    )
  })

  it('refuses an invalid section rather than applying part of it', () => {
    assert.throws(
      () =>
        parseImportedPreferences(
          JSON.stringify({
            kind: EXPORT_KIND,
            version: EXPORT_VERSION,
            preferences: { general: { language: 'klingon' } },
          }),
        ),
      (error: unknown) => error instanceof ImportError && error.code === 'invalid',
    )
  })

  it('maps every import error to a dictionary key', () => {
    for (const code of ['too-large', 'not-json', 'wrong-kind', 'too-new', 'invalid'] as const) {
      assert.match(importErrorMessageKey(code), /^settings\.data\.import\./)
    }
  })
})

describe('formatDateSample', () => {
  const date = new Date('2026-11-08T00:00:00Z')

  it('renders ISO without a locale', () => {
    assert.equal(formatDateSample(date, 'iso'), '2026-11-08')
  })

  it('renders Jalali and Gregorian as numeric dates', () => {
    assert.match(formatDateSample(date, 'jalali'), /^\d{4}\/\d{2}\/\d{2}$/)
    assert.match(formatDateSample(date, 'gregorian'), /^\d{4}\/\d{2}\/\d{2}$/)
  })
})

describe('defaults', () => {
  it('opens a reader with no stored value on the bilingual view', () => {
    assert.equal(readEmptyPreferences().reading.reading_mode, 'bilingual')
  })
})
