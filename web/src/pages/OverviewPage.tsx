import { Link } from 'react-router-dom'
import { useApp } from '../app/AppContext'
import { ErrorNotice, EmptyState, Loading } from '../components/Feedback'
import { PageHeader, Panel } from '../components/Panel'
import { RunsTable } from '../components/RunsTable'
import { useApiResource, useNow } from '../hooks/useAsync'
import type { Health } from '../api/types'

const DEMO_CAPABILITY = 'coreone.member_balance'

interface HealthRow {
  label: string
  ok: boolean | null
  value: string
}

export function healthRows(health: Health | null): HealthRow[] {
  if (!health) return []
  return [
    { label: 'CoreOne mock app', ok: health.mock_app === 'up', value: health.mock_app === 'up' ? 'Up' : 'Down' },
    { label: 'Planner: Anthropic', ok: health.planners.anthropic, value: health.planners.anthropic ? 'Available' : 'No API key' },
    { label: 'Planner: Ollama (dev)', ok: health.planners.ollama, value: health.planners.ollama ? 'Available' : 'Not running' },
    { label: 'Planner: scripted', ok: health.planners.scripted, value: 'Offline, deterministic' },
    { label: 'Active run', ok: null, value: health.active_run ?? 'None' },
    { label: 'Access token', ok: null, value: health.auth_required ? 'Required' : 'Not required' },
  ]
}

function HealthPanel() {
  const { health, healthError } = useApp()
  return (
    <Panel title="System health" subtitle={health ? `API version ${health.version}` : undefined}>
      {healthError ? <ErrorNotice error={healthError} /> : null}
      {!health && !healthError ? <Loading label="Checking health" /> : null}
      {health ? (
        <ul className="health-list">
          {healthRows(health).map((row) => (
            <li key={row.label}>
              <span>{row.label}</span>
              <span className="health">
                {row.ok !== null ? <span className={`dot ${row.ok ? 'up' : 'down'}`} aria-hidden="true" /> : null}
                {row.label === 'Active run' && health.active_run ? (
                  <Link to={`/runs/${encodeURIComponent(health.active_run)}`} className="mono">
                    {health.active_run}
                  </Link>
                ) : (
                  row.value
                )}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </Panel>
  )
}

function QuickActions() {
  const runBase = `/capabilities/${encodeURIComponent(DEMO_CAPABILITY)}/run`
  return (
    <Panel title="Quick actions">
      <div className="quick-actions">
        <Link className="quick-action" to={`${runBase}?member_number=10002`}>
          <strong>Replay: member 10002</strong>
          <span className="faint">Deterministic replay, no model. Returns the savings balance.</span>
        </Link>
        <Link className="quick-action" to={`${runBase}?member_number=99999`}>
          <strong>Replay: unknown member 99999</strong>
          <span className="faint">Returns the business outcome MEMBER_NOT_FOUND, not an error.</span>
        </Link>
        <Link className="quick-action" to={`${runBase}?member_number=10001&fault=identity_check`}>
          <strong>Replay with an identity check</strong>
          <span className="faint">Pauses for an operator to take control of the live session.</span>
        </Link>
        <Link className="quick-action" to="/discover">
          <strong>Discover a new capability</strong>
          <span className="faint">A model works out the flow once and records it.</span>
        </Link>
      </div>
    </Panel>
  )
}

function RecentRuns() {
  const { client } = useApp()
  const runs = useApiResource(() => client.runs(8), 'recent-runs')
  const now = useNow(1000, true)
  return (
    <Panel title="Recent runs" actions={<Link to="/runs">All runs</Link>} flush>
      {runs.error ? (
        <div className="panel-body">
          <ErrorNotice error={runs.error} />
        </div>
      ) : null}
      {runs.loading && !runs.data ? (
        <div className="panel-body">
          <Loading label="Loading runs" />
        </div>
      ) : null}
      {runs.data && runs.data.length === 0 ? <EmptyState title="No runs yet">Start with a quick action.</EmptyState> : null}
      {runs.data && runs.data.length > 0 ? <RunsTable runs={runs.data} nowMillis={now} caption="Recent runs" /> : null}
    </Panel>
  )
}

export function OverviewPage() {
  return (
    <>
      <PageHeader
        eyebrow="Overview"
        title="AI-agent integration for back-office systems"
        lede="hands lets an agent operate legacy banking software that has no API, safely and repeatably."
      />
      <ol className="explainer" aria-label="How hands works">
        <li>
          <span className="step-no">01 · Discover</span>
          <strong>A model works out the task once</strong>
          <span className="muted">It drives the real app through the accessibility tree, behind policy and redaction.</span>
        </li>
        <li>
          <span className="step-no">02 · Capability</span>
          <strong>The run becomes a typed, versioned contract</strong>
          <span className="muted">Inputs, outputs, ranked locators, outcomes and recoveries, reviewed and approved.</span>
        </li>
        <li>
          <span className="step-no">03 · Replay</span>
          <strong>Production replays it with no model</strong>
          <span className="muted">A typed result: success, business outcome, escalated to a human, or failed with evidence.</span>
        </li>
      </ol>
      <div className="grid grid-sidebar">
        <RecentRuns />
        <div className="stack">
          <HealthPanel />
          <QuickActions />
        </div>
      </div>
    </>
  )
}
