import { useCallback, useEffect, useRef, useState } from 'react'
import type { ApiError, ApiResult } from '../api/client'

export interface AsyncState<T> {
  data: T | null
  error: ApiError | null
  loading: boolean
  reload: () => void
}

/**
 * Loads one API resource and re-loads when `key` changes. Results from a superseded load are
 * ignored, so a slow response never overwrites a newer one.
 */
export function useApiResource<T>(load: () => Promise<ApiResult<T>>, key: string): AsyncState<T> {
  const [data, setData] = useState<T | null>(null)
  const [error, setError] = useState<ApiError | null>(null)
  const [loading, setLoading] = useState(true)
  const [generation, setGeneration] = useState(0)
  const loadRef = useRef(load)
  loadRef.current = load

  useEffect(() => {
    let current = true
    setLoading(true)
    loadRef.current().then((result) => {
      if (!current) return
      if (result.ok) {
        setData(result.data)
        setError(null)
      } else {
        setError(result.error)
      }
      setLoading(false)
    })
    return () => {
      current = false
    }
  }, [key, generation])

  const reload = useCallback(() => setGeneration((value) => value + 1), [])
  return { data, error, loading, reload }
}

/** Calls `tick` every `intervalMs` while `enabled`; the first call happens immediately. */
export function useInterval(tick: () => void, intervalMs: number, enabled: boolean): void {
  const tickRef = useRef(tick)
  tickRef.current = tick
  useEffect(() => {
    if (!enabled) return
    tickRef.current()
    const handle = window.setInterval(() => tickRef.current(), intervalMs)
    return () => window.clearInterval(handle)
  }, [intervalMs, enabled])
}

/** A clock that re-renders every `intervalMs` while enabled, for counting durations of live runs. */
export function useNow(intervalMs: number, enabled: boolean): number {
  const [now, setNow] = useState(() => Date.now())
  useInterval(() => setNow(Date.now()), intervalMs, enabled)
  return now
}
