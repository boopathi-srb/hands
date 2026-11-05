import { useState, type FormEvent, type KeyboardEvent, type MouseEvent } from 'react'
import { Link, useNavigate, useParams } from 'react-router-dom'
import type { ApiError } from '../api/client'
import type { ControlLease, HandbackOutcome } from '../api/types'
import { useApp } from '../app/AppContext'
import { ErrorNotice, Loading, Notice } from '../components/Feedback'
import { TextField } from '../components/FormControls'
import { InterventionFacts, InterventionScreenshot } from '../components/InterventionPanel'
import { PageHeader, Panel } from '../components/Panel'
import { useLiveSession, type LiveSession } from '../hooks/useLiveSession'
import { useRunLive } from '../hooks/useRunLive'
import { holderLabel, normalizeIntervention, type InterventionView } from '../lib/interventions'
import { describeHumanAction } from '../lib/liveInput'

const OUTCOMES: { value: HandbackOutcome; label: string; hint: string }[] = [
  { value: 'resume', label: 'Resume', hint: 'Automation re-checks the current step and continues.' },
  {
    value: 'step_completed_by_human',
    label: 'Step completed by human',
    hint: 'I finished this step myself; automation marks it human and moves on.',
  },
  { value: 'abort', label: 'Abort', hint: 'Stop the run. It returns escalated with your note.' },
]

function LiveCanvas({ live }: { live: LiveSession }) {
  function onClick(event: MouseEvent<HTMLCanvasElement>) {
    event.currentTarget.focus({ preventScroll: true })
    live.sendClick(event.clientX, event.clientY)
  }
  function onKey(event: KeyboardEvent<HTMLCanvasElement>, phase: 'down' | 'up') {
    // Escape leaves the canvas so keyboard users are never trapped in the live view.
    if (event.key === 'Escape' && phase === 'down') {
      event.currentTarget.blur()
      return
    }
    event.preventDefault()
    live.sendKey(event, phase)
  }
  return (
    <div className="live-canvas-wrap">
      <canvas
        ref={live.canvasRef}
        className="live-canvas"
        width={1280}
        height={800}
        tabIndex={0}
        aria-label="Live session. Click to focus, then click and type to control the application. Press Escape to leave."
        onClick={onClick}
        onKeyDown={(event) => onKey(event, 'down')}
        onKeyUp={(event) => onKey(event, 'up')}
      />
      {!live.hasFrame ? <div className="live-overlay">Waiting for the first frame…</div> : null}
    </div>
  )
}

function useTakeControl(interventionId: string | null, onTaken: (lease: ControlLease) => void) {
  const { client } = useApp()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  function take(operatorId: string) {
    if (!interventionId) return
    setBusy(true)
    setError(null)
    client.takeControl(interventionId, operatorId).then((result) => {
      setBusy(false)
      if (result.ok) onTaken(result.data.lease)
      else setError(result.error)
    })
  }
  return { take, busy, error }
}

function useHandBack(interventionId: string | null, onDone: () => void) {
  const { client } = useApp()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  function handBack(operatorId: string, outcome: HandbackOutcome, note: string) {
    if (!interventionId) return
    setBusy(true)
    setError(null)
    client.handBack(interventionId, { operator_id: operatorId, outcome, note }).then((result) => {
      setBusy(false)
      if (result.ok) onDone()
      else setError(result.error)
    })
  }
  return { handBack, busy, error }
}

function HandBackForm({
  disabled,
  busy,
  onSubmit,
}: {
  disabled: boolean
  busy: boolean
  onSubmit: (outcome: HandbackOutcome, note: string) => void
}) {
  const [outcome, setOutcome] = useState<HandbackOutcome>('resume')
  const [note, setNote] = useState('')
  function submit(event: FormEvent) {
    event.preventDefault()
    onSubmit(outcome, note.trim())
  }
  return (
    <form className="form" onSubmit={submit}>
      <fieldset>
        <legend>Outcome</legend>
        {OUTCOMES.map((option) => (
          <label key={option.value} className="radio-card">
            <input
              type="radio"
              name="handback-outcome"
              value={option.value}
              checked={outcome === option.value}
              onChange={() => setOutcome(option.value)}
            />
            <span className="check-text">
              <strong>{option.label}</strong>
              <span className="faint">{option.hint}</span>
            </span>
          </label>
        ))}
      </fieldset>
      <div className="field">
        <label className="field-label" htmlFor="handback-note">
          Note for the run record
        </label>
        <textarea
          id="handback-note"
          className="textarea"
          rows={3}
          value={note}
          maxLength={2000}
          placeholder="What you did and why"
          onChange={(event) => setNote(event.target.value)}
        />
      </div>
      <div className="form-actions">
        <button type="submit" className={`button ${outcome === 'abort' ? 'danger' : 'primary'}`} disabled={disabled || busy}>
          {busy ? 'Handing back…' : 'Hand back'}
        </button>
      </div>
    </form>
  )
}

