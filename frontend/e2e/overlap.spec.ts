import type { Page } from "@playwright/test";
import type { FindingFeature, FindingShape } from "../src/features/findings/types.js";
import { offset } from "../src/test/fixtures/findings.js";
import { openMap, tabTo } from "./support/app.js";
import { fakeFindings } from "./support/findings.js";
import { expect, test } from "./support/fixtures.js";

/**
 * Picking one of overlapping findings in a real browser, in fixture mode
 * (Decision 0031): areas are picked by their edges, markers beat lines and
 * lines beat area edges, two alike open the chooser, a finger reaches
 * further than a mouse, and the Explore list reaches every finding by
 * keyboard. Shapes clipped into several parts draw and pick like whole
 * ones. Every place is in metres from the view's centre, at zoom 15, where
 * a pixel is about 1.5 m.
 */

const CENTRE = { lon: -1.8542, lat: 51.4286 };
const ZOOM = 15;
const VIEW = `#m=${ZOOM}/${CENTRE.lat}/${CENTRE.lon}/0/0&v=composite`;

type Metres = [number, number];

function at([east, north]: Metres): [number, number] {
  const { lon, lat } = offset(east, north, CENTRE);
  return [lon, lat];
}

function finding(
  publicId: string,
  title: string,
  anchor: Metres,
  shape: FindingShape | null,
  featureClass: string,
): FindingFeature {
  return {
    type: "Feature",
    geometry: { type: "Point", coordinates: at(anchor) },
    properties: {
      public_id: publicId,
      tier: "seen",
      state: "open",
      obscured: false,
      sensitivity: "open",
      title,
      feature_class: featureClass,
      ...(shape ? { shape } : {}),
    },
  };
}

function line(points: Metres[]): FindingShape {
  return { type: "LineString", coordinates: points.map(at) };
}

function ring(west: number, south: number, east: number, north: number): Array<[number, number]> {
  return [at([west, south]), at([east, south]), at([east, north]), at([west, north]), at([west, south])];
}

/**
 * A field system, a pit inside it, a road through its east edge, and a
 * hollow way crossing the road. The road is 280 m and the hollow way 350 m,
 * alike, so neither is clearly the smaller.
 */
const FIELDS = finding(
  "f-fields",
  "Field system on the down",
  [-120, 40],
  { type: "Polygon", coordinates: [ring(-130, -150, 40, 50)] },
  "field_system",
);
const PIT = finding("f-pit", "Pit in the fields", [-60, 0], null, "pit");
const ROAD = finding(
  "f-road",
  "Roman road over the down",
  [-140, -60],
  line([
    [-140, -60],
    [140, -60],
  ]),
  "road",
);
const HOLLOW_WAY = finding(
  "f-hollow",
  "Hollow way to the ford",
  [100, 150],
  line([
    [100, -200],
    [100, 150],
  ]),
  "trackway",
);
const OVERLAPPING = [FIELDS, PIT, ROAD, HOLLOW_WAY];

/** Where a place falls on the page, with the map centred on `CENTRE`, north up, filling the window. */
function onScreen(page: Page, metres: Metres): { x: number; y: number } {
  const size = page.viewportSize() ?? { width: 0, height: 0 };
  const world = 512 * 2 ** ZOOM;
  const mercator = ([lon, lat]: [number, number]) => ({
    x: ((lon + 180) / 360) * world,
    y: ((1 - Math.asinh(Math.tan((lat * Math.PI) / 180)) / Math.PI) / 2) * world,
  });
  const centre = mercator([CENTRE.lon, CENTRE.lat]);
  const point = mercator(at(metres));
  return { x: size.width / 2 + point.x - centre.x, y: size.height / 2 + point.y - centre.y };
}

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

/** A tap where the project has a finger, a click where it has a mouse. */
async function press(page: Page, metres: Metres): Promise<void> {
  const { x, y } = onScreen(page, metres);
  if (isPhone(page)) await page.touchscreen.tap(x, y);
  else await page.mouse.click(x, y);
}

