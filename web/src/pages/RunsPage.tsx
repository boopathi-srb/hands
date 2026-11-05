import { useApp } from '../app/AppContext'
import { EmptyState, ErrorNotice, Loading } from '../components/Feedback'
import { PageHeader, Panel } from '../components/Panel'
import { RunsTable } from '../components/RunsTable'
import { useApiResource, useInterval, useNow } from '../hooks/useAsync'
import { isActiveState } from '../lib/format'

const RUNS_LIMIT = 100
const RUNS_POLL_MS = 3000

export function RunsPage() {
  const { client } = useApp()
  const runs = useApiResource(() => client.runs(RUNS_LIMIT), 'runs')
  const hasActive = Boolean(runs.data?.some((run) => isActiveState(run.state)))
  useInterval(runs.reload, RUNS_POLL_MS, hasActive)
  const now = useNow(1000, hasActive)
  return (
    <>
      <PageHeader
        eyebrow="Runs"
        title="Runs"
        lede="Every discovery and replay, newest first, including runs recorded on disk by earlier sessions."
      />
      <Panel
        title="All runs"
        subtitle={runs.data ? `${runs.data.length} shown (limit ${RUNS_LIMIT})` : undefined}
        actions={
          <button type="button" className="button small" onClick={runs.reload} disabled={runs.loading}>
            Refresh
          </button>
        }
        flush
      >
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
        {runs.data && runs.data.length === 0 ? <EmptyState title="No runs yet" /> : null}
        {runs.data && runs.data.length > 0 ? <RunsTable runs={runs.data} nowMillis={now} caption="All runs" /> : null}
      </Panel>
    </>
  )
}
