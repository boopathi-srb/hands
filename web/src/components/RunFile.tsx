import { useState } from 'react'
import { useApp } from '../app/AppContext'
import { useRunFileUrl } from '../hooks/useRunFile'

interface RunImageProps {
  runId: string
  path: string
  alt: string
  className?: string
}

export function RunImage({ runId, path, alt, className }: RunImageProps) {
  const { url, failed } = useRunFileUrl(runId, path)
  if (failed) return <div className={`${className ?? ''} thumb-placeholder`} role="img" aria-label={`${alt} (unavailable)`} />
  if (!url) return <div className={`${className ?? ''} thumb-placeholder`} aria-hidden="true" />
  return <img src={url} alt={alt} className={className} />
}

/**
 * Opens an evidence file (screenshot or snapshot JSON) in a new tab. The file is fetched on click
 * through the API client so the bearer token is applied; nothing is downloaded until asked for.
 */
export function RunFileLink({ runId, path, label }: { runId: string; path: string; label?: string }) {
  const { client } = useApp()
  const [state, setState] = useState<'idle' | 'loading' | 'failed'>('idle')
  const text = label ?? path

  function open() {
    setState('loading')
    client.runFile(runId, path).then((result) => {
      if (!result.ok) {
        setState('failed')
        return
      }
      const url = URL.createObjectURL(result.data)
      const opened = window.open(url, '_blank')
      if (!opened) console.warn('RunFileLink.open: popup blocked for evidence file', { runId, path })
      window.setTimeout(() => URL.revokeObjectURL(url), 60_000)
      setState('idle')
    })
  }

  return (
    <button type="button" className="link-button mono" onClick={open} disabled={state === 'loading'} title={path}>
      {state === 'failed' ? `${text} (unavailable)` : text}
    </button>
  )
}
