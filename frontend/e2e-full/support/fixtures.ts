import { test as base, expect } from "@playwright/test";
import { stubUpstream, tilesRoute } from "../../e2e/support/network.js";

/**
 * Playwright's `test` for runs against the real backend. The API is real.
 * Terrain tiles and every outside service are stubbed, as in fixture mode, so
 * the map draws without the internet or the elevation mirror.
 * `/meta` is the backend's own, which says `auth.dev_login` because this
 * backend has the development sign-in on (FIELDCLUB_DEV_LOGIN).
 */
export const test = base.extend<{ stubs: undefined }>({
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
