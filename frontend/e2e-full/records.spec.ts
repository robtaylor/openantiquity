import { openMap } from "../e2e/support/app.js";
import { seedRecords } from "./support/env.js";
import { expect, test } from "./support/fixtures.js";

/**
 * The record index and the search box against the real API, where fixture
 * mode can't catch the two sides disagreeing: the record search's repeated
 * filters, a record's page and its credit, and the search box's places and
 * records with the credits for them. `support/records.py` seeds the rows.
 */

test.beforeAll(() => {
  seedRecords();
});

test("searches the records by two kinds and a source, and opens a record with its credit", async ({ page }) => {
  await openMap(page, "/records?q=barrow&scope=everywhere&category=designation&category=monument");
  const panel = page.getByRole("complementary", { name: "Search the records" });
  await expect(panel.getByRole("searchbox", { name: "Words to look for" })).toHaveValue("barrow");

  // Two kinds: the designation and the monument record, and not the find.
  await expect(panel.getByRole("link", { name: "Barrow cemetery on Overton Hill" })).toBeVisible();
  await expect(panel.getByRole("link", { name: "Long barrow at East Kennett" })).toBeVisible();
  await expect(panel.getByRole("link", { name: "Barrow ditch finds" })).toHaveCount(0);

  // And one source on top: only the designation is left.
  await panel.getByLabel("Source").selectOption({ label: "E2E designations" });
  await expect(page).toHaveURL(/[?&]source=e2e-designations\b/);
  await expect(panel.getByRole("link", { name: "Long barrow at East Kennett" })).toHaveCount(0);
  const result = panel.getByRole("link", { name: "Barrow cemetery on Overton Hill" });
  await expect(result).toBeVisible();
  await expect(panel.getByText("From E2E designations · OGL v3.0")).toBeVisible();

  await result.click();
  const record = page.getByRole("complementary", { name: "Barrow cemetery on Overton Hill" });
  await expect(record.getByText("E2E designations", { exact: true })).toBeVisible();
  await expect(record.getByText("© E2E Heritage 2026")).toBeVisible();
  await expect(record.getByRole("link", { name: "OGL v3.0" })).toHaveAttribute("href", /open-government-licence/);

  // Back brings the same search back from the address.
  await page.goBack();
  await expect(panel.getByRole("link", { name: "Barrow cemetery on Overton Hill" })).toBeVisible();
  await expect(panel.getByLabel("Source")).toHaveValue("e2e-designations");
});

test("finds a place and a record from the search box, and credits where the names come from", async ({ page }) => {
  await openMap(page);
  const box = page.getByRole("combobox", { name: /Search for a place/ });
  await box.fill("Kennettbury");
  const list = page.getByRole("listbox", { name: "Search results" });
  await expect(list.getByRole("option", { name: /^Kennettbury/ })).toBeVisible();
  const credits = page.getByRole("list", { name: "Where these names come from" });
  await expect(credits).toContainText("E2E place names · OGL v3.0");
  const gazetteer = credits.getByRole("listitem").filter({ hasText: "E2E place names" });
  await expect(gazetteer.getByRole("link", { name: "OGL v3.0" })).toHaveAttribute("href", /open-government-licence/);

  await box.fill("Long barrow at East Kennett");
  const option = list.getByRole("option", { name: /^Long barrow at East Kennett/ });
  await expect(option).toBeVisible();
  await expect(credits).toContainText("E2E monument records · OGL v3.0");
  await option.click();
  await expect(page.getByRole("complementary", { name: "Long barrow at East Kennett" })).toBeVisible();
  await expect(page).toHaveURL(/\/r\/\d+/);
});
