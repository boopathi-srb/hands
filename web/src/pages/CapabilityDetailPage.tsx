import { useState } from 'react'
import { Link, useParams, useSearchParams } from 'react-router-dom'
import type { ApiError } from '../api/client'
import { useApp } from '../app/AppContext'
import { CapabilityStatusBadge } from '../components/Badge'
import {
  ContractPanel,
  OverlaysPanel,
  ProvenancePanel,
  RuntimeKnowledgePanel,
  StatsPanel,
  StepsPanel,
} from '../components/CapabilitySections'
import { ErrorNotice, Loading, Notice } from '../components/Feedback'
import { JsonDisclosure } from '../components/JsonDisclosure'
import { PageHeader, Panel } from '../components/Panel'
import { useApiResource } from '../hooks/useAsync'

function useApprove(capabilityId: string, version: string | null, onApproved: () => void) {
  const { client } = useApp()
  const [busy, setBusy] = useState(false)
  const [error, setError] = useState<ApiError | null>(null)
  function approve() {
    setBusy(true)
    setError(null)
    client.approve(capabilityId, version).then((result) => {
      setBusy(false)
      if (result.ok) onApproved()
      else setError(result.error)
    })
  }
  return { approve, busy, error }
}

export function CapabilityDetailPage() {
  const { capabilityId = '' } = useParams()
  const [searchParams] = useSearchParams()
  const version = searchParams.get('version')
  const { client } = useApp()
  const detail = useApiResource(() => client.capability(capabilityId, version), `capability:${capabilityId}:${version ?? ''}`)
  const approval = useApprove(capabilityId, detail.data?.capability.version ?? version, detail.reload)

  if (detail.error && !detail.data) return <ErrorNotice error={detail.error} />
  if (!detail.data) return <Loading label="Loading capability" />

  const { capability, overlays, tool } = detail.data
  const runHref = `/capabilities/${encodeURIComponent(capability.id)}/run${version ? `?version=${encodeURIComponent(version)}` : ''}`
  const isApproved = capability.status === 'approved'

  return (
    <>
      <PageHeader
        eyebrow={
          <>
            <Link to="/capabilities">Capabilities</Link>
            <span aria-hidden="true">/</span>
            <span className="mono">
              {capability.id}@{capability.version}
            </span>
          </>
        }
        title={capability.title}
        badges={<CapabilityStatusBadge status={capability.status} />}
        lede={capability.description}
        actions={
          <>
            {!isApproved ? (
              <button type="button" className="button" onClick={approval.approve} disabled={approval.busy}>
                {approval.busy ? 'Approving…' : 'Approve'}
              </button>
            ) : null}
            <Link to={runHref} className="button primary">
              Run capability
            </Link>
          </>
        }
      />
      {approval.error ? <ErrorNotice error={approval.error} /> : null}
      {!isApproved ? (
        <Notice tone="info" title="Draft capability">
          <span>
            Drafts replay normally, but steps that policy marks risky are denied until the capability is approved and
            the caller confirms. Review the steps and candidates below before approving.
          </span>
        </Notice>
      ) : null}
      <div className="grid grid-sidebar">
        <div className="stack">
          <ContractPanel capability={capability} />
          <StepsPanel capability={capability} />
          <RuntimeKnowledgePanel capability={capability} />
        </div>
        <div className="stack">
          <StatsPanel stats={capability.stats} />
          <ProvenancePanel capability={capability} />
          <OverlaysPanel overlays={overlays} capabilityId={capability.id} />
          <Panel title="Agent tool definition" subtitle={<code>{tool.name}</code>}>
            <p className="muted">{tool.description}</p>
            <JsonDisclosure value={tool} summary="Show tool JSON" />
            <JsonDisclosure value={capability} summary="Show full artifact JSON" />
          </Panel>
        </div>
      </div>
    </>
  )
}
