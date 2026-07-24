import { defineConfig } from 'vite';
import react from '@vitejs/plugin-react';
import { structuralAnchorDraftIntegrityPlugin } from './build/structuralAnchorDraftIntegrityPlugin';

const VPS_TARGET = 'https://api01.apexcoastalrentals.co.za';

export default defineConfig({
  plugins: [
    structuralAnchorDraftIntegrityPlugin(),
    react({ allowConstantExport: true }),
  ],
  base: './',
  appType: 'spa',
  server: {
    host: '0.0.0.0',
    port: 5173,
    strictPort: true,
    proxy: {
      '/api': { target: VPS_TARGET, changeOrigin: true, secure: true },
      '/state': { target: VPS_TARGET, changeOrigin: true, secure: true },
      '/trade': { target: VPS_TARGET, changeOrigin: true, secure: true },
      '/sql': { target: VPS_TARGET, changeOrigin: true, secure: true },
    },
  },
});
