import { defineConfig, devices } from "@playwright/test";
import { fileURLToPath } from "node:url";
import { tmpdir } from "node:os";
import { join } from "node:path";
export default defineConfig({
  testDir: "./integration/frontend",
  fullyParallel: true,
  workers: 2,
  reporter: [["list"]],
  outputDir: join(tmpdir(), "prest-survey-playwright"),
  use: {
    baseURL: "http://127.0.0.1:4176",
    // Ben is working (person.ts), so a test starts past the name screen; the name screen's own tests start with none.
    storageState: { cookies: [], origins: [{ origin: "http://127.0.0.1:4176",
      localStorage: [{ name: "prestcribe.person", value: JSON.stringify({ id: 1, name: "Ben" }) }] }] },
    trace: "off",
    screenshot: "off",
    video: "off",
  },
  projects: [
    {
      name: "chromium",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 1440, height: 1000 },
      },
    },
    {
      // Safari's engine: only the specs that depend on its layout.
      name: "webkit",
      testMatch: "{row-links,zz-probe}.spec.ts",
      use: {
        ...devices["Desktop Safari"],
        viewport: { width: 1440, height: 1000 },
      },
    },
  ],
  webServer: {
    command: "npm run dev -- --host 127.0.0.1 --port 4176 --strictPort",
    cwd: fileURLToPath(new URL("../frontend", import.meta.url)),
    url: "http://127.0.0.1:4176",
    reuseExistingServer: false,
    timeout: 60000,
  },
});