async function openOverlapping(page: Page, features = OVERLAPPING): Promise<void> {
  await fakeFindings(page, features);
  await openMap(page, `/?panel=none${VIEW}`);
  await markersDrawn(page, features.length);
}

/** Each finding's anchor marker is drawn, so its shapes have arrived with it. */
async function markersDrawn(page: Page, count: number): Promise<void> {
  await expect
    .poll(() =>
      page.evaluate(async (count) => {
        // The dev server's own copy of the module, so the same map the page draws.
        const url = "/src/map/mainMap.ts";
        const { useMainMapStore } = (await import(/* @vite-ignore */ url)) as typeof import("../src/map/mainMap.js");
        const map = useMainMapStore.getState().map;
        if (!map) return false;
        const ids = new Set(
          map.queryRenderedFeatures({ layers: ["findings-points"] }).map((feature) => feature.properties?.public_id),
        );
        return ids.size === count;
      }, count),
    )
    .toBe(true);
}

async function expectOpened(page: Page, publicId: string): Promise<void> {
  await expect(page).toHaveURL(new RegExp(`/f/${publicId}(#|$)`));
}

async function expectNothingOpened(page: Page): Promise<void> {
  await page.waitForTimeout(400);
  expect(new URL(page.url()).pathname).toBe("/");
  await expect(page.getByRole("dialog")).toHaveCount(0);
}

test("a point inside an area opens the point", async ({ page }) => {
  await openOverlapping(page);
  await press(page, [-60, 0]);
  await expectOpened(page, "f-pit");
});

test("a tap inside an area away from its edge opens nothing of it", async ({ page }) => {
  await openOverlapping(page);
  await press(page, [-90, -100]);
  await expectNothingOpened(page);
});

test("an area opens from its edge", async ({ page }) => {
  await openOverlapping(page);
  await press(page, [-50, -150]);
  await expectOpened(page, "f-fields");
});

test("a road through a field system's edge opens the road", async ({ page }) => {
  await openOverlapping(page);
  await press(page, [40, -60]);
  await expectOpened(page, "f-road");
});

