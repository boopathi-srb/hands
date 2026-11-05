import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import {
  apiUrl,
  authHeaders,
  buildLiveSocketUrl,
  createApiClient,
  encodeFilePath,
  errorFromResponse,
  parseJson,
  type FetchLike,
} from './client'
import type { ConnectionSettings } from './settings'
import type { ReplayRequest } from './types'

interface Call {
  url: string
  init: RequestInit | undefined
}

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

function mockFetch(response: Response | (() => Promise<Response>)) {
  const calls: Call[] = []
  const fetchImpl: FetchLike = (url, init) => {
    calls.push({ url, init })
    return typeof response === 'function' ? response() : Promise.resolve(response.clone())
  }
  return { calls, fetchImpl }
}

function client(fetchImpl: FetchLike, settings: ConnectionSettings = { baseUrl: '', token: '' }) {
  return createApiClient(() => settings, fetchImpl, () => ({ protocol: 'http:', host: 'localhost:5173' }))
}

function headerOf(call: Call, name: string): string | undefined {
  return (call.init?.headers as Record<string, string> | undefined)?.[name]
}

const REPLAY_BODY: ReplayRequest = {
  capability_id: 'coreone.member_balance',
  version: null,
  inputs: { member_number: '10002' },
  tenant: 'lakeside',
  faults: [],
  risky_confirmed: false,
  escalation: 'console',
}

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

afterEach(() => {
  vi.restoreAllMocks()
})

describe('apiUrl', () => {
  it('joins base and path', () => {
    expect(apiUrl('https://api.example.com', '/api/health')).toBe('https://api.example.com/api/health')
  })
  it('keeps the path relative when the base is empty (same origin)', () => {
    expect(apiUrl('', '/api/health')).toBe('/api/health')
  })
})

describe('authHeaders', () => {
  it('sends a bearer token when set', () => {
    expect(authHeaders('secret')).toEqual({ Authorization: 'Bearer secret' })
  })
  it('sends nothing for an empty token', () => {
    expect(authHeaders('')).toEqual({})
  })
})

describe('encodeFilePath', () => {
  it('encodes segments but keeps slashes', () => {
    expect(encodeFilePath('screenshots/005 obs#1.png')).toBe('screenshots/005%20obs%231.png')
  })
  it('drops empty segments and leading slashes', () => {
    expect(encodeFilePath('/snapshots//a.json')).toBe('snapshots/a.json')
  })
  it('returns empty for an empty path', () => {
    expect(encodeFilePath('')).toBe('')
  })
})

