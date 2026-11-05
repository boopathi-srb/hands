import { useMemo } from 'react'
import { Link, useParams } from 'react-router-dom'
import type { RunDetail, RunResult } from '../api/types'
import { useApp } from '../app/AppContext'
import { RunBadge } from '../components/Badge'
import { ErrorNotice, Loading } from '../components/Feedback'
import { Filmstrip } from '../components/Filmstrip'
import { InterventionPanel } from '../components/InterventionPanel'
import { JsonDisclosure } from '../components/JsonDisclosure'
import { KeyValueList, PageHeader, Panel } from '../components/Panel'
import { ResultCard } from '../components/ResultCard'
import { RunFileLink } from '../components/RunFile'
import { Timeline } from '../components/Timeline'
import { useApiResource, useNow } from '../hooks/useAsync'
import { useRunLive } from '../hooks/useRunLive'
import { formatDuration, formatTimestamp, humanize, isRunResult, runHeadline } from '../lib/format'
import { normalizeIntervention } from '../lib/interventions'
import { appliedRecoveries, stepDescriptions, traceStatusCounts } from '../lib/steps'
import { buildTimeline, currentActivity, notablePolicies } from '../lib/timeline'

function useCapabilityFor(run: RunDetail | null) {
  const { client } = useApp()
  const capabilityId = run?.mode === 'replay' ? run.capability_id : null
  const version = run?.result && isRunResult(run.result) ? run.result.capability_version : null
  return useApiResource(
    () =>
      capabilityId
        ? client.capability(capabilityId, version)
        : Promise.resolve({ ok: false as const, error: { status: 0, code: 'none', message: '', body: null } }),
    `run-capability:${capabilityId ?? ''}:${version ?? ''}`,
  )
}

function RunFacts({ run, result, nowMillis }: { run: RunDetail; result: RunResult | null; nowMillis: number }) {
  const counts = traceStatusCounts(result?.steps)
  return (
    <Panel title="Run">
      <KeyValueList
        items={[
          { label: 'Mode', value: humanize(run.mode) },
          {
            label: 'Capability',
            value: run.capability_id ? (
              <Link to={`/capabilities/${encodeURIComponent(run.capability_id)}`} className="mono">
                {run.capability_id}
                {result ? `@${result.capability_version}` : ''}
              </Link>
            ) : null,
          },
          { label: 'Tenant', value: run.tenant ?? result?.tenant_id ?? 'lakeside (default)' },
          { label: 'Started', value: formatTimestamp(run.started_at) },
          { label: 'Finished', value: run.finished_at ? formatTimestamp(run.finished_at) : null },
          {
            label: 'Duration',
            value: <span className="num">{formatDuration(run.started_at, run.finished_at, nowMillis)}</span>,
          },
          {
            label: 'Step trace',
            value: Object.keys(counts).length
              ? Object.entries(counts)
                  .map(([status, count]) => `${count} ${status}`)
                  .join(' · ')
              : null,
          },
          { label: 'Evidence', value: result?.evidence_dir ? <code>{result.evidence_dir}</code> : null },
        ]}
      />
    </Panel>
  )
}

function DriftPanel({ result }: { result: RunResult }) {
  const recoveries = appliedRecoveries(result)
  const { fallback_steps: fallbackSteps, fingerprint_changes: fingerprintChanges } = result.drift
  const drifted = fallbackSteps.length > 0 || fingerprintChanges.length > 0
  return (
    <Panel title="Drift and recoveries">
      <KeyValueList
        items={[
          {
            label: 'Drift',
            value: drifted ? <span className="chip warn">UI differs from the recording</span> : 'None: every step matched its primary candidate',
          },
          {
            label: 'Fallback steps',
            value: fallbackSteps.length ? fallbackSteps.map((step) => <code key={step} className="chip mono">{step}</code>) : null,
          },
          {
            label: 'Fingerprint changes',
            value: fingerprintChanges.length ? fingerprintChanges.map((step) => <code key={step} className="chip mono">{step}</code>) : null,
          },
          {
            label: 'Recoveries applied',
            value: recoveries.length ? (
              <span className="tag-list">
                {recoveries.map((name) => (
                  <span key={name} className="chip warn mono">
                    {name}
                  </span>
                ))}
              </span>
            ) : (
              'None'
            ),
          },
        ]}
      />
    </Panel>
  )
}

