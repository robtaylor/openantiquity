import type { Page } from "@playwright/test";
import { openMap, tabTo } from "./support/app.js";
import { fakeFindings } from "./support/findings.js";
import { expect, test } from "./support/fixtures.js";
import {
  at,
  finding,
  isPhone,
  line,
  type Metres,
  markersDrawn,
  onScreen,
  openWithFindings,
  press,
  ring,
  VIEW,
} from "./support/shapes.js";

/**
 * Picking one of overlapping findings in a real browser, in fixture mode
 * (Decision 0031): areas are picked by their edges, markers beat lines and
 * lines beat area edges, two alike open the chooser, a finger reaches
 * further than a mouse, and the Explore list reaches every finding by
 * keyboard. Shapes clipped into several parts draw and pick like whole
 * ones. Every place is in metres from the view's centre, at zoom 15, where
 * a pixel is about 1.5 m.
 */

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

async function openOverlapping(page: Page, features = OVERLAPPING): Promise<void> {
  await openWithFindings(page, features);
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

/**
 * Two alike ways side by side, 18 m apart: about 12 px. A tap on the first
 * reaches the second with a finger's 16 px and not with a mouse's 6 px.
 */
const SIDE_BY_SIDE = [
  finding(
    "f-west-way",
    "West way",
    [-120, 150],
    line([
      [-120, -150],
      [-120, 150],
    ]),
    "trackway",
  ),
  finding(
    "f-east-way",
    "East way",
    [-102, -150],
    line([
      [-102, -150],
      [-102, 150],
    ]),
    "trackway",
  ),
];

test("a finger's tap between two close ways opens the chooser where a mouse's click there opens one", async ({
  page,
  browser,
}) => {
  await openOverlapping(page, SIDE_BY_SIDE);
  const { x, y } = onScreen(page, [-120, 0]);
  await page.mouse.click(x, y);
  await expectOpened(page, "f-west-way");

  const tap = async (touch: Page): Promise<void> => {
    await touch.touchscreen.tap(x, y);
    const chooser = touch.getByRole("dialog", { name: "2 findings here" });
    await expect(chooser.getByRole("button", { name: /^West way,/ })).toBeVisible();
    await expect(chooser.getByRole("button", { name: /^East way,/ })).toBeVisible();
  };
  if (isPhone(page)) {
    await openOverlapping(page, SIDE_BY_SIDE);
    await tap(page);
    return;
  }
  const context = await browser.newContext({ viewport: page.viewportSize(), hasTouch: true, locale: "en-GB" });
  try {
    const touch = await context.newPage();
    const { stubNetwork } = await import("./support/network.js");
    await stubNetwork(touch);
    await openOverlapping(touch, SIDE_BY_SIDE);
    await tap(touch);
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
