import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import brotli from 'rollup-plugin-brotli'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
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
  resolve: {
    // Use Preact in production automatically (or when USE_PREACT=1)
    alias: (mode === 'production' || process.env.USE_PREACT === '1')
      ? {
          react: 'preact/compat',
          'react-dom/test-utils': 'preact/test-utils',
          'react-dom': 'preact/compat',
        }
      : undefined,
  },
  esbuild: {
    // Drop debug code in production, keep in dev for DX
    drop: mode === 'production' ? ['console', 'debugger'] : [],
  },
}))