test("a tap where two roads cross shows the chooser with both, and Escape closes it", async ({ page }) => {
  await openOverlapping(page);
  await press(page, [100, -60]);
  const chooser = page.getByRole("dialog", { name: "2 findings here" });
  await expect(chooser).toBeVisible();
  await expect(chooser.getByRole("button", { name: /^Roman road over the down,/ })).toBeVisible();
  await expect(chooser.getByRole("button", { name: /^Hollow way to the ford,/ })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(chooser).toHaveCount(0);
  expect(new URL(page.url()).pathname).toBe("/");
});

/** Every click on the map's canvas from now on, by the kind of pointer the browser says made it. */
async function recordClicks(page: Page): Promise<() => Promise<string[]>> {
  await page.evaluate(() => {
    const seen: string[] = [];
    (window as unknown as { clicksSeen: string[] }).clicksSeen = seen;
    document.querySelector(".fc-map__pane--main canvas")?.addEventListener(
      "click",
      (event) => {
        seen.push(event instanceof PointerEvent ? event.pointerType : "not a pointer event");
      },
      { capture: true },
    );
  });
  return () => page.evaluate(() => [...(window as unknown as { clicksSeen: string[] }).clicksSeen]);
}

/** 16 m east of the hollow way: about 11 px, past a mouse's 6 px reach and inside a finger's 16 px. */
const BESIDE_THE_WAY: Metres = [116, 100];

test("a finger's tap beside a line opens it where a mouse's click at the same spot opens nothing", async ({
  page,
  browser,
}) => {
  await openOverlapping(page);
  const clicks = await recordClicks(page);
  const { x, y } = onScreen(page, BESIDE_THE_WAY);

  // The browser says which pointer made each click, and the reach follows it.
  await page.mouse.click(x, y);
  await expectNothingOpened(page);
  expect(await clicks()).toEqual(["mouse"]);

  if (isPhone(page)) {
    await page.touchscreen.tap(x, y);
    await expectOpened(page, "f-hollow");
    expect(await clicks()).toEqual(["mouse", "touch"]);
    return;
  }
  // The desktop project has no touch screen: the finger is tried in a browser of the same size that has one.
  const context = await browser.newContext({ viewport: page.viewportSize(), hasTouch: true, locale: "en-GB" });
  try {
    const touch = await context.newPage();
    const { stubNetwork } = await import("./support/network.js");
    await stubNetwork(touch);
    await openOverlapping(touch);
    const touchClicks = await recordClicks(touch);
    await touch.touchscreen.tap(x, y);
    await expectOpened(touch, "f-hollow");
    expect(await touchClicks()).toEqual(["touch"]);
  } finally {
    await context.close();
  }
});

test("a click that doesn't say its pointer takes the reach of the last pointer to go down", async ({ page }) => {
  await openOverlapping(page);
  const { x, y } = onScreen(page, BESIDE_THE_WAY);
  /** A plain mouse event, with no pointer type, after a pointer of this kind went down elsewhere on the page. */
  const clickAfter = (pointerType: string) =>
    page.evaluate(
      ({ pointerType, x, y }) => {
        document.body.dispatchEvent(new PointerEvent("pointerdown", { pointerType, bubbles: true }));
        const canvas = document.querySelector(".fc-map__pane--main canvas");
        if (!canvas) throw new Error("no map canvas");
        const init = { clientX: x, clientY: y, bubbles: true, cancelable: true, button: 0 };
        canvas.dispatchEvent(new MouseEvent("mousedown", init));
        canvas.dispatchEvent(new MouseEvent("mouseup", init));
        canvas.dispatchEvent(new MouseEvent("click", init));
      },
      { pointerType, x, y },
    );
  await clickAfter("mouse");
  await expectNothingOpened(page);
  await clickAfter("touch");
  await expectOpened(page, "f-hollow");
});

test("Explore's list reaches every overlapping finding by keyboard", async ({ page }) => {
  await fakeFindings(page, OVERLAPPING);
  await openMap(page, `/${VIEW}`);
  const panel = page.getByRole("complementary", { name: "Explore" });
  if (isPhone(page)) await panel.getByRole("button", { name: /Press to resize/ }).click();
  const list = panel.getByRole("list", { name: "Findings in view" });
  await expect(list.getByRole("listitem")).toHaveCount(OVERLAPPING.length);
  for (const feature of OVERLAPPING) {
    const title = String(feature.properties.title);
    await tabTo(page, list.getByRole("link", { name: new RegExp(`^${title}`) }));
  }
  await page.keyboard.press("Enter");
  await expectOpened(page, String(OVERLAPPING.at(-1)?.properties.public_id));
});

/** A road clipped at the view's edge into two parts, and an area in two parts, as the server may send them. */
const CLIPPED_ROAD = finding(
  "f-clipped-road",
  "Road in two parts",
  [-140, 120],
  {
    type: "MultiLineString",
    coordinates: [
      [at([-140, 120]), at([-40, 120])],
      [at([20, 200]), at([140, 200])],
    ],
  },
  "road",
);
const CLIPPED_AREA = finding(
  "f-clipped-area",
  "Enclosure in two parts",
  [-120, -140],
  { type: "MultiPolygon", coordinates: [[ring(-130, -150, -60, -90)], [ring(20, -150, 120, -60)]] },
  "enclosure",
);

test("a line and an area in several parts draw every part, and each part picks its finding", async ({ page }) => {
  await openOverlapping(page, [CLIPPED_ROAD, CLIPPED_AREA]);
  await press(page, [80, 200]);
  await expectOpened(page, "f-clipped-road");
  await openMap(page, `/?panel=none${VIEW}`);
  await markersDrawn(page, 2);
  await press(page, [120, -100]);
  await expectOpened(page, "f-clipped-area");
});
