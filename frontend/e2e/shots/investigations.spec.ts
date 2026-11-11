import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { expect, type Page, test } from "@playwright/test";
import { AVEBURY_AREA, itemFinding, itemRecord } from "../../src/test/fixtures/investigations.js";
import { fakeSession, meFixture } from "../support/account.js";
import { ADA, GUS, MARY, serveInvestigations } from "../support/investigations.js";
import { apiRoute, stubNetwork } from "../support/network.js";

/**
 * Design-review screenshots of investigations: the lists, a notebook with
 * every kind of item, its area on the map, the dialogs, "Add to an
 * investigation" on the pages that offer it, and the loading, failed and
 * empty states, at desktop and phone width. Taken with
 * `pnpm shots e2e/shots/investigations.spec.ts`. They assert nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=14/51.4286/-1.8542/0/0&v=composite";

async function shoot(page: Page, name: string): Promise<void> {
  // Let a dialog's entrance and the sheet's slide finish.
  await page.waitForTimeout(450);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `investigations-${name}-${size?.width}x${size?.height}.png`) });
}

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

/** Put the phone sheet at a stop. Does nothing on a desktop. */
async function sheetTo(page: Page, stop: "peek" | "half" | "full"): Promise<void> {
  if (!isPhone(page)) return;
  const sheet = page.locator(".fc-sheet");
  const order = ["peek", "half", "full"];
  await sheet.getByRole("button", { name: /Press to resize/ }).focus();
  for (let i = 0; i < 3; i++) {
    const now = order.indexOf((await sheet.getAttribute("data-stop")) ?? "half");
    if (now === order.indexOf(stop)) return;
    await page.keyboard.press(now < order.indexOf(stop) ? "ArrowUp" : "ArrowDown");
  }
}

