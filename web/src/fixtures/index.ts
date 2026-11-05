/**
 * Test fixtures copied verbatim from the real evidence (../../../evidence): the recorded artifact,
 * run results of every class, and events.jsonl streams. Imported only by *.test.ts files; production
 * code never imports this folder.
 */
import type { Capability, DiscoverySummary, RunEvent, RunResult, ToolDefinition } from '../api/types'
import capabilityJson from './capability.member_balance.json'
import eventsJson from './events.json'
import resultsJson from './results.json'
import toolsJson from './tool_definitions.json'

export const memberBalanceCapability = capabilityJson as unknown as Capability
export const memberBalanceTool = (toolsJson as unknown as ToolDefinition[])[0]

const results = resultsJson as unknown as Record<string, RunResult | DiscoverySummary>
export const successResult = results.success as RunResult
export const businessOutcomeResult = results.business_outcome as RunResult
export const failedResult = results.failed as RunResult
export const escalatedResult = results.escalated as RunResult
export const invalidInputResult = results.invalid_input as RunResult
export const humanResumeResult = results.human_resume as RunResult
export const discoverySummary = results.discovery as DiscoverySummary

const events = eventsJson as unknown as Record<string, RunEvent[]>
export const replaySuccessEvents = events.replay_success
export const replayHumanResumeEvents = events.replay_human_resume
export const replayFailedEvents = events.replay_failed
export const replayOutcomeEvents = events.replay_outcome
export const discoveryEvents = events.discovery
