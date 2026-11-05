/*
 * hands web console.
 *
 * Stack: Vite + React + TypeScript + react-router, hand-written CSS on design tokens. No UI kit:
 * the screens are mostly tables, definition lists and timelines, which plain semantic HTML does
 * well; a kit would add weight, its own visual language and theming to fight, and hide the focus,
 * contrast and dark-mode rules that this console needs to control exactly. Server state is fetched
 * through one typed client (src/api) and kept in component state; there is no global store.
 */
import { BrowserRouter, Route, Routes } from 'react-router-dom'
import { AppProvider } from './app/AppContext'
import { Layout } from './components/Layout'
import { CapabilitiesPage } from './pages/CapabilitiesPage'
import { CapabilityDetailPage } from './pages/CapabilityDetailPage'
import { DiscoverPage } from './pages/DiscoverPage'
import { NotFoundPage } from './pages/NotFoundPage'
import { OperatorPage } from './pages/OperatorPage'
import { OverviewPage } from './pages/OverviewPage'
import { RunCapabilityPage } from './pages/RunCapabilityPage'
import { RunDetailPage } from './pages/RunDetailPage'
import { RunsPage } from './pages/RunsPage'
import { SettingsPage } from './pages/SettingsPage'

export function App() {
  return (
    <AppProvider>
      <BrowserRouter>
        <Routes>
          <Route element={<Layout />}>
            <Route index element={<OverviewPage />} />
            <Route path="capabilities" element={<CapabilitiesPage />} />
            <Route path="capabilities/:capabilityId" element={<CapabilityDetailPage />} />
            <Route path="capabilities/:capabilityId/run" element={<RunCapabilityPage />} />
            <Route path="discover" element={<DiscoverPage />} />
            <Route path="runs" element={<RunsPage />} />
            <Route path="runs/:runId" element={<RunDetailPage />} />
            <Route path="runs/:runId/operator" element={<OperatorPage />} />
            <Route path="settings" element={<SettingsPage />} />
            <Route path="*" element={<NotFoundPage />} />
          </Route>
        </Routes>
      </BrowserRouter>
    </AppProvider>
  )
}
