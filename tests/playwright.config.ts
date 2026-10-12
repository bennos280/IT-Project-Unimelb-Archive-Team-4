import { defineConfig, devices } from '@playwright/test';
import { fileURLToPath } from 'node:url';
import { tmpdir } from 'node:os';
import { join } from 'node:path';
export default defineConfig({
  testDir: './e2e/ui-reviewscreen', fullyParallel: true, workers: 2,
  reporter: [['list']],
  outputDir: join(tmpdir(), 'prest-survey-playwright'),
  use: { baseURL: 'http://127.0.0.1:4176', trace: 'off', screenshot: 'off', video: 'off' },
  projects: [{ name: 'chromium', use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 1000 } } }],
  webServer: {
    command: 'npm run dev -- --host 127.0.0.1 --port 4176 --strictPort',
    cwd: fileURLToPath(new URL('../frontend', import.meta.url)),
    url: 'http://127.0.0.1:4176', reuseExistingServer: false, timeout: 60000,
  },
});