describe('buildLiveSocketUrl', () => {
  it('uses ws on the page origin when the base URL is empty', () => {
    expect(buildLiveSocketUrl('', { protocol: 'http:', host: 'localhost:5173' }, 'replay-1', 'alice', '')).toBe(
      'ws://localhost:5173/console/api/sessions/replay-1/live?operator_id=alice',
    )
  })
  it('uses wss on an https page', () => {
    expect(buildLiveSocketUrl('', { protocol: 'https:', host: 'ui.example.com' }, 'r', 'a', '')).toMatch(/^wss:\/\/ui\.example\.com\//)
  })
  it('converts an https API base to wss and adds the token', () => {
    expect(buildLiveSocketUrl('https://api.example.com', { protocol: 'http:', host: 'x' }, 'r 1', 'bob', 't0k')).toBe(
      'wss://api.example.com/console/api/sessions/r%201/live?operator_id=bob&token=t0k',
    )
  })
})

describe('parseJson', () => {
  it('parses JSON', () => {
    expect(parseJson('{"a":1}')).toEqual({ a: 1 })
  })
  it('returns null for empty text', () => {
    expect(parseJson('')).toBeNull()
  })
  it('returns undefined for invalid JSON', () => {
    expect(parseJson('<html>')).toBeUndefined()
  })
})

describe('errorFromResponse', () => {
  it('reads the contract error body', () => {
    const error = errorFromResponse(409, JSON.stringify({ error: 'busy', message: 'a run is active', run_id: 'replay-1' }))
    expect(error).toMatchObject({ status: 409, code: 'busy', message: 'a run is active' })
    expect(error.body?.run_id).toBe('replay-1')
  })
  it('falls back to the code when there is no message', () => {
    expect(errorFromResponse(401, '{"error":"unauthorized"}').message).toBe('unauthorized')
  })
  it('flattens FastAPI validation details', () => {
    const error = errorFromResponse(422, JSON.stringify({ detail: [{ msg: 'field required' }, { msg: 'bad type' }] }))
    expect(error).toMatchObject({ code: 'http_422', message: 'field required; bad type' })
  })
  it('handles an empty body', () => {
    expect(errorFromResponse(500, '')).toMatchObject({ code: 'http_500', message: 'Request failed with HTTP 500.' })
  })
  it('maps a bare 401 to unauthorized', () => {
    expect(errorFromResponse(401, 'nope').code).toBe('unauthorized')
  })
})

describe('createApiClient', () => {
  it('GETs health from the base URL with the bearer token', async () => {
    const health = { status: 'ok', auth_required: true, mock_app: 'up', planners: {}, active_run: null, version: '1' }
    const { calls, fetchImpl } = mockFetch(jsonResponse(health))
    const result = await client(fetchImpl, { baseUrl: 'https://api.example.com', token: 'tok' }).health()
    expect(result).toEqual({ ok: true, data: health })
    expect(calls[0].url).toBe('https://api.example.com/api/health')
    expect(calls[0].init?.method).toBe('GET')
    expect(headerOf(calls[0], 'Authorization')).toBe('Bearer tok')
  })

  it('omits Authorization when no token is set', async () => {
    const { calls, fetchImpl } = mockFetch(jsonResponse([]))
    await client(fetchImpl).tenants()
    expect(headerOf(calls[0], 'Authorization')).toBeUndefined()
    expect(calls[0].url).toBe('/api/tenants')
  })

  it('POSTs a replay as JSON', async () => {
    const { calls, fetchImpl } = mockFetch(jsonResponse({ run_id: 'replay-ab' }, 202))
    const result = await client(fetchImpl).startReplay(REPLAY_BODY)
    expect(result).toEqual({ ok: true, data: { run_id: 'replay-ab' } })
    expect(calls[0].url).toBe('/api/runs/replay')
    expect(calls[0].init?.method).toBe('POST')
    expect(headerOf(calls[0], 'Content-Type')).toBe('application/json')
    expect(JSON.parse(String(calls[0].init?.body))).toEqual(REPLAY_BODY)
  })

  it('returns busy with the active run id on 409', async () => {
    const { fetchImpl } = mockFetch(jsonResponse({ error: 'busy', run_id: 'replay-x' }, 409))
    const result = await client(fetchImpl).startReplay(REPLAY_BODY)
    expect(result.ok).toBe(false)
    if (!result.ok) {
      expect(result.error.code).toBe('busy')
      expect(result.error.body?.run_id).toBe('replay-x')
    }
  })

  it('returns unreachable when fetch rejects, and logs it', async () => {
    const fetchImpl: FetchLike = () => Promise.reject(new TypeError('Failed to fetch'))
    const result = await client(fetchImpl).runs()
    expect(result).toMatchObject({ ok: false, error: { status: 0, code: 'unreachable' } })
    expect(console.error).toHaveBeenCalled()
  })

  it('returns bad_json for a 200 with a non-JSON body', async () => {
    const { fetchImpl } = mockFetch(new Response('<html>', { status: 200 }))
    const result = await client(fetchImpl).capabilities()
    expect(result).toMatchObject({ ok: false, error: { code: 'bad_json' } })
  })

  it('builds the capability URL with an optional version', async () => {
    const { calls, fetchImpl } = mockFetch(jsonResponse({}))
    const api = client(fetchImpl)
    await api.capability('coreone.member_balance')
    await api.capability('coreone.member_balance', '1.0.0')
    expect(calls[0].url).toBe('/api/capabilities/coreone.member_balance')
    expect(calls[1].url).toBe('/api/capabilities/coreone.member_balance?version=1.0.0')
  })

  it('approves with and without a version', async () => {
    const { calls, fetchImpl } = mockFetch(jsonResponse({ id: 'c', version: '1.0.0', status: 'approved' }))
    const api = client(fetchImpl)
    await api.approve('c', '1.0.0')
    await api.approve('c', null)
    expect(calls[0].url).toBe('/api/capabilities/c/approve')
    expect(JSON.parse(String(calls[0].init?.body))).toEqual({ version: '1.0.0' })
    expect(JSON.parse(String(calls[1].init?.body))).toEqual({})
  })

  it('pages events with after=', async () => {
    const { calls, fetchImpl } = mockFetch(jsonResponse({ events: [], last_seq: 7, state: 'running' }))
    await client(fetchImpl).runEvents('replay-1', 7)
    expect(calls[0].url).toBe('/api/runs/replay-1/events?after=7')
  })

  it('lists runs with a limit (default 50)', async () => {
    const { calls, fetchImpl } = mockFetch(jsonResponse([]))
    const api = client(fetchImpl)
    await api.runs()
    await api.runs(5)
    expect(calls.map((call) => call.url)).toEqual(['/api/runs?limit=50', '/api/runs?limit=5'])
  })

  it('fetches run detail, faults and discovery start', async () => {
    const { calls, fetchImpl } = mockFetch(jsonResponse({ run_id: 'disc-1' }))
    const api = client(fetchImpl)
    await api.run('disc-1')
    await api.faults()
    await api.startDiscovery({
      goal: 'g',
      inputs: {},
      sensitive_inputs: [],
      capability_id: 'c',
      title: 't',
      description: '',
      tenant: 'lakeside',
      planner: 'scripted',
      model: null,
      max_steps: 25,
      escalation: 'none',
    })
    expect(calls.map((call) => call.url)).toEqual(['/api/runs/disc-1', '/api/faults', '/api/runs/discovery'])
  })

  it('downloads a run file as a blob', async () => {
    const { calls, fetchImpl } = mockFetch(new Response('png-bytes', { status: 200, headers: { 'Content-Type': 'image/png' } }))
    const result = await client(fetchImpl).runFile('replay-1', 'screenshots/a b.png')
    expect(calls[0].url).toBe('/api/runs/replay-1/files/screenshots/a%20b.png')
    expect(result.ok).toBe(true)
    if (result.ok) expect(result.data.size).toBe(9)
  })

  it('returns a 404 for a missing run file', async () => {
    const { fetchImpl } = mockFetch(jsonResponse({ error: 'not_found', message: 'no such file' }, 404))
    const result = await client(fetchImpl).runFile('replay-1', '../etc/passwd')
    expect(result).toMatchObject({ ok: false, error: { status: 404, code: 'not_found' } })
  })

  it('speaks the console routes for take control and hand back', async () => {
    const { calls, fetchImpl } = mockFetch(jsonResponse({ lease: null }))
    const api = client(fetchImpl)
    await api.intervention('i-1')
    await api.takeControl('i-1', 'alice')
    await api.handBack('i-1', { operator_id: 'alice', outcome: 'resume', note: 'done' })
    expect(calls.map((call) => call.url)).toEqual([
      '/console/api/interventions/i-1',
      '/console/api/interventions/i-1/take',
      '/console/api/interventions/i-1/handback',
    ])
    expect(JSON.parse(String(calls[1].init?.body))).toEqual({ operator_id: 'alice' })
    expect(JSON.parse(String(calls[2].init?.body))).toEqual({ operator_id: 'alice', outcome: 'resume', note: 'done' })
  })

  it('builds the live socket URL from the current settings', () => {
    const { fetchImpl } = mockFetch(jsonResponse({}))
    const url = client(fetchImpl, { baseUrl: 'http://127.0.0.1:8080', token: 'k' }).liveSocketUrl('replay-1', 'ops')
    expect(url).toBe('ws://127.0.0.1:8080/console/api/sessions/replay-1/live?operator_id=ops&token=k')
  })
})
