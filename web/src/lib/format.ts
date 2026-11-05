/**
 * Display formatters. Every visual rule about numbers, durations and statuses lives here, with a unit
 * test, so the same value always renders the same way on every screen.
 */

import type {
  AnyRunResult,
  DiscoverySummary,
  RunErrorResult,
  RunListItem,
  RunResult,
  RunState,
  RunStatus,
  ValueType,
} from '../api/types'

export const EMPTY_VALUE = '—'

// ---------------------------------------------------------------- statuses

/** Visual tone of a badge. Business outcomes are answers, so they get an informational tone, not a warning. */
export type Tone = 'success' | 'outcome' | 'escalated' | 'failed' | 'running' | 'attention' | 'neutral'

export interface Badge {
  label: string
  tone: Tone
  /** Longer explanation for a tooltip or screen readers. */
  hint: string
}

const STATUS_BADGES: Record<RunStatus, Badge> = {
  success: { label: 'Success', tone: 'success', hint: 'Checkpoint met; declared outputs returned.' },
  business_outcome: {
    label: 'Business outcome',
    tone: 'outcome',
    hint: 'A declared business result such as MEMBER_NOT_FOUND. A legitimate answer, not an error.',
  },
  escalated: { label: 'Escalated', tone: 'escalated', hint: 'A human was brought in and the run ended in human hands.' },
  failed: { label: 'Failed', tone: 'failed', hint: 'Hard failure with step, expected, observed and evidence.' },
  completed: { label: 'Completed', tone: 'success', hint: 'Discovery reached the goal and recorded a capability.' },
  stuck: { label: 'Stuck', tone: 'escalated', hint: 'Discovery could not make progress.' },
  escalated_abort: { label: 'Aborted by operator', tone: 'escalated', hint: 'Discovery escalated and the operator aborted.' },
  budget_exhausted: { label: 'Step budget used', tone: 'escalated', hint: 'Discovery ran out of steps before the goal.' },
  error: { label: 'Error', tone: 'failed', hint: 'The run stopped on an internal error.' },
}

const STATE_BADGES: Record<RunState, Badge> = {
  running: { label: 'Running', tone: 'running', hint: 'Automation holds the session.' },
  waiting_for_operator: {
    label: 'Needs operator',
    tone: 'attention',
    hint: 'Paused on an intervention; a human must take control or decide.',
  },
  finished: { label: 'Finished', tone: 'neutral', hint: 'The run has ended.' },
  error: { label: 'Error', tone: 'failed', hint: 'The run stopped on an internal error.' },
}

const UNKNOWN_BADGE: Badge = { label: 'Unknown', tone: 'neutral', hint: 'No status reported.' }

export function statusBadge(status: RunStatus | string | null | undefined): Badge {
  if (!status) return UNKNOWN_BADGE
  return STATUS_BADGES[status as RunStatus] ?? { label: humanize(status), tone: 'neutral', hint: status }
}

export function stateBadge(state: RunState | string | null | undefined): Badge {
  if (!state) return UNKNOWN_BADGE
  return STATE_BADGES[state as RunState] ?? { label: humanize(state), tone: 'neutral', hint: state }
}

/** The single badge a run row shows: its live state while active, its terminal status once finished. */
export function runBadge(item: Pick<RunListItem, 'state' | 'status'>): Badge {
  if (item.state === 'running' || item.state === 'waiting_for_operator') return stateBadge(item.state)
  if (item.status) return statusBadge(item.status)
  return stateBadge(item.state)
}

export function isActiveState(state: RunState | string | null | undefined): boolean {
  return state === 'running' || state === 'waiting_for_operator'
}

// ---------------------------------------------------------------- text

