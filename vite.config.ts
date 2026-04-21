import { defineConfig } from 'vite';
import { resolve } from 'path';

export default defineConfig({
  root: resolve(__dirname, 'vauxhall/dashboard/ui'),
  base: './',
  build: {
    outDir: resolve(__dirname, 'vauxhall/dashboard/ui/dist'),
    emptyOutDir: true,
    rollupOptions: {
      input: resolve(__dirname, 'vauxhall/dashboard/ui/index.html'),
    },
  },
});
