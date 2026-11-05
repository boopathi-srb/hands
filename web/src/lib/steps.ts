/** Step-id lookups against a capability, for labelling timeline rows and failure cards. */

import type { Capability, RunResult, StepTrace } from '../api/types'

/** step id -> description for main steps and every subflow step. */
export function stepDescriptions(capability: Capability | null | undefined): Record<string, string> {
  if (!capability) return {}
  const descriptions: Record<string, string> = {}
  const subflowSteps = Object.values(capability.subflows ?? {}).flat()
  for (const step of [...capability.steps, ...subflowSteps]) descriptions[step.id] = step.description
  return descriptions
}

/** Counts per step status in a result's trace, e.g. {ok: 7, recovered: 1}. */
export function traceStatusCounts(steps: StepTrace[] | null | undefined): Record<string, number> {
  const counts: Record<string, number> = {}
  for (const step of steps ?? []) counts[step.status] = (counts[step.status] ?? 0) + 1
  return counts
}

/** Distinct recoveries applied anywhere in the trace, in first-seen order. */
export function appliedRecoveries(result: RunResult | null | undefined): string[] {
  const names: string[] = []
  for (const step of result?.steps ?? []) {
    for (const name of step.recoveries_applied) if (!names.includes(name)) names.push(name)
  }
  return names
}
