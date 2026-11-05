/**
 * Connection settings (API base URL, access token) and the operator id, persisted in localStorage.
 * Storage access is injected so the functions are testable and degrade to defaults when storage is
 * unavailable (private windows, blocked site data).
 */

export interface ConnectionSettings {
  baseUrl: string
  token: string
}

export interface KeyValueStore {
  getItem(key: string): string | null
  setItem(key: string, value: string): void
  removeItem(key: string): void
}

export const STORAGE_KEYS = {
  baseUrl: 'hands.apiBaseUrl',
  token: 'hands.apiToken',
  operatorId: 'hands.operator',
  theme: 'hands.theme',
} as const

/** Trailing slashes removed so paths can always be appended as `${base}/api/...`. */
export function normalizeBaseUrl(rawUrl: string | null | undefined): string {
  if (!rawUrl) return ''
  return rawUrl.trim().replace(/\/+$/, '')
}

/** The env default for the API URL; empty means same origin (dev proxy or the API serving the UI). */
export function envDefaultBaseUrl(): string {
  return normalizeBaseUrl(import.meta.env.VITE_HANDS_API_URL as string | undefined)
}

export function browserStore(): KeyValueStore | null {
  if (typeof window === 'undefined') return null
  const probe = '__hands_probe__'
  const storage = window.localStorage
  if (!storage) return null
  // localStorage throws in some sandboxed contexts; this probe is the one unavoidable guard.
  try {
    storage.setItem(probe, probe)
    storage.removeItem(probe)
    return storage
  } catch (error) {
    console.warn('browserStore: localStorage unavailable, settings will not persist', error)
    return null
  }
}

export function readStored(store: KeyValueStore | null, key: string): string | null {
  return store ? store.getItem(key) : null
}

export function writeStored(store: KeyValueStore | null, key: string, value: string): void {
  if (!store) return
  if (value === '') store.removeItem(key)
  else store.setItem(key, value)
}

export function loadConnectionSettings(
  store: KeyValueStore | null,
  defaultBaseUrl: string,
): ConnectionSettings {
  const storedUrl = readStored(store, STORAGE_KEYS.baseUrl)
  return {
    baseUrl: storedUrl === null ? normalizeBaseUrl(defaultBaseUrl) : normalizeBaseUrl(storedUrl),
    token: readStored(store, STORAGE_KEYS.token) ?? '',
  }
}

export function saveConnectionSettings(store: KeyValueStore | null, settings: ConnectionSettings): void {
  // Stored even when empty: an explicit "same origin" must win over a non-empty env default.
  store?.setItem(STORAGE_KEYS.baseUrl, normalizeBaseUrl(settings.baseUrl))
  writeStored(store, STORAGE_KEYS.token, settings.token.trim())
}
