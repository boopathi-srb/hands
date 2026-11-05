import { describe, expect, it, vi } from 'vitest'
import type { Condition, TargetSpec } from '../api/types'
import { memberBalanceCapability } from '../fixtures'
import { conditionToText, describeCondition } from './conditions'

const target: TargetSpec = {
  description: 'savings balance value',
  candidates: [{ kind: 'label', label: 'Balance', confidence: 0.8, reason: 'r' }],
}

describe('describeCondition', () => {
  it('renders text_visible with the literal separated', () => {
    const node = describeCondition({ kind: 'text_visible', pattern: 'Member Detail' })
    expect(node.children).toEqual([])
    expect(node.segments).toEqual([
      { text: 'Text ', style: 'plain' },
      { text: 'Member Detail', style: 'literal' },
      { text: ' is visible', style: 'plain' },
    ])
  })

  it('notes regex and case-sensitive matching', () => {
    const text = conditionToText({ kind: 'text_visible', pattern: '^A', regex: true, case_sensitive: true })
    expect(text).toBe('Text “^A” is visible (regex, case-sensitive)')
  })

  it('renders node_present and value_matches by target description', () => {
    expect(conditionToText({ kind: 'node_present', target })).toBe('“savings balance value” is present')
    expect(conditionToText({ kind: 'value_matches', target, pattern: '\\d+' })).toBe('“savings balance value” value matches “\\d+”')
  })

  it('renders location_matches with pattern, title, both, or neither', () => {
    expect(conditionToText({ kind: 'location_matches', pattern: '/t/:tenant/main', title_pattern: null })).toBe(
      'Location matches “/t/:tenant/main”',
    )
    expect(conditionToText({ kind: 'location_matches', title_pattern: 'Sign On' })).toBe('Window title matches “Sign On”')
    expect(conditionToText({ kind: 'location_matches', pattern: '/a', title_pattern: 'B' })).toBe(
      'Location matches “/a” and title matches “B”',
    )
    expect(conditionToText({ kind: 'location_matches' })).toBe('Any location')
  })

  it('renders dialog_open by nativeness', () => {
    expect(conditionToText({ kind: 'dialog_open', native: true })).toBe('A native dialog is open')
    expect(conditionToText({ kind: 'dialog_open', native: false, title_pattern: 'Notice' })).toBe('An in-page dialog is open titled “Notice”')
    expect(conditionToText({ kind: 'dialog_open', native: null, text_pattern: 'Expired' })).toBe('A dialog is open reading “Expired”')
    expect(conditionToText({ kind: 'dialog_open', title_pattern: 'T', text_pattern: 'X' })).toBe('A dialog is open titled “T” and reading “X”')
  })

  it('nests all_of / any_of / not as a tree', () => {
    const condition: Condition = {
      kind: 'all_of',
      conditions: [
        { kind: 'text_visible', pattern: 'A' },
        { kind: 'any_of', conditions: [{ kind: 'not', condition: { kind: 'text_visible', pattern: 'B' } }] },
      ],
    }
    const node = describeCondition(condition)
    expect(node.segments[0].text).toBe('All of')
    expect(node.children).toHaveLength(2)
    expect(node.children[1].children[0].segments[0].text).toBe('Not')
    expect(conditionToText(condition)).toBe('All of: Text “A” is visible; Any of: Not: Text “B” is visible')
  })

  it('renders the real checkpoint from the recorded artifact', () => {
    expect(conditionToText(memberBalanceCapability.checkpoint)).toBe(
      'All of: Location matches “/t/:tenant/main”; “savings balance value” is present',
    )
  })

  it('falls back for an unknown kind and logs it', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    const text = conditionToText({ kind: 'mystery' } as unknown as Condition)
    expect(text).toBe('Condition “mystery”')
    expect(warn).toHaveBeenCalled()
    warn.mockRestore()
  })
})

describe('conditionToText', () => {
  it('returns empty for null and undefined', () => {
    expect(conditionToText(null)).toBe('')
    expect(conditionToText(undefined)).toBe('')
  })
})
