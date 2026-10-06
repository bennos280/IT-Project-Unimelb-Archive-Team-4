import { defineConfig } from 'vitest/config';
export default defineConfig({ test: { environment: 'node', include: ['unit/ui-reviewscreen/**/*.test.ts'], restoreMocks: true, unstubGlobals: true } });