function OperatorConsole({ runId, intervention }: { runId: string; intervention: InterventionView }) {
  const { client, operatorId, setOperatorId } = useApp()
  const navigate = useNavigate()
  const live = useLiveSession()
  const [takenLease, setLease] = useState<ControlLease | null>(null)
  const lease = takenLease ?? intervention.lease
  const [operatorTouched, setOperatorTouched] = useState(false)
  const interventionId = intervention.request.intervention_id
  const operatorError = operatorTouched && !operatorId.trim() ? 'Enter your operator id first' : null

  const control = useTakeControl(interventionId, (taken) => {
    setLease(taken)
    live.connect(client.liveSocketUrl(intervention.request.session_id, operatorId.trim()))
  })
  const handback = useHandBack(interventionId, () => {
    live.disconnect()
    navigate(`/runs/${encodeURIComponent(runId)}`)
  })

  function requireOperator(): string | null {
    setOperatorTouched(true)
    return operatorId.trim() || null
  }

  const inControl = live.status === 'live' || live.status === 'connecting'
  // After a reload the lease may still be ours: reconnect the stream instead of taking control again.
  const heldByMe = lease?.holder === 'human' && Boolean(operatorId.trim()) && lease.holder_id === operatorId.trim()
  const reconnect = () => live.connect(client.liveSocketUrl(intervention.request.session_id, operatorId.trim()))
  return (
    <div className="grid grid-sidebar">
      <div className="stack">
        <Panel
          title="Live session"
          subtitle={`Control: ${holderLabel(lease)}`}
          actions={
            !inControl && heldByMe ? (
              <button type="button" className="button primary" onClick={reconnect}>
                Reconnect live view
              </button>
            ) : !inControl ? (
              <button
                type="button"
                className="button primary"
                disabled={control.busy}
                onClick={() => {
                  const operator = requireOperator()
                  if (operator) control.take(operator)
                }}
              >
                {control.busy ? 'Taking control…' : 'Take control'}
              </button>
            ) : (
              <span className="badge tone-escalated">You are in control</span>
            )
          }
        >
          {control.error ? <ErrorNotice error={control.error} /> : null}
          {live.message ? (
            <Notice tone={live.status === 'refused' ? 'error' : 'info'} title={live.status === 'live' ? 'Live' : 'Live view'}>
              <span>{live.message}</span>
            </Notice>
          ) : null}
          {live.status === 'idle' ? (
            <div className="stack-sm">
              <span className="sub-label">Screen when automation asked for help</span>
              <InterventionScreenshot runId={runId} intervention={intervention} />
            </div>
          ) : (
            <LiveCanvas live={live} />
          )}
        </Panel>
        <Panel title="Captured actions" subtitle="Recorded in the run evidence in the artifact's vocabulary; typed text is kept only as a length">
          {live.actions.length === 0 ? (
            <p className="muted">No actions yet.</p>
          ) : (
            <ol className="action-log" aria-live="polite">
              {live.actions.map((action, index) => (
                <li key={index}>{describeHumanAction(action)}</li>
              ))}
            </ol>
          )}
        </Panel>
      </div>
      <div className="stack">
        <Panel title="Operator">
          <TextField
            id="operator-id"
            label="Operator id"
            value={operatorId}
            onChange={setOperatorId}
            placeholder="e.g. alice"
            hint="Remembered on this device. Recorded on the lease and in the evidence."
            error={operatorError}
            autoComplete="username"
          />
        </Panel>
        <Panel title="Intervention">
          <InterventionFacts intervention={{ ...intervention, lease }} />
        </Panel>
        <Panel title="Hand back">
          {handback.error ? <ErrorNotice error={handback.error} /> : null}
          <HandBackForm
            disabled={false}
            busy={handback.busy}
            onSubmit={(outcome, note) => {
              const operator = requireOperator()
              if (operator) handback.handBack(operator, outcome, note)
            }}
          />
          <p className="faint">Without taking control this is a decision only, for example to abort without touching the app.</p>
        </Panel>
      </div>
    </div>
  )
}

export function OperatorPage() {
  const { runId = '' } = useParams()
  const live = useRunLive(runId)
  if (live.error && !live.run) return <ErrorNotice error={live.error} />
  if (!live.run) return <Loading label="Loading run" />
  const intervention = normalizeIntervention(live.run.intervention)
  const runHref = `/runs/${encodeURIComponent(runId)}`
  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <Link to="/runs">Runs</Link>
            <span aria-hidden="true">/</span>
            <Link to={runHref} className="mono">
              {runId}
            </Link>
            <span aria-hidden="true">/</span>
            <span>Operator</span>
          </>
        }
        title="Operator live view"
        lede="Take control of the paused session, act in the application, then hand back to automation."
      />
      {intervention ? (
        <OperatorConsole key={intervention.request.intervention_id} runId={runId} intervention={intervention} />
      ) : (
        <Notice tone="info" title="No open intervention">
          <span>
            This run is not waiting for an operator. <Link to={runHref}>Back to the run</Link>.
          </span>
        </Notice>
      )}
    </>
  )
}