function never(): Promise<never> {
  return new Promise(() => {});
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("the lists", async ({ page }) => {
  const session = await fakeSession(page, meFixture());
  const fake = await serveInvestigations(page, { me: () => (session.current() ? ADA : null) });
  fake.seed({
    title: "Barrows of Overton Down",
    owner: ADA,
    visibility: "public",
    summary: "Every round barrow on the down, walked and checked against the 1888 map and the HER.",
    area: AVEBURY_AREA,
  });
  fake.seed({ title: "Hollow ways to the ford", owner: ADA, visibility: "unlisted" });
  const invited = fake.seed({ title: "Enclosures of the Kennet", owner: GUS, visibility: "unlisted" });
  fake.invite(invited, ADA, "editor");
  fake.seed({ title: "Lynchets above Fyfield", owner: MARY, visibility: "public", summary: "Strip lynchets." });

  await page.goto(`/investigations${VIEW}`);
  await expect(page.getByRole("link", { name: /Hollow ways to the ford/ })).toBeVisible();
  await shoot(page, "01-yours");
  await sheetTo(page, "full");
  await shoot(page, "02-yours-full");
  await page.getByRole("tab", { name: "Invitations" }).click();
  await expect(page.getByRole("button", { name: "Accept" })).toBeVisible();
  await shoot(page, "03-invitations");
  await page.getByRole("tab", { name: "Public" }).click();
  await page.getByRole("switch", { name: "Only those whose area is in view" }).click();
  await shoot(page, "04-public-in-view");
});

test("the lists signed out and empty", async ({ page }) => {
  await fakeSession(page, null);
  await page.route(apiRoute("/investigations"), (route) =>
    route.fulfill({ status: 200, contentType: "application/json", body: '{"items":[],"next_cursor":null}' }),
  );
  await page.goto(`/investigations${VIEW}`);
  await expect(page.getByText("No public investigations yet")).toBeVisible();
  await sheetTo(page, "full");
  await shoot(page, "05-signed-out-empty");
  await page.getByRole("tab", { name: "Yours" }).click();
  await shoot(page, "06-signed-out-yours");
});

test("the list loading", async ({ page }) => {
  await fakeSession(page, null);
  await page.route(apiRoute("/investigations"), () => never());
  await page.goto(`/investigations?list=public${VIEW}`);
  await sheetTo(page, "full");
  await shoot(page, "07-loading");
});

test("the list failed", async ({ page }) => {
  await fakeSession(page, null);
  await page.route(apiRoute("/investigations"), (route) => route.abort("connectionrefused"));
  await page.goto(`/investigations?list=public${VIEW}`);
  await expect(page.getByText("The list couldn't be loaded")).toBeVisible({ timeout: 15_000 });
  await sheetTo(page, "full");
  await shoot(page, "08-failed");
});

test("a notebook with every kind of item, its area on the map, at each stop of the sheet", async ({ page }) => {
  const session = await fakeSession(page, meFixture());
  const fake = await serveInvestigations(page, { me: () => (session.current() ? ADA : null) });
  const id = fake.seed(
    {
      title: "Barrows of Overton Down",
      owner: ADA,
      visibility: "public",
      area: AVEBURY_AREA,
      summary: "Every round barrow on the down, walked and checked against the 1888 map.",
      notes:
        "## What we're after\n\nWhich of the mounds on the **1888 six-inch map** are still there.\n\n- walk the north side\n- check the HER\n\nSee [Grinsell's list](https://example.org/grinsell).",
    },
    [
      {
        kind: "finding",
        finding: itemFinding().public_id,
        note: "The ditch shows best in *raking light* from the west.",
      },
      { kind: "record", record_id: itemRecord().id },
      {
        kind: "view",
        title: "From the south, raking light",
        view: { centre: [-1.8542, 51.4286], zoom: 16, layer: "raking", sun_azimuth: 270, sun_altitude: 15 },
      },
      {
        kind: "profile",
        title: "Across the north bank",
        profile: {
          line: {
            type: "LineString",
            coordinates: [
              [-1.855, 51.4286],
              [-1.8534, 51.4288],
            ],
          },
          samples: 120,
        },
      },
      {
        kind: "reference",
        title: "The Archaeology of Wessex",
        reference: { url: "https://example.org/wessex", citation: "Grinsell, L. V. 1958. London: Methuen. pp. 32–41." },
      },
      { kind: "note", note: "Ask the landowner before the next walk." },
    ],
  );
  fake.store.get(id)?.items.push({
    id: 999,
    kind: "finding",
    position: 6,
    title: null,
    note: null,
    unavailable: "withdrawn",
    added_by: MARY,
    created_at: "2026-11-10T10:00:00Z",
  });
  fake.invite(id, MARY, "editor", true);
  fake.invite(id, GUS, "viewer");
  await page.route(apiRoute("/terrain/profile"), (route) => {
    const samples = Array.from({ length: 120 }, (_, i) => ({
      distance_m: i,
      lon: -1.855 + i * 0.0000133,
      lat: 51.4286,
      elevation: 160 + Math.sin(i / 9) * 1.2 + (i > 50 && i < 70 ? 1.5 : 0),
    }));
    return route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ samples, length_m: 119, resolution_m: 1 }),
    });
  });

  await page.goto(`/i/${id}#m=12/51.3/-1.6/0/0&v=composite`);
  await expect(page.getByRole("heading", { name: "What we're after" })).toBeVisible();
  await sheetTo(page, "peek");
  await shoot(page, "10-notebook-peek");
  await sheetTo(page, "half");
  await shoot(page, "11-notebook-half");
  await sheetTo(page, "full");
  await shoot(page, "12-notebook-full");
  await page.locator(".fc-inv-items").scrollIntoViewIfNeeded();
  await shoot(page, "13-items");
  await page.locator(".fc-inv-item[data-kind='profile']").scrollIntoViewIfNeeded();
  await shoot(page, "14-items-profile");
  await page.getByRole("heading", { name: "Who works on it" }).scrollIntoViewIfNeeded();
  await shoot(page, "15-people");
  await page.getByRole("heading", { name: "Delete it" }).scrollIntoViewIfNeeded();
  await shoot(page, "16-settings");

  await page.getByRole("button", { name: "Edit the title, summary and notes" }).click();
  await shoot(page, "17-edit-dialog");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Add a reference" }).click();
  await shoot(page, "18-add-reference");
  await page.keyboard.press("Escape");
  await page
    .getByRole("button", { name: "Make it private" })
    .or(page.getByRole("button", { name: "Make it unlisted" }))
    .first()
    .click();
  await shoot(page, "19-visibility-dialog");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Delete this investigation" }).click();
  await shoot(page, "20-delete-dialog");
});

