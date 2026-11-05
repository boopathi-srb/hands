/**
 * Typed client for the hands HTTP API (docs/API.md). Every call returns an ApiResult instead of
 * throwing, so callers handle failure explicitly. Network and parse failures are logged with the
 * operation name and inputs, then surfaced as ApiError values.
 */

import type {
  ApiErrorBody,
  ApproveResponse,
  CapabilityDetail,
  CatalogEntry,
  DiscoveryRequest,
  FaultInfo,
  HandbackRequest,
  HandbackResponse,
  Health,
  InterventionContext,
  ReplayRequest,
  RunDetail,
  RunEventsPage,
  RunListItem,
  RunStarted,
  TakeControlResponse,
  Tenant,
} from './types'
import type { ConnectionSettings } from './settings'

export interface ApiError {
  /** HTTP status, or 0 when the server could not be reached. */
  status: number
  /** Machine code from the error body (`busy`, `unauthorized`, ...) or a client-side code. */
  code: string
  message: string
  body: ApiErrorBody | null
}

export type ApiResult<T> = { ok: true; data: T } | { ok: false; error: ApiError }

export type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

export interface ApiClient {
  health(): Promise<ApiResult<Health>>
  tenants(): Promise<ApiResult<Tenant[]>>
  faults(): Promise<ApiResult<FaultInfo[]>>
  capabilities(): Promise<ApiResult<CatalogEntry[]>>
  capability(id: string, version?: string | null): Promise<ApiResult<CapabilityDetail>>
  approve(id: string, version?: string | null): Promise<ApiResult<ApproveResponse>>
  startReplay(body: ReplayRequest): Promise<ApiResult<RunStarted>>
  startDiscovery(body: DiscoveryRequest): Promise<ApiResult<RunStarted>>
  runs(limit?: number): Promise<ApiResult<RunListItem[]>>
  run(runId: string): Promise<ApiResult<RunDetail>>
  runEvents(runId: string, after: number): Promise<ApiResult<RunEventsPage>>
  runFile(runId: string, path: string): Promise<ApiResult<Blob>>
  intervention(interventionId: string): Promise<ApiResult<InterventionContext>>
  takeControl(interventionId: string, operatorId: string): Promise<ApiResult<TakeControlResponse>>
  handBack(interventionId: string, body: HandbackRequest): Promise<ApiResult<HandbackResponse>>
  liveSocketUrl(sessionId: string, operatorId: string): string
}

type ResponseKind = 'json' | 'blob'

interface RequestSpec {
  operation: string
  method: 'GET' | 'POST'
  path: string
  body?: unknown
  responseKind?: ResponseKind
}

function isResponseLike(value: unknown): value is Response {
  return typeof value === 'object' && value !== null && typeof (value as Response).status === 'number' && typeof (value as Response).text === 'function'
}

export function apiUrl(baseUrl: string, path: string): string {
  return `${baseUrl}${path}`
}

export function authHeaders(token: string): Record<string, string> {
  return token ? { Authorization: `Bearer ${token}` } : {}
}

/** Encodes each segment of a relative evidence path, keeping the slashes between them. */
export function encodeFilePath(path: string): string {
  return path
    .split('/')
    .filter((segment) => segment.length > 0)
    .map(encodeURIComponent)
    .join('/')
}

/**
 * ws(s) URL for the operator live view. An empty base URL means same origin as the page; an
 * http(s) base URL is converted to ws(s). The token travels as a query parameter because browsers
 * cannot set headers on a websocket handshake.
 */
export function buildLiveSocketUrl(
  baseUrl: string,
  pageLocation: { protocol: string; host: string },
  sessionId: string,
  operatorId: string,
  token: string,
): string {
  const origin = baseUrl
    ? baseUrl.replace(/^http/, 'ws')
    : `${pageLocation.protocol === 'https:' ? 'wss' : 'ws'}://${pageLocation.host}`
  const query = new URLSearchParams({ operator_id: operatorId })
  if (token) query.set('token', token)
  return `${origin}/console/api/sessions/${encodeURIComponent(sessionId)}/live?${query.toString()}`
}

function networkError(operation: string, path: string, reason: unknown): ApiError {
  console.error(`${operation}: request to ${path} failed`, reason)
  return { status: 0, code: 'unreachable', message: 'The hands API could not be reached.', body: null }
}

function isErrorBody(value: unknown): value is ApiErrorBody {
  return typeof value === 'object' && value !== null && typeof (value as ApiErrorBody).error === 'string'
}

/** Builds an ApiError from a non-2xx response body (JSON when possible, text otherwise). */
export function errorFromResponse(status: number, bodyText: string): ApiError {
  const parsed = parseJson(bodyText)
  if (isErrorBody(parsed)) {
    return { status, code: parsed.error, message: parsed.message ?? parsed.error, body: parsed }
  }
  const detail = detailMessage(parsed)
  return {
    status,
    code: status === 401 ? 'unauthorized' : `http_${status}`,
    message: detail ?? (bodyText.trim() || `Request failed with HTTP ${status}.`),
    body: null,
  }
}

/** FastAPI validation errors arrive as {"detail": [...]}; flatten them to one readable line. */
function detailMessage(parsed: unknown): string | null {
  if (typeof parsed !== 'object' || parsed === null || !('detail' in parsed)) return null
  const detail = (parsed as { detail: unknown }).detail
  if (typeof detail === 'string') return detail
  if (!Array.isArray(detail)) return null
  return detail
    .map((item) => (typeof item === 'object' && item && 'msg' in item ? String(item.msg) : String(item)))
    .join('; ')
}

