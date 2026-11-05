import { useState } from 'react'
import { RunImage } from './RunFile'

/** `screenshots/005-obs-001.png` -> `005-obs-001`. */
export function screenshotCaption(path: string): string {
  const name = path.split('/').pop() ?? path
  return name.replace(/\.(png|jpe?g)$/i, '')
}

/** Screenshot gallery: thumbnails plus one enlarged viewer. Selection is keyboard reachable. */
export function Filmstrip({ runId, paths }: { runId: string; paths: string[] }) {
  const [selected, setSelected] = useState<string | null>(null)
  const active = selected && paths.includes(selected) ? selected : (paths[paths.length - 1] ?? null)
  if (paths.length === 0) return <p className="muted">No screenshots were recorded for this run.</p>
  return (
    <div className="stack">
      {active ? (
        <figure className="viewer" style={{ margin: 0 }}>
          <RunImage runId={runId} path={active} alt={`Screenshot ${screenshotCaption(active)}`} className="shot" />
          <figcaption className="faint mono">{active}</figcaption>
        </figure>
      ) : null}
      <div className="filmstrip" role="group" aria-label="Screenshots">
        {paths.map((path) => (
          <button
            key={path}
            type="button"
            className="thumb"
            aria-pressed={path === active}
            onClick={() => setSelected(path)}
          >
            <RunImage runId={runId} path={path} alt="" />
            <span className="thumb-caption">{screenshotCaption(path)}</span>
          </button>
        ))}
      </div>
    </div>
  )
}
