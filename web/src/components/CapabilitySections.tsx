import { Link } from 'react-router-dom'
import type { Capability, OutcomeDetector, RecoveryRule, ReplayStats, Step } from '../api/types'
import { describeRecoveryResponse, describeStepAction, stepTarget } from '../lib/candidates'
import { formatDurationMs, formatTimestamp, humanize } from '../lib/format'
import { CandidateList } from './CandidateList'
import { ConditionView } from './ConditionView'
import { KeyValueList, Panel, Stat } from './Panel'

function YesNo({ value, yes, no }: { value: boolean; yes: string; no?: string }) {
  return value ? <span className="chip warn">{yes}</span> : <span className="muted">{no ?? '—'}</span>
}

export function ContractPanel({ capability }: { capability: Capability }) {
  const inputs = Object.entries(capability.inputs)
  const outputs = Object.entries(capability.outputs)
  const credentials = Object.entries(capability.credentials ?? {})
  return (
    <Panel title="Contract" subtitle="What a calling agent passes in and gets back" flush>
      <div className="table-wrap">
        <table className="table" aria-label="Inputs">
          <thead>
            <tr>
              <th scope="col">Input</th>
              <th scope="col">Type</th>
              <th scope="col">Required</th>
              <th scope="col">Pattern</th>
              <th scope="col">Sensitive</th>
              <th scope="col">Description</th>
            </tr>
          </thead>
          <tbody>
            {inputs.length === 0 ? (
              <tr>
                <td colSpan={6} className="muted">
                  No inputs.
                </td>
              </tr>
            ) : null}
            {inputs.map(([name, spec]) => (
              <tr key={name}>
                <td className="mono cell-main">{name}</td>
                <td className="mono">{spec.type}</td>
                <td>{spec.required === false ? 'Optional' : 'Required'}</td>
                <td>{spec.pattern ? <code className="condition-literal">{spec.pattern}</code> : <span className="muted">—</span>}</td>
                <td>
                  <YesNo value={Boolean(spec.sensitive)} yes="masked" />
                </td>
                <td>
                  {spec.description}
                  {spec.example ? <div className="faint">Example: <code>{spec.example}</code></div> : null}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-wrap">
        <table className="table" aria-label="Outputs">
          <thead>
            <tr>
              <th scope="col">Output</th>
              <th scope="col">Type</th>
              <th scope="col">Sensitive</th>
              <th scope="col">Description</th>
            </tr>
          </thead>
          <tbody>
            {outputs.map(([name, spec]) => (
              <tr key={name}>
                <td className="mono cell-main">{name}</td>
                <td className="mono">{spec.type}</td>
                <td>
                  <YesNo value={Boolean(spec.sensitive)} yes="masked" />
                </td>
                <td>{spec.description}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {credentials.length ? (
        <div className="panel-body">
          <span className="sub-label">Credentials (resolved server-side, never passed by the caller)</span>
          {credentials.map(([name, spec]) => (
            <div key={name} className="row">
              <code className="chip mono">{name}</code>
              {spec.fields.map((field) => (
                <code key={field} className="chip mono">{`{{${name}.${field}}}`}</code>
              ))}
              <span className="faint">{spec.description}</span>
            </div>
          ))}
        </div>
      ) : null}
    </Panel>
  )
}

function StepDetail({ step, subflows }: { step: Step; subflows: Record<string, Step[]> }) {
  const target = stepTarget(step)
  const subflowSteps = step.action === 'subflow' ? (subflows[step.subflow] ?? []) : []
  return (
    <div className="step-detail">
      <KeyValueList
        items={[
          { label: 'Action', value: describeStepAction(step) },
          { label: 'Timeout', value: step.timeout_ms ? formatDurationMs(step.timeout_ms) : null },
          { label: 'Risk', value: step.risk === 'risky' ? <span className="chip warn">risky</span> : 'Safe' },
          { label: 'Precondition', value: <ConditionView condition={step.precondition} emptyText="None (no wait before acting)" /> },
          { label: 'Postcondition', value: <ConditionView condition={step.postcondition} emptyText="None" /> },
          { label: 'Wait until', value: step.action === 'wait' ? <ConditionView condition={step.until} /> : null },
          {
            label: 'Step recoveries',
            value: step.recoveries?.length ? step.recoveries.map((name) => <code key={name} className="chip mono">{name}</code>) : null,
          },
        ]}
      />
      {target ? (
        <div className="stack-sm">
          <span className="sub-label">Target: {target.description} · candidates tried in rank order</span>
          <CandidateList target={target} />
        </div>
      ) : null}
      {subflowSteps.length ? (
        <div className="stack-sm">
          <span className="sub-label">Subflow “{step.action === 'subflow' ? step.subflow : ''}” (from the vendor profile)</span>
          <StepList steps={subflowSteps} subflows={{}} label={`Subflow steps`} />
        </div>
      ) : null}
    </div>
  )
}

export function StepList({ steps, subflows, label }: { steps: Step[]; subflows: Record<string, Step[]>; label: string }) {
  return (
    <ol className="step-list panel" aria-label={label} style={{ boxShadow: 'none' }}>
      {steps.map((step, index) => (
        <li key={step.id} className="step-item">
          <details>
            <summary className="step-summary">
              <span className="step-index">{String(index + 1).padStart(2, '0')}</span>
              <span className="step-title">
                <span className="cell-main">{step.description}</span>
                <span className="faint mono">{step.id}</span>
              </span>
              <span className="row">
                <span className="chip">{step.action}</span>
                {step.risk === 'risky' ? <span className="chip warn">risky</span> : null}
                {stepTarget(step) ? (
                  <span className="chip">{stepTarget(step)?.candidates.length} candidates</span>
                ) : null}
              </span>
            </summary>
            <StepDetail step={step} subflows={subflows} />
          </details>
        </li>
      ))}
    </ol>
  )
}

export function StepsPanel({ capability }: { capability: Capability }) {
  return (
    <Panel title="Steps" subtitle={`${capability.steps.length} steps · expand a step to see its locator candidates and conditions`}>
      <StepList steps={capability.steps} subflows={capability.subflows ?? {}} label="Capability steps" />
      <div className="stack-sm">
        <span className="sub-label">Success checkpoint (asserted after the last step)</span>
        <ConditionView condition={capability.checkpoint} />
      </div>
    </Panel>
  )
}

function OutcomeRow({ outcome }: { outcome: OutcomeDetector }) {
  return (
    <tr>
      <td className="mono cell-main">{outcome.code}</td>
      <td>
        {outcome.description}
        {outcome.message_target ? <div className="faint">Message read from: {outcome.message_target.description}</div> : null}
      </td>
      <td>
        <ConditionView condition={outcome.when} />
      </td>
      <td>{outcome.scope?.length ? outcome.scope.join(', ') : 'All steps'}</td>
    </tr>
  )
}

function RecoveryRow({ rule }: { rule: RecoveryRule }) {
  return (
    <tr>
      <td className="mono cell-main">{rule.name}</td>
      <td>{rule.description}</td>
      <td>
        <ConditionView condition={rule.when} />
      </td>
      <td>{describeRecoveryResponse(rule.response)}</td>
      <td className="right num">{rule.max_applications ?? 2}</td>
    </tr>
  )
}

export function RuntimeKnowledgePanel({ capability }: { capability: Capability }) {
  const outcomes = capability.outcomes ?? []
  const recoveries = capability.recoveries ?? []
  return (
    <Panel
      title="Outcomes and recoveries"
      subtitle={`From the ${capability.app.vendor} ${capability.app.product} vendor profile; shared by every tenant`}
      flush
    >
      <div className="table-wrap">
        <table className="table" aria-label="Business outcomes">
          <thead>
            <tr>
              <th scope="col">Business outcome</th>
              <th scope="col">Meaning</th>
              <th scope="col">Detected when</th>
              <th scope="col">Scope</th>
            </tr>
          </thead>
          <tbody>
            {outcomes.length === 0 ? (
              <tr>
                <td colSpan={4} className="muted">
                  No business outcomes declared.
                </td>
              </tr>
            ) : null}
            {outcomes.map((outcome) => (
              <OutcomeRow key={outcome.code} outcome={outcome} />
            ))}
          </tbody>
        </table>
      </div>
      <div className="table-wrap">
        <table className="table" aria-label="Recoveries">
          <thead>
            <tr>
              <th scope="col">Recovery</th>
              <th scope="col">Situation</th>
              <th scope="col">Triggered when</th>
              <th scope="col">Response</th>
              <th scope="col" className="right">
                Max per run
              </th>
            </tr>
          </thead>
          <tbody>
            {recoveries.length === 0 ? (
              <tr>
                <td colSpan={5} className="muted">
                  No recoveries declared.
                </td>
              </tr>
            ) : null}
            {recoveries.map((rule) => (
              <RecoveryRow key={rule.name} rule={rule} />
            ))}
          </tbody>
        </table>
      </div>
    </Panel>
  )
}

export function ProvenancePanel({ capability }: { capability: Capability }) {
  const { provenance, app } = capability
  return (
    <Panel title="Provenance">
      <KeyValueList
        items={[
          { label: 'Application', value: `${app.vendor} ${app.product} ${app.product_version} (${app.surface})` },
          { label: 'Planner', value: humanize(provenance.planner) },
          { label: 'Model', value: provenance.model ? <code>{provenance.model}</code> : 'None' },
          {
            label: 'Discovery run',
            value: (
              <Link to={`/runs/${encodeURIComponent(provenance.discovery_run_id)}`} className="mono">
                {provenance.discovery_run_id}
              </Link>
            ),
          },
          { label: 'Recorded', value: formatTimestamp(provenance.recorded_at) },
          { label: 'Recorded on', value: provenance.recorded_on_tenant },
          { label: 'Goal', value: <span className="prose-block" style={{ display: 'block' }}>{provenance.goal}</span> },
        ]}
      />
    </Panel>
  )
}

const EMPTY_STATS: ReplayStats = { runs: 0, successes: 0, business_outcomes: 0, failures: 0, fallback_matches: 0 }

export function StatsPanel({ stats }: { stats: ReplayStats | undefined }) {
  const values = stats ?? EMPTY_STATS
  return (
    <Panel title="Replay stats" subtitle="Fallback matches are the early drift signal">
      <div className="stats">
        <Stat label="Runs" value={values.runs} />
        <Stat label="Successes" value={values.successes} />
        <Stat label="Business outcomes" value={values.business_outcomes} />
        <Stat label="Failures" value={values.failures} />
        <Stat label="Fallback matches" value={values.fallback_matches} />
      </div>
    </Panel>
  )
}

export function OverlaysPanel({ overlays, capabilityId }: { overlays: string[]; capabilityId: string }) {
  return (
    <Panel title="Tenant overlays" subtitle="Per-tenant label, entry-point and target overrides; never add or remove steps">
      {overlays.length === 0 ? (
        <p className="muted">No overlays. Every tenant runs the base flow.</p>
      ) : (
        <div className="stack-sm">
          {overlays.map((tenant) => (
            <div key={tenant} className="row-between">
              <code className="chip mono">{tenant}</code>
              <Link to={`/capabilities/${encodeURIComponent(capabilityId)}/run?tenant=${encodeURIComponent(tenant)}`}>
                Replay on {tenant}
              </Link>
            </div>
          ))}
        </div>
      )}
    </Panel>
  )
}
