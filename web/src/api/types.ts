/**
 * Types mirroring docs/API.md and the Python contracts they serialize:
 * - Capability, steps, targets, conditions: src/hands/core/{artifact,targets,conditions}.py
 * - RunResult and traces: src/hands/core/results.py
 * - Interventions, leases, human actions: src/hands/core/control.py and hands/console/context.py
 * - CatalogEntry: src/hands/catalog/store.py
 * Keep these in step with the backend; the UI renders only what these types allow.
 */

// ---------------------------------------------------------------- health and reference data

export interface Health {
  status: string
  auth_required: boolean
  mock_app: 'up' | 'down'
  planners: { anthropic: boolean; ollama: boolean; scripted: boolean }
  active_run: string | null
  version: string
}

export interface Tenant {
  id: string
  name: string
}

export interface FaultInfo {
  name: string
  description: string
}

// ---------------------------------------------------------------- targets and conditions

interface CandidateBase {
  confidence: number
  reason: string
}

export interface RoleNameCandidate extends CandidateBase {
  kind: 'role_name'
  role: string
  name: string
  exact?: boolean
}

export interface LabelCandidate extends CandidateBase {
  kind: 'label'
  label: string
  role?: string | null
}

export interface TextAnchorCandidate extends CandidateBase {
  kind: 'text_anchor'
  anchor_text: string
  relation: 'right_of' | 'below' | 'same_row' | 'inside'
  role?: string | null
  ordinal?: number
}

export interface StructuralCandidate extends CandidateBase {
  kind: 'structural'
  container_path: string[]
  structural_path: string
}

export interface VisualAnchorCandidate extends CandidateBase {
  kind: 'visual_anchor'
  anchor_text: string
  dx: number
  dy: number
}

export type Candidate =
  | RoleNameCandidate
  | LabelCandidate
  | TextAnchorCandidate
  | StructuralCandidate
  | VisualAnchorCandidate

export type CandidateKind = Candidate['kind']

export interface TargetSpec {
  description: string
  candidates: Candidate[]
}

export type Condition =
  | { kind: 'text_visible'; pattern: string; regex?: boolean; case_sensitive?: boolean }
  | { kind: 'node_present'; target: TargetSpec }
  | { kind: 'location_matches'; pattern?: string | null; title_pattern?: string | null }
  | { kind: 'dialog_open'; title_pattern?: string | null; text_pattern?: string | null; native?: boolean | null }
  | { kind: 'value_matches'; target: TargetSpec; pattern: string }
  | { kind: 'all_of'; conditions: Condition[] }
  | { kind: 'any_of'; conditions: Condition[] }
  | { kind: 'not'; condition: Condition }

// ---------------------------------------------------------------- capability

export type ValueType = 'string' | 'integer' | 'decimal' | 'boolean' | 'date'
export type Risk = 'safe' | 'risky'
export type CapabilityStatus = 'draft' | 'approved' | 'deprecated'

export interface InputSpec {
  type: ValueType
  description: string
  required?: boolean
  sensitive?: boolean
  pattern?: string | null
  example?: string | null
}

export interface OutputSpec {
  type: ValueType
  description: string
  sensitive?: boolean
}

export interface CredentialSpec {
  description: string
  fields: string[]
}

interface StepBase {
  id: string
  description: string
  risk?: Risk
  precondition?: Condition | null
  postcondition?: Condition | null
  timeout_ms?: number
  recoveries?: string[]
}

export type Step =
  | (StepBase & { action: 'open'; entry_point: string })
  | (StepBase & { action: 'click'; target: TargetSpec })
  | (StepBase & { action: 'type'; target: TargetSpec; value: string; clear_first?: boolean })
  | (StepBase & { action: 'press'; key: string; target?: TargetSpec | null })
  | (StepBase & { action: 'select'; target: TargetSpec; option: string })
  | (StepBase & { action: 'extract'; target: TargetSpec; output: string; pattern?: string | null })
  | (StepBase & { action: 'wait'; until: Condition })
  | (StepBase & { action: 'subflow'; subflow: string })

export type StepAction = Step['action']

