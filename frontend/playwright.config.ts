import { defineConfig, devices } from "@playwright/test";

/**
 * End-to-end tests run against the Vite dev server in fixture mode, on their
 * own port so they never collide with `pnpm dev`. They need no backend and no
 * network: the specs answer every request to an outside host themselves.
 */
const PORT = Number(process.env.FIELDCLUB_E2E_PORT ?? 5199);

export default defineConfig({
  testDir: "e2e",
  // Design-review screenshots have their own config. See playwright.shots.config.ts.
  testIgnore: ["shots/**"],
  outputDir: "test-results",
  timeout: 60_000,
  expect: { timeout: 15_000 },
  fullyParallel: true,
  forbidOnly: Boolean(process.env.CI),
  retries: process.env.CI ? 1 : 0,
  reporter: [["list"]],
  use: {
    baseURL: `http://localhost:${PORT}`,
    trace: "retain-on-failure",
    locale: "en-GB",
  },
  projects: [
    {
      name: "desktop",
      use: { ...devices["Desktop Chrome"], viewport: { width: 1440, height: 900 } },
    },
    {
      name: "phone",
      use: {
        ...devices["Desktop Chrome"],
        viewport: { width: 390, height: 844 },
        hasTouch: true,
        isMobile: true,
      },
    },
  ],
  webServer: {
    command: `pnpm exec vite --port ${PORT} --strictPort`,
    url: `http://localhost:${PORT}`,
    env: { VITE_USE_FIXTURES: "1" },
    reuseExistingServer: !process.env.CI,
    timeout: 60_000,
  },
});
