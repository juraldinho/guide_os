import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { fileURLToPath, URL } from 'node:url';

const rootIndex = fileURLToPath(new URL('./index.html', import.meta.url));

export default defineConfig({
  plugins: [react()],
  resolve: {
    alias: {
      '@': fileURLToPath(new URL('./src', import.meta.url)),
    },
  },
  server: {
    allowedHosts: ['.trycloudflare.com'],
    proxy: {
      '/app/v1': {
        target: 'http://127.0.0.1:8083',
        changeOrigin: true,
      },
    },
  },
  build: {
    rollupOptions: {
      input: rootIndex,
    },
  },
  optimizeDeps: {
    entries: [rootIndex],
  },
  test: {
    environment: 'jsdom',
    globals: true,
    setupFiles: './tests/setup.ts',
  },
});
