import { useState } from 'react'

/** Collapsible pretty-printed JSON with a copy button. Closed by default. */
export function JsonDisclosure({ value, summary }: { value: unknown; summary: string }) {
  const [copied, setCopied] = useState(false)
  const text = JSON.stringify(value, null, 2)

  function copy() {
    if (!navigator.clipboard) {
      console.warn('JsonDisclosure.copy: clipboard API unavailable')
      return
    }
    navigator.clipboard.writeText(text).then(
      () => {
        setCopied(true)
        window.setTimeout(() => setCopied(false), 1500)
      },
      (error: unknown) => console.error('JsonDisclosure.copy: clipboard write failed', error),
    )
  }

  return (
    <details className="disclosure">
      <summary>{summary}</summary>
      <div className="stack-sm" style={{ marginTop: 8 }}>
        <div className="row">
          <button type="button" className="button small" onClick={copy}>
            {copied ? 'Copied' : 'Copy JSON'}
          </button>
        </div>
        <pre className="code" tabIndex={0}>
          {text}
        </pre>
      </div>
    </details>
  )
}
