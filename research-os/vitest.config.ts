import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'
import { resolve } from 'path'

export default defineConfig({
  plugins: [react()],
  test: {
    globals: true,
    environment: 'node',
    setupFiles: ['./vitest.setup.ts'],
    environmentOptions: {},
    coverage: {
      provider: 'v8',
      reporter: ['text', 'html'],
      include: ['lib/**', 'app/api/**', 'inngest/**'],
      exclude: ['**/*.test.ts', '**/__tests__/**'],
    },
    env: {
      STUB_AI: 'true',
      NEXT_PUBLIC_SUPABASE_URL: 'http://localhost:54321',
      NEXT_PUBLIC_SUPABASE_ANON_KEY: 'test-anon-key',
      SUPABASE_SERVICE_ROLE_KEY: 'test-service-role-key',
      OPENAI_API_KEY: 'test-openai-key',
      ANTHROPIC_API_KEY: 'test-anthropic-key',
      INNGEST_EVENT_KEY: 'test-inngest-key',
      INNGEST_SIGNING_KEY: 'test-signing-key',
    },
  },
  resolve: {
    alias: { '@': resolve(__dirname, '.') },
  },
})
