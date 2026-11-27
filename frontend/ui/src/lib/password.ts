/**
 * Password strength, as advice rather than as a gate.
 *
 * THE RULE THIS MUST NOT BREAK
 * ----------------------------
 * The server accepts any password between 8 and 200 characters
 * (`validate_password` in `app/auth/service.py`). It has no character-class
 * requirement, no dictionary check and no upper bound on entropy. So this
 * module must never be used to *reject* a password the server would accept:
 * a strength meter that blocks `correcthorsebatterystaple` because it has no
 * digit is a front end inventing a policy the product does not have, and it
 * would lock a user out of an account they could otherwise create.
 *
 * What it does instead is describe. Four levels, computed from length and
 * variety, shown beside the field so a person can see that `abc12345` is not
 * the same kind of secret as a long passphrase. `validPassword` in
 * `lib/auth.ts` remains the only thing that decides whether a password may be
 * submitted, and it mirrors the server exactly.
 *
 * WHY LENGTH DOMINATES
 * --------------------
 * Variety is easy to game and length is not: `P@ssw0rd` scores well on classes
 * and falls to a wordlist in seconds, while four unrelated words take
 * centuries. So length carries the most weight, variety adds at the margin,
 * and a repeated or sequential run is penalised because it is length without
 * entropy.
 */

export type StrengthLevel = 0 | 1 | 2 | 3 | 4

export interface Strength {
  /** 0 = empty, 1 = weak, 2 = fair, 3 = good, 4 = strong. */
  level: StrengthLevel
  /** Translation key for the level's label. */
  labelKey:
    | 'auth.strength.weak'
    | 'auth.strength.fair'
    | 'auth.strength.good'
    | 'auth.strength.strong'
}

/** True when the whole string is one character repeated, or a run like `12345678`. */
function isTrivial(value: string): boolean {
  if (value.length < 2) return true
  if (/^(.)\1+$/.test(value)) return true
  // A strictly ascending or descending run of single characters.
  const codes = Array.from(value, (char) => char.codePointAt(0) ?? 0)
  const step = codes[1]! - codes[0]!
  if (step === 0) return true
  return codes.every((code, index) => index === 0 || code - codes[index - 1]! === step)
}

/**
 * Score a password. Pure, so `tests/password.test.ts` can pin the levels
 * without a DOM, and so the same answer is produced on every render.
 */
export function passwordStrength(value: string): Strength {
  if (value.length === 0) return { level: 0, labelKey: 'auth.strength.weak' }

  const length = value.length
  let score = 0

  // Length: the dominant term. 8 is the server floor, so it is the first step.
  if (length >= 8) score += 1
  if (length >= 12) score += 1
  if (length >= 16) score += 1
  if (length >= 24) score += 1

  // Variety: at the margin only.
  const classes = [/[a-z]/, /[A-Z]/, /\d/, /[^\w\s]/].filter((pattern) => pattern.test(value)).length
  if (classes >= 3) score += 1
  if (classes >= 4) score += 1

  // Length without entropy is not strength.
  if (isTrivial(value)) score = 1

  // Below the server floor it is never better than weak, whatever the variety.
  if (length < 8) score = Math.min(score, 1)

  const level = Math.max(1, Math.min(4, score)) as StrengthLevel
  const labelKey =
    level === 1
      ? 'auth.strength.weak'
      : level === 2
        ? 'auth.strength.fair'
        : level === 3
          ? 'auth.strength.good'
          : 'auth.strength.strong'

  return { level, labelKey }
}

/**
 * A same-origin path from a `next` parameter, or null.
 *
 * The redirect after a successful sign-in is attacker-reachable: a link to
 * `/login?next=https://evil.example` must not bounce a freshly authenticated
 * user off-site, and `//evil.example` is a protocol-relative URL that a naive
 * `startsWith('/')` check would wave through. So: one leading slash, not two,
 * no backslash (some browsers treat `\` as `/`), and no control characters.
 */
export function safeNextPath(raw: string | null | undefined): string | null {
  if (!raw) return null
  const value = raw.trim()
  if (value.length === 0 || value.length > 512) return null
  if (!value.startsWith('/')) return null
  if (value.startsWith('//')) return null
  if (value.includes('\\')) return null
  // eslint-disable-next-line no-control-regex
  if (/[\u0000-\u001f\u007f]/.test(value)) return null
  // A path that is itself an auth page would loop.
  if (/^\/(login|signup)(\/|$|\?)/.test(value)) return null
  return value
}
