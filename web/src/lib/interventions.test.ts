import { describe, expect, it, vi } from 'vitest'
import type { ControlLease, InterventionRequest, RawIntervention } from '../api/types'
import { humanResumeResult, memberBalanceCapability, successResult } from '../fixtures'
import { holderLabel, interventionKindLabel, normalizeIntervention, relativeRunPath } from './interventions'
import { appliedRecoveries, stepDescriptions, traceStatusCounts } from './steps'

const request: InterventionRequest = {
  intervention_id: 'replay-b8fd4634c051-intervention-1',
  session_id: 'replay-b8fd4634c051',
  run_id: 'replay-b8fd4634c051',
  mode: 'replay',
  kind: 'stuck',
  reason: 'Member identity verification requires a human operator.',
  capability_id: 'coreone.member_balance',
  step_id: 'login_submit',
  screenshot_path: 'screenshots/053-replay-b8fd4634c051-intervention-1.png',
  created_at: '2026-09-28T17:52:01.946596Z',
}
const lease: ControlLease = { session_id: request.session_id, holder: 'nobody', holder_id: null, since: request.created_at }

describe('normalizeIntervention', () => {
  it('accepts the flat API shape (request plus lease)', () => {
    const view = normalizeIntervention({ ...request, lease })
    expect(view?.request.intervention_id).toBe(request.intervention_id)
    expect(view?.lease).toEqual(lease)
    expect(view?.screenshotPath).toBe(request.screenshot_path)
    expect(view?.request).not.toHaveProperty('lease')
  })
  it('accepts the console context shape', () => {
    const view = normalizeIntervention({ request, lease, screenshot_data_url: 'data:image/png;base64,AA' })
    expect(view?.screenshotDataUrl).toBe('data:image/png;base64,AA')
  })
  it('returns null for null and for objects without an id', () => {
    const warn = vi.spyOn(console, 'warn').mockImplementation(() => undefined)
    expect(normalizeIntervention(null)).toBeNull()
    expect(normalizeIntervention({ reason: 'x' } as unknown as RawIntervention)).toBeNull()
    warn.mockRestore()
  })
  it('defaults a missing lease to null', () => {
    expect(normalizeIntervention(request)?.lease).toBeNull()
  })
})

describe('interventionKindLabel', () => {
  it('labels known kinds and passes unknown ones through', () => {
    expect(interventionKindLabel('risky_action')).toBe('Risky action needs approval')
    expect(interventionKindLabel('other')).toBe('other')
    expect(interventionKindLabel(null)).toBe('Intervention')
  })
})

describe('holderLabel', () => {
  it('names the holder, with the operator for humans', () => {
    expect(holderLabel({ ...lease, holder: 'human', holder_id: 'alice' })).toBe('Human (alice)')
    expect(holderLabel({ ...lease, holder: 'automation', holder_id: 'replay-1' })).toBe('Automation')
    expect(holderLabel(lease)).toBe('Nobody')
  })
  it('handles a missing lease', () => {
    expect(holderLabel(null)).toBe('Unknown')
  })
})

describe('relativeRunPath', () => {
  it('keeps relative paths', () => {
    expect(relativeRunPath('screenshots/a.png')).toBe('screenshots/a.png')
  })
  it('reduces absolute paths to the run-relative part', () => {
    expect(relativeRunPath('/Users/x/hands/runs/replay-1/screenshots/a.png')).toBe('screenshots/a.png')
  })
  it('returns null for empty or unservable paths', () => {
    expect(relativeRunPath(null)).toBeNull()
    expect(relativeRunPath('/etc/passwd')).toBeNull()
  })
})

describe('stepDescriptions', () => {
  it('includes main and subflow steps', () => {
    const descriptions = stepDescriptions(memberBalanceCapability)
    expect(descriptions.click_search_button).toBe('Click Search button.')
    expect(descriptions.login_submit).toBe('Sign on.')
  })
  it('is empty without a capability', () => {
    expect(stepDescriptions(null)).toEqual({})
  })
})

describe('traceStatusCounts', () => {
  it('counts statuses in the trace', () => {
    expect(traceStatusCounts(humanResumeResult.steps)).toEqual({ ok: 7, human: 1 })
  })
  it('is empty for no steps', () => {
    expect(traceStatusCounts(undefined)).toEqual({})
    expect(traceStatusCounts([])).toEqual({})
  })
})

describe('appliedRecoveries', () => {
  it('lists distinct recoveries', () => {
    expect(appliedRecoveries(humanResumeResult)).toEqual(['identity_verification'])
  })
  it('is empty when nothing was recovered or there is no result', () => {
    expect(appliedRecoveries(successResult)).toEqual([])
    expect(appliedRecoveries(null)).toEqual([])
  })
})
