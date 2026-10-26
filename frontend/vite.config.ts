import { fileURLToPath, URL } from 'node:url';

import vue from '@vitejs/plugin-vue';
import { loadEnv } from 'vite';
import { defineConfig } from 'vitest/config';

import { createDevServerProxy } from './src/viteProxy';

// https://vitejs.dev/config/
export default defineConfig(({ mode }) => {
  const env = { ...process.env, ...loadEnv(mode, process.cwd(), '') };

  return {
    plugins: [
      vue(),
    ],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url)),
      },
    },
    server: {
      host: '0.0.0.0',
      port: Number(env.FRONTEND_PORT || 5173),
      proxy: createDevServerProxy(env),
      // Docker on Windows doesn't pass file-change events into the container; poll instead.
      watch: env.VITE_USE_POLLING === 'true' ? { usePolling: true, interval: 500 } : undefined,
    },
    test: {
      environment: 'jsdom',
      globals: true,
      setupFiles: ['./test/setup.ts'],
      include: ['test/**/*.{test,spec}.ts'],
    },
  };
});
