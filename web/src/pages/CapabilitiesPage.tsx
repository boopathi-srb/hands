import { Link } from 'react-router-dom'
import { useApp } from '../app/AppContext'
import { CapabilityStatusBadge } from '../components/Badge'
import { EmptyState, ErrorNotice, Loading } from '../components/Feedback'
import { PageHeader, Panel } from '../components/Panel'
import { useApiResource } from '../hooks/useAsync'
import type { CatalogEntry, FieldSummary } from '../api/types'

function fieldList(fields: Record<string, FieldSummary> | undefined): string {
  const entries = Object.entries(fields ?? {})
  if (entries.length === 0) return '—'
  return entries.map(([name, spec]) => `${name}: ${spec.type}`).join(', ')
}

function CapabilityRow({ entry }: { entry: CatalogEntry }) {
  const href = `/capabilities/${encodeURIComponent(entry.id)}`
  return (
    <tr>
      <td>
        <Link to={href} className="cell-main">
          {entry.title}
        </Link>
        <div className="faint mono">{entry.id}</div>
      </td>
      <td>
        <CapabilityStatusBadge status={entry.status} />
      </td>
      <td className="mono">{entry.latest_version}</td>
      <td className="mono">{fieldList(entry.inputs)}</td>
      <td className="mono">{fieldList(entry.outputs)}</td>
      <td>
        <div className="tag-list">
          {(entry.outcome_codes ?? []).map((code) => (
            <span key={code} className="chip mono">
              {code}
            </span>
          ))}
        </div>
      </td>
      <td className="right">
        <Link to={`${href}/run`} className="button small">
          Run
        </Link>
      </td>
    </tr>
  )
}

export function CapabilitiesPage() {
  const { client } = useApp()
  const catalog = useApiResource(() => client.capabilities(), 'capabilities')
  return (
    <>
      <PageHeader
        eyebrow="Catalog"
        title="Capabilities"
        lede="Typed, versioned flows recorded by discovery. Calling agents invoke these by id with typed inputs."
        actions={
          <Link to="/discover" className="button">
            Discover new
          </Link>
        }
      />
      <Panel title="Catalog" flush>
        {catalog.error ? (
          <div className="panel-body">
            <ErrorNotice error={catalog.error} />
          </div>
        ) : null}
        {catalog.loading && !catalog.data ? (
          <div className="panel-body">
            <Loading label="Loading capabilities" />
          </div>
        ) : null}
        {catalog.data && catalog.data.length === 0 ? (
          <EmptyState title="No capabilities yet">
            <Link to="/discover">Discover the first one</Link>
          </EmptyState>
        ) : null}
        {catalog.data && catalog.data.length > 0 ? (
          <div className="table-wrap">
            <table className="table" aria-label="Capabilities">
              <thead>
                <tr>
                  <th scope="col">Capability</th>
                  <th scope="col">Status</th>
                  <th scope="col">Version</th>
                  <th scope="col">Inputs</th>
                  <th scope="col">Outputs</th>
                  <th scope="col">Business outcomes</th>
                  <th scope="col" className="right">
                    <span className="visually-hidden">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody>
                {catalog.data.map((entry) => (
                  <CapabilityRow key={entry.id} entry={entry} />
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </Panel>
    </>
  )
}
