/**
 * The settings tab model, asserted without a DOM.
 *
 * The page renders `SETTINGS_TABS`; it does not restate the order. These tests
 * pin the order, the URL round trip and the wrap-around the arrow keys use.
 */
import assert from 'node:assert/strict'
import { describe, it } from 'node:test'

import {
  nextSettingsTab,
  parseSettingsTab,
  settingsTabFromSearch,
  settingsTabHref,
  SETTINGS_TABS,
} from '../src/components/settings/tabs.ts'

describe('settings tabs', () => {
  it('lists the eight sections in the documented order', () => {
    assert.deepEqual(
      SETTINGS_TABS.map((tab) => tab.key),
      [
        'general',
        'translation',
        'reading',
        'appearance',
        'notifications',
        'diagnostics',
        'system',
        'data',
      ],
    )
  })

  it('groups personal settings before advanced ones', () => {
    assert.deepEqual(
      SETTINGS_TABS.map((tab) => tab.group),
      [
        'personal',
        'personal',
        'personal',
        'personal',
        'personal',
        'advanced',
        'advanced',
        'advanced',
      ],
    )
  })

  it('gives every tab a unique key and label', () => {
    const keys = SETTINGS_TABS.map((tab) => tab.key)
    const labels = SETTINGS_TABS.map((tab) => tab.labelKey)
    assert.equal(new Set(keys).size, keys.length)
    assert.equal(new Set(labels).size, labels.length)
  })

  it('falls back to general for a missing or stale tab', () => {
    assert.equal(parseSettingsTab(null), 'general')
    assert.equal(parseSettingsTab(''), 'general')
    assert.equal(parseSettingsTab('nope'), 'general')
    assert.equal(parseSettingsTab('reading'), 'reading')
  })

  it('reads the tab from a query string and ignores other parameters', () => {
    assert.equal(settingsTabFromSearch('?tab=appearance&x=1'), 'appearance')
    assert.equal(settingsTabFromSearch('tab=data'), 'data')
    assert.equal(settingsTabFromSearch('?x=1'), 'general')
  })

  it('wraps in both directions', () => {
    assert.equal(nextSettingsTab('general', -1), 'data')
    assert.equal(nextSettingsTab('data', 1), 'general')
    assert.equal(nextSettingsTab('translation', 2), 'appearance')
    assert.equal(nextSettingsTab('notifications', 1), 'diagnostics')
    assert.equal(nextSettingsTab('diagnostics', -1), 'notifications')
  })

  it('builds a deep link for every tab', () => {
    for (const tab of SETTINGS_TABS) {
      assert.equal(settingsTabHref(tab.key), `/settings?tab=${tab.key}`)
    }
  })
})
