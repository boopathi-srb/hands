/**
 * Folds a run's event stream (events.jsonl as served by /api/runs/{id}/events) into a timeline the
 * run page renders: steps with status, matched candidate, policy verdict and recoveries; model
 * decisions for discovery; outcomes, escalations, human actions, restarts and the final result.
 * Plumbing events (observed, action_attempted, action_result, control transfers) attach to the
 * step they belong to or are dropped, so the timeline reads as what happened, not how.
 */

import type { RunEvent } from '../api/types'
import { appendHumanAction, type HumanActionView } from './liveInput'

export type StepStatus = 'running' | 'ok' | 'recovered' | 'human' | 'failed' | 'skipped'

export interface PolicyView {
  verdict: string
  risk: string | null
  rule: string | null
  reason: string | null
}

export interface StepEntry {
  type: 'step'
  key: string
  seq: number
  ts: string
  stepId: string
  action: string | null
  description: string | null
  risk: string | null
  depth: number
  status: StepStatus
  recoveries: RecoveryView[]
  policy: PolicyView | null
  matchedRank: number | null
  matchedKind: string | null
  ambiguous: boolean
  output: string | null
  failedCheck: string | null
  finishedTs: string | null
}

export interface RecoveryView {
  name: string
  response: string | null
  applications: number | null
  maxApplications: number | null
}

export interface DecisionEntry {
  type: 'decision'
  key: string
  seq: number
  ts: string
  step: number | null
  actionKind: string
  actionSummary: string
  rationale: string | null
  expectedResult: string | null
  error: string | null
  latencyMs: number | null
  inputTokens: number | null
  outputTokens: number | null
  policy: PolicyView | null
  screenshot: string | null
}

export interface NoticeEntry {
  type: 'notice'
  key: string
  seq: number
  ts: string
  tone: 'outcome' | 'escalated' | 'failed' | 'neutral' | 'success' | 'attention'
  title: string
  detail: string | null
  stepId: string | null
  screenshot: string | null
}

export interface HumanEntry {
  type: 'human'
  key: string
  seq: number
  ts: string
  operatorId: string | null
  actions: HumanActionView[]
}

export type TimelineEntry = StepEntry | DecisionEntry | NoticeEntry | HumanEntry

interface Builder {
  entries: TimelineEntry[]
  openSteps: StepEntry[]
  depth: number
  pendingScreenshot: string | null
  noticedInterventions: string[]
  resolvedInterventions: string[]
}

const str = (value: unknown): string | null => (typeof value === 'string' && value !== '' ? value : null)
const num = (value: unknown): number | null => (typeof value === 'number' && !Number.isNaN(value) ? value : null)

function lastStep(builder: Builder, stepId: string | null): StepEntry | null {
  if (!stepId) return builder.openSteps[builder.openSteps.length - 1] ?? null
  for (let index = builder.openSteps.length - 1; index >= 0; index -= 1) {
    if (builder.openSteps[index].stepId === stepId) return builder.openSteps[index]
  }
  for (let index = builder.entries.length - 1; index >= 0; index -= 1) {
    const entry = builder.entries[index]
    if (entry.type === 'step' && entry.stepId === stepId) return entry
  }
  return null
}

function policyFrom(data: Record<string, unknown>): PolicyView {
  return { verdict: str(data.verdict) ?? 'unknown', risk: str(data.risk), rule: str(data.rule), reason: str(data.reason) }
}

function asStepStatus(value: unknown): StepStatus {
  const allowed: StepStatus[] = ['ok', 'recovered', 'human', 'failed', 'skipped']
  return allowed.includes(value as StepStatus) ? (value as StepStatus) : 'ok'
}

function onStepStarted(builder: Builder, event: RunEvent): void {
  const data = event.data
  const entry: StepEntry = {
    type: 'step',
    key: `step-${event.seq}`,
    seq: event.seq,
    ts: event.ts,
    stepId: str(data.step_id) ?? 'step',
    action: str(data.action),
    description: str(data.description),
    risk: str(data.risk),
    depth: builder.depth,
    status: 'running',
    recoveries: [],
    policy: null,
    matchedRank: null,
    matchedKind: null,
    ambiguous: false,
    output: null,
    failedCheck: null,
    finishedTs: null,
  }
  builder.entries.push(entry)
  builder.openSteps.push(entry)
}

function onStepFinished(builder: Builder, event: RunEvent): void {
  const stepId = str(event.data.step_id)
  const step = lastStep(builder, stepId)
  if (!step) return
  step.status = asStepStatus(event.data.status)
  step.finishedTs = event.ts
  builder.openSteps = builder.openSteps.filter((open) => open !== step)
}

function onPolicyDecision(builder: Builder, event: RunEvent): void {
  const policy = policyFrom(event.data)
  const discoveryStep = num(event.data.step)
  if (discoveryStep !== null) {
    const decision = findDecision(builder, discoveryStep)
    if (decision) decision.policy = policy
    else if (policy.verdict !== 'allow') pushPolicyNotice(builder, event, policy)
    return
  }
  const step = lastStep(builder, str(event.data.step_id))
  if (step) step.policy = policy
  if (policy.verdict !== 'allow' && !step) pushPolicyNotice(builder, event, policy)
}

