import { describe, expect, it } from 'vitest'
import {
  businessOutcomeResult,
  discoverySummary,
  escalatedResult,
  failedResult,
  invalidInputResult,
  successResult,
} from '../fixtures'
import {
  confidenceLevel,
  EMPTY_VALUE,
  formatClock,
  formatConfidence,
  formatDuration,
  formatDurationMs,
  formatRelative,
  formatTimestamp,
  formatValue,
  groupDecimalString,
  headlineFromResult,
  humanize,
  isActiveState,
  isDiscoverySummary,
  isIdentifierName,
  isRunResult,
  parseTime,
  runBadge,
  runHeadline,
  stateBadge,
  statusBadge,
  truncate,
} from './format'

describe('statusBadge', () => {
  it('gives each result class its own tone', () => {
    expect(statusBadge('success').tone).toBe('success')
    expect(statusBadge('business_outcome').tone).toBe('outcome')
    expect(statusBadge('escalated').tone).toBe('escalated')
    expect(statusBadge('failed').tone).toBe('failed')
  })
  it('never styles a business outcome as a failure', () => {
    const badge = statusBadge('business_outcome')
    expect(badge.tone).not.toBe('failed')
    expect(badge.hint).toMatch(/not an error/i)
  })
  it('covers discovery statuses', () => {
    expect(statusBadge('completed').tone).toBe('success')
    expect(statusBadge('stuck').tone).toBe('escalated')
    expect(statusBadge('error').tone).toBe('failed')
  })
  it('handles null and unknown values', () => {
    expect(statusBadge(null).label).toBe('Unknown')
    expect(statusBadge('weird_state')).toMatchObject({ label: 'Weird state', tone: 'neutral' })
  })
})

describe('stateBadge', () => {
  it('maps live states', () => {
    expect(stateBadge('running').tone).toBe('running')
    expect(stateBadge('waiting_for_operator')).toMatchObject({ label: 'Needs operator', tone: 'attention' })
    expect(stateBadge('finished').tone).toBe('neutral')
  })
  it('handles undefined', () => {
    expect(stateBadge(undefined).label).toBe('Unknown')
  })
})

describe('runBadge', () => {
  it('shows the live state while active', () => {
    expect(runBadge({ state: 'running', status: null }).label).toBe('Running')
    expect(runBadge({ state: 'waiting_for_operator', status: null }).label).toBe('Needs operator')
  })
  it('shows the terminal status once finished', () => {
    expect(runBadge({ state: 'finished', status: 'business_outcome' }).label).toBe('Business outcome')
  })
  it('falls back to the state when status is missing', () => {
    expect(runBadge({ state: 'error', status: null }).label).toBe('Error')
  })
})

describe('isActiveState', () => {
  it('is true only for running and waiting', () => {
    expect(isActiveState('running')).toBe(true)
    expect(isActiveState('waiting_for_operator')).toBe(true)
    expect(isActiveState('finished')).toBe(false)
    expect(isActiveState(null)).toBe(false)
  })
})

describe('humanize', () => {
  it('turns snake case into a sentence', () => {
    expect(humanize('business_outcome')).toBe('Business outcome')
  })
  it('keeps codes verbatim', () => {
    expect(humanize('MEMBER_NOT_FOUND')).toBe('MEMBER_NOT_FOUND')
  })
  it('returns empty for empty input', () => {
    expect(humanize('')).toBe('')
    expect(humanize(null)).toBe('')
  })
})

describe('truncate', () => {
  it('leaves short text alone', () => {
    expect(truncate('abc', 5)).toBe('abc')
  })
  it('cuts long text with an ellipsis at the limit', () => {
    expect(truncate('abcdefgh', 5)).toBe('abcd…')
  })
  it('handles null', () => {
    expect(truncate(null, 3)).toBe('')
  })
})

