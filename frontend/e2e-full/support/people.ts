import { type Browser, expect, type Page } from "@playwright/test";
import { stubUpstream, tilesRoute } from "../../e2e/support/network.js";
import { WEB_PORT } from "./env.js";

/**
 * The people in a full-stack test: each signed in through the development
 * sign-in and through the welcome step, in a browser of their own, with the
 * same stubs as the test's own page.
 */

/** The same stubs the fixture gives `page`, for a page in another browser context. */
export async function stub(page: Page): Promise<void> {
  await stubUpstream(page);
  await page.route(tilesRoute(), (route) => route.fulfill({ status: 204 }));
}

/** Sign `page`'s browser in as a new member who has been through the welcome step. */
export async function join(page: Page, handle: string): Promise<void> {
  const headers = { "X-FieldClub-Client": "web" };
  const login = await page.request.post("/api/v1/auth/dev-login", { headers, data: { handle } });
  expect(login.status(), await login.text()).toBe(200);
  const welcome = await page.request.post("/api/v1/auth/welcome", {
    headers,
    data: { age_band: "18_plus", accept_terms: true },
  });
  expect(welcome.status(), await welcome.text()).toBe(200);
}

/** A member in a browser of their own, the size of the test's page. */
export async function helper(browser: Browser, viewport: { width: number; height: number } | null, handle: string) {
  const context = await browser.newContext({
    baseURL: `http://localhost:${WEB_PORT}`,
    viewport,
    locale: "en-GB",
  });
  const page = await context.newPage();
  await stub(page);
  await join(page, handle);
  return { context, page };
}
