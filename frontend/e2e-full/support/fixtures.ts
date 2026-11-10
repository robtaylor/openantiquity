import { test as base, expect } from "@playwright/test";
import { stubUpstream, tilesRoute } from "../../e2e/support/network.js";

/**
 * Playwright's `test` for runs against the real backend. The API is real.
 * Terrain tiles and every outside service are stubbed, as in fixture mode, so
 * the map draws without the internet or the elevation mirror.
 *
 * `/meta` is passed through with one addition: `auth.dev_login`, which the
 * backend doesn't send yet. It tells the sign-in sheet to offer the
 * development sign-in, which this backend has (FIELDCLUB_DEV_LOGIN is on).
 */
export const test = base.extend<{ stubs: undefined }>({
  stubs: [
    async ({ page }, use) => {
      const network = await stubUpstream(page);
      await page.route(tilesRoute(), (route) => route.fulfill({ status: 204 }));
      await page.route(/\/api\/v1\/meta(\?|$)/, async (route) => {
        const response = await route.fetch();
        const meta = (await response.json()) as { auth: Record<string, unknown> };
        meta.auth.dev_login = true;
        await route.fulfill({ response, json: meta });
      });
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
