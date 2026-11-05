import type { DecisionEntry, HumanEntry, NoticeEntry, PolicyView, StepEntry, StepStatus, TimelineEntry } from '../lib/timeline'
import { candidateKindLabel } from '../lib/candidates'
import { describeHumanAction } from '../lib/liveInput'
import { formatClock, formatDurationMs, parseTime, type Tone } from '../lib/format'
import { RunFileLink } from './RunFile'

const STEP_TONES: Record<StepStatus, Tone> = {
  running: 'running',
  ok: 'success',
  recovered: 'attention',
  human: 'escalated',
  failed: 'failed',
  skipped: 'neutral',
}

const STEP_LABELS: Record<StepStatus, string> = {
  running: 'running',
  ok: 'ok',
  recovered: 'recovered',
  human: 'human',
  failed: 'failed',
  skipped: 'skipped',
}

function Marker({ tone, filled }: { tone: Tone; filled?: boolean }) {
  return <span className={`tl-marker ${filled ? 'filled' : ''}`} style={{ color: `var(--${tone === 'neutral' ? 'neutral' : tone})` }} aria-hidden="true" />
}

function PolicyChip({ policy }: { policy: PolicyView }) {
  const className = policy.verdict === 'allow' ? 'chip' : policy.verdict === 'deny' ? 'chip danger' : 'chip warn'
  return (
    <span className={className} title={policy.reason ?? undefined}>
      policy {policy.verdict}
      {policy.rule ? ` · ${policy.rule}` : ''}
    </span>
  )
}

function stepDuration(entry: StepEntry): string | null {
  const start = parseTime(entry.ts)
  const end = parseTime(entry.finishedTs)
  return start !== null && end !== null ? formatDurationMs(end - start) : null
}

function StepItem({ entry, label }: { entry: StepEntry; label: string }) {
  const tone = STEP_TONES[entry.status]
  const duration = stepDuration(entry)
  return (
    <li className={`tl-item depth-${Math.min(entry.depth, 2)}`}>
      <Marker tone={tone} filled={entry.status !== 'running'} />
      <div className="tl-body">
        <div className="tl-title">
          <span className="cell-main">{label}</span>
          <span className={`badge no-dot tone-${tone}`}>{STEP_LABELS[entry.status]}</span>
        </div>
        <div className="tl-meta">
          <code className="chip mono">{entry.stepId}</code>
          {entry.action ? <span className="chip">{entry.action}</span> : null}
          {entry.risk === 'risky' ? <span className="chip warn">risky</span> : null}
          {entry.matchedRank !== null ? (
            <span className={entry.matchedRank > 0 ? 'chip warn' : 'chip'} title="Which ranked locator candidate found the target">
              {entry.matchedRank > 0 ? `fallback #${entry.matchedRank + 1}` : 'primary'} · {candidateKindLabel(entry.matchedKind).toLowerCase()}
            </span>
          ) : null}
          {entry.ambiguous ? <span className="chip warn">ambiguous match</span> : null}
          {entry.output ? <span className="chip info">→ {entry.output}</span> : null}
          {entry.policy ? <PolicyChip policy={entry.policy} /> : null}
          {entry.failedCheck ? <span className="chip danger">{entry.failedCheck} failed</span> : null}
        </div>
        {entry.recoveries.length ? (
          <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }} aria-label="Recoveries applied">
            {entry.recoveries.map((recovery, index) => (
              <li key={`${recovery.name}-${index}`} className="row">
                <span className="chip warn">recovery {recovery.name}</span>
                <span className="faint">
                  {recovery.response ? `${recovery.response}` : ''}
                  {recovery.applications !== null && recovery.maxApplications !== null
                    ? ` · application ${recovery.applications} of ${recovery.maxApplications}`
                    : ''}
                </span>
              </li>
            ))}
          </ul>
        ) : null}
      </div>
      <span className="tl-time">{duration ?? formatClock(entry.ts)}</span>
    </li>
  )
}

function DecisionItem({ entry, runId }: { entry: DecisionEntry; runId: string }) {
  const tone: Tone = entry.error ? 'failed' : 'running'
  return (
    <li className="tl-item">
      <Marker tone={tone} filled />
      <div className="tl-body">
        <div className="tl-title">
          <span className="cell-main">Model decision{entry.step !== null ? ` ${entry.step}` : ''}</span>
          <code className="chip mono">{entry.actionSummary}</code>
        </div>
        {entry.rationale ? <p className="rationale">{entry.rationale}</p> : null}
        <div className="tl-meta">
          {entry.expectedResult ? <span className="chip">expects: {entry.expectedResult}</span> : null}
          {entry.latencyMs !== null ? <span className="chip num">{formatDurationMs(entry.latencyMs)}</span> : null}
          {entry.inputTokens !== null ? (
            <span className="chip num" title="Input / output tokens">
              {entry.inputTokens} in / {entry.outputTokens ?? 0} out
            </span>
          ) : null}
          {entry.policy ? <PolicyChip policy={entry.policy} /> : null}
          {entry.screenshot ? <RunFileLink runId={runId} path={entry.screenshot} label="screen the model saw" /> : null}
        </div>
        {entry.error ? <p className="field-error">Rejected: {entry.error}</p> : null}
      </div>
      <span className="tl-time">{formatClock(entry.ts)}</span>
    </li>
  )
}

function NoticeItem({ entry, runId }: { entry: NoticeEntry; runId: string }) {
  return (
    <li className="tl-item">
      <Marker tone={entry.tone} filled />
      <div className="tl-body">
        <span className="cell-main" style={{ color: `var(--${entry.tone})` }}>
          {entry.title}
        </span>
        {entry.detail ? <span className="muted">{entry.detail}</span> : null}
        <div className="tl-meta">
          {entry.stepId ? <code className="chip mono">{entry.stepId}</code> : null}
          {entry.screenshot ? <RunFileLink runId={runId} path={entry.screenshot} label="screenshot" /> : null}
        </div>
      </div>
      <span className="tl-time">{formatClock(entry.ts)}</span>
    </li>
  )
}

function HumanItem({ entry }: { entry: HumanEntry }) {
  return (
    <li className="tl-item">
      <Marker tone="escalated" filled />
      <div className="tl-body">
        <span className="cell-main">Operator {entry.operatorId ?? ''} acted on the live session</span>
        <ul className="action-log" aria-label="Captured human actions">
          {entry.actions.map((action, index) => (
            <li key={index}>{describeHumanAction(action)}</li>
          ))}
        </ul>
        <span className="faint">Typed text is never stored, only its length.</span>
      </div>
      <span className="tl-time">{formatClock(entry.ts)}</span>
    </li>
  )
}

interface TimelineProps {
  entries: TimelineEntry[]
  runId: string
  stepLabel: (stepId: string, fallback: string | null) => string
}

export function Timeline({ entries, runId, stepLabel }: TimelineProps) {
  if (entries.length === 0) return <p className="muted" style={{ padding: '12px 16px' }}>No events yet.</p>
  return (
    <ol className="timeline" aria-label="Run timeline">
      {entries.map((entry) => {
        switch (entry.type) {
          case 'step':
            return <StepItem key={entry.key} entry={entry} label={stepLabel(entry.stepId, entry.description)} />
          case 'decision':
            return <DecisionItem key={entry.key} entry={entry} runId={runId} />
          case 'notice':
            return <NoticeItem key={entry.key} entry={entry} runId={runId} />
          case 'human':
            return <HumanItem key={entry.key} entry={entry} />
        }
      })}
    </ol>
  )
}
