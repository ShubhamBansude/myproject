import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import tailwindcss from '@tailwindcss/vite'
import brotli from 'rollup-plugin-brotli'
import { VitePWA } from 'vite-plugin-pwa'

// https://vite.dev/config/
export default defineConfig(({ mode }) => ({
  plugins: [
    react(),
    tailwindcss(),
    VitePWA({
      registerType: 'autoUpdate',
      injectRegister: 'auto',
      manifest: {
        name: 'Waste Rewards',
        short_name: 'WasteRewards',
        description: 'Scan waste, earn points, redeem rewards.',
        theme_color: '#0b1220',
        background_color: '#000000',
        display: 'standalone',
        icons: [
          { src: '/vpkbiet-logo.png', sizes: '512x512', type: 'image/png', purpose: 'any' },
          { src: '/vite.svg', sizes: '256x256', type: 'image/svg+xml', purpose: 'any' },
          { src: '/swachh-bharat.svg', sizes: '256x256', type: 'image/svg+xml', purpose: 'any' },
        ],
      },
      workbox: {
        globPatterns: ['**/*.{js,css,html,ico,png,svg,webp}'],
        navigateFallback: 'index.html',
        maximumFileSizeToCacheInBytes: 7 * 1024 * 1024,
      },
      devOptions: { enabled: false },
    }),
    brotli(),
  ],
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
