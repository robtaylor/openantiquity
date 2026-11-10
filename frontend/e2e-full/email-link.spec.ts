import type { Page } from "@playwright/test";
import { openMap } from "../e2e/support/app.js";
import { stubUpstream, tilesRoute } from "../e2e/support/network.js";
import { expect, test } from "./support/fixtures.js";
import { emailedLink } from "./support/inbox.js";

/**
 * The emailed sign-in link, against the real backend and its log mailer.
 * Opened in the browser that asked for it, the link signs in at once,
 * because the backend's `fieldclub_email_link` cookie binds it to that
 * browser. Opened anywhere else, it asks "is this you?" first and signs in
 * only after the click. A link works once.
 */

async function askForLink(page: Page, address: string): Promise<void> {
  await openMap(page, "/account");
  const panel = page.getByRole("complementary", { name: "Account" });
  await panel.getByRole("button", { name: "Sign in" }).click();
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await sheet.getByLabel("Email address").fill(address);
  await sheet.getByRole("button", { name: "Email me a link" }).click();
  await expect(sheet.getByText("Check your inbox")).toBeVisible();
  await sheet.getByRole("button", { name: "Close" }).click();
}

function address(name: string, project: string): string {
  return `${name}.${project}.${Date.now()}@example.org`;
}

test("signs straight in from a link opened in the browser that asked, and the link works once", async ({
  page,
}, testInfo) => {
  const email = address("same", testInfo.project.name);
  await askForLink(page, email);
  const link = await emailedLink(email);
  expect(new URL(link).pathname).toBe("/signin/email");

  await page.goto(link);
  // A new account: the welcome step is owed, and the token has left the address.
  await expect(page.getByRole("dialog", { name: "Welcome to Field Club" })).toBeVisible();
  expect(page.url()).not.toContain("token=");
  expect(new URL(page.url()).pathname).toBe("/account");
  const me = await page.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(200);
  expect(await me.json()).toMatchObject({ email, needs_welcome: true });

  // Spent: the same link again says so, and asks for nothing more.
  await page.goto(link);
  const panel = page.getByRole("complementary", { name: "Signing in" });
  await expect(panel.getByRole("heading", { name: "This link can't be used" })).toBeVisible();
});

test("asks before signing in from a link opened in another browser, and signs in only on yes", async ({
  page,
  browser,
}, testInfo) => {
  const email = address("other", testInfo.project.name);
  await askForLink(page, email);
  const link = await emailedLink(email);

  // Another browser: no link cookie, no session.
  const elsewhere = await browser.newContext({ viewport: page.viewportSize(), locale: "en-GB" });
  const other = await elsewhere.newPage();
  await stubUpstream(other);
  await other.route(tilesRoute(), (route) => route.fulfill({ status: 204 }));
  await other.goto(link);
  const panel = other.getByRole("complementary", { name: "Signing in" });
  const question = panel.getByRole("heading", { name: /^Sign in as .+\?$/ });
  await expect(question).toBeVisible();
  await expect(question).not.toContainText(email);
  expect((await other.request.get("/api/v1/auth/me")).status()).toBe(401);

  await panel.getByRole("button", { name: "Yes, sign me in" }).click();
  await expect(other.getByRole("dialog", { name: "Welcome to Field Club" })).toBeVisible();
  const me = await other.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(200);
  expect(await me.json()).toMatchObject({ email });

  // The browser that asked is still signed out: the link signed in only the one that used it.
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
  await elsewhere.close();
});
