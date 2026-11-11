import { openMap } from "../e2e/support/app.js";
import { DRAFTS_STORAGE_KEY } from "../src/features/drafts/store.js";
import { expect, test } from "./support/fixtures.js";

/**
 * The exit test for accounts (docs/plans): mark a finding signed out, sign
 * in through the development sign-in, and find the draft saved as a real
 * finding at the same place, once, against the real backend. Each project
 * signs in as a handle of its own, because both share one database.
 */

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";

test("saves a finding marked signed out as a real finding at the same place, once, after sign-in", async ({
  page,
}, testInfo) => {
  const handle = `Mark${testInfo.project.name}${Date.now() % 1_000_000}`;
  await openMap(page, `/mark${VIEW}`);
  await page.getByRole("button", { name: "Place it here" }).click();
  const panel = page.getByRole("complementary", { name: "Mark a finding" });
  await panel.getByRole("radio", { name: "Enclosure" }).click();
  await panel.getByLabel("Note (optional)").fill("A faint ring with a gap on the east side.");
  await panel.getByRole("button", { name: "Save finding" }).click();

  // Kept as a draft, with nothing sent, while the sign-in sheet is open over the form.
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await expect(sheet).toBeVisible();
  const stored = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "{}"), DRAFTS_STORAGE_KEY);
  expect(stored.drafts).toHaveLength(1);
  const [lon, lat] = stored.drafts[0].data.point as [number, number];

  await sheet.getByLabel("Development sign-in").fill(handle);
  await sheet.getByRole("button", { name: "Sign in", exact: true }).click();
  const welcome = page.getByRole("dialog", { name: "Welcome to Open Antiquity" });
  await welcome.getByRole("radio", { name: "18 or over" }).click();
  await welcome.getByRole("checkbox", { name: "I accept the contributor terms" }).check();
  await welcome.getByRole("button", { name: "Join Open Antiquity" }).click();

  // Saved without anything typed again, and its page opens.
  await expect(page).toHaveURL(/\/f\/[^/#]+#/);
  await expect(page.getByText("Your draft is saved.")).toBeVisible();
  const publicId = decodeURIComponent(new URL(page.url()).pathname.split("/")[2] ?? "");

  const response = await page.request.get(`/api/v1/findings/${publicId}`);
  expect(response.status()).toBe(200);
  const finding = await response.json();
  expect(finding).toMatchObject({
    feature_class: "enclosure",
    description: "A faint ring with a gap on the east side.",
    author: { handle },
    tier: "spotted",
    view_state: { layer: "composite", zoom: 15 },
  });
  expect(finding.title).toMatch(/^Enclosure in SU \d{2} \d{2}$/);
  expect(finding.location.obscured).toBe(false);
  expect(finding.location.lon).toBeCloseTo(lon, 6);
  expect(finding.location.lat).toBeCloseTo(lat, 6);

  // Exactly once, and the draft is gone from the browser.
  await page.waitForTimeout(500);
  const mine = await (await page.request.get(`/api/v1/findings?author=${handle}`)).json();
  expect(mine.items).toHaveLength(1);
  const left = await page.evaluate((key) => JSON.parse(localStorage.getItem(key) ?? "{}"), DRAFTS_STORAGE_KEY);
  expect(left.drafts).toEqual([]);
});
