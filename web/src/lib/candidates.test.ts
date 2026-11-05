import { describe, expect, it, vi } from 'vitest'
import type { Candidate, Step } from '../api/types'
import { memberBalanceCapability } from '../fixtures'
import {
  candidateKindLabel,
  describeCandidate,
  describeRecoveryResponse,
  describeStepAction,
  isFallbackMatch,
  matchedCandidateLabel,
  ordinalWord,
  rankCandidates,
  stepTarget,
} from './candidates'

const typeStep = memberBalanceCapability.steps[1]
const extractStep = memberBalanceCapability.steps[3]

describe('candidateKindLabel', () => {
  it('labels every kind', () => {
    expect(candidateKindLabel('role_name')).toBe('Role and name')
    expect(candidateKindLabel('visual_anchor')).toBe('Visual offset')
  })
  it('handles null and unknown kinds', () => {
    expect(candidateKindLabel(null)).toBe('Unknown')
    expect(candidateKindLabel('ocr')).toBe('ocr')
  })
})

describe('ordinalWord', () => {
  it('handles 1st/2nd/3rd/4th and the teens', () => {
    expect([0, 1, 2, 3].map(ordinalWord)).toEqual(['1st', '2nd', '3rd', '4th'])
    expect([10, 11, 12].map(ordinalWord)).toEqual(['11th', '12th', '13th'])
    expect(ordinalWord(20)).toBe('21st')
  })
})

describe('describeCandidate', () => {
  it('describes the real candidates of the member-number step', () => {
    const target = stepTarget(typeStep)
    expect(target).not.toBeNull()
    expect(target?.candidates.map(describeCandidate)).toEqual([
      'textbox labelled “Member Number”',
      'textbox right of “Member Number”',
      'frame:content › form[1]/table[1]/row[1]/cell[2]/textbox[1]',
      'point offset (+112.3, +0) px from “Member Number”',
    ])
  })
  it('describes role and name, exact and contains', () => {
    const exact: Candidate = { kind: 'role_name', role: 'button', name: 'Search', exact: true, confidence: 0.9, reason: '' }
    expect(describeCandidate(exact)).toBe('button named “Search”')
    expect(describeCandidate({ ...exact, exact: false })).toBe('button named “Search” (contains)')
  })
  it('includes the ordinal for later matches and defaults missing roles', () => {
    const anchor: Candidate = {
      kind: 'text_anchor',
      anchor_text: 'Share Savings',
      relation: 'same_row',
      role: 'cell',
      ordinal: 1,
      confidence: 0.75,
      reason: '',
    }
    expect(describeCandidate(anchor)).toBe('2nd cell in the same row as “Share Savings”')
    expect(describeCandidate({ ...anchor, role: null, ordinal: 0 })).toBe('node in the same row as “Share Savings”')
    expect(describeCandidate({ kind: 'label', label: 'User ID', confidence: 1, reason: '' })).toBe('control labelled “User ID”')
  })
  it('handles an empty container path and negative offsets', () => {
    expect(describeCandidate({ kind: 'structural', container_path: [], structural_path: 'table[1]', confidence: 0.5, reason: '' })).toBe(
      'table[1]',
    )
    expect(describeCandidate({ kind: 'visual_anchor', anchor_text: 'X', dx: -4, dy: 2, confidence: 0.3, reason: '' })).toBe(
      'point offset (-4, +2) px from “X”',
    )
  })
  it('falls back for unknown kinds and logs', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    expect(describeCandidate({ kind: 'ocr' } as unknown as Candidate)).toBe('candidate of kind ocr')
    warn.mockRestore()
  })
})

describe('rankCandidates', () => {
  it('keeps the recorded order as the rank with confidence levels', () => {
    const ranked = rankCandidates(stepTarget(extractStep)?.candidates)
    expect(ranked.map((item) => [item.rank, item.kindLabel, item.level, item.isPrimary])).toEqual([
      [1, 'Text anchor', 'medium', true],
      [2, 'Structural path', 'medium', false],
      [3, 'Visual offset', 'low', false],
    ])
  })
  it('returns an empty list for null or empty input', () => {
    expect(rankCandidates(null)).toEqual([])
    expect(rankCandidates([])).toEqual([])
  })
})

describe('matchedCandidateLabel / isFallbackMatch', () => {
  it('labels primary and fallback matches', () => {
    expect(matchedCandidateLabel({ matched_candidate_rank: 0, matched_candidate_kind: 'label' })).toBe('Primary (label)')
    expect(matchedCandidateLabel({ matched_candidate_rank: 2, matched_candidate_kind: 'structural' })).toBe('Fallback #3 (structural path)')
    expect(isFallbackMatch({ matched_candidate_rank: 2 })).toBe(true)
    expect(isFallbackMatch({ matched_candidate_rank: 0 })).toBe(false)
  })
  it('returns null / false when nothing was resolved', () => {
    expect(matchedCandidateLabel({ matched_candidate_rank: null, matched_candidate_kind: null })).toBeNull()
    expect(isFallbackMatch({ matched_candidate_rank: null })).toBe(false)
  })
})

describe('describeStepAction', () => {
  it('describes the real steps', () => {
    expect(memberBalanceCapability.steps.map(describeStepAction)).toEqual([
      'Run subflow “login”',
      'Type {{member_number}} into Member Number textbox',
      'Click Search button',
      'Read savings balance value into savings_balance',
    ])
  })
  it('describes open, press, select and wait', () => {
    const base = { id: 's', description: 'd' }
    expect(describeStepAction({ ...base, action: 'open', entry_point: 'http://x/login' })).toBe('Open http://x/login')
    expect(describeStepAction({ ...base, action: 'press', key: 'Enter' })).toBe('Press Enter')
    const target = { description: 'Share type', candidates: [] }
    expect(describeStepAction({ ...base, action: 'press', key: 'Tab', target })).toBe('Press Tab in Share type')
    expect(describeStepAction({ ...base, action: 'select', target, option: 'Savings' })).toBe('Select “Savings” in Share type')
    expect(describeStepAction({ ...base, action: 'wait', until: { kind: 'text_visible', pattern: 'x' } })).toBe('Wait for a condition')
  })
})

describe('stepTarget', () => {
  it('returns null for steps without a target', () => {
    expect(stepTarget(memberBalanceCapability.steps[0])).toBeNull()
    expect(stepTarget({ id: 'p', description: '', action: 'press', key: 'Enter', target: null } as Step)).toBeNull()
  })
})

describe('describeRecoveryResponse', () => {
  it('describes each recovery from the vendor profile', () => {
    const recoveries = memberBalanceCapability.recoveries ?? []
    expect(recoveries.map((rule) => describeRecoveryResponse(rule.response))).toEqual([
      'Run subflow “login”, then restart the flow',
      'Dismiss by clicking Acknowledge button',
      'Dismiss (accept / Escape)',
      'Run subflow “login”, then restart the flow',
      'Escalate to a human: Member identity verification requires a human operator.',
    ])
  })
  it('describes retry with and without a backoff', () => {
    expect(describeRecoveryResponse({ kind: 'retry', backoff_ms: 500 })).toBe('Retry the step after 500 ms')
    expect(describeRecoveryResponse({ kind: 'retry' })).toBe('Retry the step after 1000 ms')
    expect(describeRecoveryResponse({ kind: 'subflow', subflow: 'login' })).toBe('Run subflow “login”, then retry the step')
  })
})
