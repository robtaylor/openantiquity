import type { Page } from "@playwright/test";
import { openMap } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";

/**
 * Joining, against the real backend: sign in through the development
 * sign-in, finish the welcome sheet, see the account page, sign out, sign in
 * again, and delete the account. Each project signs in as a handle of its
 * own, because both share one database.
 */

async function devSignIn(page: Page, handle: string): Promise<void> {
  const panel = page.getByRole("complementary", { name: "Account" });
  await panel.getByRole("button", { name: "Sign in" }).click();
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await sheet.getByLabel("Development sign-in").fill(handle);
  await sheet.getByRole("button", { name: "Sign in", exact: true }).click();
}

test("signs in, joins, signs out, signs in again and deletes the account", async ({ page }, testInfo) => {
  const handle = `E2e${testInfo.project.name}${Date.now() % 1_000_000}`;
  await openMap(page, "/account");
  const panel = page.getByRole("complementary", { name: "Account" });
  await expect(panel.getByRole("heading", { name: "You're not signed in" })).toBeVisible();

  // First sign-in: the welcome step is owed.
  await devSignIn(page, handle);
  const welcome = page.getByRole("dialog", { name: "Welcome to Open Antiquity" });
  await expect(welcome).toBeVisible();
  await expect(welcome.getByLabel("Your name on the map")).toHaveValue(handle);
  await welcome.getByRole("radio", { name: "18 or over" }).click();
  await welcome.getByRole("checkbox", { name: "I accept the contributor terms" }).check();
  await welcome.getByRole("button", { name: "Join Open Antiquity" }).click();
  await expect(welcome).toBeHidden();

  // The account page shows them, and the server agrees.
  await expect(panel.getByText(`@${handle}`)).toBeVisible();
  await expect(panel.getByRole("button", { name: "Finish joining" })).toHaveCount(0);
  const me = await page.request.get("/api/v1/auth/me");
  expect(me.status()).toBe(200);
  expect(await me.json()).toMatchObject({ handle, needs_welcome: false, age_band: "18_plus" });

  // A bio can be written now the welcome step is done.
  await panel.getByLabel("About you").fill("Walks the Ridgeway on Sundays.");
  await panel.getByRole("button", { name: "Save changes" }).click();
  await expect(page.getByText("Your details are saved.")).toBeVisible();

  await panel.getByRole("button", { name: "Sign out" }).click();
  await expect(panel.getByRole("heading", { name: "You're not signed in" })).toBeVisible();
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);

  // Back again: no welcome this time, and the bio is still there.
  await devSignIn(page, handle);
  await expect(panel.getByText(`@${handle}`)).toBeVisible();
  await expect(welcome).toBeHidden();
  await expect(panel.getByLabel("About you")).toHaveValue("Walks the Ridgeway on Sundays.");

  await panel.getByRole("button", { name: "Delete my account" }).click();
  const dialog = page.getByRole("dialog", { name: "Delete your account?" });
  await expect(dialog).toContainText("credited to “Former member”");
  await dialog.getByRole("button", { name: "Delete my account" }).click();
  await expect(panel.getByRole("heading", { name: "You're not signed in" })).toBeVisible();
  await expect(page.getByText("Your account has been deleted.")).toBeVisible();
  expect((await page.request.get("/api/v1/auth/me")).status()).toBe(401);
});
