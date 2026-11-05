import { useState, type FormEvent } from 'react'
import { envDefaultBaseUrl } from '../api/settings'
import { useApp } from '../app/AppContext'
import { ErrorNotice, Notice } from '../components/Feedback'
import { TextField } from '../components/FormControls'
import { KeyValueList, PageHeader, Panel } from '../components/Panel'

export function validateBaseUrl(value: string): string | null {
  const trimmed = value.trim()
  if (trimmed === '') return null
  if (!/^https?:\/\/[^\s/]+/.test(trimmed)) return 'Use a full http(s) URL, or leave empty for the same origin'
  return null
}

export function SettingsPage() {
  const { settings, updateSettings, health, healthError, needsToken, refreshHealth } = useApp()
  const [baseUrl, setBaseUrl] = useState(settings.baseUrl)
  const [token, setToken] = useState(settings.token)
  const [saved, setSaved] = useState(false)
  const urlError = validateBaseUrl(baseUrl)
  const envDefault = envDefaultBaseUrl()

  function save(event: FormEvent) {
    event.preventDefault()
    if (urlError) return
    updateSettings({ baseUrl, token })
    setSaved(true)
  }

  return (
    <>
      <PageHeader eyebrow="Settings" title="Connection" lede="Where this console finds the hands API. Stored in this browser only." />
      <div className="grid grid-sidebar">
        <Panel title="API connection">
          <form className="form" onSubmit={save}>
            <TextField
              id="api-base-url"
              label="API base URL"
              value={baseUrl}
              onChange={(value) => {
                setBaseUrl(value)
                setSaved(false)
              }}
              placeholder="Same origin"
              mono
              hint={`Empty means same origin (the dev server proxies /api and /console). Build default: ${envDefault || 'same origin'}.`}
              error={urlError}
            />
            <TextField
              id="api-token"
              label="Access token"
              type="password"
              value={token}
              onChange={(value) => {
                setToken(value)
                setSaved(false)
              }}
              mono
              hint="Sent as Authorization: Bearer on every request, and as ?token= on the live-view websocket."
              autoComplete="off"
            />
            <div className="form-actions">
              <button type="submit" className="button primary" disabled={Boolean(urlError)}>
                Save
              </button>
              <button type="button" className="button" onClick={refreshHealth}>
                Test connection
              </button>
              {saved ? <span className="faint" role="status">Saved.</span> : null}
            </div>
          </form>
        </Panel>
        <div className="stack">
          {needsToken ? (
            <Notice tone="attention" title="Token required">
              <span>The API reports that authentication is required and no token is set.</span>
            </Notice>
          ) : null}
          {healthError ? <ErrorNotice error={healthError} /> : null}
          <Panel title="Current connection">
            <KeyValueList
              items={[
                { label: 'API', value: <code>{settings.baseUrl || window.location.origin}</code> },
                { label: 'Status', value: health ? health.status : healthError ? 'Unreachable' : 'Checking…' },
                { label: 'Version', value: health?.version },
                { label: 'Auth', value: health ? (health.auth_required ? 'Token required' : 'Open') : null },
                { label: 'Token set', value: settings.token ? 'Yes' : 'No' },
              ]}
            />
          </Panel>
        </div>
      </div>
    </>
  )
}
