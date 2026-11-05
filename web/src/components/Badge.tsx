import type { RunListItem } from '../api/types'
import { runBadge, stateBadge, statusBadge, type Badge as BadgeModel, type Tone } from '../lib/format'

export function Badge({ badge }: { badge: BadgeModel }) {
  return (
    <span className={`badge tone-${badge.tone}`} title={badge.hint}>
      {badge.label}
    </span>
  )
}

export function ToneBadge({ tone, children, title }: { tone: Tone; children: string; title?: string }) {
  return (
    <span className={`badge tone-${tone}`} title={title}>
      {children}
    </span>
  )
}

export function RunBadge({ run }: { run: Pick<RunListItem, 'state' | 'status'> }) {
  return <Badge badge={runBadge(run)} />
}

export function StatusBadge({ status }: { status: string | null | undefined }) {
  return <Badge badge={statusBadge(status)} />
}

export function StateBadge({ state }: { state: string | null | undefined }) {
  return <Badge badge={stateBadge(state)} />
}

const CAPABILITY_STATUS_TONES: Record<string, Tone> = { approved: 'success', draft: 'neutral', deprecated: 'failed' }

export function CapabilityStatusBadge({ status }: { status: string }) {
  const label = status.charAt(0).toUpperCase() + status.slice(1)
  return <ToneBadge tone={CAPABILITY_STATUS_TONES[status] ?? 'neutral'}>{label}</ToneBadge>
}
