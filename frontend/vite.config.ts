/// <reference types="vitest/config" />
import react from '@vitejs/plugin-react'
import { defineConfig } from 'vite'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  server: {
    proxy: {
      // In development the backend runs separately on :8080.
      '/api': 'http://localhost:8080',
      '/healthz': 'http://localhost:8080',
    },
  },
  build: {
    chunkSizeWarningLimit: 700, // echarts alone is ~575 kB minified; it is split below
    rolldownOptions: {
      output: {
        // Keep the (large, rarely changing) chart engine in its own cacheable chunk.
        advancedChunks: {
          groups: [{ name: 'echarts', test: /node_modules[\\/](echarts|zrender)[\\/]/ }],
        },
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: ['./src/test/setup.ts'],
  },
})
