import { defineConfig } from "@playwright/test";
const port = Number(process.env.YAMS_E2E_WEB_PORT || 3117);
const apiPort = Number(process.env.YAMS_E2E_API_PORT || 3118);
export default defineConfig({
  testDir: "./tests/e2e",
  fullyParallel: false,
  workers: 1,
  retries: 0,
  timeout: 30000,
  expect: { timeout: 10000 },
  outputDir: "test-results/e2e",
  reporter: [["list"], ["html", { open: "never" }]],
  use: {
    baseURL: `http://127.0.0.1:${port}`,
    trace: "retain-on-failure",
    screenshot: "only-on-failure",
  },
  projects: [
    {
      name: "desktop",
      use: { browserName: "chromium", viewport: { width: 1280, height: 900 } },
    },
    {
      name: "mobile",
      use: { browserName: "chromium", viewport: { width: 360, height: 800 } },
    },
  ],
  webServer: [
    {
      command: "node tests/fixture-server.mjs",
      url: `http://127.0.0.1:${apiPort}/__ready`,
      reuseExistingServer: false,
      timeout: 30000,
    },
    {
      command: `pnpm exec next start --hostname 127.0.0.1 --port ${port}`,
      url: `http://127.0.0.1:${port}`,
      reuseExistingServer: false,
      timeout: 60000,
      env: {
        API_INTERNAL_ORIGIN: `http://127.0.0.1:${apiPort}`,
        NEXT_TELEMETRY_DISABLED: "1",
      },
    },
  ],
});
