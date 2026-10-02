import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5173,
    host: true,
    proxy: {
      // BR/spec: same-origin proxy keeps the Django session cookie on
      // localhost:5173, so SameSite=Lax + CORS are never exercised
      // cross-origin during development.
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
});
