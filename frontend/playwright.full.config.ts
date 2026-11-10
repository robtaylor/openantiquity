import { defineConfig, devices } from "@playwright/test";
import { API_PORT, BACKEND_DIR, backendEnv, createDatabaseCommand, WEB_PORT } from "./e2e-full/support/env.js";

/**
 * `pnpm e2e:full`: end-to-end tests against the real backend, for the flows
 * fixture mode can't prove. The backend's start command first creates a
 * database of its own on the development PostGIS server
 * (`fieldclub_e2e_<pid>`), and the global teardown drops it. The backend runs on `FIELDCLUB_E2E_API_PORT` (default 6198) in
 * the test environment with the development sign-in on, and the Vite server
 * on `FIELDCLUB_E2E_PORT` (default 5198) proxies `/api` to it. Outside tile
 * services and terrain tiles are stubbed, so no test reaches the internet.
 */
export default defineConfig({
  testDir: "e2e-full",
  outputDir: "test-results/full",
  globalTeardown: "./e2e-full/support/globalTeardown.ts",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  // One backend and one database for every test, so tests that share state run in order.
  fullyParallel: false,
  workers: 1,
  forbidOnly: Boolean(process.env.CI),
  retries: 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${WEB_PORT}`,
    trace: "retain-on-failure",
    locale: "en-GB",
  },
  projects: [
    { name: "desktop", use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } } },
    {
      name: "phone",
      use: { ...devices["Desktop Chrome"], viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true },
    },
  ],
  webServer: [
    {
      // The database first, so the backend never starts without one.
      command: `${createDatabaseCommand()} && uv run fieldclub-api`,
      cwd: BACKEND_DIR,
      url: `http://127.0.0.1:${API_PORT}/healthz`,
      env: backendEnv(),
      reuseExistingServer: false,
      timeout: 120_000,
    },
    {
      command: `pnpm exec vite --port ${WEB_PORT} --strictPort`,
      url: `http://localhost:${WEB_PORT}`,
      env: { FIELDCLUB_API_URL: `http://127.0.0.1:${API_PORT}` },
      reuseExistingServer: false,
      timeout: 60_000,
    },
  ],
});
