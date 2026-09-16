import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

const __dirname = dirname(fileURLToPath(import.meta.url))

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      '/api': 'http://localhost:8080',
      // Reconnect-Google-Health links point at these directly (see
      // Sync.jsx/QuickSyncButton.jsx authExpired handling) - proxied so
      // they work from the Vite dev origin without hardcoding :8080.
      '/auth-login.php': 'http://localhost:8080',
      '/auth-callback.php': 'http://localhost:8080',
    },
  },
  build: {
    // faq.html is a second, standalone entry point (frontend/src/faq-main.jsx)
    // - the FAQ page opens in its own tab, not as a route inside the main
    // SPA (which has no router library), so it needs its own built page.
    rollupOptions: {
      input: {
        main: resolve(__dirname, 'index.html'),
        faq: resolve(__dirname, 'faq.html'),
      },
    },
  },
})
