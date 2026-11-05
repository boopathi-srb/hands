import { Link } from 'react-router-dom'
import { holderLabel, interventionKindLabel, relativeRunPath, type InterventionView } from '../lib/interventions'
import { formatClock } from '../lib/format'
import { KeyValueList } from './Panel'
import { RunImage } from './RunFile'

export function InterventionScreenshot({ runId, intervention }: { runId: string; intervention: InterventionView }) {
  if (intervention.screenshotDataUrl) {
    return <img src={intervention.screenshotDataUrl} alt="Screen when automation asked for help" className="shot" />
  }
  const path = relativeRunPath(intervention.screenshotPath)
  if (!path) return null
  return <RunImage runId={runId} path={path} alt="Screen when automation asked for help" className="shot" />
}

export function InterventionFacts({ intervention, stepLabel }: { intervention: InterventionView; stepLabel?: string | null }) {
  const { request, lease } = intervention
  return (
    <KeyValueList
      label="Intervention details"
      items={[
        { label: 'Reason', value: request.reason },
        { label: 'Kind', value: interventionKindLabel(request.kind) },
        { label: 'Step', value: request.step_id ? `${stepLabel ?? request.step_description ?? request.step_id}` : null },
        { label: 'Step id', value: request.step_id ? <code>{request.step_id}</code> : null },
        { label: 'Location', value: request.location ? <code>{request.location}</code> : null },
        { label: 'Goal', value: request.goal },
        { label: 'Control', value: holderLabel(lease) },
        { label: 'Raised', value: formatClock(request.created_at) },
        { label: 'Intervention', value: <code>{request.intervention_id}</code> },
      ]}
    />
  )
}

/** Shown on the run page while the run waits for an operator. */
export function InterventionPanel({ runId, intervention, stepLabel }: { runId: string; intervention: InterventionView; stepLabel?: string | null }) {
  return (
    <section className="panel result tone-attention-border" aria-label="Operator needed">
      <header className="panel-head">
        <div className="stack-sm" style={{ gap: 0 }}>
          <h2>Operator needed</h2>
          <span className="panel-sub">The run is paused on the same live browser session, waiting for a human.</span>
        </div>
        <span className="badge tone-attention">Needs operator</span>
      </header>
      <div className="panel-body">
        <div className="grid grid-2">
          <div className="stack">
            <InterventionFacts intervention={intervention} stepLabel={stepLabel} />
            <div className="form-actions">
              <Link to={`/runs/${encodeURIComponent(runId)}/operator`} className="button primary">
                Take control
              </Link>
              <span className="faint">Opens the live view. You can also resume or abort without taking control.</span>
            </div>
          </div>
          <InterventionScreenshot runId={runId} intervention={intervention} />
        </div>
      </div>
    </section>
  )
}
