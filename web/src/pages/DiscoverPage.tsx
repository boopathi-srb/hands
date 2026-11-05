import { useEffect, useMemo, useState, type FormEvent } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ApiError } from '../api/client'
import type { DiscoveryRequest, EscalationMode, Health, PlannerName } from '../api/types'
import { useApp } from '../app/AppContext'
import { ErrorNotice } from '../components/Feedback'
import { EscalationChoice, TenantSelect, TextField } from '../components/FormControls'
import { PageHeader, Panel } from '../components/Panel'
import { useApiResource } from '../hooks/useAsync'
import {
  goalPlaceholders,
  rowsToInputs,
  syncRowsWithPlaceholders,
  validateCapabilityId,
  type KeyValueRow,
} from '../lib/inputs'

const DEFAULT_GOAL =
  'Look up member {{member_number}} in CoreOne and return the balance of their savings share as savings_balance.'
const DEFAULT_MAX_STEPS = 25

interface PlannerOption {
  name: PlannerName
  label: string
  hint: string
}

/** Planners offered in the form: Anthropic and scripted always, Ollama only when the server reports it running. */
export function plannerOptions(health: Health | null): PlannerOption[] {
  const options: PlannerOption[] = [
    {
      name: 'anthropic',
      label: 'Anthropic (Claude)',
      hint: health && !health.planners.anthropic ? 'Unavailable: the server has no ANTHROPIC_API_KEY' : 'Production planner',
    },
    { name: 'scripted', label: 'Scripted', hint: 'Offline and deterministic; no model' },
  ]
  if (health?.planners.ollama) options.push({ name: 'ollama', label: 'Ollama (local)', hint: 'Development planner' })
  return options
}

export function defaultPlanner(health: Health | null): PlannerName {
  return health?.planners.anthropic ? 'anthropic' : 'scripted'
}

