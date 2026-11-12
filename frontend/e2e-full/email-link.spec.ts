import type { Page } from "@playwright/test";
import { openMap } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";
import { emailedLink } from "./support/inbox.js";
import { stub } from "./support/people.js";

/**
 * The emailed sign-in link, against the real backend and its log mailer.
 * Opened in the browser that asked for it, the link signs in at once,
 * because the backend's `openantiquity_email_link` cookie binds it to that
 * browser. Opened anywhere else, it asks the person to type their address
 * and signs in only when it is the link's own. A link works once, and
 * signed-out drafts are never saved to an account a link from elsewhere
 * signed in to (Decision 0022).
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
  await expect(page.getByRole("dialog", { name: "Welcome to Open Antiquity" })).toBeVisible();
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

test("signs in from a link opened in another browser only when the person types the link's address", async ({
  page,
  browser,
}, testInfo) => {
  const email = address("other", testInfo.project.name);
  await askForLink(page, email);
  const link = await emailedLink(email);

  // Another browser: no link cookie, no session.
  const elsewhere = await browser.newContext({ viewport: page.viewportSize(), locale: "en-GB" });
  const other = await elsewhere.newPage();
  await stub(other);
  await other.goto(link);
  const panel = other.getByRole("complementary", { name: "Signing in" });
  await expect(panel.getByRole("heading", { name: "Which email address is this link for?" })).toBeVisible();
  // Nothing about the address is shown or filled in: a stranger's can be made to look like yours.
  await expect(panel).not.toContainText("***");
  const field = panel.getByLabel("Your email address");
  await expect(field).toHaveValue("");
  expect((await other.request.get("/api/v1/auth/me")).status()).toBe(401);

  // Someone else's address: refused, and the link is not spent.
  await field.fill(`someone.else.${Date.now()}@example.org`);
  await panel.getByRole("button", { name: "Sign me in" }).click();
  await expect(panel.getByText(/That isn't the address this link was sent to/)).toBeVisible();
  expect((await other.request.get("/api/v1/auth/me")).status()).toBe(401);

  await panel.getByLabel("Your email address").fill(email.toUpperCase());
  await panel.getByRole("button", { name: "Sign me in" }).click();
  await expect(other.getByRole("dialog", { name: "Welcome to Open Antiquity" })).toBeVisible();
  const me = await other.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(200);
  expect(await me.json()).toMatchObject({ email });

  // The browser that asked is still signed out: the link signed in only the one that used it.
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
  await elsewhere.close();
});

test("never saves drafts left in a browser to the account a link from elsewhere signs in to", async ({
  page,
  browser,
}, testInfo) => {
  // Someone asks for a link to their own address, in their own browser.
  const sender = address("sender", testInfo.project.name);
  const theirs = await browser.newContext({ viewport: page.viewportSize(), locale: "en-GB" });
  const theirPage = await theirs.newPage();
  await stub(theirPage);
  await askForLink(theirPage, sender);
  const link = await emailedLink(sender);
  await theirs.close();

  // In another browser, someone signed out has marked a finding and begun to sign in from this tab.
  await openMap(page, "/");
  await page.evaluate(
    ({ key }) => {
      const now = new Date().toISOString();
      const visit = "visit-of-the-person-here";
      window.sessionStorage.setItem("fieldclub.drafts.visit", visit);
      window.sessionStorage.setItem("fieldclub.drafts.signin", JSON.stringify({ visit, way: "email", at: Date.now() }));
      const draft = {
        id: "draft-left-here",
        kind: "finding",
        data: { note: "not theirs" },
        owner: { signedOut: visit },
        createdAt: now,
        updatedAt: now,
        state: "waiting",
      };
      window.localStorage.setItem(key, JSON.stringify({ version: 3, drafts: [draft] }));
    },
    { key: "fieldclub.drafts" },
  );

  // They are sent the link and, told to, type the sender's address. They are signed in as the sender.
  await page.goto(link);
  const panel = page.getByRole("complementary", { name: "Signing in" });
  await panel.getByLabel("Your email address").fill(sender);
  await panel.getByRole("button", { name: "Sign me in" }).click();
  await expect(page.getByRole("dialog", { name: "Welcome to Open Antiquity" })).toBeVisible();

  // The draft was not taken over: it stays in this browser, nobody's, and nothing was sent.
  await page.waitForTimeout(500);
  const stored = await page.evaluate(() => JSON.parse(window.localStorage.getItem("fieldclub.drafts") ?? "null"));
  expect(stored.drafts).toEqual([
    expect.objectContaining({ id: "draft-left-here", owner: { signedOut: "visit-of-the-person-here" } }),
  ]);
});