export function RunDetailPage() {
  const { runId = '' } = useParams()
  const live = useRunLive(runId)
  const capability = useCapabilityFor(live.run)
  const now = useNow(1000, live.active)
  const timeline = useMemo(() => buildTimeline(live.events), [live.events])
  const descriptions = useMemo(() => stepDescriptions(capability.data?.capability), [capability.data])

  if (live.error && !live.run) return <ErrorNotice error={live.error} action={<button type="button" className="button small" onClick={live.refresh}>Retry</button>} />
  if (!live.run) return <Loading label="Loading run" />

  const run = live.run
  const result = run.result
  const replayResult = isRunResult(result) ? result : null
  const intervention = run.state === 'waiting_for_operator' ? normalizeIntervention(run.intervention) : null
  const activity = live.active ? currentActivity(timeline) : null
  const policies = notablePolicies(timeline)
  const stepLabel = (stepId: string | null | undefined): string | null => (stepId ? (descriptions[stepId] ?? null) : null)

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <Link to="/runs">Runs</Link>
            <span aria-hidden="true">/</span>
            <span className="mono">{run.run_id}</span>
          </>
        }
        title={runHeadline(run, result)}
        badges={<RunBadge run={run} />}
        lede={`${humanize(run.mode)} run${run.capability_id ? ` of ${run.capability_id}` : ''}${run.tenant ? ` on ${run.tenant}` : ''}.`}
        actions={
          run.capability_id && run.mode === 'replay' ? (
            <Link to={`/capabilities/${encodeURIComponent(run.capability_id)}/run`} className="button">
              Run again
            </Link>
          ) : null
        }
      />
      {live.error ? <ErrorNotice error={live.error} /> : null}
      {intervention ? <InterventionPanel runId={run.run_id} intervention={intervention} stepLabel={stepLabel(intervention.request.step_id)} /> : null}
      {result ? (
        <ResultCard
          runId={run.run_id}
          result={result}
          outputSpecs={capability.data?.capability.outputs}
          stepLabel={(stepId) => (stepId ? `${stepLabel(stepId) ?? stepId} (${stepId})` : null)}
        />
      ) : null}
      <div className="grid grid-sidebar">
        <Panel title="Timeline" subtitle={`${live.events.length} events`} flush>
          {activity ? (
            <div className="live-status" role="status" aria-live="polite">
              <span className="dot busy" aria-hidden="true" />
              <span className="live-status-text">{activity}</span>
            </div>
          ) : null}
          <Timeline entries={timeline} runId={run.run_id} stepLabel={(stepId, fallback) => descriptions[stepId] ?? fallback ?? stepId} />
        </Panel>
        <div className="stack">
          <RunFacts run={run} result={replayResult} nowMillis={now} />
          {replayResult ? <DriftPanel result={replayResult} /> : null}
          <Panel title="Policy" subtitle="Every action passes the policy gate before it reaches the app">
            {policies.length === 0 ? (
              <p className="muted">All actions were allowed by policy. Hover a policy chip in the timeline for the rule.</p>
            ) : (
              <ul className="stack-sm" style={{ listStyle: 'none', margin: 0, padding: 0 }}>
                {policies.map((policy, index) => (
                  <li key={index} className="stack-sm" style={{ gap: 2 }}>
                    <span className={policy.verdict === 'deny' ? 'chip danger' : 'chip warn'}>
                      {policy.verdict} · {policy.rule ?? 'rule'}
                    </span>
                    <span className="faint">{policy.reason}</span>
                  </li>
                ))}
              </ul>
            )}
          </Panel>
        </div>
      </div>
      <Panel title="Screenshots" subtitle="Masked before they reach the model or the disk">
        <Filmstrip runId={run.run_id} paths={run.files?.screenshots ?? []} />
        {run.files?.snapshots?.length ? (
          <div className="stack-sm">
            <span className="sub-label">Accessibility snapshots (redacted, no pixels)</span>
            <div className="tag-list">
              {run.files.snapshots.map((path) => (
                <RunFileLink key={path} runId={run.run_id} path={path} label={path.split('/').pop()} />
              ))}
            </div>
          </div>
        ) : null}
      </Panel>
      {result ? (
        <Panel title="Raw result">
          <JsonDisclosure value={result} summary="Show result JSON returned to the caller" />
        </Panel>
      ) : null}
    </>
  )
}
