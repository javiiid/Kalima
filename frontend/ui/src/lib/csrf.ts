/**
 * Double-submit CSRF for cookie-authenticated writes.
 *
 * The backend mints a non-HttpOnly `kalima_csrf` cookie on any GET and requires
 * a cookie-authenticated mutating request to echo the same value back in the
 * `X-CSRF-Token` header. This app authenticates with the session cookie, so
 * every write has to carry the token or the server answers 403.
 *
 * Patching `window.fetch` once is deliberate. The codebase has both the typed
 * `request` helper and several raw `fetch` calls (multipart uploads, rescue
 * import); a single chokepoint cannot be skipped by a call site someone adds
 * later. Callers that authenticate with a Bearer token are unaffected -- the
 * server only enforces this for cookie sessions, and an extra header there is
 * ignored.
 */
export const CSRF_COOKIE = 'kalima_csrf'
export const CSRF_HEADER = 'X-CSRF-Token'

const MUTATING = new Set(['POST', 'PUT', 'PATCH', 'DELETE'])
const INSTALLED = '__kalimaCsrfInstalled'

function readCookie(name: string): string {
  for (const part of document.cookie.split(';')) {
    const separator = part.indexOf('=')
    if (separator === -1) continue
    if (part.slice(0, separator).trim() === name) {
      return decodeURIComponent(part.slice(separator + 1).trim())
    }
  }
  return ''
}

function requestMethod(input: RequestInfo | URL, init?: RequestInit): string {
  const declared = init?.method ?? (typeof Request !== 'undefined' && input instanceof Request ? input.method : 'GET')
  return (declared || 'GET').toUpperCase()
}

export function installCsrf(): void {
  if (typeof window === 'undefined') return
  const scope = window as unknown as Record<string, unknown>
  if (scope[INSTALLED]) return
  scope[INSTALLED] = true

  const original = window.fetch.bind(window)
  window.fetch = (input: RequestInfo | URL, init?: RequestInit): Promise<Response> => {
    if (MUTATING.has(requestMethod(input, init))) {
      const token = readCookie(CSRF_COOKIE)
      if (token) {
        const headers = new Headers(init?.headers ?? (input instanceof Request ? input.headers : undefined))
        if (!headers.has(CSRF_HEADER)) headers.set(CSRF_HEADER, token)
        init = { ...init, headers }
      }
    }
    return original(input, init)
  }
}
