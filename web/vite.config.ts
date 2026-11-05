import react from '@vitejs/plugin-react'
import { defineConfig } from 'vitest/config'

// The hands API (`hands serve`) listens on 8080. In dev the UI is served by Vite on another port,
// so /api and /console (including the operator live-view websocket) are proxied to keep requests
// same-origin and avoid CORS during development.
const HANDS_API_TARGET = process.env.HANDS_API_TARGET ?? 'http://127.0.0.1:8080'

export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': { target: HANDS_API_TARGET, changeOrigin: true },
      '/console': { target: HANDS_API_TARGET, changeOrigin: true, ws: true },
    },
  },
  test: {
    environment: 'jsdom',
    include: ['src/**/*.test.{ts,tsx}'],
    setupFiles: ['src/test/setup.ts'],
  },
})
