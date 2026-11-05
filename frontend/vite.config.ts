import vue from '@vitejs/plugin-vue'
import { defineConfig } from 'vitest/config'

const config = {
  plugins: [vue()],
  server: {
    host: '127.0.0.1',
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8000',
        changeOrigin: false,
      },
    },
  },
  test: {
    environment: 'jsdom',
    globals: true,
    clearMocks: true,
    setupFiles: ['./src/test/setup.ts'],
  },
}

export default defineConfig(config)
