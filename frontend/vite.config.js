import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import brotli from 'rollup-plugin-brotli'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react(), tailwindcss(), brotli()],
  build: {
    cssCodeSplit: true,
    sourcemap: false,
    rollupOptions: {
      output: {
        manualChunks(id) {
          if (id.includes('node_modules')) {
            if (id.includes('react') || id.includes('react-dom')) return 'vendor-react';
            if (id.includes('exif-js')) return 'vendor-exif';
            if (id.includes('tailwindcss')) return 'vendor-tailwind';
            return 'vendor';
          }
        },
      },
    },
    target: 'es2018',
    minify: 'esbuild',
  },
  esbuild: {
    drop: ['console', 'debugger'],
  },
})