describe('isIdentifierName', () => {
  it('recognizes identifier columns', () => {
    expect(isIdentifierName('member_number')).toBe(true)
    expect(isIdentifierName('account_id')).toBe(true)
    expect(isIdentifierName('Share_Code')).toBe(true)
  })
  it('does not flag measures', () => {
    expect(isIdentifierName('savings_balance')).toBe(false)
    expect(isIdentifierName(null)).toBe(false)
  })
})

describe('groupDecimalString', () => {
  it('groups the integer part without float conversion', () => {
    expect(groupDecimalString('9870.12')).toBe('9,870.12')
    expect(groupDecimalString('1234567.005')).toBe('1,234,567.005')
  })
  it('keeps negatives and short values', () => {
    expect(groupDecimalString('-1250.00')).toBe('-1,250.00')
    expect(groupDecimalString('12')).toBe('12')
  })
  it('returns non-numeric strings unchanged (already formatted or text)', () => {
    expect(groupDecimalString('1,250.00')).toBe('1,250.00')
    expect(groupDecimalString('')).toBe('')
  })
})

describe('formatValue', () => {
  it('groups decimal measures', () => {
    expect(formatValue('9870.12', 'decimal', 'savings_balance')).toBe('9,870.12')
  })
  it('never groups identifiers, whatever the type', () => {
    expect(formatValue('1208925', 'integer', 'member_number')).toBe('1208925')
  })
  it('renders empties as a dash', () => {
    expect(formatValue(null)).toBe(EMPTY_VALUE)
    expect(formatValue(undefined)).toBe(EMPTY_VALUE)
    expect(formatValue('')).toBe(EMPTY_VALUE)
  })
  it('renders booleans and objects', () => {
    expect(formatValue(true)).toBe('Yes')
    expect(formatValue({ a: 1 })).toBe('{"a":1}')
  })
  it('leaves untyped strings alone', () => {
    expect(formatValue('9870.12')).toBe('9870.12')
  })
})

describe('formatConfidence / confidenceLevel', () => {
  it('formats as a percentage', () => {
    expect(formatConfidence(0.85)).toBe('85%')
    expect(formatConfidence(0)).toBe('0%')
  })
  it('handles null and NaN', () => {
    expect(formatConfidence(null)).toBe(EMPTY_VALUE)
    expect(formatConfidence(Number.NaN)).toBe(EMPTY_VALUE)
  })
  it('buckets at the 0.8 and 0.5 boundaries', () => {
    expect(confidenceLevel(0.8)).toBe('high')
    expect(confidenceLevel(0.79)).toBe('medium')
    expect(confidenceLevel(0.5)).toBe('medium')
    expect(confidenceLevel(0.3)).toBe('low')
  })
})

describe('parseTime', () => {
  it('parses ISO timestamps', () => {
    expect(parseTime('2026-09-28T17:50:27.094398Z')).toBe(Date.parse('2026-09-28T17:50:27.094Z'))
  })
  it('returns null for empty or invalid', () => {
    expect(parseTime(null)).toBeNull()
    expect(parseTime('not a date')).toBeNull()
  })
})

describe('formatDurationMs', () => {
  it('uses ms below a second', () => {
    expect(formatDurationMs(183)).toBe('183 ms')
    expect(formatDurationMs(0)).toBe('0 ms')
  })
  it('uses one decimal of seconds below a minute', () => {
    expect(formatDurationMs(4898)).toBe('4.9 s')
    expect(formatDurationMs(1000)).toBe('1.0 s')
  })
  it('uses minutes and padded seconds', () => {
    expect(formatDurationMs(68_400)).toBe('1 m 08 s')
  })
  it('uses hours and padded minutes', () => {
    expect(formatDurationMs(3_726_000)).toBe('1 h 02 m')
  })
  it('renders invalid durations as a dash', () => {
    expect(formatDurationMs(null)).toBe(EMPTY_VALUE)
    expect(formatDurationMs(-5)).toBe(EMPTY_VALUE)
  })
})