export function DiscoverPage() {
  const { client, health } = useApp()
  const navigate = useNavigate()
  const tenants = useApiResource(() => client.tenants(), 'tenants')
  const [goal, setGoal] = useState(DEFAULT_GOAL)
  const [rows, setRows] = useState<KeyValueRow[]>([{ key: 'member_number', value: '10001', sensitive: false }])
  const [planner, setPlanner] = useState<PlannerName | null>(null)
  const [capabilityId, setCapabilityId] = useState('coreone.member_balance')
  const [title, setTitle] = useState('Member savings balance')
  const [description, setDescription] = useState('Look up a member by member number and return the balance of their savings share.')
  const [tenant, setTenant] = useState('lakeside')
  const [escalation, setEscalation] = useState<EscalationMode>('console')
  const [touched, setTouched] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<ApiError | null>(null)

  const placeholders = useMemo(() => goalPlaceholders(goal), [goal])
  useEffect(() => setRows((current) => syncRowsWithPlaceholders(current, placeholders)), [placeholders])

  const chosenPlanner = planner ?? defaultPlanner(health)
  const options = plannerOptions(health)
  const missingValues = placeholders.filter((name) => !rows.find((row) => row.key.trim() === name && row.value.trim()))
  const idError = validateCapabilityId(capabilityId)
  const goalError = goal.trim() ? null : 'Required'
  const titleError = title.trim() ? null : 'Required'
  const invalid = Boolean(idError || goalError || titleError || missingValues.length)

  function updateRow(index: number, patch: Partial<KeyValueRow>) {
    setRows((current) => current.map((row, rowIndex) => (rowIndex === index ? { ...row, ...patch } : row)))
  }

  function submit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (invalid || submitting) return
    const { inputs, sensitive } = rowsToInputs(rows)
    const body: DiscoveryRequest = {
      goal: goal.trim(),
      inputs,
      sensitive_inputs: sensitive,
      capability_id: capabilityId.trim(),
      title: title.trim(),
      description: description.trim(),
      tenant,
      planner: chosenPlanner,
      model: null,
      max_steps: DEFAULT_MAX_STEPS,
      escalation,
    }
    setSubmitting(true)
    setServerError(null)
    client.startDiscovery(body).then((result) => {
      setSubmitting(false)
      if (result.ok) navigate(`/runs/${encodeURIComponent(result.data.run_id)}`)
      else setServerError(result.error)
    })
  }

  return (
    <>
      <PageHeader
        eyebrow="Discover"
        title="Discover a capability"
        lede="A model drives the live app once to reach the goal. The run is recorded as a typed, versioned capability that replays with no model."
      />
      <form className="grid grid-sidebar" onSubmit={submit} noValidate>
        <div className="stack">
          <Panel title="Goal">
            <div className="field">
              <label className="field-label" htmlFor="goal">
                What should the agent do?
              </label>
              <textarea
                id="goal"
                className="textarea"
                value={goal}
                onChange={(event) => setGoal(event.target.value)}
                aria-invalid={touched && goalError ? true : undefined}
                aria-describedby="goal-hint"
                rows={3}
              />
              <span id="goal-hint" className="field-hint">
                Mark caller inputs as <code>{'{{name}}'}</code>; each becomes a typed input of the capability. Credentials
                such as <code>{'{{teller.password}}'}</code> are resolved by the server and never typed here.
              </span>
              {touched && goalError ? <span className="field-error">{goalError}</span> : null}
            </div>
            <div className="stack-sm">
              <span className="sub-label">Inputs for this run</span>
              <div className="kv-rows">
                {rows.map((row, index) => (
                  <div key={index} className="kv-row">
                    <input
                      className="input mono"
                      value={row.key}
                      placeholder="name"
                      aria-label={`Input ${index + 1} name`}
                      onChange={(event) => updateRow(index, { key: event.target.value })}
                    />
                    <input
                      className="input mono"
                      value={row.value}
                      type={row.sensitive ? 'password' : 'text'}
                      placeholder="value"
                      aria-label={`Input ${row.key || index + 1} value`}
                      autoComplete="off"
                      onChange={(event) => updateRow(index, { value: event.target.value })}
                    />
                    <label className="check faint">
                      <input
                        type="checkbox"
                        checked={row.sensitive}
                        onChange={(event) => updateRow(index, { sensitive: event.target.checked })}
                      />
                      sensitive
                    </label>
                    <button
                      type="button"
                      className="button ghost small"
                      aria-label={`Remove input ${row.key || index + 1}`}
                      onClick={() => setRows((current) => current.filter((_, rowIndex) => rowIndex !== index))}
                    >
                      Remove
                    </button>
                  </div>
                ))}
              </div>
              <div>
                <button
                  type="button"
                  className="button small"
                  onClick={() => setRows((current) => [...current, { key: '', value: '', sensitive: false }])}
                >
                  Add input
                </button>
              </div>
              {touched && missingValues.length ? (
                <span className="field-error">Give a value for: {missingValues.join(', ')}</span>
              ) : null}
            </div>
          </Panel>
          <Panel title="Capability to record">
            <TextField
              id="capability-id"
              label="Capability id"
              value={capabilityId}
              onChange={setCapabilityId}
              mono
              hint="Stable name agents call, e.g. coreone.member_balance. Recording an existing id adds a version."
              error={touched ? idError : null}
            />
            <TextField id="capability-title" label="Title" value={title} onChange={setTitle} error={touched ? titleError : null} />
            <div className="field">
              <label className="field-label" htmlFor="capability-description">
                Description
              </label>
              <textarea
                id="capability-description"
                className="textarea"
                rows={2}
                value={description}
                onChange={(event) => setDescription(event.target.value)}
              />
              <span className="field-hint">Shown to calling agents in the tool definition.</span>
            </div>
          </Panel>
        </div>
        <div className="stack">
          <Panel title="Planner">
            <fieldset>
              <legend>Model that plans each step</legend>
              {options.map((option) => (
                <label key={option.name} className="radio-card">
                  <input
                    type="radio"
                    name="planner"
                    value={option.name}
                    checked={chosenPlanner === option.name}
                    onChange={() => setPlanner(option.name)}
                  />
                  <span className="check-text">
                    <strong>{option.label}</strong>
                    <span className="faint">{option.hint}</span>
                  </span>
                </label>
              ))}
            </fieldset>
            <TenantSelect tenants={tenants.data ?? []} value={tenant} onChange={setTenant} />
            <EscalationChoice value={escalation} onChange={setEscalation} />
          </Panel>
          {serverError ? <ErrorNotice error={serverError} /> : null}
          <div className="form-actions">
            <button type="submit" className="button primary" disabled={submitting}>
              {submitting ? 'Starting…' : 'Start discovery'}
            </button>
          </div>
          <p className="faint">
            Discovery never commits a change: risky steps always escalate. Every action passes the policy gate, and
            screenshots are redacted before the model sees them.
          </p>
        </div>
      </form>
    </>
  )
}
