import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type {
  AnyRunResult,
  BusinessOutcomeResult,
  DiscoverySummary,
  EscalatedResult,
  FailedResult,
  OutputSpec,
  SuccessResult,
} from '../api/types'
import { formatValue, humanize, isDiscoverySummary, isRunError, statusBadge, type Tone } from '../lib/format'
import { Badge } from './Badge'
import { KeyValueList } from './Panel'
import { RunFileLink, RunImage } from './RunFile'

interface ResultCardProps {
  runId: string
  result: AnyRunResult
  outputSpecs?: Record<string, OutputSpec>
  stepLabel?: (stepId: string | null | undefined) => string | null
}

function ResultFrame({ tone, title, status, children }: { tone: Tone; title: string; status: string; children: ReactNode }) {
  return (
    <section className={`panel result tone-${tone}-border`} aria-label={`Result: ${title}`}>
      <header className="panel-head">
        <h2>{title}</h2>
        <Badge badge={statusBadge(status)} />
      </header>
      <div className="panel-body">{children}</div>
    </section>
  )
}

function SuccessCard({ result, outputSpecs }: { result: SuccessResult; outputSpecs?: Record<string, OutputSpec> }) {
  const entries = Object.entries(result.outputs ?? {})
  return (
    <ResultFrame tone="success" title="Result" status="success">
      {entries.length === 0 ? (
        <p className="muted">The checkpoint held; this capability declares no outputs.</p>
      ) : (
        <div className="outputs">
          {entries.map(([name, value]) => (
            <div key={name} className="output">
              <span className="faint mono">
                {name}
                {outputSpecs?.[name] ? ` · ${outputSpecs[name].type}` : ''}
              </span>
              <span className="result-value">{formatValue(value, outputSpecs?.[name]?.type, name)}</span>
            </div>
          ))}
        </div>
      )}
      <p className="faint">Checkpoint met. Values are returned with their declared types; decimals stay exact strings.</p>
    </ResultFrame>
  )
}

function OutcomeCard({ result, stepLabel }: { result: BusinessOutcomeResult; stepLabel?: ResultCardProps['stepLabel'] }) {
  return (
    <ResultFrame tone="outcome" title="Business outcome" status="business_outcome">
      <span className="result-code">{result.code}</span>
      {result.message ? <p>“{result.message}”</p> : null}
      <KeyValueList
        items={[{ label: 'Detected at', value: result.at_step ? (stepLabel?.(result.at_step) ?? result.at_step) : null }]}
      />
      <p className="faint">A declared business result returned to the caller as an answer. It is not an error.</p>
    </ResultFrame>
  )
}

function EscalatedCard({ result }: { result: EscalatedResult }) {
  return (
    <ResultFrame tone="escalated" title="Escalated" status="escalated">
      <p>{result.reason}</p>
      <KeyValueList
        items={[
          { label: 'Operator note', value: result.operator_note },
          { label: 'Intervention', value: <code>{result.intervention_id}</code> },
        ]}
      />
    </ResultFrame>
  )
}

function isScreenshot(path: string): boolean {
  return /\.(png|jpe?g)$/i.test(path)
}

function FailedCard({ runId, result, stepLabel }: { runId: string; result: FailedResult; stepLabel?: ResultCardProps['stepLabel'] }) {
  const { failure } = result
  const screenshot = failure.evidence.find(isScreenshot) ?? null
  const otherEvidence = failure.evidence.filter((path) => path !== screenshot)
  return (
    <ResultFrame tone="failed" title="Failure" status="failed">
      <span className="result-code">{failure.code}</span>
      <p>{failure.message}</p>
      <KeyValueList
        items={[
          { label: 'Step', value: failure.step_id ? (stepLabel?.(failure.step_id) ?? failure.step_id) : 'Before the app was touched' },
          { label: 'Expected', value: failure.expected ? <div className="prose-block">{failure.expected}</div> : null },
          { label: 'Observed', value: failure.observed ? <div className="prose-block">{failure.observed}</div> : null },
          {
            label: 'Evidence',
            value: failure.evidence.length ? (
              <div className="stack-sm">
                {failure.evidence.map((path) => (
                  <RunFileLink key={path} runId={runId} path={path} />
                ))}
              </div>
            ) : null,
          },
        ]}
      />
      {screenshot ? (
        <figure className="viewer" style={{ margin: 0 }}>
          <RunImage runId={runId} path={screenshot} alt="Screen at the moment of failure" className="shot" />
          <figcaption className="faint">
            Screen at failure{otherEvidence.length ? '; the accessibility snapshot is linked above.' : '.'}
          </figcaption>
        </figure>
      ) : null}
    </ResultFrame>
  )
}

function capabilityLink(capability: string | null | undefined) {
  if (!capability) return null
  const [id, version] = capability.split('@')
  const href = `/capabilities/${encodeURIComponent(id)}${version ? `?version=${encodeURIComponent(version)}` : ''}`
  return <Link to={href} className="mono">{capability}</Link>
}

function DiscoveryCard({ result }: { result: DiscoverySummary }) {
  const tone: Tone = statusBadge(result.status).tone
  const extracted = Object.entries(result.extracted ?? {})
  return (
    <ResultFrame tone={tone} title="Discovery" status={result.status}>
      {result.reason ? <p>{result.reason}</p> : null}
      {extracted.length ? (
        <div className="outputs">
          {extracted.map(([name, value]) => (
            <div key={name} className="output">
              <span className="faint mono">{name} (as read on screen)</span>
              <span className="result-value">{formatValue(value, null, name)}</span>
            </div>
          ))}
        </div>
      ) : null}
      <KeyValueList
        items={[
          { label: 'Recorded capability', value: capabilityLink(result.capability) },
          { label: 'Planner', value: `${humanize(result.planner)}${result.model ? ` · ${result.model}` : ''}` },
          { label: 'Model decisions', value: <span className="num">{result.planner_calls}</span> },
          { label: 'Invalid decisions', value: <span className="num">{result.invalid_decisions}</span> },
          { label: 'Record error', value: result.record_error },
          {
            label: 'Record warnings',
            value: result.record_warnings?.length ? result.record_warnings.join('; ') : null,
          },
        ]}
      />
    </ResultFrame>
  )
}

/** One card per result class; the `status` (or discovery mode) is the component switch. */
function RunErrorCard({ message }: { message: string }) {
  return (
    <ResultFrame tone="failed" title="Run error" status="error">
      <p>{message}</p>
      <p className="faint">The run crashed or could not start (for example, the browser failed to launch). No result was produced.</p>
    </ResultFrame>
  )
}

export function ResultCard({ runId, result, outputSpecs, stepLabel }: ResultCardProps) {
  if (isRunError(result)) return <RunErrorCard message={result.message} />
  if (isDiscoverySummary(result)) return <DiscoveryCard result={result} />
  switch (result.status) {
    case 'success':
      return <SuccessCard result={result} outputSpecs={outputSpecs} />
    case 'business_outcome':
      return <OutcomeCard result={result} stepLabel={stepLabel} />
    case 'escalated':
      return <EscalatedCard result={result} />
    case 'failed':
      return <FailedCard runId={runId} result={result} stepLabel={stepLabel} />
  }
}