describe('formatDuration', () => {
  it('measures a finished run from the real evidence', () => {
    expect(formatDuration(successResult.started_at, successResult.finished_at)).toBe('4.9 s')
  })
  it('counts an open run up to now', () => {
    const start = '2026-01-01T00:00:00Z'
    expect(formatDuration(start, null, Date.parse(start) + 2500)).toBe('2.5 s')
  })
  it('renders a missing start as a dash', () => {
    expect(formatDuration(null, null)).toBe(EMPTY_VALUE)
  })
})

describe('formatTimestamp / formatClock', () => {
  it('formats valid timestamps', () => {
    expect(formatTimestamp('2026-09-28T17:50:27Z')).toMatch(/2026/)
    expect(formatClock('2026-09-28T17:50:27Z')).toMatch(/\d{2}.\d{2}.\d{2}/)
  })
  it('renders missing timestamps as a dash', () => {
    expect(formatTimestamp(null)).toBe(EMPTY_VALUE)
    expect(formatClock('')).toBe(EMPTY_VALUE)
  })
})

describe('formatRelative', () => {
  const now = Date.parse('2026-11-05T12:00:00Z')
  it('describes recent and old times', () => {
    expect(formatRelative('2026-11-05T11:59:50Z', now)).toBe('just now')
    expect(formatRelative('2026-11-05T11:56:00Z', now)).toBe('4 min ago')
    expect(formatRelative('2026-11-05T09:00:00Z', now)).toBe('3 h ago')
    expect(formatRelative('2026-11-01T12:00:00Z', now)).toBe('4 d ago')
  })
  it('clamps future times to just now and handles null', () => {
    expect(formatRelative('2026-11-05T12:05:00Z', now)).toBe('just now')
    expect(formatRelative(null, now)).toBe(EMPTY_VALUE)
  })
})

describe('isDiscoverySummary / isRunResult', () => {
  it('tells discovery summaries and replay results apart', () => {
    expect(isDiscoverySummary(discoverySummary)).toBe(true)
    expect(isRunResult(discoverySummary)).toBe(false)
    expect(isRunResult(successResult)).toBe(true)
    expect(isDiscoverySummary(successResult)).toBe(false)
  })
  it('is false for null', () => {
    expect(isDiscoverySummary(null)).toBe(false)
    expect(isRunResult(undefined)).toBe(false)
  })
})

describe('headlineFromResult', () => {
  it('summarizes each result class from real evidence', () => {
    expect(headlineFromResult(successResult)).toBe('savings_balance 9870.12')
    expect(headlineFromResult(businessOutcomeResult)).toBe('MEMBER_NOT_FOUND')
    expect(headlineFromResult(failedResult)).toBe('recovery_exhausted at login_open')
    expect(headlineFromResult(invalidInputResult)).toBe('invalid_input')
    expect(headlineFromResult(escalatedResult)).toMatch(/^Escalated: Member identity verification/)
    expect(headlineFromResult(discoverySummary)).toBe('Completed: recorded coreone.member_balance@1.0.0')
  })
  it('returns empty for no result', () => {
    expect(headlineFromResult(null)).toBe('')
  })
})

describe('runHeadline', () => {
  it('prefers the API headline', () => {
    expect(runHeadline({ headline: 'savings_balance 1250.00', state: 'finished' }, failedResult)).toBe('savings_balance 1250.00')
  })
  it('derives one from the result when missing', () => {
    expect(runHeadline({ headline: null, state: 'finished' }, businessOutcomeResult)).toBe('MEMBER_NOT_FOUND')
  })
  it('says in progress for a running run with nothing yet', () => {
    expect(runHeadline({ headline: null, state: 'running' })).toBe('In progress')
    expect(runHeadline({ headline: null, state: 'finished' })).toBe(EMPTY_VALUE)
  })
})
