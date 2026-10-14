import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import path from 'path'

export default defineConfig({
  plugins: [react(), tailwindcss()],
  resolve: {
    alias: {
      '@': path.resolve(import.meta.dirname, './src'),
    },
  },
  server: {
    port: 5173,
    proxy: {
      '/api': {
        target: 'http://localhost:8000',
        changeOrigin: true,
      },
    },
  },
  build: {
    rolldownOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules/react') || id.includes('node_modules/@remix-run')) return 'react-runtime'
          if (id.includes('node_modules/@tanstack') || id.includes('node_modules/zustand')) return 'data-runtime'
          if (id.includes('node_modules/cmdk') || id.includes('node_modules/vaul') || id.includes('node_modules/@radix-ui') || id.includes('node_modules/framer-motion')) return 'interaction-runtime'
          return undefined
        },
      },
    },
  },
})
