import { expect, type Page, test } from "@playwright/test";
import type { FindingDetail } from "../src/features/finding/types.js";
import { GUIDE_FOLDED_KEY } from "../src/features/mark/guideRows.js";
import { finderView } from "../src/test/fixtures/findingPage.js";
import { fakeSession, meWith } from "./support/account.js";
import { type Box, openMap, overlaps } from "./support/app.js";
import { fakeFindingPage } from "./support/findingPage.js";
import { stubNetwork } from "./support/network.js";

/**
 * Lines and shapes in fixture mode: where "Change the shape" puts a saved
 * path. Every handle has to land where a finger or a mouse can take it,
 * clear of the drawing guide in the search box's place, folded or not, the
 * map's buttons, the drawing bar, the panel or the sheet, and the status
 * and tab bars.
 */

const CENTRE = { lon: -1.8542, lat: 51.4286 };
const VIEW = `#m=15/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite`;
const FINDER = meWith({ handle: "QuietBarrow42", display_name: "Ada Lovelace" });

/** The shapes framed: a line rising to the north-east, one running north to south, and a wide closed one. */
const SHAPES: Record<string, { closed: boolean; points: Array<[number, number]> }> = {
  "a line rising to the north-east": {
    closed: false,
    points: [
      [-1.8572, 51.4276],
      [-1.8556, 51.4283],
      [-1.8542, 51.4286],
      [-1.8528, 51.4292],
    ],
  },
  "a line running north to south": {
    closed: false,
    points: [
      [-1.8542, 51.4246],
      [-1.8545, 51.4286],
      [-1.8541, 51.4326],
    ],
  },
  "a wide closed shape": {
    closed: true,
    points: [
      [-1.8612, 51.4276],
      [-1.8472, 51.4276],
      [-1.8472, 51.4296],
      [-1.8612, 51.4296],
    ],
  },
};

function shapeFinding(points: Array<[number, number]>, closed: boolean): FindingDetail {
  const base = finderView({ title: "Hollow way up the down", feature_class: "trackway" });
  const lons = points.map(([lon]) => lon);
  const lats = points.map(([, lat]) => lat);
  const ring = closed ? [...points, points[0] as [number, number]] : points;
  return {
    ...base,
    location: {
      ...base.location,
      lon: points[1]?.[0] ?? CENTRE.lon,
      lat: points[1]?.[1] ?? CENTRE.lat,
      outline: closed ? { type: "Polygon", coordinates: [ring] } : { type: "LineString", coordinates: ring },
      path: {
        closed,
        curve: "catmull-rom-centripetal-1",
        points: points.map(([lon, lat]) => ({ lon, lat, kind: "corner" })),
      },
      shape: {
        ...base.location.shape,
        kind: closed ? "area" : "line",
        length_m: 400,
        revision: 1,
        extent: [Math.min(...lons), Math.min(...lats), Math.max(...lons), Math.max(...lats)],
        changes: [{ kind: "drawn", on: "2026-11-02" }],
      },
    },
  };
}

/** Every handle's box, once the map has stopped moving them for half a second. */
async function settledHandles(page: Page, count: number): Promise<Box[]> {
  const handles = page.locator(".fc-path-handle");
  await expect(handles).toHaveCount(count);
  let last = "";
  for (let tries = 0; tries < 40; tries++) {
    const boxes = await handles.evaluateAll((elements) =>
      elements.map((element) => {
        const { x, y, width, height } = element.getBoundingClientRect();
        return { x, y, width, height };
      }),
    );
    const now = JSON.stringify(boxes.map(({ x, y }) => [Math.round(x), Math.round(y)]));
    if (now === last) return boxes;
    last = now;
    await page.waitForTimeout(500);
  }
  throw new Error("The handles never stopped moving.");
}

/** The boxes of everything a handle mustn't sit under, by name. */
async function coveringBoxes(page: Page): Promise<Record<string, Box>> {
  return page.evaluate(() => {
    const named: Record<string, string> = {
      "the search box or the drawing guide": ".fc-stage__search",
      "the map's buttons": ".fc-stage__controls",
      "the drawing bar": ".fc-mark-float",
      "the panel": ".fc-panel",
      "the status bar": ".fc-shell__status",
      "the tab bar": ".fc-tabbar",
      "the mode rail": ".fc-rail",
    };
    const out: Record<string, { x: number; y: number; width: number; height: number }> = {};
    for (const [name, selector] of Object.entries(named)) {
      for (const element of Array.from(document.querySelectorAll(selector))) {
        const { x, y, width, height } = element.getBoundingClientRect();
        if (width > 0 && height > 0) out[`${name} (${selector})`] = { x, y, width, height };
      }
    }
    return out;
  });
}