function pushPolicyNotice(builder: Builder, event: RunEvent, policy: PolicyView): void {
  builder.entries.push({
    type: 'notice',
    key: `policy-${event.seq}`,
    seq: event.seq,
    ts: event.ts,
    tone: policy.verdict === 'deny' ? 'failed' : 'attention',
    title: `Policy ${policy.verdict}`,
    detail: policy.reason,
    stepId: str(event.data.step_id),
    screenshot: null,
  })
}

function findDecision(builder: Builder, step: number): DecisionEntry | null {
  for (let index = builder.entries.length - 1; index >= 0; index -= 1) {
    const entry = builder.entries[index]
    if (entry.type === 'decision' && entry.step === step) return entry
  }
  return null
}

/** `type {{teller.username}} into n12`, `click n18`, `extract n49 as savings_balance`, `done`. */
export function summarizeDecisionAction(action: Record<string, unknown> | null | undefined): string {
  if (!action) return 'no action'
  const kind = str(action.kind) ?? 'action'
  const node = str(action.node_ref)
  const onNode = node ? ` ${node}` : ''
  switch (kind) {
    case 'type':
      return `type ${str(action.value) ?? ''} into${onNode || ' field'}`.replace(/\s+/g, ' ').trim()
    case 'extract':
      return `extract${onNode}${str(action.output_name) ? ` as ${str(action.output_name)}` : ''}`
    case 'press':
      return `press ${str(action.key) ?? 'key'}${onNode ? ` on${onNode}` : ''}`
    case 'select':
      return `select “${str(action.option) ?? ''}”${onNode ? ` in${onNode}` : ''}`
    default:
      return `${kind}${onNode}`
  }
}

function onDecision(builder: Builder, event: RunEvent): void {
  const data = event.data
  const action = (data.action ?? null) as Record<string, unknown> | null
  builder.entries.push({
    type: 'decision',
    key: `decision-${event.seq}`,
    seq: event.seq,
    ts: event.ts,
    step: num(data.step),
    actionKind: str(action?.kind) ?? 'action',
    actionSummary: summarizeDecisionAction(action),
    rationale: str(data.rationale),
    expectedResult: str(data.expected_result),
    error: str(data.error),
    latencyMs: num(data.latency_ms),
    inputTokens: num(data.input_tokens),
    outputTokens: num(data.output_tokens),
    policy: null,
    screenshot: builder.pendingScreenshot,
  })
  builder.pendingScreenshot = null
}

function onRecovery(builder: Builder, event: RunEvent): void {
  const step = lastStep(builder, str(event.data.step_id))
  const recovery: RecoveryView = {
    name: str(event.data.recovery) ?? 'recovery',
    response: str(event.data.response),
    applications: num(event.data.applications),
    maxApplications: num(event.data.max_applications),
  }
  if (step) step.recoveries.push(recovery)
  else notice(builder, event, 'neutral', `Recovery ${recovery.name}`, recovery.response)
}

function notice(
  builder: Builder,
  event: RunEvent,
  tone: NoticeEntry['tone'],
  title: string,
  detail: string | null,
  screenshot: string | null = null,
): void {
  builder.entries.push({
    type: 'notice',
    key: `${event.kind}-${event.seq}`,
    seq: event.seq,
    ts: event.ts,
    tone,
    title,
    detail,
    stepId: str(event.data.step_id),
    screenshot,
  })
}

function onEscalation(builder: Builder, event: RunEvent): void {
  const interventionId = str(event.data.intervention_id) ?? `seq-${event.seq}`
  if (builder.noticedInterventions.includes(interventionId)) return
  builder.noticedInterventions.push(interventionId)
  notice(builder, event, 'attention', 'Escalated to an operator', str(event.data.reason), str(event.data.screenshot_path))
}

function onResolution(builder: Builder, event: RunEvent): void {
  const interventionId = str(event.data.intervention_id) ?? `seq-${event.seq}`
  if (builder.resolvedInterventions.includes(interventionId)) return
  builder.resolvedInterventions.push(interventionId)
  const outcome = str(event.data.outcome) ?? 'resolved'
  const operator = str(event.data.operator_id)
  const note = str(event.data.note)
  const detail = [operator ? `by ${operator}` : null, note].filter(Boolean).join(' — ') || null
  const tone = outcome === 'abort' ? 'escalated' : 'success'
  notice(builder, event, tone, `Operator handed back: ${outcome.replace(/_/g, ' ')}`, detail)
}