export function parseJson(text: string): unknown {
  if (!text) return null
  // JSON.parse has no non-throwing variant; this is the single parse boundary.
  try {
    return JSON.parse(text)
  } catch {
    return undefined
  }
}

/** Duck-typed so blobs from any realm (browser, test runtime) are accepted. */
function isBlobLike(value: unknown): value is Blob {
  return typeof value === 'object' && value !== null && typeof (value as Blob).size === 'number' && typeof (value as Blob).type === 'string'
}

async function readBody<T>(
  operation: string,
  response: Response,
  responseKind: ResponseKind,
): Promise<ApiResult<T>> {
  if (responseKind === 'blob') {
    const blob = await response.blob().catch((reason: unknown) => reason)
    if (isBlobLike(blob)) return { ok: true, data: blob as T }
    console.error(`${operation}: could not read file body`, blob)
    return { ok: false, error: { status: response.status, code: 'bad_body', message: 'Could not read file.', body: null } }
  }
  const text = await response.text().catch(() => '')
  const parsed = parseJson(text)
  if (parsed === undefined) {
    console.error(`${operation}: response was not JSON`, { status: response.status, length: text.length })
    return {
      ok: false,
      error: { status: response.status, code: 'bad_json', message: 'The API returned an unreadable response.', body: null },
    }
  }
  return { ok: true, data: parsed as T }
}

export function createApiClient(
  getSettings: () => ConnectionSettings,
  fetchImpl: FetchLike = (input, init) => fetch(input, init),
  pageLocation: () => { protocol: string; host: string } = () => window.location,
): ApiClient {
  async function request<T>(spec: RequestSpec): Promise<ApiResult<T>> {
    const { baseUrl, token } = getSettings()
    const headers: Record<string, string> = { ...authHeaders(token) }
    if (spec.body !== undefined) headers['Content-Type'] = 'application/json'
    const init: RequestInit = {
      method: spec.method,
      headers,
      body: spec.body === undefined ? undefined : JSON.stringify(spec.body),
    }
    const response = await fetchImpl(apiUrl(baseUrl, spec.path), init).catch((reason: unknown) => reason)
    if (!isResponseLike(response)) {
      return { ok: false, error: networkError(spec.operation, spec.path, response) }
    }
    if (!response.ok) {
      const text = await response.text().catch(() => '')
      const error = errorFromResponse(response.status, text)
      console.error(`${spec.operation}: HTTP ${response.status} for ${spec.method} ${spec.path}`, error.code)
      return { ok: false, error }
    }
    return readBody<T>(spec.operation, response, spec.responseKind ?? 'json')
  }

  const id = encodeURIComponent

  return {
    health: () => request({ operation: 'health', method: 'GET', path: '/api/health' }),
    tenants: () => request({ operation: 'tenants', method: 'GET', path: '/api/tenants' }),
    faults: () => request({ operation: 'faults', method: 'GET', path: '/api/faults' }),
    capabilities: () => request({ operation: 'capabilities', method: 'GET', path: '/api/capabilities' }),
    capability: (capabilityId, version) =>
      request({
        operation: 'capability',
        method: 'GET',
        path: `/api/capabilities/${id(capabilityId)}${version ? `?version=${id(version)}` : ''}`,
      }),
    approve: (capabilityId, version) =>
      request({
        operation: 'approve',
        method: 'POST',
        path: `/api/capabilities/${id(capabilityId)}/approve`,
        body: version ? { version } : {},
      }),
    startReplay: (body) => request({ operation: 'startReplay', method: 'POST', path: '/api/runs/replay', body }),
    startDiscovery: (body) =>
      request({ operation: 'startDiscovery', method: 'POST', path: '/api/runs/discovery', body }),
    runs: (limit = 50) => request({ operation: 'runs', method: 'GET', path: `/api/runs?limit=${limit}` }),
    run: (runId) => request({ operation: 'run', method: 'GET', path: `/api/runs/${id(runId)}` }),
    runEvents: (runId, after) =>
      request({ operation: 'runEvents', method: 'GET', path: `/api/runs/${id(runId)}/events?after=${after}` }),
    runFile: (runId, path) =>
      request({
        operation: 'runFile',
        method: 'GET',
        path: `/api/runs/${id(runId)}/files/${encodeFilePath(path)}`,
        responseKind: 'blob',
      }),
    intervention: (interventionId) =>
      request({ operation: 'intervention', method: 'GET', path: `/console/api/interventions/${id(interventionId)}` }),
    takeControl: (interventionId, operatorId) =>
      request({
        operation: 'takeControl',
        method: 'POST',
        path: `/console/api/interventions/${id(interventionId)}/take`,
        body: { operator_id: operatorId },
      }),
    handBack: (interventionId, body) =>
      request({
        operation: 'handBack',
        method: 'POST',
        path: `/console/api/interventions/${id(interventionId)}/handback`,
        body,
      }),
    liveSocketUrl: (sessionId, operatorId) => {
      const { baseUrl, token } = getSettings()
      return buildLiveSocketUrl(baseUrl, pageLocation(), sessionId, operatorId, token)
    },
  }
}
