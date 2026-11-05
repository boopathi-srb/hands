import { useEffect, useState } from 'react'
import { useApp } from '../app/AppContext'

export interface RunFileState {
  url: string | null
  failed: boolean
}

/**
 * Fetches an evidence file through the API client (so the bearer token is sent) and exposes it as
 * an object URL, revoked when the path changes or the component unmounts.
 */
export function useRunFileUrl(runId: string | null, path: string | null): RunFileState {
  const { client } = useApp()
  const [state, setState] = useState<RunFileState>({ url: null, failed: false })

  useEffect(() => {
    if (!runId || !path) {
      setState({ url: null, failed: false })
      return
    }
    let objectUrl: string | null = null
    let current = true
    setState({ url: null, failed: false })
    client.runFile(runId, path).then((result) => {
      if (!current) return
      if (!result.ok) {
        setState({ url: null, failed: true })
        return
      }
      objectUrl = URL.createObjectURL(result.data)
      setState({ url: objectUrl, failed: false })
    })
    return () => {
      current = false
      if (objectUrl) URL.revokeObjectURL(objectUrl)
    }
  }, [client, runId, path])

  return state
}
