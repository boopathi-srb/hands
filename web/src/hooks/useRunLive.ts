import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApiError } from '../api/client'
import type { RunDetail, RunEvent, RunState } from '../api/types'
import { useApp } from '../app/AppContext'
import { isActiveState } from '../lib/format'
import { mergeEvents } from '../lib/timeline'
import { useInterval } from './useAsync'

const EVENTS_POLL_MS = 1000
/** The run detail carries the intervention screenshot, so it is polled at half the event rate. */
const DETAIL_EVERY_N_TICKS = 2

export interface RunLiveState {
  run: RunDetail | null
  events: RunEvent[]
  error: ApiError | null
  active: boolean
  refresh: () => void
}

/**
 * Follows one run: loads its detail and events, then while it is running or waiting for an operator
 * polls new events (`after=<last seq>`) every second and the run detail every other second. When
 * the run ends, one final fetch picks up the result and the last events.
 */
export function useRunLive(runId: string): RunLiveState {
  const { client } = useApp()
  const [run, setRun] = useState<RunDetail | null>(null)
  const [events, setEvents] = useState<RunEvent[]>([])
  const [error, setError] = useState<ApiError | null>(null)
  const [state, setState] = useState<RunState | null>(null)
  const lastSeqRef = useRef(0)
  const inFlightRef = useRef(false)
  const tickRef = useRef(0)

  const loadDetail = useCallback(async () => {
    const result = await client.run(runId)
    if (result.ok) {
      setRun(result.data)
      setState(result.data.state)
      setError(null)
    } else {
      setError(result.error)
    }
  }, [client, runId])

  const loadEvents = useCallback(async () => {
    const result = await client.runEvents(runId, lastSeqRef.current)
    if (!result.ok) {
      setError(result.error)
      return null
    }
    const page = result.data
    setEvents((known) => {
      const merged = mergeEvents(known, page.events)
      lastSeqRef.current = merged.length ? merged[merged.length - 1].seq : lastSeqRef.current
      return merged
    })
    lastSeqRef.current = Math.max(lastSeqRef.current, page.last_seq ?? 0)
    return page.state
  }, [client, runId])

  const poll = useCallback(async () => {
    if (inFlightRef.current) return
    inFlightRef.current = true
    tickRef.current += 1
    const eventState = await loadEvents()
    const finishedNow = eventState !== null && !isActiveState(eventState)
    if (finishedNow || tickRef.current % DETAIL_EVERY_N_TICKS === 0) await loadDetail()
    inFlightRef.current = false
  }, [loadDetail, loadEvents])

  useEffect(() => {
    lastSeqRef.current = 0
    tickRef.current = 0
    setRun(null)
    setEvents([])
    setState(null)
    setError(null)
    void loadDetail().then(() => loadEvents())
  }, [loadDetail, loadEvents])

  const active = isActiveState(state)
  useInterval(() => void poll(), EVENTS_POLL_MS, active)

  const refresh = useCallback(() => {
    void loadDetail().then(() => loadEvents())
  }, [loadDetail, loadEvents])

  return { run, events, error, active, refresh }
}
