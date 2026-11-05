import { describe, expect, it, vi } from 'vitest'
import type { InputSpec } from '../api/types'
import { memberBalanceCapability } from '../fixtures'
import {
  buildInputFields,
  collectInputValues,
  compilePattern,
  goalPlaceholders,
  labelFromName,
  rowsToInputs,
  syncRowsWithPlaceholders,
  validateCapabilityId,
  validateInputs,
  validateInputValue,
} from './inputs'

const memberSpec = memberBalanceCapability.inputs.member_number

describe('labelFromName', () => {
  it('turns identifiers into labels', () => {
    expect(labelFromName('member_number')).toBe('Member number')
    expect(labelFromName('')).toBe('')
  })
})

describe('buildInputFields', () => {
  it('builds a field from the real contract', () => {
    const [field] = buildInputFields(memberBalanceCapability.inputs)
    expect(field).toMatchObject({ name: 'member_number', required: true, sensitive: false, htmlType: 'text', placeholder: '10001' })
  })
  it('masks sensitive inputs and hides their example', () => {
    const [field] = buildInputFields({ ssn: { type: 'string', description: '', sensitive: true, example: '123' } })
    expect(field).toMatchObject({ htmlType: 'password', placeholder: '', sensitive: true })
  })
  it('picks numeric keyboards for numbers and treats required:false as optional', () => {
    const [amount] = buildInputFields({ amount: { type: 'decimal', description: '', required: false } })
    expect(amount).toMatchObject({ inputMode: 'decimal', required: false })
  })
  it('returns no fields for null or empty inputs', () => {
    expect(buildInputFields(null)).toEqual([])
    expect(buildInputFields({})).toEqual([])
  })
})

describe('compilePattern', () => {
  it('compiles valid patterns', () => {
    expect(compilePattern('^\\d+$')?.test('10001')).toBe(true)
  })
  it('returns null for empty or JS-incompatible patterns', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    expect(compilePattern(null)).toBeNull()
    expect(compilePattern('')).toBeNull()
    expect(compilePattern('(?P<x>a)')).toBeNull()
    warn.mockRestore()
  })
})

describe('validateInputValue', () => {
  it('accepts values matching the pattern', () => {
    expect(validateInputValue(memberSpec, '10002')).toBeNull()
    expect(validateInputValue(memberSpec, ' 99999 ')).toBeNull()
  })
  it('rejects values that break the pattern', () => {
    expect(validateInputValue(memberSpec, 'abc')).toBe('Must match ^\\d+$')
  })
  it('requires required values, including null and whitespace', () => {
    expect(validateInputValue(memberSpec, '')).toBe('Required')
    expect(validateInputValue(memberSpec, null)).toBe('Required')
    expect(validateInputValue(memberSpec, '   ')).toBe('Required')
  })
  it('allows empty optional values', () => {
    expect(validateInputValue({ ...memberSpec, required: false }, '')).toBeNull()
  })
  it('checks declared types', () => {
    const spec = (type: InputSpec['type']): InputSpec => ({ type, description: '' })
    expect(validateInputValue(spec('integer'), '1.5')).toMatch(/whole number/)
    expect(validateInputValue(spec('decimal'), '1250.00')).toBeNull()
    expect(validateInputValue(spec('decimal'), '1,250')).toMatch(/decimal/)
    expect(validateInputValue(spec('boolean'), 'TRUE')).toBeNull()
    expect(validateInputValue(spec('date'), '2026-13')).toMatch(/YYYY-MM-DD/)
  })
})

describe('validateInputs / collectInputValues', () => {
  const fields = buildInputFields({ ...memberBalanceCapability.inputs, note: { type: 'string', description: '', required: false } })
  it('collects per-field errors', () => {
    expect(validateInputs(fields, { member_number: 'x' })).toEqual({ member_number: 'Must match ^\\d+$' })
    expect(validateInputs(fields, { member_number: '1' })).toEqual({})
    expect(validateInputs(fields, {})).toEqual({ member_number: 'Required' })
  })
  it('trims and drops empty optional values', () => {
    expect(collectInputValues(fields, { member_number: ' 10002 ', note: '  ' })).toEqual({ member_number: '10002' })
    expect(collectInputValues([], {})).toEqual({})
  })
})

describe('goalPlaceholders', () => {
  it('finds caller inputs in order, without duplicates or credentials', () => {
    const goal = 'Sign on as {{teller.username}}, find {{ member_number }} then {{share}} for {{member_number}}'
    expect(goalPlaceholders(goal)).toEqual(['member_number', 'share'])
  })
  it('returns nothing for empty or placeholder-free goals', () => {
    expect(goalPlaceholders('')).toEqual([])
    expect(goalPlaceholders(null)).toEqual([])
    expect(goalPlaceholders('no inputs {{ }}')).toEqual([])
  })
})

describe('syncRowsWithPlaceholders', () => {
  it('adds rows for new placeholders and keeps existing rows', () => {
    const rows = [{ key: 'member_number', value: '10001', sensitive: false }]
    expect(syncRowsWithPlaceholders(rows, ['member_number', 'share'])).toEqual([
      rows[0],
      { key: 'share', value: '', sensitive: false },
    ])
  })
  it('never drops a row the user typed', () => {
    const rows = [{ key: 'extra', value: 'x', sensitive: true }]
    expect(syncRowsWithPlaceholders(rows, [])).toEqual(rows)
  })
})

describe('rowsToInputs', () => {
  it('builds inputs and the sensitive list, skipping blank keys', () => {
    expect(
      rowsToInputs([
        { key: ' member_number ', value: '10001', sensitive: false },
        { key: 'pin', value: '1234', sensitive: true },
        { key: '', value: 'ignored', sensitive: true },
      ]),
    ).toEqual({ inputs: { member_number: '10001', pin: '1234' }, sensitive: ['pin'] })
  })
  it('returns empty structures for no rows', () => {
    expect(rowsToInputs([])).toEqual({ inputs: {}, sensitive: [] })
  })
})

describe('validateCapabilityId', () => {
  it('accepts slugs', () => {
    expect(validateCapabilityId('coreone.member_balance')).toBeNull()
  })
  it('rejects empty and malformed ids', () => {
    expect(validateCapabilityId('  ')).toBe('Required')
    expect(validateCapabilityId('CoreOne Balance')).toMatch(/Lowercase/)
    expect(validateCapabilityId('1abc')).toMatch(/start with a letter/)
  })
})
