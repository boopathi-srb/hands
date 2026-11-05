import { cleanup, render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import type { ApiError } from '../api/client'
import {
  businessOutcomeResult,
  discoverySummary,
  escalatedResult,
  failedResult,
  memberBalanceCapability,
  replayHumanResumeEvents,
  successResult,
} from '../fixtures'
import { stepTarget } from '../lib/candidates'
import { buildTimeline } from '../lib/timeline'
import { renderWithApp } from '../test/renderWithApp'
import { Badge, CapabilityStatusBadge, RunBadge, StateBadge, StatusBadge, ToneBadge } from './Badge'
import { CandidateList, ConfidenceMeter } from './CandidateList'
import { ConditionView } from './ConditionView'
import { EmptyState, ErrorNotice, explainApiError, Loading, Notice } from './Feedback'
import { screenshotCaption } from './Filmstrip'
import { KeyValueList, PageHeader, Panel, Stat } from './Panel'
import { ResultCard } from './ResultCard'
import { Timeline } from './Timeline'

beforeEach(() => {
  vi.spyOn(console, 'error').mockImplementation(() => undefined)
})

afterEach(() => {
  cleanup()
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

const apiError = (code: string, status = 400, body: ApiError['body'] = null): ApiError => ({ status, code, message: `msg ${code}`, body })

describe('Badge components', () => {
  it('render the label with the tone class', () => {
    render(<Badge badge={{ label: 'Success', tone: 'success', hint: 'h' }} />)
    expect(screen.getByText('Success')).toHaveClass('tone-success')
  })
  it('render status, state and run badges', () => {
    render(
      <>
        <StatusBadge status="business_outcome" />
        <StateBadge state="waiting_for_operator" />
        <RunBadge run={{ state: 'finished', status: 'failed' }} />
        <ToneBadge tone="neutral">Plain</ToneBadge>
        <CapabilityStatusBadge status="approved" />
      </>,
    )
    expect(screen.getByText('Business outcome')).toHaveClass('tone-outcome')
    expect(screen.getByText('Needs operator')).toHaveClass('tone-attention')
    expect(screen.getByText('Failed')).toHaveClass('tone-failed')
    expect(screen.getByText('Plain')).toHaveClass('tone-neutral')
    expect(screen.getByText('Approved')).toHaveClass('tone-success')
  })
  it('handles a null status', () => {
    render(<StatusBadge status={null} />)
    expect(screen.getByText('Unknown')).toBeInTheDocument()
  })
})

describe('ConditionView', () => {
  it('renders the checkpoint as a readable tree, not JSON', () => {
    render(<ConditionView condition={memberBalanceCapability.checkpoint} />)
    expect(screen.getByText('All of')).toBeInTheDocument()
    expect(screen.getByText('/t/:tenant/main')).toHaveClass('condition-literal')
    expect(screen.queryByText(/"kind"/)).toBeNull()
  })
  it('shows the empty text for a missing condition', () => {
    render(<ConditionView condition={null} emptyText="No postcondition" />)
    expect(screen.getByText('No postcondition')).toBeInTheDocument()
  })
})

describe('CandidateList / ConfidenceMeter', () => {
  it('lists candidates in rank order with reasons and confidence', () => {
    const target = stepTarget(memberBalanceCapability.steps[1])
    if (!target) throw new Error('fixture step has no target')
    render(<CandidateList target={target} matchedRank={0} />)
    const items = screen.getAllByRole('listitem')
    expect(items).toHaveLength(4)
    expect(items[0]).toHaveTextContent('#1')
    expect(items[0]).toHaveTextContent('textbox labelled “Member Number”')
    expect(items[0]).toHaveTextContent('85%')
    expect(items[0]).toHaveTextContent('matched')
    expect(items[3]).toHaveTextContent('Visual offset')
  })
  it('renders an accessible meter, clamping out-of-range values', () => {
    render(<ConfidenceMeter confidence={1.4} level="high" />)
    expect(screen.getByLabelText('Confidence 100 percent, high')).toBeInTheDocument()
  })
})

describe('explainApiError / ErrorNotice', () => {
  it('explains unreachable, unauthorized, busy and generic errors', () => {
    expect(explainApiError(apiError('unreachable', 0)).next).toBe('settings')
    expect(explainApiError(apiError('unauthorized', 401)).title).toMatch(/token/i)
    expect(explainApiError(apiError('busy', 409, { error: 'busy', run_id: 'r1' })).next).toBe('run')
    expect(explainApiError(apiError('busy', 409)).next).toBeNull()
    expect(explainApiError(apiError('unknown_tenant', 400))).toMatchObject({ detail: 'msg unknown_tenant', next: null })
    expect(explainApiError(apiError('boom', 500)).title).toMatch(/server/)
  })
  it('links to the active run when busy', () => {
    render(
      <MemoryRouter>
        <ErrorNotice error={apiError('busy', 409, { error: 'busy', run_id: 'replay-1' })} />
      </MemoryRouter>,
    )
    expect(screen.getByRole('alert')).toHaveTextContent('Another run is in progress')
    expect(screen.getByRole('link', { name: /replay-1/ })).toHaveAttribute('href', '/runs/replay-1')
  })
})

describe('Feedback and panel primitives', () => {
  it('render notices, empty and loading states', () => {
    render(
      <>
        <Notice title="Heads up">body</Notice>
        <EmptyState title="Nothing here" />
        <Loading label="Loading runs" />
      </>,
    )
    expect(screen.getByText('Heads up')).toBeInTheDocument()
    expect(screen.getByText('Nothing here')).toBeInTheDocument()
    expect(screen.getByText('Loading runs…')).toBeInTheDocument()
  })
  it('KeyValueList skips empty values', () => {
    render(<KeyValueList items={[{ label: 'Shown', value: 'yes' }, { label: 'Hidden', value: null }, { label: 'Blank', value: '' }]} />)
    expect(screen.getByText('Shown')).toBeInTheDocument()
    expect(screen.queryByText('Hidden')).toBeNull()
    expect(screen.queryByText('Blank')).toBeNull()
  })
  it('Panel, PageHeader and Stat render their content', () => {
    render(
      <>
        <PageHeader title="Runs" lede="All runs" />
        <Panel title="Stats" id="stats">
          <Stat label="Runs" value={16} />
        </Panel>
      </>,
    )
    expect(screen.getByRole('heading', { name: 'Runs' })).toBeInTheDocument()
    expect(screen.getByRole('region', { name: 'Stats' })).toHaveTextContent('16')
  })
})

describe('screenshotCaption', () => {
  it('strips folder and extension', () => {
    expect(screenshotCaption('screenshots/005-obs-001.png')).toBe('005-obs-001')
    expect(screenshotCaption('a.jpeg')).toBe('a')
    expect(screenshotCaption('')).toBe('')
  })
})

describe('ResultCard', () => {
  it('renders a success with the typed, grouped output', () => {
    renderWithApp(<ResultCard runId="r" result={successResult} outputSpecs={memberBalanceCapability.outputs} />)
    expect(screen.getByText('9,870.12')).toBeInTheDocument()
    expect(screen.getByText('savings_balance · decimal')).toBeInTheDocument()
  })
  it('renders a business outcome as an answer, not an error', () => {
    renderWithApp(<ResultCard runId="r" result={businessOutcomeResult} />)
    expect(screen.getByText('MEMBER_NOT_FOUND')).toBeInTheDocument()
    expect(screen.getByText(/not an error/i)).toBeInTheDocument()
    expect(screen.queryByRole('alert')).toBeNull()
  })
  it('renders a failure with code, step, expected, observed and evidence', () => {
    renderWithApp(<ResultCard runId="replay-336aef34b540" result={failedResult} stepLabel={(id) => `label for ${id}`} />)
    expect(screen.getByText('recovery_exhausted')).toBeInTheDocument()
    expect(screen.getByText('label for login_open')).toBeInTheDocument()
    expect(screen.getByText(/needed at most 1 time/)).toBeInTheDocument()
    expect(screen.getByText(/match #2/)).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'snapshots/112-failure-login_open.json' })).toBeInTheDocument()
  })
  it('renders an escalation with the operator note', () => {
    renderWithApp(<ResultCard runId="r" result={escalatedResult} />)
    expect(screen.getByText('scripted operator chose abort')).toBeInTheDocument()
  })
  it('renders a discovery summary with the recorded capability link', () => {
    renderWithApp(<ResultCard runId="r" result={discoverySummary} />)
    expect(screen.getByRole('link', { name: 'coreone.member_balance@1.0.0' })).toHaveAttribute(
      'href',
      '/capabilities/coreone.member_balance?version=1.0.0',
    )
  })
  it('renders a crashed run', () => {
    renderWithApp(<ResultCard runId="r" result={{ status: 'error', message: 'browser launch failed' }} />)
    expect(screen.getByText('browser launch failed')).toBeInTheDocument()
  })
})

describe('Timeline', () => {
  it('renders steps, the escalation, human actions and the hand-back', () => {
    renderWithApp(
      <Timeline entries={buildTimeline(replayHumanResumeEvents)} runId="replay-b8fd4634c051" stepLabel={(id, fallback) => fallback ?? id} />,
    )
    expect(screen.getByText('Escalated to an operator')).toBeInTheDocument()
    expect(screen.getByText('type 19 chars into textbox')).toBeInTheDocument()
    expect(screen.getByText(/Operator handed back: resume/)).toBeInTheDocument()
    expect(screen.getAllByText('human').length).toBeGreaterThan(0)
  })
  it('shows a placeholder with no events', () => {
    render(<Timeline entries={[]} runId="r" stepLabel={(id) => id} />)
    expect(screen.getByText('No events yet.')).toBeInTheDocument()
  })
})
