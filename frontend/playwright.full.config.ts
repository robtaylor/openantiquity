import { defineConfig, devices } from "@playwright/test";
import {
  API_PORT,
  BACKEND_DIR,
  BACKEND_LOG,
  backendEnv,
  buildFrontendCommand,
  createDatabaseCommand,
  WEB_PORT,
} from "./e2e-full/support/env.js";

/**
 * `pnpm e2e:full`: end-to-end tests against the real backend, for the flows
 * fixture mode can't prove. The backend's start command first builds the
 * interface into a folder of its own (`E2E_DIST`) and creates a database of
 * its own on the development PostGIS server (`fieldclub_e2e_<pid>`), and the
 * global teardown drops it. The backend runs on `FIELDCLUB_E2E_API_PORT`
 * (default 6198) in the test environment with the development sign-in on,
 * and serves the built interface as production does, with its security
 * headers, so every test also proves the interface works under the
 * `Content-Security-Policy` (a violation fails the test). Outside tile
 * services and terrain tiles are stubbed, so no test reaches the internet.
 * The backend's output goes to `BACKEND_LOG`, where the tests read the
 * emailed sign-in links its log mailer writes.
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
      // The interface and the database first, so the backend never starts without either.
      command: `${buildFrontendCommand()} && ${createDatabaseCommand()} && exec uv run fieldclub-api > ${JSON.stringify(BACKEND_LOG)} 2>&1`,
      cwd: BACKEND_DIR,
      url: `http://127.0.0.1:${API_PORT}/healthz`,
      env: backendEnv(),
      reuseExistingServer: false,
      timeout: 240_000,
    },
  ],
});
