/**
 * Tests for the API client's response handling.
 *
 * The rule: a non-JSON answer must surface as an `ApiError` carrying the
 * HTTP status, never as a raw `SyntaxError`. The usual shape of this is a
 * 502 HTML page from Vite's proxy when the Python backend is down — and
 * without the guard, every page's `error.message` handling displayed a
 * parser crash instead of the failure it was meant to report.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { ApiError, libraryQuery, readJsonBody, uploadIdFrom, withUploadId } from '../src/lib/api.ts'

describe('readJsonBody', () => {
  it('parses a JSON object', () => {
    assert.deepEqual(readJsonBody('{"ok":true}', 200), { ok: true })
  })

  it('returns null for an empty body, so a 204 is not a parse failure', () => {
    assert.equal(readJsonBody('', 204), null)
  })

  it('throws an ApiError, not a SyntaxError, for an HTML error page', () => {
    assert.throws(
      () => readJsonBody('<html><body>Bad Gateway</body></html>', 502),
      (error: unknown) => error instanceof ApiError,
      'a proxy error page must arrive as an ApiError',
    )
  })

  it('carries the HTTP status on the ApiError', () => {
    try {
      readJsonBody('<html>nope</html>', 502)
      assert.fail('must throw')
    } catch (error) {
      assert.ok(error instanceof ApiError)
      assert.equal(error.status, 502)
      assert.equal(typeof error.message, 'string')
    }
  })

  it('ApiError keeps its name, so error boundaries can match on it', () => {
    const error = new ApiError('boom', 500)
    assert.equal(error.name, 'ApiError')
    assert.equal(error.status, 500)
  })
})

describe('the upload id the calibration route needs', () => {
  /* `POST /api/jobs/upload` answers with a full filesystem path.
     `POST /api/calibrations` wants a bare filename -- it joins it to the upload
     directory itself and rejects anything with a separator, so the browser
     cannot choose where on the server a file lives. Two shapes of path, one
     derived id, because the two shapes exist on the same machine. */
  it('takes the last segment of a posix path', () => {
    assert.equal(uploadIdFrom('/srv/kalima/uploads/ab12_book.epub'), 'ab12_book.epub')
  })

  it('takes the last segment of a windows path', () => {
    assert.equal(uploadIdFrom('D:\\KALIMA\\uploads\\ab12_book.epub'), 'ab12_book.epub')
  })

  it('leaves a bare name alone', () => {
    assert.equal(uploadIdFrom('book.epub'), 'book.epub')
  })

  it('adds the id to what the server sent, without losing a field', () => {
    const stored = withUploadId({
      file_path: '/srv/uploads/ab12_book.epub',
      filename: 'book.epub',
      size: 1234,
    })
    assert.deepEqual(stored, {
      upload_id: 'ab12_book.epub',
      file_path: '/srv/uploads/ab12_book.epub',
      filename: 'book.epub',
      size: 1234,
    })
  })

  it('never returns a path with a separator in it', () => {
    // The server rejects a token that is not a bare name, so an id that kept a
    // slash would be a 422 on the very next call.
    const id = uploadIdFrom('/srv/uploads/ab12_book.epub')
    assert.ok(!id.includes('/') && !id.includes('\\'))
  })
})

describe('the library query URL', () => {
  /* The filters the page adds -- model, scope, dates, sort -- all have to reach
     the endpoint as parameters, because every one of them narrows or reorders
     the server's answer rather than one page of it. The rule this pins is which
     empty values mean "no filter": omit, do not send an empty parameter. */
  it('sends only the page and limit when nothing is filtered', () => {
    assert.equal(libraryQuery({ page: 1, limit: 12 }), '/api/library?page=1&limit=12')
  })

  it('trims a query and drops an empty one', () => {
    assert.equal(
      libraryQuery({ page: 2, limit: 12, query: '  ', tag: '' }),
      '/api/library?page=2&limit=12',
    )
    const withQuery = libraryQuery({ page: 1, limit: 12, query: '  شب  ' })
    assert.ok(withQuery.includes('q=%D8%B4%D8%A8'))
  })

  it('carries status, shelf and tag only when set', () => {
    const url = libraryQuery({ page: 1, limit: 12, status: 'completed', shelf: 'reading', tag: 'رمان' })
    assert.ok(url.includes('status=completed'))
    assert.ok(url.includes('shelf=reading'))
    assert.ok(url.includes(`tag=${encodeURIComponent('رمان')}`))
    assert.ok(!libraryQuery({ page: 1, limit: 12, status: '', shelf: '' }).includes('status='))
  })

  it('passes model, scope, dates and sort through untouched', () => {
    const url = libraryQuery({
      page: 3,
      limit: 24,
      model: 'gpt-6.1-sol',
      scope: 'content',
      since: '2026-01-01',
      until: '2026-06-30',
      sort: 'cost',
    })
    assert.ok(url.includes('model=gpt-6.1-sol'))
    assert.ok(url.includes('scope=content'))
    assert.ok(url.includes('since=2026-01-01'))
    assert.ok(url.includes('until=2026-06-30'))
    assert.ok(url.includes('sort=cost'))
  })
})
