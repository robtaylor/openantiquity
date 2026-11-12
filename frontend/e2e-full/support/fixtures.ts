import { test as base, expect } from "@playwright/test";
import { stubUpstream, tilesRoute } from "../../e2e/support/network.js";
import { collectViolations, watchPolicy } from "./policy.js";

/**
 * Playwright's `test` for runs against the real backend. The API is real, and
 * so is the page: the backend serves the built interface with its security
 * headers. Terrain tiles and every outside service are stubbed, as in fixture
 * mode, so the map draws without the internet or the elevation mirror.
 * `/meta` is the backend's own, which says `auth.dev_login` because this
 * backend has the development sign-in on (FIELDCLUB_DEV_LOGIN).
 *
 * Every test fails on a `Content-Security-Policy` violation, whether the
 * browser reports it as a `securitypolicyviolation` event or in its console
 * (`watchPolicy`), in the test's page and in every other person's browser
 * the test opens (`people.ts`). `csp` holds what was seen, for a test that
 * means to cause one.
 */
export const test = base.extend<{ stubs: undefined; csp: string[] }>({
  csp: [
    async ({ page }, use) => {
      const violations: string[] = [];
      collectViolations(violations);
      await watchPolicy(page);
      await use(violations);
      collectViolations(null);
      expect(violations, "Content-Security-Policy violations").toEqual([]);
    },
    { auto: true },
  ],
  stubs: [
    async ({ page }, use) => {
      const network = await stubUpstream(page);
      await page.route(tilesRoute(), (route) => route.fulfill({ status: 204 }));
      const problems: string[] = [];
      page.on("pageerror", (error) => problems.push(error.stack ?? error.message));
      await use(undefined);
      expect(network.unexpected, "requests that escaped the stubs").toEqual([]);
      expect(problems, "errors in the page").toEqual([]);
    },
    { auto: true },
  ],
});

export { expect };