export interface OutcomeDetector {
  code: string
  description: string
  when: Condition
  message_target?: TargetSpec | null
  scope?: string[] | null
}

export type RecoveryResponse =
  | { kind: 'dismiss'; target?: TargetSpec | null }
  | { kind: 'retry'; backoff_ms?: number }
  | { kind: 'subflow'; subflow: string; then?: 'retry_step' | 'restart' }
  | { kind: 'escalate'; reason: string }

export interface RecoveryRule {
  name: string
  description: string
  when: Condition
  response: RecoveryResponse
  max_applications?: number
  scope?: 'global' | 'step'
}

export interface AppRef {
  vendor: string
  product: string
  product_version: string
  surface: 'web' | 'desktop'
}

export interface Provenance {
  discovery_run_id: string
  recorded_at: string
  planner: string
  model?: string | null
  recorded_on_tenant?: string | null
  goal: string
}

export interface ReplayStats {
  runs: number
  successes: number
  business_outcomes: number
  failures: number
  fallback_matches: number
}

export interface Capability {
  schema_version: string
  id: string
  version: string
  status: CapabilityStatus
  title: string
  description: string
  app: AppRef
  inputs: Record<string, InputSpec>
  outputs: Record<string, OutputSpec>
  credentials?: Record<string, CredentialSpec>
  steps: Step[]
  checkpoint: Condition
  outcomes?: OutcomeDetector[]
  recoveries?: RecoveryRule[]
  subflows?: Record<string, Step[]>
  provenance: Provenance
  stats?: ReplayStats
}

export interface FieldSummary {
  type: string
  description: string
  required?: boolean | null
  sensitive?: boolean
  pattern?: string | null
}

export interface CatalogEntry {
  id: string
  latest_version: string
  versions?: string[]
  status: string
  title: string
  description: string
  inputs?: Record<string, FieldSummary>
  outputs?: Record<string, FieldSummary>
  outcome_codes?: string[]
  stats?: ReplayStats
}

export interface ToolDefinition {
  name: string
  description: string
  input_schema: Record<string, unknown>
}

export interface CapabilityDetail {
  capability: Capability
  overlays: string[]
  tool: ToolDefinition
}

export interface ApproveResponse {
  id: string
  version: string
  status: 'approved'
}

// ---------------------------------------------------------------- results

export type StepTraceStatus = 'ok' | 'recovered' | 'failed' | 'skipped' | 'human'

export interface StepTrace {
  step_id: string
  status: StepTraceStatus
  matched_candidate_rank?: number | null
  matched_candidate_kind?: CandidateKind | null
  recoveries_applied: string[]
  duration_ms: number
  fingerprint?: string | null
}

export interface DriftReport {
  fallback_steps: string[]
  fingerprint_changes: string[]
}

export interface FailureDetail {
  code: string
  step_id: string | null
  message: string
  expected?: string | null
  observed?: string | null
  evidence: string[]
}

interface ResultBase {
  run_id: string
  capability_id: string
  capability_version: string
  tenant_id?: string | null
  started_at: string
  finished_at: string
  steps: StepTrace[]
  interventions: string[]
  drift: DriftReport
  evidence_dir: string
}

export interface SuccessResult extends ResultBase {
  status: 'success'
  outputs: Record<string, unknown>
}

export interface BusinessOutcomeResult extends ResultBase {
  status: 'business_outcome'
  code: string
  message?: string | null
  at_step?: string | null
}

export interface EscalatedResult extends ResultBase {
  status: 'escalated'
  intervention_id: string
  reason: string
  operator_note?: string | null
}

export interface FailedResult extends ResultBase {
  status: 'failed'
  failure: FailureDetail
}

export type RunResult = SuccessResult | BusinessOutcomeResult | EscalatedResult | FailedResult

/** discovery_result.json as written by the discovery runner. */
export interface DiscoverySummary {
  mode: 'discovery'
  run_id: string
  planner: string
  model?: string | null
  status: 'completed' | 'stuck' | 'escalated_abort' | 'budget_exhausted' | 'error' | string
  reason?: string | null
  steps: number
  planner_calls: number
  invalid_decisions: number
  extracted: Record<string, unknown>
  capability?: string | null
  record_error?: string | null
  record_warnings?: string[]
  evidence_dir?: string
  artifact_path?: string | null
}

