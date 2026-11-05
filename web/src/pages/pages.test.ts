import { describe, expect, it } from 'vitest'
import type { Health } from '../api/types'
import { nextThemeChoice, parseThemeChoice } from '../hooks/useTheme'
import { defaultPlanner, plannerOptions } from './DiscoverPage'
import { healthRows } from './OverviewPage'
import { faultRequests } from './RunCapabilityPage'
import { validateBaseUrl } from './SettingsPage'

const health = (planners: Partial<Health['planners']>): Health => ({
  status: 'ok',
  auth_required: false,
  mock_app: 'up',
  planners: { anthropic: false, ollama: false, scripted: true, ...planners },
  active_run: null,
  version: '0.1.0',
})

describe('plannerOptions', () => {
  it('offers ollama only when the server reports it', () => {
    expect(plannerOptions(health({})).map((option) => option.name)).toEqual(['anthropic', 'scripted'])
    expect(plannerOptions(health({ ollama: true })).map((option) => option.name)).toEqual(['anthropic', 'scripted', 'ollama'])
  })
  it('explains an unavailable anthropic planner', () => {
    expect(plannerOptions(health({}))[0].hint).toMatch(/ANTHROPIC_API_KEY/)
    expect(plannerOptions(null)[0].hint).toBe('Production planner')
  })
})

describe('defaultPlanner', () => {
  it('defaults to anthropic when available, else scripted', () => {
    expect(defaultPlanner(health({ anthropic: true }))).toBe('anthropic')
    expect(defaultPlanner(health({}))).toBe('scripted')
    expect(defaultPlanner(null)).toBe('scripted')
  })
})

describe('healthRows', () => {
  it('lists the mock app, planners, active run and auth', () => {
    const rows = healthRows({ ...health({ anthropic: true }), mock_app: 'down', active_run: 'replay-1', auth_required: true })
    expect(rows.find((row) => row.label === 'CoreOne mock app')).toMatchObject({ ok: false, value: 'Down' })
    expect(rows.find((row) => row.label === 'Planner: Anthropic')).toMatchObject({ ok: true })
    expect(rows.find((row) => row.label === 'Active run')?.value).toBe('replay-1')
    expect(rows.find((row) => row.label === 'Access token')?.value).toBe('Required')
  })
  it('is empty before health arrives', () => {
    expect(healthRows(null)).toEqual([])
  })
})

describe('faultRequests', () => {
  it('turns the checklist into API fault entries', () => {
    expect(faultRequests({ session_expired: 1, maintenance_notice: 2 })).toEqual([
      { name: 'session_expired', count: 1 },
      { name: 'maintenance_notice', count: 2 },
    ])
  })
  it('is empty when nothing is checked', () => {
    expect(faultRequests({})).toEqual([])
  })
})

describe('validateBaseUrl', () => {
  it('accepts empty (same origin) and http(s) URLs', () => {
    expect(validateBaseUrl('')).toBeNull()
    expect(validateBaseUrl('  ')).toBeNull()
    expect(validateBaseUrl('http://127.0.0.1:8080')).toBeNull()
    expect(validateBaseUrl('https://hands.example.com/')).toBeNull()
  })
  it('rejects other values', () => {
    expect(validateBaseUrl('127.0.0.1:8080')).toMatch(/http/)
    expect(validateBaseUrl('ftp://x')).toMatch(/http/)
  })
})

describe('theme choice', () => {
  it('parses stored values, defaulting to system', () => {
    expect(parseThemeChoice('dark')).toBe('dark')
    expect(parseThemeChoice('neon')).toBe('system')
    expect(parseThemeChoice(null)).toBe('system')
  })
  it('cycles system → light → dark → system', () => {
    expect(nextThemeChoice('system')).toBe('light')
    expect(nextThemeChoice('light')).toBe('dark')
    expect(nextThemeChoice('dark')).toBe('system')
  })
})
