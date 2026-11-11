import type { Locator, Page } from "@playwright/test";
import { openMap } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";
import { join } from "./support/people.js";

/**
 * Investigations against the real backend, where fixture mode can't catch
 * the two sides disagreeing: start one, add a finding from its page and a
 * note, reorder them, publish it, and see it listed once signed out. Each
 * project uses handles and titles of its own, because both share one
 * database.
 */

const AVEBURY = { lon: -1.8542, lat: 51.4286 };
const VIEW = "#m=16/51.4286/-1.8542/0/0&v=composite";

function panel(page: Page, title: string): Locator {
  return page.getByRole("complementary", { name: title });
}

/** On a phone, open the sheet the whole way, so what's below the fold can be reached. */
async function openSheet(page: Page): Promise<void> {
  if ((page.viewportSize()?.width ?? 0) >= 720) return;
  const sheet = page.locator(".fc-sheet");
  await sheet.getByRole("button", { name: /Press to resize/ }).focus();
  while ((await sheet.getAttribute("data-stop")) !== "full") await page.keyboard.press("ArrowUp");
}

test("starts an investigation, adds a finding and a note, reorders them, publishes it and sees it listed signed out", async ({
  page,
}, testInfo) => {
  const tag = `${testInfo.project.name.slice(0, 1)}${Date.now() % 1_000_000}`;
  const title = `Barrows ${tag}`;
  await join(page, `Inv${tag}`);
  const created = await page.request.post("/api/v1/findings", {
    headers: { "X-FieldClub-Client": "web" },
    data: {
      location: { type: "Point", coordinates: [AVEBURY.lon, AVEBURY.lat] },
      feature_class: "enclosure",
      title: `Enclosure ${tag}`,
      view_state: { layer: "composite", zoom: 16 },
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const { public_id: findingId } = (await created.json()) as { public_id: string };

  // Start it from the list: a title and nothing else.
  await openMap(page, `/investigations${VIEW}`);
  const list = panel(page, "Investigations");
  await list.getByRole("button", { name: "Start an investigation" }).click();
  await list.getByLabel("Start an investigation").fill(title);
  await list.getByRole("button", { name: "Start" }).click();
  const notebook = panel(page, title);
  await expect(notebook.getByText("Private", { exact: true })).toBeVisible();
  const notebookUrl = new URL(page.url()).pathname;
  expect(notebookUrl).toMatch(/^\/i\//);

  // A finding, from its own page.
  await page.goto(`/f/${findingId}${VIEW}`);
  const finding = panel(page, `Enclosure ${tag}`);
  await finding.getByRole("button", { name: "Add to an investigation" }).click();
  const chooser = page.getByRole("dialog", { name: "Add to an investigation" });
  await chooser.getByRole("radio", { name: new RegExp(title) }).check();
  await chooser.getByRole("button", { name: "Add it" }).click();
  await expect(page.getByText(`Added to “${title}”.`)).toBeVisible();

  // A note, on the notebook itself.
  await page.goto(`${notebookUrl}${VIEW}`);
  await notebook.getByRole("button", { name: "Add a note" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a note" });
  await dialog.getByLabel("Note").fill("Walk the **north** side first.");
  await dialog.getByRole("button", { name: "Add the note" }).click();
  const items = notebook.locator(".fc-inv-items > li");
  await expect(items).toHaveCount(2);
  await expect(items.nth(0)).toContainText(`Enclosure ${tag}`);
  await expect(items.nth(1)).not.toHaveAttribute("aria-busy", "true");

  // The note goes first, and the server keeps that order.
  await notebook.getByRole("button", { name: "Move “Walk the north side first.” up" }).click();
  await expect(items.nth(0)).toContainText("Walk the north side first.");
  await expect
    .poll(async () => {
      const answer = await page.request.get(`/api/v1/investigations${notebookUrl.slice(2)}/items`);
      return ((await answer.json()) as { items: Array<{ kind: string }> }).items.map((item) => item.kind);
    })
    .toEqual(["note", "finding"]);
  await page.reload();
  await expect(items.nth(0)).toContainText("Walk the north side first.");

  // Publishing, said in one sentence first.
  await openSheet(page);
  await notebook.getByRole("button", { name: "Publish it" }).click();
  await page
    .getByRole("dialog", { name: "Publish this investigation?" })
    .getByRole("button", { name: "Publish it" })
    .click();
  await expect(notebook.getByText("Public.", { exact: true })).toBeVisible();

  // Signed out, it is in the public list.
  const out = await page.request.post("/api/v1/auth/logout", { headers: { "X-FieldClub-Client": "web" } });
  expect(out.ok()).toBe(true);
  await openMap(page, `/investigations?list=public${VIEW}`);
  await expect(panel(page, "Investigations").getByRole("link", { name: new RegExp(title) })).toBeVisible();
  await page.getByRole("link", { name: new RegExp(title) }).click();
  await expect(panel(page, title).locator(".fc-inv-items > li")).toHaveCount(2);
});