// ---------------------------------------------------------------- runs

export type RunMode = 'replay' | 'discovery'
export type RunState = 'running' | 'waiting_for_operator' | 'finished' | 'error'
export type RunStatus =
  | 'success'
  | 'business_outcome'
  | 'escalated'
  | 'failed'
  | 'completed'
  | 'stuck'
  | 'escalated_abort'
  | 'budget_exhausted'
  | 'error'

export interface RunListItem {
  run_id: string
  mode: RunMode
  state: RunState
  status: RunStatus | null
  capability_id: string | null
  tenant: string | null
  started_at: string | null
  finished_at: string | null
  headline: string | null
}

export type Holder = 'automation' | 'human' | 'nobody'

export interface ControlLease {
  session_id: string
  holder: Holder
  holder_id: string | null
  since: string
  reason?: string
}

export type InterventionKind = 'stuck' | 'unrecoverable' | 'risky_action' | 'policy_block'

export interface InterventionRequest {
  intervention_id: string
  session_id: string
  run_id: string
  mode: RunMode
  kind: InterventionKind
  reason: string
  capability_id?: string | null
  goal?: string | null
  step_id?: string | null
  step_description?: string | null
  location?: string | null
  screenshot_path?: string | null
  created_at: string
}

export interface HumanAction {
  at: string
  kind: 'click' | 'type' | 'press' | 'scroll'
  x?: number | null
  y?: number | null
  key?: string | null
  text_length?: number | null
  node_role?: string | null
  node_name?: string | null
}

export type HandbackOutcome = 'resume' | 'step_completed_by_human' | 'abort'

/**
 * The open intervention on a run. docs/API.md says "open InterventionRequest + lease" without fixing the
 * shape, so the UI accepts either the console's context shape ({request, lease, ...}) or a flat request
 * with a `lease` field, and normalizes it with `normalizeIntervention`.
 */
export interface InterventionContext {
  request: InterventionRequest
  status?: string
  lease: ControlLease | null
  screenshot_data_url?: string | null
  human_actions?: HumanAction[]
}

export type RawIntervention =
  | InterventionContext
  | (InterventionRequest & { lease?: ControlLease | null; screenshot_data_url?: string | null })

export interface RunFiles {
  screenshots: string[]
  snapshots: string[]
}

/** The result of a run that crashed or could not start. */
export interface RunErrorResult {
  status: 'error'
  message: string
}

export type AnyRunResult = RunResult | DiscoverySummary | RunErrorResult

export interface RunDetail extends RunListItem {
  result: AnyRunResult | null
  intervention: RawIntervention | null
  files: RunFiles
}

export interface RunEvent {
  seq: number
  ts: string
  kind: string
  data: Record<string, unknown>
}

export interface RunEventsPage {
  events: RunEvent[]
  last_seq: number
  state: RunState
}

export interface FaultRequest {
  name: string
  count: number
}

export type EscalationMode = 'console' | 'none'

export interface ReplayRequest {
  capability_id: string
  version: string | null
  inputs: Record<string, string>
  tenant: string
  faults: FaultRequest[]
  risky_confirmed: boolean
  escalation: EscalationMode
}

export type PlannerName = 'anthropic' | 'ollama' | 'scripted'

export interface DiscoveryRequest {
  goal: string
  inputs: Record<string, string>
  sensitive_inputs: string[]
  capability_id: string
  title: string
  description: string
  tenant: string
  planner: PlannerName
  model: string | null
  max_steps: number
  escalation: EscalationMode
}

export interface RunStarted {
  run_id: string
}

export interface TakeControlResponse {
  lease: ControlLease
  live_path: string
}

export interface HandbackRequest {
  operator_id: string
  outcome: HandbackOutcome
  note: string
}

export interface HandbackResponse {
  resolution: Record<string, unknown> | null
  lease: ControlLease | null
}

export interface ApiErrorBody {
  error: string
  message?: string
  run_id?: string
}
