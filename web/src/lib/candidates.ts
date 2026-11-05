/**
 * Readable descriptions of target candidates. The recorder ranks candidates; the engine tries them in
 * list order, so the list order is the rank and the UI never re-sorts it.
 */

import type { Candidate, CandidateKind, RecoveryResponse, Step, StepTrace, TargetSpec } from '../api/types'
import { confidenceLevel, type ConfidenceLevel } from './format'

const KIND_LABELS: Record<CandidateKind, string> = {
  role_name: 'Role and name',
  label: 'Label',
  text_anchor: 'Text anchor',
  structural: 'Structural path',
  visual_anchor: 'Visual offset',
}

const RELATION_WORDS: Record<string, string> = {
  right_of: 'right of',
  below: 'below',
  same_row: 'in the same row as',
  inside: 'inside',
}

export function candidateKindLabel(kind: CandidateKind | string | null | undefined): string {
  if (!kind) return 'Unknown'
  return KIND_LABELS[kind as CandidateKind] ?? kind
}

/** 0 -> "1st", 1 -> "2nd", 2 -> "3rd", 10 -> "11th". */
export function ordinalWord(index: number): string {
  const position = index + 1
  const lastTwo = position % 100
  if (lastTwo >= 11 && lastTwo <= 13) return `${position}th`
  const suffix = ['th', 'st', 'nd', 'rd'][position % 10] ?? 'th'
  return `${position}${suffix}`
}

function signed(value: number): string {
  return value >= 0 ? `+${value}` : String(value)
}

/** One sentence saying what this candidate looks for, in the artifact's own vocabulary. */
export function describeCandidate(candidate: Candidate): string {
  switch (candidate.kind) {
    case 'role_name':
      return `${candidate.role} named “${candidate.name}”${candidate.exact === false ? ' (contains)' : ''}`
    case 'label':
      return `${candidate.role ?? 'control'} labelled “${candidate.label}”`
    case 'text_anchor': {
      const ordinal = candidate.ordinal ? `${ordinalWord(candidate.ordinal)} ` : ''
      const relation = RELATION_WORDS[candidate.relation] ?? candidate.relation
      return `${ordinal}${candidate.role ?? 'node'} ${relation} “${candidate.anchor_text}”`
    }
    case 'structural': {
      const container = candidate.container_path.length ? `${candidate.container_path.join(' › ')} › ` : ''
      return `${container}${candidate.structural_path}`
    }
    case 'visual_anchor':
      return `point offset (${signed(candidate.dx)}, ${signed(candidate.dy)}) px from “${candidate.anchor_text}”`
    default:
      return describeUnknownCandidate(candidate)
  }
}

function describeUnknownCandidate(candidate: never): string {
  const kind = (candidate as { kind?: string }).kind ?? 'unknown'
  console.warn('describeCandidate: unrecognized candidate kind', kind)
  return `candidate of kind ${kind}`
}

export interface RankedCandidate {
  rank: number
  candidate: Candidate
  description: string
  kindLabel: string
  level: ConfidenceLevel
  isPrimary: boolean
}

export function rankCandidates(candidates: Candidate[] | null | undefined): RankedCandidate[] {
  if (!candidates) return []
  return candidates.map((candidate, index) => ({
    rank: index + 1,
    candidate,
    description: describeCandidate(candidate),
    kindLabel: candidateKindLabel(candidate.kind),
    level: confidenceLevel(candidate.confidence),
    isPrimary: index === 0,
  }))
}

/** "Primary (label)" or "Fallback #2 (structural path)" for a step trace; null when nothing was resolved. */
export function matchedCandidateLabel(trace: Pick<StepTrace, 'matched_candidate_rank' | 'matched_candidate_kind'>): string | null {
  if (trace.matched_candidate_rank === null || trace.matched_candidate_rank === undefined) return null
  const kind = candidateKindLabel(trace.matched_candidate_kind).toLowerCase()
  if (trace.matched_candidate_rank === 0) return `Primary (${kind})`
  return `Fallback #${trace.matched_candidate_rank + 1} (${kind})`
}

export function isFallbackMatch(trace: Pick<StepTrace, 'matched_candidate_rank'>): boolean {
  return typeof trace.matched_candidate_rank === 'number' && trace.matched_candidate_rank > 0
}

/** What a step does, as a short phrase: `Type {{member_number}} into Member Number textbox`. */
export function describeStepAction(step: Step): string {
  switch (step.action) {
    case 'open':
      return `Open ${step.entry_point}`
    case 'click':
      return `Click ${step.target.description}`
    case 'type':
      return `Type ${step.value} into ${step.target.description}`
    case 'press':
      return `Press ${step.key}${step.target ? ` in ${step.target.description}` : ''}`
    case 'select':
      return `Select “${step.option}” in ${step.target.description}`
    case 'extract':
      return `Read ${step.target.description} into ${step.output}`
    case 'wait':
      return 'Wait for a condition'
    case 'subflow':
      return `Run subflow “${step.subflow}”`
  }
}

export function stepTarget(step: Step): TargetSpec | null {
  return 'target' in step && step.target ? step.target : null
}

export function describeRecoveryResponse(response: RecoveryResponse): string {
  switch (response.kind) {
    case 'dismiss':
      return response.target ? `Dismiss by clicking ${response.target.description}` : 'Dismiss (accept / Escape)'
    case 'retry':
      return `Retry the step after ${response.backoff_ms ?? 1000} ms`
    case 'subflow':
      return `Run subflow “${response.subflow}”, then ${response.then === 'restart' ? 'restart the flow' : 'retry the step'}`
    case 'escalate':
      return `Escalate to a human: ${response.reason}`
  }
}
