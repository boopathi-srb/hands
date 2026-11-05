import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'
import type { ApiError } from '../api/client'

export interface ErrorExplanation {
  title: string
  detail: string
  next: 'settings' | 'run' | null
}

/** A calm explanation of an API failure and what to do next. */
export function explainApiError(error: ApiError): ErrorExplanation {
  switch (error.code) {
    case 'unreachable':
      return {
        title: 'The hands API is not reachable',
        detail: 'Check the API URL in Settings, or start the server with `uv run hands serve`.',
        next: 'settings',
      }
    case 'unauthorized':
      return {
        title: 'Access token required',
        detail: 'This API needs an access token. Add it in Settings.',
        next: 'settings',
      }
    case 'busy':
      return {
        title: 'Another run is in progress',
        detail: 'hands drives one browser session at a time. Wait for the active run to finish.',
        next: error.body?.run_id ? 'run' : null,
      }
    default:
      return {
        title: error.status >= 500 ? 'The server could not complete the request' : 'The request was not accepted',
        detail: error.message,
        next: null,
      }
  }
}

export function ErrorNotice({ error, action }: { error: ApiError; action?: ReactNode }) {
  const explanation = explainApiError(error)
  return (
    <div className="notice error" role="alert">
      <div className="notice-body">
        <span className="notice-title">{explanation.title}</span>
        <span>{explanation.detail}</span>
        <span className="faint mono">
          {error.status ? `HTTP ${error.status} · ` : ''}
          {error.code}
        </span>
        <div className="row">
          {explanation.next === 'settings' ? <Link to="/settings">Open settings</Link> : null}
          {explanation.next === 'run' && error.body?.run_id ? (
            <Link to={`/runs/${encodeURIComponent(error.body.run_id)}`}>View active run {error.body.run_id}</Link>
          ) : null}
          {action}
        </div>
      </div>
    </div>
  )
}

export function Notice({
  tone = 'info',
  title,
  children,
}: {
  tone?: 'info' | 'attention' | 'error'
  title: ReactNode
  children?: ReactNode
}) {
  return (
    <div className={`notice ${tone}`} role={tone === 'error' ? 'alert' : 'status'}>
      <div className="notice-body">
        <span className="notice-title">{title}</span>
        {children}
      </div>
    </div>
  )
}

export function EmptyState({ title, children }: { title: string; children?: ReactNode }) {
  return (
    <div className="empty">
      <strong>{title}</strong>
      {children}
    </div>
  )
}

export function Loading({ label = 'Loading' }: { label?: string }) {
  return (
    <div className="loading-line" role="status" aria-live="polite">
      <span className="dot busy" aria-hidden="true" />
      {label}…
    </div>
  )
}
