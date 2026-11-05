import { describe, expect, it } from 'vitest'
import {
  browserStore,
  envDefaultBaseUrl,
  loadConnectionSettings,
  normalizeBaseUrl,
  readStored,
  saveConnectionSettings,
  STORAGE_KEYS,
  writeStored,
  type KeyValueStore,
} from './settings'

function memoryStore(initial: Record<string, string> = {}): KeyValueStore & { data: Record<string, string> } {
  const data = { ...initial }
  return {
    data,
    getItem: (key) => (key in data ? data[key] : null),
    setItem: (key, value) => {
      data[key] = value
    },
    removeItem: (key) => {
      delete data[key]
    },
  }
}

describe('normalizeBaseUrl', () => {
  it('strips trailing slashes and whitespace', () => {
    expect(normalizeBaseUrl(' https://api.example.com/// ')).toBe('https://api.example.com')
  })
  it('returns empty for null, undefined and empty', () => {
    expect(normalizeBaseUrl(null)).toBe('')
    expect(normalizeBaseUrl(undefined)).toBe('')
    expect(normalizeBaseUrl('')).toBe('')
  })
})

describe('envDefaultBaseUrl', () => {
  it('is empty when VITE_HANDS_API_URL is not set in tests', () => {
    expect(envDefaultBaseUrl()).toBe('')
  })
})

describe('browserStore', () => {
  it('returns localStorage in a browser-like environment', () => {
    expect(browserStore()).not.toBeNull()
  })
})

describe('readStored / writeStored', () => {
  it('reads null from a null store', () => {
    expect(readStored(null, 'x')).toBeNull()
  })
  it('writes and removes on empty value', () => {
    const store = memoryStore()
    writeStored(store, 'k', 'v')
    expect(store.data.k).toBe('v')
    writeStored(store, 'k', '')
    expect('k' in store.data).toBe(false)
  })
  it('ignores writes to a null store', () => {
    expect(() => writeStored(null, 'k', 'v')).not.toThrow()
  })
})

describe('loadConnectionSettings', () => {
  it('uses the env default when nothing is stored', () => {
    expect(loadConnectionSettings(memoryStore(), 'https://api.example.com/')).toEqual({
      baseUrl: 'https://api.example.com',
      token: '',
    })
  })
  it('prefers a stored value, even an empty one (same origin)', () => {
    const store = memoryStore({ [STORAGE_KEYS.baseUrl]: '', [STORAGE_KEYS.token]: 'abc' })
    expect(loadConnectionSettings(store, 'https://api.example.com')).toEqual({ baseUrl: '', token: 'abc' })
  })
  it('falls back to defaults with no storage', () => {
    expect(loadConnectionSettings(null, '')).toEqual({ baseUrl: '', token: '' })
  })
})

describe('saveConnectionSettings', () => {
  it('normalizes the URL, trims the token, and round-trips', () => {
    const store = memoryStore()
    saveConnectionSettings(store, { baseUrl: 'http://127.0.0.1:8080/', token: ' t ' })
    expect(loadConnectionSettings(store, 'ignored')).toEqual({ baseUrl: 'http://127.0.0.1:8080', token: 't' })
  })
  it('clears the token when saved empty', () => {
    const store = memoryStore({ [STORAGE_KEYS.token]: 'old' })
    saveConnectionSettings(store, { baseUrl: '', token: '' })
    expect(store.data[STORAGE_KEYS.token]).toBeUndefined()
  })
})
