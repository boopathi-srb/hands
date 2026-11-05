/**
 * Form generation and client-side validation from a capability's input contract. The server
 * validates again; its errors are shown as well, so the client check is a convenience, not a gate.
 */

import type { InputSpec, ValueType } from '../api/types'

export interface InputField {
  name: string
  label: string
  spec: InputSpec
  required: boolean
  sensitive: boolean
  htmlType: 'text' | 'password' | 'date'
  inputMode: 'text' | 'numeric' | 'decimal'
  placeholder: string
}

const INPUT_MODES: Record<ValueType, InputField['inputMode']> = {
  string: 'text',
  integer: 'numeric',
  decimal: 'decimal',
  boolean: 'text',
  date: 'text',
}

const TYPE_PATTERNS: Partial<Record<ValueType, { pattern: RegExp; message: string }>> = {
  integer: { pattern: /^-?\d+$/, message: 'must be a whole number' },
  decimal: { pattern: /^-?\d+(\.\d+)?$/, message: 'must be a decimal number such as 1250.00' },
  boolean: { pattern: /^(true|false)$/i, message: 'must be true or false' },
  date: { pattern: /^\d{4}-\d{2}-\d{2}$/, message: 'must be a date as YYYY-MM-DD' },
}

/** `member_number` -> `Member number`. */
export function labelFromName(name: string): string {
  const spaced = name.replace(/[_.-]+/g, ' ').trim()
  return spaced.charAt(0).toUpperCase() + spaced.slice(1)
}

export function buildInputFields(inputs: Record<string, InputSpec> | null | undefined): InputField[] {
  if (!inputs) return []
  return Object.entries(inputs).map(([name, spec]) => ({
    name,
    label: labelFromName(name),
    spec,
    required: spec.required !== false,
    sensitive: Boolean(spec.sensitive),
    htmlType: spec.sensitive ? 'password' : spec.type === 'date' ? 'date' : 'text',
    inputMode: INPUT_MODES[spec.type] ?? 'text',
    placeholder: spec.sensitive ? '' : (spec.example ?? ''),
  }))
}

/** Compiles a backend (Python) regex for client use; null when JavaScript cannot express it. */
export function compilePattern(pattern: string | null | undefined): RegExp | null {
  if (!pattern) return null
  // Patterns come from the artifact and may use syntax JS lacks; failing to compile skips the client check.
  try {
    return new RegExp(pattern)
  } catch (error) {
    console.warn('compilePattern: pattern not valid in JavaScript; skipping client check', { pattern, error })
    return null
  }
}

/** The error message for one value, or null when it is acceptable. */
export function validateInputValue(spec: InputSpec, rawValue: string | null | undefined): string | null {
  const value = (rawValue ?? '').trim()
  if (value === '') return spec.required === false ? null : 'Required'
  const typeRule = TYPE_PATTERNS[spec.type]
  if (typeRule && !typeRule.pattern.test(value)) return `Value ${typeRule.message}`
  const pattern = compilePattern(spec.pattern)
  if (pattern && !pattern.test(value)) return `Must match ${spec.pattern}`
  return null
}

export function validateInputs(
  fields: InputField[],
  values: Record<string, string>,
): Record<string, string> {
  const errors: Record<string, string> = {}
  for (const field of fields) {
    const error = validateInputValue(field.spec, values[field.name])
    if (error) errors[field.name] = error
  }
  return errors
}

/** Trimmed values for non-empty fields only; optional blanks are omitted from the request. */
export function collectInputValues(fields: InputField[], values: Record<string, string>): Record<string, string> {
  const collected: Record<string, string> = {}
  for (const field of fields) {
    const value = (values[field.name] ?? '').trim()
    if (value !== '') collected[field.name] = value
  }
  return collected
}

// ---------------------------------------------------------------- discovery goal placeholders

const PLACEHOLDER = /\{\{\s*([a-zA-Z_][a-zA-Z0-9_]*(?:\.[a-zA-Z_][a-zA-Z0-9_]*)?)\s*\}\}/g

/**
 * Caller input names referenced as {{name}} in a goal, in first-use order, without duplicates.
 * Dotted names ({{teller.password}}) are credential fields resolved by the server, so they are skipped.
 */
export function goalPlaceholders(goal: string | null | undefined): string[] {
  if (!goal) return []
  const names: string[] = []
  for (const match of goal.matchAll(PLACEHOLDER)) {
    const name = match[1]
    if (!name.includes('.') && !names.includes(name)) names.push(name)
  }
  return names
}

export interface KeyValueRow {
  key: string
  value: string
  sensitive: boolean
}

/** Keeps existing rows, adds a row for each new placeholder, and drops nothing the user typed. */
export function syncRowsWithPlaceholders(rows: KeyValueRow[], placeholders: string[]): KeyValueRow[] {
  const existing = rows.map((row) => row.key)
  const added = placeholders
    .filter((name) => !existing.includes(name))
    .map((name) => ({ key: name, value: '', sensitive: false }))
  return [...rows, ...added]
}

export function rowsToInputs(rows: KeyValueRow[]): { inputs: Record<string, string>; sensitive: string[] } {
  const inputs: Record<string, string> = {}
  const sensitive: string[] = []
  for (const row of rows) {
    const key = row.key.trim()
    if (!key) continue
    inputs[key] = row.value
    if (row.sensitive) sensitive.push(key)
  }
  return { inputs, sensitive }
}

const SLUG = /^[a-z][a-z0-9_.-]*$/

export function validateCapabilityId(capabilityId: string): string | null {
  if (!capabilityId.trim()) return 'Required'
  if (!SLUG.test(capabilityId.trim())) return 'Lowercase letters, digits, and . _ - only; must start with a letter'
  return null
}
