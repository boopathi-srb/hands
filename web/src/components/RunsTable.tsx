import { useNavigate, Link } from 'react-router-dom'
import type { RunListItem } from '../api/types'
import { formatDuration, formatRelative, formatTimestamp, humanize, isActiveState, runHeadline, truncate } from '../lib/format'
import { RunBadge } from './Badge'

interface RunsTableProps {
  runs: RunListItem[]
  nowMillis: number
  caption: string
}

/** Runs newest first; a row opens the run. The run id is also a real link for keyboard and new-tab use. */
export function RunsTable({ runs, nowMillis, caption }: RunsTableProps) {
  const navigate = useNavigate()
  return (
    <div className="table-wrap">
      <table className="table" aria-label={caption}>
        <thead>
          <tr>
            <th scope="col">Run</th>
            <th scope="col">Status</th>
            <th scope="col">Headline</th>
            <th scope="col">Capability</th>
            <th scope="col">Tenant</th>
            <th scope="col">Started</th>
            <th scope="col" className="right">
              Duration
            </th>
          </tr>
        </thead>
        <tbody>
          {runs.map((run) => {
            const href = `/runs/${encodeURIComponent(run.run_id)}`
            return (
              <tr key={run.run_id} className="clickable" onClick={() => navigate(href)}>
                <td>
                  <Link to={href} className="mono run-id" onClick={(event) => event.stopPropagation()}>
                    {run.run_id}
                  </Link>
                  <div className="faint">{humanize(run.mode)}</div>
                </td>
                <td>
                  <RunBadge run={run} />
                </td>
                <td title={run.headline ?? undefined}>{truncate(runHeadline(run), 80)}</td>
                <td className="mono">{run.capability_id ?? '—'}</td>
                <td>{run.tenant ?? '—'}</td>
                <td title={formatTimestamp(run.started_at)}>{formatRelative(run.started_at, nowMillis)}</td>
                <td className="right num">
                  {formatDuration(run.started_at, isActiveState(run.state) ? null : run.finished_at, nowMillis)}
                </td>
              </tr>
            )
          })}
        </tbody>
      </table>
    </div>
  )
}
