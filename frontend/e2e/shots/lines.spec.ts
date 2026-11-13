import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import type { FindingDetail } from "../../src/features/finding/types.js";
import type { FindingFeature } from "../../src/features/findings/types.js";
import { finderView, pageFixture } from "../../src/test/fixtures/findingPage.js";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindingPage } from "../support/findingPage.js";
import { fakeFindings } from "../support/findings.js";
import { apiRoute, stubNetwork } from "../support/network.js";

/**
 * Screenshots of lines and shapes: changing a saved finding's shape, what
 * the finding page says was added, and the chooser between overlapping
 * findings, at desktop and phone width. They stub every tile and assert
 * nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const CENTRE = { lon: -1.8542, lat: 51.4286 };
const VIEW = `#m=15/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite`;
const FINDER = meWith({ handle: "QuietBarrow42", display_name: "Ada Lovelace" });

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(500);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `lines-${name}-${size?.width}x${size?.height}.png`) });
}

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

const ROAD: Array<[number, number]> = [
  [-1.8572, 51.4276],
  [-1.8556, 51.4283],
  [-1.8542, 51.4286],
  [-1.8528, 51.4292],
];

/** The finder's line, with second looks given on its first three points and 300 m added since. */
function road(): FindingDetail {
  const base = finderView({ title: "Hollow way up the down", feature_class: "trackway" });
  return {
    ...base,
    location: {
      ...base.location,
      lon: ROAD[1]?.[0] ?? CENTRE.lon,
      lat: ROAD[1]?.[1] ?? CENTRE.lat,
      outline: { type: "LineString", coordinates: ROAD },
      path: {
        closed: false,
        curve: "catmull-rom-centripetal-1",
        points: ROAD.map(([lon, lat], index) => ({ lon, lat, kind: index === 1 ? "smooth" : "corner" })),
      },
      shape: {
        kind: "line",
        length_m: 330,
        revision: 2,
        extent: [-1.8572, 51.4276, -1.8528, 51.4292],
        changes: [
          { kind: "drawn", on: "2026-11-02" },
          {
            kind: "extended",
            on: "2026-11-12",
            added_length_m: 300,
            added_view: { lon: -1.853, lat: 51.429, zoom: 17 },
          },
        ],
        added_since_looked_m: 300,
        added_view: { lon: -1.853, lat: 51.429, zoom: 16 },
        looked_at: { type: "LineString", coordinates: ROAD.slice(0, 3) },
      },
    },
  };
}

test("changing a saved finding's shape", async ({ page }) => {
  const finding = road();
  await fakeSession(page, FINDER);
  await fakeFindingPage(page, finding, { me: FINDER });
  await openMap(page, `/f/${finding.public_id}${VIEW}`);
  const findingPanel = page.getByRole("complementary", { name: finding.title });
  await findingPanel.getByRole("region", { name: "Added since the last second look" }).scrollIntoViewIfNeeded();
  await shoot(page, "30-added-since");

  await findingPanel.getByRole("button", { name: "Change the shape" }).scrollIntoViewIfNeeded();
  await findingPanel.getByRole("button", { name: "Change the shape" }).click();
  const panel = page.getByRole("complementary", { name: "Change the shape" });
  await panel.waitFor();
  await page.getByRole("button", { name: /^Point 4 of 4/ }).waitFor();
  await shoot(page, "31-change-shape");

  await page.getByRole("button", { name: /^Point 4 of 4/ }).click();
  await page.getByRole("button", { name: "Continue from this end" }).first().click();
  await page.getByRole("button", { name: "Done" }).first().click();
  const end = await page.getByRole("button", { name: /^Point 4 of 4/ }).boundingBox();
  if (end) {
    const at = { x: end.x + end.width / 2 + 60, y: end.y + end.height / 2 - 30 };
    if (isPhone(page)) await page.touchscreen.tap(at.x, at.y);
    else await page.mouse.click(at.x, at.y);
  }
  await shoot(page, "32-change-shape-drawing");

  await page.route(apiRoute(`/findings/${finding.public_id}`), (route) =>
    route.request().method() === "PATCH"
      ? route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "looked_at_moved",
              message:
                "Only 60% of what others looked at would be left within 250 m of it, and three-quarters has to stay. Withdraw it and mark it again to start afresh.",
            },
          }),
        })
      : route.fallback(),
  );
  await page.getByRole("button", { name: "Finish" }).first().click();
  await panel.getByRole("button", { name: "Save the shape" }).click();
  await panel.getByRole("alert").waitFor();
  await shoot(page, "33-change-shape-refused");
});

/** A line finding as the map's box answers it, with its anchor and its shape. */
function lineFeature(publicId: string, title: string, line: Array<[number, number]>, tier: string): FindingFeature {
  const anchor = line[0] ?? [CENTRE.lon, CENTRE.lat];
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: anchor },
    properties: {
      public_id: publicId,
      tier,
      state: "open",
      obscured: false,
      sensitivity: "open",
      title,
      feature_class: "road",
      shape: { type: "LineString", coordinates: line },
    },
  };
}

test("the chooser between crossing roads", async ({ page }) => {
  await fakeFindings(page, [
    lineFeature(
      "f-road-east",
      "Roman road east of the henge",
      [
        [-1.8592, CENTRE.lat],
        [-1.8492, CENTRE.lat],
      ],
      "probable",
    ),
    lineFeature(
      "f-road-north",
      "Hollow way to the ford",
      [
        [CENTRE.lon, 51.4256],
        [CENTRE.lon, 51.4316],
      ],
      "seen",
    ),
  ]);
  await openMap(page, `/?panel=none${VIEW}`);
  await page.waitForTimeout(800);
  const size = page.viewportSize() ?? { width: 1280, height: 800 };
  const at = { x: size.width / 2, y: size.height / 2 };
  if (isPhone(page)) await page.touchscreen.tap(at.x, at.y);
  else await page.mouse.click(at.x, at.y);
  await page.getByRole("dialog", { name: /findings here$/ }).waitFor();
  await shoot(page, "40-chooser");
  await page.keyboard.press("ArrowDown");
  await shoot(page, "41-chooser-second-focused");
  await page.keyboard.press("Escape");
  if (!isPhone(page)) {
    await page.mouse.move(at.x + 2, at.y + 1);
    await page.mouse.move(at.x, at.y);
    await shoot(page, "42-hover-hint");
  }
});

test("a protected line seen signed out", async ({ page }) => {
  const hidden = pageFixture();
  await fakeFindings(page, [
    {
      type: "Feature",
      geometry: { type: "Point", coordinates: [CENTRE.lon, CENTRE.lat] },
      properties: {
        public_id: hidden.public_id,
        tier: "seen",
        state: "open",
        obscured: true,
        sensitivity: "protected",
        square: "SU1069",
        title: "Linear bank or ditch in SU 10 69",
        feature_class: "linear",
      },
    },
  ]);
  await openMap(page, `/?panel=none${VIEW}`);
  await page.waitForTimeout(800);
  await shoot(page, "50-protected-line-signed-out");
});
