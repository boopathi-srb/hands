import { Link, NavLink, Outlet } from 'react-router-dom'
import { useApp } from '../app/AppContext'
import { useTheme, type ThemeChoice } from '../hooks/useTheme'
import { Notice } from './Feedback'

const NAV_ITEMS = [
  { to: '/', label: 'Overview', end: true },
  { to: '/capabilities', label: 'Capabilities', end: false },
  { to: '/runs', label: 'Runs', end: false },
  { to: '/discover', label: 'Discover', end: false },
  { to: '/settings', label: 'Settings', end: false },
]

const THEME_LABELS: Record<ThemeChoice, string> = { system: 'Theme: system', light: 'Theme: light', dark: 'Theme: dark' }

function HealthIndicator() {
  const { health, healthError } = useApp()
  if (healthError) {
    return (
      <span className="health" role="status">
        <span className="dot down" aria-hidden="true" />
        API unreachable
      </span>
    )
  }
  if (!health) {
    return (
      <span className="health" role="status">
        <span className="dot" aria-hidden="true" />
        Checking API…
      </span>
    )
  }
  return (
    <span className="row" role="status" style={{ gap: 14 }}>
      <span className="health">
        <span className={`dot ${health.mock_app === 'up' ? 'up' : 'down'}`} aria-hidden="true" />
        CoreOne {health.mock_app === 'up' ? 'up' : 'down'}
      </span>
      {health.active_run ? (
        <Link to={`/runs/${encodeURIComponent(health.active_run)}`} className="health">
          <span className="dot busy" aria-hidden="true" />
          Active run <code>{health.active_run}</code>
        </Link>
      ) : (
        <span className="health">
          <span className="dot up" aria-hidden="true" />
          Idle
        </span>
      )}
    </span>
  )
}

function TokenPrompt() {
  const { needsToken } = useApp()
  if (!needsToken) return null
  return (
    <Notice tone="attention" title="This API requires an access token">
      <span>
        Requests will be refused until a token is set. <Link to="/settings">Add the token in Settings</Link>.
      </span>
    </Notice>
  )
}

export function Layout() {
  const { theme, cycleTheme } = useTheme()
  const { health } = useApp()
  return (
    <div className="shell">
      <nav className="nav" aria-label="Primary">
        <Link to="/" className="brand">
          <span className="brand-mark" aria-hidden="true">h</span>
          <span className="brand-name">
            hands
            <span className="brand-sub">Back-office capabilities</span>
          </span>
        </Link>
        <div>
          <div className="nav-section">Console</div>
          <ul className="nav-list">
            {NAV_ITEMS.map((item) => (
              <li key={item.to}>
                <NavLink to={item.to} end={item.end} className="nav-link">
                  {item.label}
                </NavLink>
              </li>
            ))}
          </ul>
        </div>
        <div className="nav-foot">
          <span className="faint">{health ? `API ${health.version}` : ''}</span>
        </div>
      </nav>
      <div className="main">
        <div className="topbar">
          <HealthIndicator />
          <span className="topbar-spacer" />
          <button type="button" className="button ghost small" onClick={cycleTheme} aria-label={`${THEME_LABELS[theme]}. Switch theme`}>
            {THEME_LABELS[theme]}
          </button>
        </div>
        <main className="content" id="main">
          <TokenPrompt />
          <Outlet />
        </main>
      </div>
    </div>
  )
}