for (const [name, shape] of Object.entries(SHAPES)) {
  for (const guide of ["unfolded", "folded"] as const) {
    test(`"Change the shape" frames ${name} with every handle clear of the controls, the guide ${guide}`, async ({
      page,
    }) => {
      await stubNetwork(page);
      if (guide === "folded") {
        await page.addInitScript((key) => window.localStorage.setItem(key, "folded"), GUIDE_FOLDED_KEY);
      }
      const finding = shapeFinding(shape.points, shape.closed);
      await fakeSession(page, FINDER);
      await fakeFindingPage(page, finding, { me: FINDER });
      await openMap(page, `/f/${finding.public_id}${VIEW}`);
      const findingPanel = page.getByRole("complementary", { name: finding.title });
      await findingPanel.getByRole("button", { name: "Change the shape" }).click();
      await page.getByRole("complementary", { name: "Change the shape" }).waitFor();

      const card = page.getByRole("region", { name: "How to draw" });
      await expect(card.getByRole("list")).toBeVisible({ visible: guide === "unfolded" });
      await expectHandlesClear(page, shape.points.length);
    });
  }
}

/**
 * Every handle, or those of the points named (counting from 1), is on
 * screen, clear of every control, and the topmost thing at its middle.
 */
async function expectHandlesClear(page: Page, count: number, only?: number[]): Promise<void> {
  const settled = await settledHandles(page, count);
  const chosen = (index: number): boolean => only === undefined || only.includes(index + 1);
  const handles = settled.map((box, index) => (chosen(index) ? box : null));
  const covers = await coveringBoxes(page);
  expect(Object.keys(covers).length, "found the controls to measure against").toBeGreaterThan(2);
  const viewport = page.viewportSize() ?? { width: 0, height: 0 };
  const problems: string[] = [];
  handles.forEach((handle, index) => {
    if (handle === null) return;
    const inside =
      handle.x >= 0 &&
      handle.y >= 0 &&
      handle.x + handle.width <= viewport.width &&
      handle.y + handle.height <= viewport.height;
    if (!inside) problems.push(`point ${index + 1} is off the screen`);
    for (const [what, box] of Object.entries(covers)) {
      if (overlaps(handle, box)) problems.push(`point ${index + 1} is under ${what}`);
    }
  });
  expect(problems).toEqual([]);

  // And the topmost thing at each handle's middle is the handle itself.
  const onTop = await page.locator(".fc-path-handle").evaluateAll(
    (elements, wanted) =>
      elements
        .filter((_, index) => wanted === null || wanted.includes(index + 1))
        .map((element) => {
          const { x, y, width, height } = element.getBoundingClientRect();
          const top = document.elementFromPoint(x + width / 2, y + height / 2);
          return top !== null && element.contains(top);
        }),
    only ?? null,
  );
  expect(onTop).toEqual(onTop.map(() => true));
}

test('"Continue from this end" brings the end clear of the controls and the drawing bar', async ({ page }) => {
  await stubNetwork(page);
  const shape = SHAPES["a line rising to the north-east"];
  if (!shape) throw new Error("no such shape");
  const finding = shapeFinding(shape.points, shape.closed);
  await fakeSession(page, FINDER);
  await fakeFindingPage(page, finding, { me: FINDER });
  await openMap(page, `/f/${finding.public_id}${VIEW}`);
  await page
    .getByRole("complementary", { name: finding.title })
    .getByRole("button", { name: "Change the shape" })
    .click();
  await expectHandlesClear(page, 4);
  await page.getByRole("button", { name: /^Point 1 of 4/ }).click();
  await page.getByRole("button", { name: "Continue from this end" }).first().click();
  await page.getByRole("button", { name: "Done" }).first().click();
  await expectHandlesClear(page, 4, [1]);
});