function onHumanAction(builder: Builder, event: RunEvent): void {
  const data = event.data
  const action: HumanActionView = {
    kind: str(data.action_kind) ?? str(data.kind) ?? 'action',
    text_length: num(data.text_length),
    key: str(data.key),
    node_role: str(data.node_role),
    node_name: str(data.node_name) ?? '',
  }
  const previous = builder.entries[builder.entries.length - 1]
  if (previous && previous.type === 'human') {
    previous.actions = appendHumanAction(previous.actions, action)
    return
  }
  builder.entries.push({
    type: 'human',
    key: `human-${event.seq}`,
    seq: event.seq,
    ts: event.ts,
    operatorId: str(data.operator_id),
    actions: [action],
  })
}

function onRunFinished(builder: Builder, event: RunEvent): void {
  const data = event.data
  const status = str(data.status) ?? 'finished'
  const toneByStatus: Record<string, NoticeEntry['tone']> = {
    success: 'success',
    completed: 'success',
    business_outcome: 'outcome',
    escalated: 'escalated',
    stuck: 'escalated',
    failed: 'failed',
    error: 'failed',
  }
  const detail = str(data.code) ?? str(data.reason) ?? str(data.error)
  notice(builder, event, toneByStatus[status] ?? 'neutral', `Run finished: ${status.replace(/_/g, ' ')}`, detail)
  for (const open of builder.openSteps) if (open.status === 'running') open.status = status === 'success' ? 'ok' : 'failed'
  builder.openSteps = []
}

function onCheckpoint(builder: Builder, event: RunEvent): void {
  if (event.data.ok !== false) return
  const step = lastStep(builder, str(event.data.step_id))
  if (step) step.failedCheck = str(event.data.check)
}

function onTargetResolved(builder: Builder, event: RunEvent): void {
  const step = lastStep(builder, str(event.data.step_id))
  if (!step) return
  step.matchedRank = num(event.data.rank)
  step.matchedKind = str(event.data.candidate_kind)
  step.ambiguous = event.data.ambiguous === true
}

const HANDLERS: Record<string, (builder: Builder, event: RunEvent) => void> = {
  step_started: onStepStarted,
  step_finished: onStepFinished,
  subflow_started: (builder) => {
    builder.depth += 1
  },
  subflow_finished: (builder) => {
    builder.depth = Math.max(0, builder.depth - 1)
  },
  policy_decision: onPolicyDecision,
  target_resolved: onTargetResolved,
  checkpoint: onCheckpoint,
  decision: onDecision,
  recovery_applied: onRecovery,
  output_extracted: (builder, event) => {
    const step = lastStep(builder, str(event.data.step_id))
    if (step) step.output = str(event.data.output)
  },
  outcome_detected: (builder, event) =>
    notice(builder, event, 'outcome', `Business outcome ${str(event.data.code) ?? ''}`.trim(), str(event.data.message)),
  escalation_requested: onEscalation,
  escalation_raised: onEscalation,
  escalation_resolved: onResolution,
  escalation_handled: onResolution,
  human_action: onHumanAction,
  run_restarted: (builder, event) =>
    notice(builder, event, 'neutral', 'Flow restarted from the first step', str(event.data.reason)),
  observation: (builder, event) => {
    const screenshot = str(event.data.screenshot)
    if (screenshot) builder.pendingScreenshot = screenshot
  },
  run_finished: onRunFinished,
}

export function buildTimeline(events: RunEvent[] | null | undefined): TimelineEntry[] {
  const builder: Builder = {
    entries: [],
    openSteps: [],
    depth: 0,
    pendingScreenshot: null,
    noticedInterventions: [],
    resolvedInterventions: [],
  }
  for (const event of events ?? []) {
    const handler = HANDLERS[event.kind]
    if (handler) handler(builder, event)
  }
  return builder.entries
}

/** The step currently running (innermost), for the one-line live status. */
export function currentActivity(entries: TimelineEntry[]): string | null {
  for (let index = entries.length - 1; index >= 0; index -= 1) {
    const entry = entries[index]
    if (entry.type === 'step' && entry.status === 'running') return entry.description ?? entry.stepId
    if (entry.type === 'decision') return entry.rationale ?? entry.actionSummary
    if (entry.type === 'notice' && entry.title.startsWith('Run finished')) return null
  }
  return null
}

/** Merges a page of new events into the known list, ignoring duplicates and keeping seq order. */
export function mergeEvents(known: RunEvent[], incoming: RunEvent[]): RunEvent[] {
  if (incoming.length === 0) return known
  const lastKnownSeq = known.length ? known[known.length - 1].seq : -1
  const fresh = incoming.filter((event) => event.seq > lastKnownSeq).sort((left, right) => left.seq - right.seq)
  return fresh.length ? [...known, ...fresh] : known
}

/** Policy verdicts that need a reviewer's eye (anything other than a plain allow). */
export function notablePolicies(entries: TimelineEntry[]): PolicyView[] {
  return entries
    .filter((entry): entry is StepEntry | DecisionEntry => entry.type === 'step' || entry.type === 'decision')
    .map((entry) => entry.policy)
    .filter((policy): policy is PolicyView => policy !== null && policy.verdict !== 'allow')
}
