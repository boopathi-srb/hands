import type { ReactNode } from 'react'
import type { EscalationMode, FaultInfo, Tenant } from '../api/types'
import type { InputField } from '../lib/inputs'

interface TextFieldProps {
  id: string
  label: ReactNode
  value: string
  onChange: (value: string) => void
  hint?: ReactNode
  error?: string | null
  type?: string
  inputMode?: 'text' | 'numeric' | 'decimal'
  placeholder?: string
  mono?: boolean
  required?: boolean
  autoComplete?: string
}

export function TextField(props: TextFieldProps) {
  const hintId = props.hint ? `${props.id}-hint` : undefined
  const errorId = props.error ? `${props.id}-error` : undefined
  return (
    <div className="field">
      <label className="field-label" htmlFor={props.id}>
        {props.label}
      </label>
      <input
        id={props.id}
        className={`input ${props.mono ? 'mono' : ''}`}
        value={props.value}
        type={props.type ?? 'text'}
        inputMode={props.inputMode}
        placeholder={props.placeholder}
        required={props.required}
        autoComplete={props.autoComplete ?? 'off'}
        aria-invalid={props.error ? true : undefined}
        aria-describedby={[hintId, errorId].filter(Boolean).join(' ') || undefined}
        onChange={(event) => props.onChange(event.target.value)}
      />
      {props.hint ? (
        <span id={hintId} className="field-hint">
          {props.hint}
        </span>
      ) : null}
      {props.error ? (
        <span id={errorId} className="field-error">
          {props.error}
        </span>
      ) : null}
    </div>
  )
}

/** An input generated from the capability contract: type, pattern and sensitivity drive the control. */
export function ContractInput({
  field,
  value,
  error,
  onChange,
}: {
  field: InputField
  value: string
  error: string | null
  onChange: (value: string) => void
}) {
  const hint = [
    field.spec.description,
    field.spec.pattern ? `Pattern ${field.spec.pattern}` : null,
    field.sensitive ? 'Sensitive: masked in evidence' : null,
  ]
    .filter(Boolean)
    .join(' · ')
  return (
    <TextField
      id={`input-${field.name}`}
      label={
        <>
          <span className="mono">{field.name}</span>
          <span className="chip mono">{field.spec.type}</span>
          {field.required ? null : <span className="faint">optional</span>}
        </>
      }
      value={value}
      onChange={onChange}
      hint={hint}
      error={error}
      type={field.htmlType}
      inputMode={field.inputMode}
      placeholder={field.placeholder}
      mono
      required={field.required}
    />
  )
}

export function TenantSelect({
  tenants,
  value,
  onChange,
}: {
  tenants: Tenant[]
  value: string
  onChange: (tenant: string) => void
}) {
  return (
    <div className="field">
      <label className="field-label" htmlFor="tenant">
        Tenant
      </label>
      <select id="tenant" className="select" value={value} onChange={(event) => onChange(event.target.value)}>
        {tenants.length === 0 ? <option value={value}>{value}</option> : null}
        {tenants.map((tenant) => (
          <option key={tenant.id} value={tenant.id}>
            {tenant.name} ({tenant.id})
          </option>
        ))}
      </select>
      <span className="field-hint">The institution whose CoreOne instance the run signs on to; overlays apply automatically.</span>
    </div>
  )
}

export function EscalationChoice({ value, onChange }: { value: EscalationMode; onChange: (mode: EscalationMode) => void }) {
  return (
    <fieldset>
      <legend>When automation needs a human</legend>
      <div className="radio-row">
        <label className="radio-card">
          <input type="radio" name="escalation" value="console" checked={value === 'console'} onChange={() => onChange('console')} />
          <span className="check-text">
            <strong>Operator console</strong>
            <span className="faint">Pause and wait for an operator to take control in this UI.</span>
          </span>
        </label>
        <label className="radio-card">
          <input type="radio" name="escalation" value="none" checked={value === 'none'} onChange={() => onChange('none')} />
          <span className="check-text">
            <strong>None</strong>
            <span className="faint">Fail fast with a typed failure instead of waiting.</span>
          </span>
        </label>
      </div>
    </fieldset>
  )
}

export interface FaultSelection {
  [name: string]: number
}

export function FaultChecklist({
  faults,
  selection,
  onChange,
}: {
  faults: FaultInfo[]
  selection: FaultSelection
  onChange: (next: FaultSelection) => void
}) {
  function toggle(name: string, checked: boolean) {
    const next = { ...selection }
    if (checked) next[name] = next[name] ?? 1
    else delete next[name]
    onChange(next)
  }
  function setCount(name: string, count: number) {
    onChange({ ...selection, [name]: Math.max(1, Math.min(10, Math.round(count) || 1)) })
  }
  return (
    <fieldset className="harness">
      <legend>Test harness: fault injection</legend>
      <span className="field-hint">
        Arms the mock CoreOne app out of band before the run starts. This simulates a misbehaving legacy system; the
        agent itself has no access to these controls.
      </span>
      {faults.length === 0 ? <span className="muted">No injectable faults reported by the server.</span> : null}
      {faults.map((fault) => {
        const checked = fault.name in selection
        return (
          <div key={fault.name} className="row-between">
            <label className="check">
              <input type="checkbox" checked={checked} onChange={(event) => toggle(fault.name, event.target.checked)} />
              <span className="check-text">
                <span className="mono">{fault.name}</span>
                <span className="faint">{fault.description}</span>
              </span>
            </label>
            {checked ? (
              <label className="row faint">
                times
                <input
                  type="number"
                  min={1}
                  max={10}
                  className="input num"
                  style={{ width: 64 }}
                  value={selection[fault.name]}
                  onChange={(event) => setCount(fault.name, Number(event.target.value))}
                  aria-label={`How many page loads ${fault.name} fires on`}
                />
              </label>
            ) : null}
          </div>
        )
      })}
    </fieldset>
  )
}
