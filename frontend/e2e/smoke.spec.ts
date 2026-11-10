import { openMap } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { STUB_GRID_REF, STUB_HEIGHT_M } from "./support/network.js";

test.describe("desktop", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) < 720, "desktop layout only");

  test("loads the map, opens the layer panel, switches view and toggles compare", async ({ page, network }) => {
    await openMap(page);

    // The fixture opens on Avebury, in grid square SU.
    await expect(page.getByTestId("status-gridref")).toHaveText(/^SU \d{3} \d{3}$/);
    await expect(page.getByTestId("status-zoom")).toHaveText("z14.0");
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-view", "composite");
    await expect.poll(() => network.served.lidar ?? 0, { message: "LIDAR tiles requested" }).toBeGreaterThan(0);

    await page.getByRole("button", { name: "Layers" }).click();
    await expect(page).toHaveURL(/[?&]panel=layers/);
    const panel = page.getByRole("complementary", { name: "Layers" });
    await expect(panel.getByRole("group", { name: "LIDAR" })).toBeVisible();
    await expect(panel.getByRole("group", { name: "Maps" })).toBeVisible();
    await expect(panel.getByRole("radio", { name: /^Composite/ })).toBeChecked();

    await panel.getByRole("radio", { name: /^Slope/ }).check();
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-view", "slope");
    await expect(page).toHaveURL(/#.*\bv=slope\b/);

    await panel.getByRole("switch", { name: "Compare two layers" }).check();
    await expect(page.locator(".fc-map__pane--compare")).toHaveAttribute("data-view", "osm_standard");
    await expect(page.locator(".fc-map__pane--compare canvas")).toBeVisible();
    await expect(page).toHaveURL(/#.*\bc=osm_standard\b/);
    await expect.poll(() => network.served["osm-raster"] ?? 0, { message: "map tiles requested" }).toBeGreaterThan(0);

    const divide = page.getByRole("slider", { name: "Comparison divide" });
    await expect(divide).toHaveAttribute("aria-valuenow", "50");
    await divide.focus();
    await page.keyboard.press("Shift+ArrowRight");
    await expect(divide).toHaveAttribute("aria-valuenow", "60");

    // The right-hand side is the one being changed after picking its tab.
    await panel.getByRole("tab", { name: /^Right/ }).click();
    await panel.getByRole("radio", { name: /^Local relief/ }).check();
    await expect(page.locator(".fc-map__pane--compare")).toHaveAttribute("data-view", "local_relief");
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-view", "slope");

    await panel.getByRole("switch", { name: "Compare two layers" }).uncheck();
    await expect(page.locator(".fc-map__pane--compare")).toHaveCount(0);
    await expect(divide).toHaveCount(0);
    await expect(page).not.toHaveURL(/\bc=/);

    await panel.getByRole("button", { name: "Close panel" }).click();
    await expect(panel).toHaveCount(0);
    await expect(page).not.toHaveURL(/panel=layers/);
  });

  test("restores a permalink, including raking light", async ({ page, network }) => {
    await openMap(page, "/#m=12.5/51.1788/-1.8263/0/0&v=raking&s=90/20&x=0.8&t=0/1.5&o=osm:40,findings:100:h");

    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-view", "raking");
    await expect(page.getByTestId("status-zoom")).toHaveText("z12.5");
    await expect(page.getByTestId("status-gridref")).toHaveText(/^SU 12\d 42\d$/);

    const raking = page.getByRole("region", { name: "Raking light", exact: true });
    await expect(raking).toBeVisible();
    await expect(raking.getByText("Light from the east")).toBeVisible();
    const dial = raking.getByRole("slider", { name: "Sun direction" });
    await expect(dial).toHaveAttribute("aria-valuenow", "90");
    await expect(raking.getByRole("slider", { name: "Sun height" })).toHaveValue("20");
    await expect.poll(() => network.served.dem ?? 0, { message: "elevation tiles requested" }).toBeGreaterThan(0);

    await dial.focus();
    await page.keyboard.press("ArrowRight");
    await expect(dial).toHaveAttribute("aria-valuenow", "95");
    await expect(page).toHaveURL(/#.*\bs=95\/20\b/);

    await page.getByRole("button", { name: "Layers" }).click();
    const panel = page.getByRole("complementary", { name: "Layers" });
    await expect(panel.getByRole("switch", { name: "Findings", exact: true })).not.toBeChecked();
    await expect(panel.locator('[data-overlay="osm"]').getByRole("slider", { name: "Opacity" })).toHaveValue("40");

    // Pasting a different link into the address bar moves the map to match.
    await page.evaluate(() => {
      window.location.hash = "#m=16/56.7968/-5.0036/0/0&v=composite&s=200/40&x=2&t=0/1.5&o=osm:80,findings:100";
    });
    await expect(page.getByTestId("status-zoom")).toHaveText("z16.0");
    await expect(page.getByTestId("status-gridref")).toHaveText(/^NN 16\d 71\d$/);
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-view", "composite");
    await expect(raking).toHaveCount(0);
    await expect(panel.getByRole("switch", { name: "Findings", exact: true })).toBeChecked();
  });

  test("keeps the URL, the readout and the map in step when a link asks for more zoom than the map has", async ({
    page,
  }) => {
    await openMap(page, "/#m=22/51.4286/-1.8542/0/0&v=composite");
    await expect(page.getByTestId("status-zoom")).toHaveText("z20.0");
    await expect(page).toHaveURL(/#m=20\/51\.4286\/-1\.8542\/0\/0&/);
    // Already at the limit, so there is no further to go.
    await expect(page.getByRole("button", { name: "Zoom in" })).toBeDisabled();
  });

  test("shows the ground height where the pointer rests, and asks the server only then", async ({ page, network }) => {
    await openMap(page);
    const height = page.getByTestId("status-height");
    const canvas = page.locator(".fc-map__pane--main canvas");
    const box = await canvas.boundingBox();
    if (!box) throw new Error("No map canvas");
    // The centre of the map is asked about once, as the map opens at rest.
    await expect.poll(() => network.served["geo-point"] ?? 0).toBe(1);

    // A sweep across the map asks nothing.
    for (let i = 0; i < 10; i++) {
      await page.mouse.move(box.x + 300 + i * 40, box.y + 300);
      await page.waitForTimeout(60);
    }
    expect(network.served["geo-point"] ?? 0).toBe(1);
    await expect(height).toHaveText("– m");

    // Resting asks once, and the height and exact reference arrive.
    await expect(height).toHaveText(`${STUB_HEIGHT_M.toFixed(1)} m`);
    expect(network.served["geo-point"]).toBe(2);
    await expect(page.getByTestId("status-gridref")).toHaveAttribute(
      "title",
      `Grid reference under the pointer: ${STUB_GRID_REF}`,
    );
    await expect(page.getByTestId("status-gridref")).toHaveText(/^SU \d{3} \d{3}$/);
  });

  test("asks for the findings in view, again after a drag", async ({ page, network }) => {
    await openMap(page);
    await expect.poll(() => network.served.findings ?? 0).toBe(1);
    const box = await page.locator(".fc-map__pane--main canvas").boundingBox();
    if (!box) throw new Error("No map canvas");
    await page.mouse.move(box.x + 400, box.y + 400);
    await page.mouse.down();
    await page.mouse.move(box.x + 700, box.y + 500, { steps: 10 });
    await page.waitForTimeout(200);
    await page.mouse.up();
    await expect.poll(() => network.served.findings ?? 0).toBe(2);
  });

  test("turns 3D on and off", async ({ page }) => {
    await openMap(page);
    // One button, with one name. Its pressed state says whether 3D is on.
    const threeD = page.getByRole("button", { name: "Tilt into 3D" });
    await expect(threeD).toHaveAttribute("aria-pressed", "false");
    await threeD.click();
    await expect(threeD).toHaveAttribute("aria-pressed", "true");
    await expect(page).toHaveURL(/#m=14\/[\d.-]+\/[\d.-]+\/0\/60&.*\bt=1\/1\.5\b/);
    // Tilted but still north-up, there is nothing for the compass to do.
    await expect(page.getByRole("button", { name: "Reset to north-up" })).toHaveCount(0);
    await threeD.click();
    await expect(page).toHaveURL(/#m=14\/[\d.-]+\/[\d.-]+\/0\/0&.*\bt=0\/1\.5\b/);
    await expect(page.getByRole("button", { name: "Reset to north-up" })).toHaveCount(0);
  });

  test("shows a titled panel for each mode and keeps the map mounted", async ({ page }) => {
    await openMap(page);
    await page.locator(".fc-map__pane--main").evaluate((element) => {
      (element as HTMLElement).dataset.marker = "still-here";
    });

    const rail = page.getByRole("navigation", { name: "Modes" });
    await rail.getByRole("link", { name: "Second look" }).click();
    await expect(page).toHaveURL(/\/review#/);
    await expect(page.getByRole("heading", { name: "Second look" })).toBeVisible();
    await expect(rail.getByRole("link", { name: "Second look" })).toHaveAttribute("aria-current", "page");
    await expect(page).toHaveTitle("Second look · Field Club");

    for (const [path, title] of [
      ["/scan", "Scan a square"],
      ["/help", "Help wanted"],
      ["/f/abc123", "Finding"],
      ["/r/42", "Heritage record"],
      ["/i/xyz", "Investigation"],
      ["/u/QuietBarrow42", "Profile"],
      ["/about", "About Field Club"],
      ["/guide", "Guide"],
    ] as const) {
      await page.goto(path);
      await expect(page.getByRole("heading", { name: title, exact: true })).toBeVisible();
    }

    await openMap(page, "/review");
    await page.locator(".fc-map__pane--main").evaluate((element) => {
      (element as HTMLElement).dataset.marker = "still-here";
    });
    await page.getByRole("button", { name: "Close panel" }).click();
    await expect(page).toHaveURL(/\/#/);
    await expect(page.getByRole("heading", { name: "Second look" })).toHaveCount(0);
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-marker", "still-here");

    await page.goBack();
    await expect(page.getByRole("heading", { name: "Second look" })).toBeVisible();
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-marker", "still-here");
  });

  test("gives feedback from the primary action", async ({ page }) => {
    await openMap(page);
    await page.getByRole("button", { name: "Mark a finding" }).click();
    await expect(page.getByRole("status").filter({ hasText: "isn't built yet" })).toBeVisible();
  });
});

test.describe("phone", () => {
  test.skip(({ viewport }) => (viewport?.width ?? 0) >= 720, "phone layout only");

  test("uses a tab bar and a three-stop bottom sheet", async ({ page }) => {
    await openMap(page);
    const tabs = page.getByRole("navigation", { name: "Modes" });
    await expect(tabs.getByRole("link")).toHaveCount(4);
    await expect(tabs.getByRole("button", { name: "More" })).toBeVisible();
    await expect(page.getByTestId("status-gridref")).toHaveText(/^SU \d{3} \d{3}$/);
    await expect(page.getByTestId("status-coords")).toHaveCount(0);
    await expect(page.getByRole("button", { name: "Mark a finding" })).toBeVisible();

    // There is no pointer on a touch screen, so the readout stays on the centre of the map after a tap.
    const centreRef = await page.getByTestId("status-gridref").textContent();
    await page.touchscreen.tap(195, 250);
    await page.waitForTimeout(400);
    await expect(page.getByTestId("status-gridref")).toHaveText(centreRef ?? "");

    await page.getByRole("button", { name: "Layers" }).click();
    const sheet = page.getByRole("complementary", { name: "Layers" });
    await expect(sheet).toHaveAttribute("data-stop", "half");
    await expect(sheet.getByRole("radio", { name: /^Composite/ })).toBeChecked();

    const handle = sheet.getByRole("button", { name: /Press to resize/ });
    await handle.focus();
    await page.keyboard.press("ArrowUp");
    await expect(sheet).toHaveAttribute("data-stop", "full");
    await page.keyboard.press("ArrowDown");
    await page.keyboard.press("ArrowDown");
    await expect(sheet).toHaveAttribute("data-stop", "peek");
    // At the lowest stop the sheet leaves the map and the primary action in reach.
    await expect(page.getByRole("button", { name: "Mark a finding" })).toBeInViewport();
    await page.keyboard.press("ArrowUp");
    await expect(sheet).toHaveAttribute("data-stop", "half");

    await sheet.getByRole("radio", { name: /^Raking light/ }).check();
    await expect(page.locator(".fc-map__pane--main")).toHaveAttribute("data-view", "raking");

    await sheet.getByRole("button", { name: "Close panel" }).click();
    await expect(sheet).toHaveCount(0);
    await expect(page.getByRole("region", { name: "Raking light", exact: true })).toBeInViewport();
  });

  test("reaches the remaining modes through More", async ({ page }) => {
    await openMap(page);
    const tabs = page.getByRole("navigation", { name: "Modes" });
    await tabs.getByRole("button", { name: "More" }).click();
    await tabs.getByRole("link", { name: "Investigations" }).click();
    await expect(page).toHaveURL(/\/investigations#/);
    await expect(page.getByRole("heading", { name: "Investigations" })).toBeVisible();
    await expect(tabs.getByRole("link", { name: "Investigations" })).toHaveCount(0);
  });
});
