import { describe, expect, it } from 'vitest'
import type { RunEvent } from '../api/types'
import {
  discoveryEvents,
  replayFailedEvents,
  replayHumanResumeEvents,
  replayOutcomeEvents,
  replaySuccessEvents,
} from '../fixtures'
import {
  buildTimeline,
  currentActivity,
  mergeEvents,
  notablePolicies,
  summarizeDecisionAction,
  type DecisionEntry,
  type HumanEntry,
  type NoticeEntry,
  type StepEntry,
} from './timeline'

const steps = (events: RunEvent[]) => buildTimeline(events).filter((entry): entry is StepEntry => entry.type === 'step')
const notices = (events: RunEvent[]) => buildTimeline(events).filter((entry): entry is NoticeEntry => entry.type === 'notice')

describe('buildTimeline', () => {
  it('returns no entries for empty or missing events', () => {
    expect(buildTimeline([])).toEqual([])
    expect(buildTimeline(null)).toEqual([])
  })

  it('folds a successful replay into ordered steps with subflow depth', () => {
    const stepEntries = steps(replaySuccessEvents)
    expect(stepEntries.map((step) => [step.stepId, step.depth, step.status])).toEqual([
      ['sign_on', 0, 'ok'],
      ['login_open', 1, 'ok'],
      ['login_user', 1, 'ok'],
      ['login_password', 1, 'ok'],
      ['login_submit', 1, 'ok'],
      ['type_member_number_textbox', 0, 'ok'],
      ['click_search_button', 0, 'ok'],
      ['read_savings_balance', 0, 'ok'],
    ])
  })

  it('attaches matched candidate, policy and output to their step', () => {
    const read = steps(replaySuccessEvents).find((step) => step.stepId === 'read_savings_balance')
    expect(read).toMatchObject({ matchedRank: 0, matchedKind: 'text_anchor', output: 'savings_balance', ambiguous: false })
    const open = steps(replaySuccessEvents).find((step) => step.stepId === 'login_open')
    expect(open?.policy).toMatchObject({ verdict: 'allow', rule: 'risk.default' })
  })

  it('ends with a run_finished notice', () => {
    const last = notices(replaySuccessEvents).at(-1)
    expect(last).toMatchObject({ title: 'Run finished: success', tone: 'success' })
  })

  it('shows a business outcome as an outcome notice, not a failure', () => {
    const outcome = notices(replayOutcomeEvents).find((notice) => notice.tone === 'outcome' && notice.title.startsWith('Business'))
    expect(outcome).toMatchObject({ title: 'Business outcome MEMBER_NOT_FOUND', detail: 'No member found for number 99999.' })
  })

  it('records recoveries and the human step of the handoff run', () => {
    const entries = buildTimeline(replayHumanResumeEvents)
    const submit = entries.find((entry): entry is StepEntry => entry.type === 'step' && entry.stepId === 'login_submit')
    expect(submit?.status).toBe('human')
    expect(submit?.recoveries).toEqual([{ name: 'identity_verification', response: 'escalate', applications: 1, maxApplications: 1 }])
    const escalations = entries.filter((entry) => entry.type === 'notice' && entry.title === 'Escalated to an operator')
    expect(escalations).toHaveLength(1)
    const human = entries.find((entry): entry is HumanEntry => entry.type === 'human')
    expect(human?.operatorId).toBe('ops-demo')
    expect(human?.actions.map((action) => action.kind)).toEqual(['click', 'type', 'click'])
    expect(human?.actions[1].text_length).toBe(19)
    const handbacks = entries.filter((entry) => entry.type === 'notice' && entry.title.startsWith('Operator handed back'))
    expect(handbacks).toHaveLength(1)
  })

  it('marks the restart and the failed steps of an exhausted recovery', () => {
    const entries = buildTimeline(replayFailedEvents)
    expect(entries.some((entry) => entry.type === 'notice' && entry.title.startsWith('Flow restarted'))).toBe(true)
    const failed = steps(replayFailedEvents).filter((step) => step.status === 'failed')
    expect(failed.map((step) => step.stepId)).toContain('login_open')
    expect(notices(replayFailedEvents).at(-1)).toMatchObject({ tone: 'failed', detail: 'recovery_exhausted' })
  })

  it('lists model decisions with rationale, policy and the screen the model saw', () => {
    const decisions = buildTimeline(discoveryEvents).filter((entry): entry is DecisionEntry => entry.type === 'decision')
    expect(decisions).toHaveLength(7)
    expect(decisions[0]).toMatchObject({
      step: 1,
      actionSummary: 'type {{teller.username}} into n12',
      rationale: 'Enter username to sign in.',
      latencyMs: 3704,
    })
    expect(decisions[0].policy?.verdict).toBe('allow')
    expect(decisions[0].screenshot).toMatch(/^screenshots\//)
    expect(decisions[5].actionSummary).toBe('extract n49 as savings_balance')
    expect(decisions[6].actionKind).toBe('done')
  })

  it('closes steps left running when the run finishes', () => {
    const events: RunEvent[] = [
      { seq: 1, ts: '2026-01-01T00:00:00Z', kind: 'step_started', data: { step_id: 'a' } },
      { seq: 2, ts: '2026-01-01T00:00:01Z', kind: 'run_finished', data: { status: 'failed', code: 'surface_error' } },
    ]
    expect(steps(events)[0].status).toBe('failed')
  })

  it('surfaces a non-allow policy verdict without a step as its own notice', () => {
    const events: RunEvent[] = [
      { seq: 1, ts: '2026-01-01T00:00:00Z', kind: 'policy_decision', data: { verdict: 'deny', reason: 'blocked path /_admin' } },
    ]
    expect(notices(events)[0]).toMatchObject({ title: 'Policy deny', tone: 'failed' })
  })
})

describe('summarizeDecisionAction', () => {
  it('summarizes each action kind', () => {
    expect(summarizeDecisionAction({ kind: 'click', node_ref: 'n18' })).toBe('click n18')
    expect(summarizeDecisionAction({ kind: 'press', key: 'Enter' })).toBe('press Enter')
    expect(summarizeDecisionAction({ kind: 'select', option: 'Savings', node_ref: 'n3' })).toBe('select “Savings” in n3')
    expect(summarizeDecisionAction({ kind: 'type', value: 'x' })).toBe('type x into field')
  })
  it('handles a missing action', () => {
    expect(summarizeDecisionAction(null)).toBe('no action')
    expect(summarizeDecisionAction({})).toBe('action')
  })
})

describe('currentActivity', () => {
  it('reports the innermost running step', () => {
    const events: RunEvent[] = [
      { seq: 1, ts: '2026-01-01T00:00:00Z', kind: 'step_started', data: { step_id: 'click_search_button', description: 'Click Search button.' } },
    ]
    expect(currentActivity(buildTimeline(events))).toBe('Click Search button.')
  })
  it('is null once the run finished, and for an empty timeline', () => {
    expect(currentActivity(buildTimeline(replaySuccessEvents))).toBeNull()
    expect(currentActivity([])).toBeNull()
  })
  it('reports the latest model rationale during discovery', () => {
    const partial = discoveryEvents.filter((event) => event.kind !== 'run_finished')
    expect(currentActivity(buildTimeline(partial))).toBe('Savings balance already extracted.')
  })
})

describe('mergeEvents', () => {
  const event = (seq: number): RunEvent => ({ seq, ts: '', kind: 'x', data: {} })
  it('appends only newer events in seq order', () => {
    expect(mergeEvents([event(1), event(2)], [event(2), event(4), event(3)]).map((item) => item.seq)).toEqual([1, 2, 3, 4])
  })
  it('returns the same list when nothing is new', () => {
    const known = [event(1)]
    expect(mergeEvents(known, [])).toBe(known)
    expect(mergeEvents(known, [event(1)])).toBe(known)
  })
  it('accepts a first page into an empty list', () => {
    expect(mergeEvents([], [event(0)])).toHaveLength(1)
  })
})

describe('notablePolicies', () => {
  it('is empty when every action was allowed', () => {
    expect(notablePolicies(buildTimeline(replaySuccessEvents))).toEqual([])
    expect(notablePolicies([])).toEqual([])
  })
  it('collects escalate and deny verdicts attached to steps', () => {
    const events: RunEvent[] = [
      { seq: 1, ts: '', kind: 'step_started', data: { step_id: 'submit' } },
      { seq: 2, ts: '', kind: 'policy_decision', data: { step_id: 'submit', verdict: 'escalate', rule: 'risk.submit' } },
    ]
    expect(notablePolicies(buildTimeline(events))).toEqual([{ verdict: 'escalate', risk: null, rule: 'risk.submit', reason: null }])
  })
})
