import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { App } from './App'
import './styles/tokens.css'
import './styles/app.css'

const rootElement = document.getElementById('root')
if (!rootElement) {
  console.error('main: #root element missing from index.html; the UI cannot mount')
} else {
  createRoot(rootElement).render(
    <StrictMode>
      <App />
    </StrictMode>,
  )
}
