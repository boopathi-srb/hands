import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react'
import { createApiClient, type ApiClient, type ApiError } from '../api/client'
import {
  browserStore,
  envDefaultBaseUrl,
  loadConnectionSettings,
  readStored,
  saveConnectionSettings,
  STORAGE_KEYS,
  writeStored,
  type ConnectionSettings,
} from '../api/settings'
import type { Health } from '../api/types'
import { useInterval } from '../hooks/useAsync'

const HEALTH_POLL_MS = 5000

export interface AppContextValue {
  client: ApiClient
  settings: ConnectionSettings
  updateSettings: (next: ConnectionSettings) => void
  health: Health | null
  healthError: ApiError | null
  refreshHealth: () => void
  needsToken: boolean
  operatorId: string
  setOperatorId: (operatorId: string) => void
}

const AppContext = createContext<AppContextValue | null>(null)

export function AppProvider({ children }: { children: ReactNode }) {
  const store = useMemo(() => browserStore(), [])
  const [settings, setSettings] = useState(() => loadConnectionSettings(store, envDefaultBaseUrl()))
  const [operatorId, setOperatorIdState] = useState(() => readStored(store, STORAGE_KEYS.operatorId) ?? '')
  const [health, setHealth] = useState<Health | null>(null)
  const [healthError, setHealthError] = useState<ApiError | null>(null)

  const settingsRef = useMemo(() => ({ current: settings }), [settings])
  const client = useMemo(() => createApiClient(() => settingsRef.current), [settingsRef])

  const refreshHealth = useCallback(() => {
    client.health().then((result) => {
      if (result.ok) {
        setHealth(result.data)
        setHealthError(null)
      } else {
        setHealthError(result.error)
      }
    })
  }, [client])

  useInterval(refreshHealth, HEALTH_POLL_MS, true)
  // New connection settings produce a new client; check health against it right away.
  useEffect(() => refreshHealth(), [refreshHealth])

  const updateSettings = useCallback(
    (next: ConnectionSettings) => {
      saveConnectionSettings(store, next)
      setSettings(loadConnectionSettings(store, envDefaultBaseUrl()))
      setHealth(null)
    },
    [store],
  )

  const setOperatorId = useCallback(
    (next: string) => {
      setOperatorIdState(next)
      writeStored(store, STORAGE_KEYS.operatorId, next.trim())
    },
    [store],
  )

  const value: AppContextValue = {
    client,
    settings,
    updateSettings,
    health,
    healthError,
    refreshHealth,
    needsToken: Boolean(health?.auth_required && !settings.token),
    operatorId,
    setOperatorId,
  }
  return <AppContext.Provider value={value}>{children}</AppContext.Provider>
}

export function useApp(): AppContextValue {
  const value = useContext(AppContext)
  if (!value) throw new Error('useApp must be used inside <AppProvider>')
  return value
}
