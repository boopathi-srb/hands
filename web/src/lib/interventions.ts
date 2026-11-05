/** Normalizes the run's open intervention, whatever shape the API sends (see RawIntervention). */

import type { ControlLease, InterventionContext, InterventionRequest, RawIntervention } from '../api/types'

export interface InterventionView {
  request: InterventionRequest
  lease: ControlLease | null
  screenshotDataUrl: string | null
  screenshotPath: string | null
}

function isContext(raw: RawIntervention): raw is InterventionContext {
  return typeof (raw as InterventionContext).request === 'object' && (raw as InterventionContext).request !== null
}

export function normalizeIntervention(raw: RawIntervention | null | undefined): InterventionView | null {
  if (!raw) return null
  if (isContext(raw)) {
    return {
      request: raw.request,
      lease: raw.lease ?? null,
      screenshotDataUrl: raw.screenshot_data_url ?? null,
      screenshotPath: raw.request.screenshot_path ?? null,
    }
  }
  if (!raw.intervention_id) {
    console.warn('normalizeIntervention: intervention without an id', Object.keys(raw))
    return null
  }
  const { lease, screenshot_data_url: screenshotDataUrl, ...request } = raw
  return {
    request,
    lease: lease ?? null,
    screenshotDataUrl: screenshotDataUrl ?? null,
    screenshotPath: request.screenshot_path ?? null,
  }
}

const KIND_LABELS: Record<string, string> = {
  stuck: 'Automation is stuck',
  unrecoverable: 'Unrecoverable state',
  risky_action: 'Risky action needs approval',
  policy_block: 'Blocked by policy',
}

export function interventionKindLabel(kind: string | null | undefined): string {
  if (!kind) return 'Intervention'
  return KIND_LABELS[kind] ?? kind
}

/** Who holds the session, for the lease chip: "Automation", "Human (alice)", "Nobody". */
export function holderLabel(lease: ControlLease | null | undefined): string {
  if (!lease) return 'Unknown'
  const name = lease.holder.charAt(0).toUpperCase() + lease.holder.slice(1)
  return lease.holder === 'human' && lease.holder_id ? `${name} (${lease.holder_id})` : name
}

/** Screenshot paths in events and requests are relative to the run dir; absolute ones are not servable. */
export function relativeRunPath(path: string | null | undefined): string | null {
  if (!path) return null
  if (path.startsWith('/')) {
    const marker = path.search(/\/(screenshots|snapshots)\//)
    return marker >= 0 ? path.slice(marker + 1) : null
  }
  return path
}
