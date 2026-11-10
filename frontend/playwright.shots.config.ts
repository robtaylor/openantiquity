import { defineConfig } from "@playwright/test";
import base from "./playwright.config.js";

/**
 * `pnpm shots`: design-review screenshots at desktop and phone sizes, written
 * to `FIELDCLUB_SHOTS_DIR` (default `test-results/shots`). Uses live tiles.
 */
export default defineConfig({
  ...base,
  testDir: "e2e/shots",
  testIgnore: [],
  timeout: 120_000,
  fullyParallel: false,
  workers: 2,
  retries: 0,
});