test("a notebook as a reader, as someone invited, loading, failed and missing", async ({ page }) => {
  const mary = meFixture({ id: 7, handle: MARY.handle, display_name: MARY.display_name });
  const session = await fakeSession(page, mary);
  const fake = await serveInvestigations(page, { me: () => (session.current() ? MARY : null) });
  const id = fake.seed({ title: "Enclosures of the Kennet", owner: GUS, visibility: "unlisted" }, [
    { kind: "note", note: "Start at the bridge." },
  ]);
  fake.invite(id, MARY, "editor");
  await page.goto(`/i/${id}${VIEW}`);
  await expect(page.getByRole("region", { name: "Your invitation" })).toBeVisible();
  await shoot(page, "21-invited");
  session.set(null);
  await page.goto(`/i/${id}${VIEW}`);
  await expect(page.getByText("Start at the bridge.")).toBeVisible();
  await shoot(page, "22-reader-signed-out");

  await page.route(/\/api\/v1\/investigations\/slow(?:\?|$)/, () => never());
  await page.goto(`/i/slow${VIEW}`);
  await shoot(page, "23-loading");
  await page.goto(`/i/missing${VIEW}`);
  await expect(page.getByText("There's no investigation at this address")).toBeVisible();
  await shoot(page, "24-missing");
  await page.route(/\/api\/v1\/investigations\/broken(?:\?|$)/, (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "internal", message: "Something went wrong on the server." } }),
    }),
  );
  await page.goto(`/i/broken${VIEW}`);
  await expect(page.getByText("This investigation couldn't be loaded")).toBeVisible({ timeout: 15_000 });
  await shoot(page, "25-failed");
});

test("adding from a finding, the layer panel and a height profile", async ({ page }) => {
  const session = await fakeSession(page, meFixture());
  const fake = await serveInvestigations(page, { me: () => (session.current() ? ADA : null) });
  fake.seed({ title: "Barrows of Overton Down", owner: ADA, visibility: "public" });
  fake.seed({ title: "Hollow ways to the ford", owner: ADA });
  await page.goto(`/f/${itemFinding().public_id}${VIEW}`);
  await page.getByRole("button", { name: "Add to an investigation" }).click();
  await shoot(page, "30-add-from-finding");
  await page.getByRole("radio", { name: "A new investigation" }).click();
  await shoot(page, "31-add-new");
  await page.keyboard.press("Escape");

  await page.goto(`/?panel=layers${VIEW}`);
  await page.getByRole("heading", { name: "Keep this view" }).scrollIntoViewIfNeeded();
  await shoot(page, "32-layer-panel");

  await page.route(apiRoute("/terrain/profile"), (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        samples: Array.from({ length: 60 }, (_, i) => ({
          distance_m: i * 2,
          lon: -1.855,
          lat: 51.4286,
          elevation: 160 + (i % 7),
        })),
        length_m: 118,
        resolution_m: 1,
      }),
    }),
  );
  await page.goto(`/profile?line=-1.855,51.4286,-1.8534,51.4288${VIEW}`);
  await expect(page.getByRole("button", { name: "Add to an investigation" })).toBeVisible();
  await sheetTo(page, "full");
  await shoot(page, "33-profile");
});
