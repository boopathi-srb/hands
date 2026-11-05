import { render } from '@testing-library/react'
import type { ReactElement } from 'react'
import { MemoryRouter } from 'react-router-dom'
import { vi } from 'vitest'
import { AppProvider } from '../app/AppContext'

/** Renders inside the app providers with `fetch` mocked: health is up, everything else 404s. */
export function renderWithApp(ui: ReactElement) {
  const fetchMock = vi.fn((input: string) => {
    if (input.endsWith('/api/health')) {
      const health = { status: 'ok', auth_required: false, mock_app: 'up', planners: { anthropic: true, ollama: false, scripted: true }, active_run: null, version: 'test' }
      return Promise.resolve(new Response(JSON.stringify(health), { status: 200 }))
    }
    return Promise.resolve(new Response(JSON.stringify({ error: 'not_found' }), { status: 404 }))
  })
  vi.stubGlobal('fetch', fetchMock)
  const result = render(
    <AppProvider>
      <MemoryRouter>{ui}</MemoryRouter>
    </AppProvider>,
  )
  return { ...result, fetchMock }
}
