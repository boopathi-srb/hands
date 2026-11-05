import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate, useParams, useSearchParams } from 'react-router-dom'
import type { ApiError } from '../api/client'
import type { EscalationMode, FaultRequest, ReplayRequest } from '../api/types'
import { useApp } from '../app/AppContext'
import { ErrorNotice, Loading } from '../components/Feedback'
import { ContractInput, EscalationChoice, FaultChecklist, TenantSelect, type FaultSelection } from '../components/FormControls'
import { PageHeader, Panel } from '../components/Panel'
import { useApiResource } from '../hooks/useAsync'
import { buildInputFields, collectInputValues, validateInputs, type InputField } from '../lib/inputs'

const DEFAULT_TENANT = 'lakeside'

function initialValues(fields: InputField[], params: URLSearchParams): Record<string, string> {
  return Object.fromEntries(fields.map((field) => [field.name, params.get(field.name) ?? '']))
}

function initialFaults(params: URLSearchParams): FaultSelection {
  return Object.fromEntries(params.getAll('fault').map((name) => [name, 1]))
}

export function faultRequests(selection: FaultSelection): FaultRequest[] {
  return Object.entries(selection).map(([name, count]) => ({ name, count }))
}

export function RunCapabilityPage() {
  const { capabilityId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const version = searchParams.get('version')
  const { client } = useApp()
  const detail = useApiResource(() => client.capability(capabilityId, version), `capability:${capabilityId}:${version ?? ''}`)
  const tenants = useApiResource(() => client.tenants(), 'tenants')
  const faults = useApiResource(() => client.faults(), 'faults')

  if (detail.error && !detail.data) return <ErrorNotice error={detail.error} />
  if (!detail.data) return <Loading label="Loading capability" />
  return (
    <ReplayForm
      key={detail.data.capability.version}
      capabilityId={capabilityId}
      version={version}
      title={detail.data.capability.title}
      fields={buildInputFields(detail.data.capability.inputs)}
      tenants={tenants.data ?? []}
      faults={faults.data ?? []}
      referenceError={tenants.error ?? faults.error}
      params={searchParams}
    />
  )
}

interface ReplayFormProps {
  capabilityId: string
  version: string | null
  title: string
  fields: InputField[]
  tenants: { id: string; name: string }[]
  faults: { name: string; description: string }[]
  referenceError: ApiError | null
  params: URLSearchParams
}

function ReplayForm(props: ReplayFormProps) {
  const { client } = useApp()
  const navigate = useNavigate()
  const [values, setValues] = useState(() => initialValues(props.fields, props.params))
  const [tenant, setTenant] = useState(props.params.get('tenant') ?? DEFAULT_TENANT)
  const [faultSelection, setFaultSelection] = useState<FaultSelection>(() => initialFaults(props.params))
  const [escalation, setEscalation] = useState<EscalationMode>('console')
  const [riskyConfirmed, setRiskyConfirmed] = useState(false)
  const [touched, setTouched] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [serverError, setServerError] = useState<ApiError | null>(null)

  const errors = useMemo(() => validateInputs(props.fields, values), [props.fields, values])
  const hasErrors = Object.keys(errors).length > 0

  function submit(event: FormEvent) {
    event.preventDefault()
    setTouched(true)
    if (hasErrors) return
    start()
  }

  /** Starts the replay. Called directly to skip client validation and let the server return its typed invalid_input result. */
  function start() {
    if (submitting) return
    const body: ReplayRequest = {
      capability_id: props.capabilityId,
      version: props.version,
      inputs: collectInputValues(props.fields, values),
      tenant,
      faults: faultRequests(faultSelection),
      risky_confirmed: riskyConfirmed,
      escalation,
    }
    setSubmitting(true)
    setServerError(null)
    client.startReplay(body).then((result) => {
      setSubmitting(false)
      if (result.ok) navigate(`/runs/${encodeURIComponent(result.data.run_id)}`)
      else setServerError(result.error)
    })
  }

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <Link to="/capabilities">Capabilities</Link>
            <span aria-hidden="true">/</span>
            <Link to={`/capabilities/${encodeURIComponent(props.capabilityId)}`} className="mono">
              {props.capabilityId}
            </Link>
            <span aria-hidden="true">/</span>
            <span>Run</span>
          </>
        }
        title={`Run: ${props.title}`}
        lede="Deterministic replay. No model is involved; the result comes back typed."
      />
      <form className="grid grid-sidebar" onSubmit={submit} noValidate>
        <div className="stack">
          <Panel title="Inputs" subtitle="Generated from the capability's input contract">
            {props.fields.length === 0 ? <p className="muted">This capability takes no inputs.</p> : null}
            {props.fields.map((field) => (
              <ContractInput
                key={field.name}
                field={field}
                value={values[field.name] ?? ''}
                error={touched ? (errors[field.name] ?? null) : null}
                onChange={(value) => setValues((previous) => ({ ...previous, [field.name]: value }))}
              />
            ))}
            <TenantSelect tenants={props.tenants} value={tenant} onChange={setTenant} />
          </Panel>
          <FaultChecklist faults={props.faults} selection={faultSelection} onChange={setFaultSelection} />
        </div>
        <div className="stack">
          <Panel title="Run options">
            <EscalationChoice value={escalation} onChange={setEscalation} />
            <label className="check">
              <input type="checkbox" checked={riskyConfirmed} onChange={(event) => setRiskyConfirmed(event.target.checked)} />
              <span className="check-text">
                <strong>Confirm risky steps</strong>
                <span className="faint">
                  Allows steps that policy marks risky (submit, transfer, approve). Takes effect only on approved
                  capabilities; otherwise risky steps are denied.
                </span>
              </span>
            </label>
          </Panel>
          {props.referenceError ? <ErrorNotice error={props.referenceError} /> : null}
          {serverError ? <ErrorNotice error={serverError} /> : null}
          {touched && hasErrors ? (
            <div className="stack-sm" role="alert">
              <p className="field-error">These inputs do not match the contract.</p>
              <p className="faint">
                The server validates too, and returns a typed <code>invalid_input</code> failure without touching the app.
              </p>
              <div>
                <button type="button" className="button small" onClick={start} disabled={submitting}>
                  Send anyway and let the server validate
                </button>
              </div>
            </div>
          ) : null}
          <div className="form-actions">
            <button type="submit" className="button primary" disabled={submitting}>
              {submitting ? 'Starting…' : 'Start replay'}
            </button>
            <Link to={`/capabilities/${encodeURIComponent(props.capabilityId)}`} className="button ghost">
              Cancel
            </Link>
          </div>
        </div>
      </form>
    </>
  )
}