/** `business_outcome` -> `Business outcome`; `MEMBER_NOT_FOUND` stays as is (codes are shown verbatim). */
export function humanize(identifier: string | null | undefined): string {
  if (!identifier) return ''
  if (/^[A-Z0-9_]+$/.test(identifier)) return identifier
  const spaced = identifier.replace(/[_-]+/g, ' ').trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function truncate(text: string | null | undefined, maxLength: number): string {
  if (!text) return ''
  if (text.length <= maxLength) return text
  return `${text.slice(0, Math.max(0, maxLength - 1)).trimEnd()}…`
}

// ---------------------------------------------------------------- values

const IDENTIFIER_NAME = /(_id|_no|_number|_code|_ref|^id)$/i

/** True for names whose values are identifiers and must never get thousands separators. */
export function isIdentifierName(name: string | null | undefined): boolean {
  return Boolean(name && IDENTIFIER_NAME.test(name))
}

/**
 * Groups the integer part of a decimal string without converting it to a float, so "9870.12"
 * becomes "9,870.12" and precision is never lost. Non-numeric strings are returned unchanged.
 */
export function groupDecimalString(value: string): string {
  const match = /^(-?)(\d+)(\.\d+)?$/.exec(value.trim())
  if (!match) return value
  const [, sign, integerPart, fraction = ''] = match
  const grouped = integerPart.replace(/\B(?=(\d{3})+(?!\d))/g, ',')
  return `${sign}${grouped}${fraction}`
}

/** Renders an output or input value by declared type and name. Identifiers stay plain. */
export function formatValue(value: unknown, type?: ValueType | string | null, name?: string | null): string {
  if (value === null || value === undefined || value === '') return EMPTY_VALUE
  if (typeof value === 'boolean') return value ? 'Yes' : 'No'
  const text = typeof value === 'object' ? JSON.stringify(value) : String(value)
  if (isIdentifierName(name)) return text
  if (type === 'decimal' || type === 'integer') return groupDecimalString(text)
  return text
}

export function formatConfidence(confidence: number | null | undefined): string {
  if (confidence === null || confidence === undefined || Number.isNaN(confidence)) return EMPTY_VALUE
  return `${Math.round(confidence * 100)}%`
}

export type ConfidenceLevel = 'high' | 'medium' | 'low'

export function confidenceLevel(confidence: number): ConfidenceLevel {
  if (confidence >= 0.8) return 'high'
  if (confidence >= 0.5) return 'medium'
  return 'low'
}

// ---------------------------------------------------------------- time

export function parseTime(iso: string | null | undefined): number | null {
  if (!iso) return null
  const millis = Date.parse(iso)
  return Number.isNaN(millis) ? null : millis
}

/** 183 -> "183 ms", 4898 -> "4.9 s", 68400 -> "1 m 08 s", 3_726_000 -> "1 h 02 m". */
export function formatDurationMs(milliseconds: number | null | undefined): string {
  if (milliseconds === null || milliseconds === undefined || Number.isNaN(milliseconds) || milliseconds < 0) {
    return EMPTY_VALUE
  }
  if (milliseconds < 1000) return `${Math.round(milliseconds)} ms`
  const totalSeconds = milliseconds / 1000
  if (totalSeconds < 60) return `${totalSeconds.toFixed(1)} s`
  const wholeSeconds = Math.floor(totalSeconds)
  const hours = Math.floor(wholeSeconds / 3600)
  const minutes = Math.floor((wholeSeconds % 3600) / 60)
  const seconds = wholeSeconds % 60
  if (hours > 0) return `${hours} h ${String(minutes).padStart(2, '0')} m`
  return `${minutes} m ${String(seconds).padStart(2, '0')} s`
}

/** Duration between two ISO timestamps; an open run counts up to `nowMillis`. */
export function formatDuration(
  startedAt: string | null | undefined,
  finishedAt: string | null | undefined,
  nowMillis: number = Date.now(),
): string {
  const start = parseTime(startedAt)
  if (start === null) return EMPTY_VALUE
  const end = parseTime(finishedAt) ?? nowMillis
  return formatDurationMs(end - start)
}

const TIMESTAMP_FORMAT = new Intl.DateTimeFormat(undefined, {
  year: 'numeric',
  month: 'short',
  day: '2-digit',
  hour: '2-digit',
  minute: '2-digit',
  second: '2-digit',
})

const CLOCK_FORMAT = new Intl.DateTimeFormat(undefined, { hour: '2-digit', minute: '2-digit', second: '2-digit' })

export function formatTimestamp(iso: string | null | undefined): string {
  const millis = parseTime(iso)
  return millis === null ? EMPTY_VALUE : TIMESTAMP_FORMAT.format(millis)
}

export function formatClock(iso: string | null | undefined): string {
  const millis = parseTime(iso)
  return millis === null ? EMPTY_VALUE : CLOCK_FORMAT.format(millis)
}

/** "just now", "4 min ago", "3 h ago", "2 d ago" relative to `nowMillis`. */
export function formatRelative(iso: string | null | undefined, nowMillis: number = Date.now()): string {
  const millis = parseTime(iso)
  if (millis === null) return EMPTY_VALUE
  const seconds = Math.max(0, Math.round((nowMillis - millis) / 1000))
  if (seconds < 45) return 'just now'
  const minutes = Math.round(seconds / 60)
  if (minutes < 60) return `${minutes} min ago`
  const hours = Math.round(minutes / 60)
  if (hours < 48) return `${hours} h ago`
  return `${Math.round(hours / 24)} d ago`
}

// ---------------------------------------------------------------- headlines

export function isDiscoverySummary(result: AnyRunResult | null | undefined): result is DiscoverySummary {
  return Boolean(result && (result as DiscoverySummary).mode === 'discovery')
}

export function isRunResult(result: AnyRunResult | null | undefined): result is RunResult {
  return Boolean(result && !isDiscoverySummary(result) && 'capability_version' in result)
}

/** A crashed or unstartable run: `{"status": "error", "message": ...}`. */
export function isRunError(result: AnyRunResult | null | undefined): result is RunErrorResult {
  return Boolean(result && result.status === 'error' && !isDiscoverySummary(result) && !isRunResult(result))
}

function outputsHeadline(outputs: Record<string, unknown>): string {
  const entries = Object.entries(outputs)
  if (entries.length === 0) return 'Success, no outputs'
  return entries.map(([name, value]) => `${name} ${formatValue(value, null, name)}`).join(', ')
}

/** A one-line summary derived from a result, used when the API headline is missing. */
export function headlineFromResult(result: AnyRunResult | null | undefined): string {
  if (!result) return ''
  if (isRunError(result)) return `error: ${result.message}`
  if (isDiscoverySummary(result)) {
    const recorded = result.capability ? `recorded ${result.capability}` : (result.reason ?? '')
    return `${humanize(result.status)}${recorded ? `: ${recorded}` : ''}`
  }
  switch (result.status) {
    case 'success':
      return outputsHeadline(result.outputs ?? {})
    case 'business_outcome':
      return result.code
    case 'escalated':
      return `Escalated: ${result.reason}`
    case 'failed':
      return result.failure.step_id ? `${result.failure.code} at ${result.failure.step_id}` : result.failure.code
  }
}

export function runHeadline(item: Pick<RunListItem, 'headline' | 'state'>, result?: AnyRunResult | null): string {
  if (item.headline) return item.headline
  const derived = headlineFromResult(result)
  if (derived) return derived
  return item.state === 'running' ? 'In progress' : EMPTY_VALUE
}
