/**
 * Password strength and the `next` sanitiser.
 *
 * ## The rule this file exists to hold
 *
 * The server accepts 8..200 characters and imposes nothing else. So the
 * strength meter must never be load-bearing: a password the server would
 * accept has to remain submittable however weak this module calls it. The
 * first test below pins exactly that, because it is the one way this feature
 * could lock a user out of their own account.
 *
 * The `next` sanitiser is the other half: an open redirect is a real defect,
 * and `//evil.example` is the case a naive `startsWith('/')` check misses.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import { passwordStrength, safeNextPath } from '../src/lib/password.ts'
import { validPassword } from '../src/lib/auth.ts'

describe('password strength describes, never gates', () => {
  it('never rejects a password the server accepts', () => {
    // Every one of these is inside the server's 8..200 window, so every one
    // must be submittable. The meter may call them weak; it may not block them.
    const serverValid = ['aaaaaaaa', '12345678', 'password', 'P@ssw0rd', 'x'.repeat(200)]
    for (const candidate of serverValid) {
      assert.equal(validPassword(candidate), true, `${candidate} should pass the server rule`)
      const strength = passwordStrength(candidate)
      assert.ok(strength.level >= 1 && strength.level <= 4, `${candidate} produced level ${strength.level}`)
    }
  })

  it('scores an empty field at zero and a real passphrase at the top', () => {
    assert.equal(passwordStrength('').level, 0)
    assert.equal(passwordStrength('correct horse battery staple').level, 4)
  })

  it('ranks a long passphrase above a short clever one', () => {
    // The whole point of weighting length: `P@ssw0rd` has every character
    // class and still falls to a wordlist in seconds.
    assert.ok(
      passwordStrength('correct horse battery staple').level >
        passwordStrength('P@ssw0rd').level,
    )
  })

  it('penalises length without entropy', () => {
    assert.equal(passwordStrength('aaaaaaaaaaaa').level, 1)
    assert.equal(passwordStrength('1234567890').level, 1)
    assert.equal(passwordStrength('abcdefghijkl').level, 1)
  })

  it('never reports better than weak below the server floor', () => {
    for (const short of ['Ab1!', 'aB1!xY', 'Ab1!xYz']) {
      assert.equal(passwordStrength(short).level, 1, `${short} was not capped at weak`)
    }
  })

  it('is deterministic', () => {
    const once = passwordStrength('Tr0ub4dor&3-longer')
    const twice = passwordStrength('Tr0ub4dor&3-longer')
    assert.deepEqual(once, twice)
  })
})

describe('safeNextPath refuses anything that could leave the origin', () => {
  it('accepts a plain same-origin path', () => {
    assert.equal(safeNextPath('/workspace'), '/workspace')
    assert.equal(safeNextPath('/library?sort=new'), '/library?sort=new')
    assert.equal(safeNextPath('  /account  '), '/account')
  })

  it('refuses absolute, protocol-relative and backslash forms', () => {
    for (const hostile of [
      'https://evil.example',
      'http://evil.example/x',
      '//evil.example',
      '///evil.example',
      '/\\evil.example',
      '\\\\evil.example',
      'javascript:alert(1)',
      'evil.example',
      '',
      null,
      undefined,
    ]) {
      assert.equal(safeNextPath(hostile), null, `${String(hostile)} was allowed`)
    }
  })

  it('refuses control characters and absurd lengths', () => {
    assert.equal(safeNextPath('/work\u0000space'), null)
    assert.equal(safeNextPath('/work\nspace'), null)
    assert.equal(safeNextPath('/' + 'a'.repeat(600)), null)
  })

  it('refuses a target that would loop back into auth', () => {
    assert.equal(safeNextPath('/login'), null)
    assert.equal(safeNextPath('/signup'), null)
    assert.equal(safeNextPath('/login?next=/signup'), null)
    // A path that merely starts with the word is fine.
    assert.equal(safeNextPath('/logins'), '/logins')
  })
})
