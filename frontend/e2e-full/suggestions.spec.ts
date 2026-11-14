import type { Page } from "@playwright/test";
import { openMap } from "../e2e/support/app.js";
import { WEB_PORT } from "./support/env.js";
import { expect, test } from "./support/fixtures.js";
import { helper, join, stub } from "./support/people.js";

/**
 * Suggestions and handing a marking on against the real backend (lines
 * phase 2, WS-C step 1). A finder draws a protected line. A second member
 * suggests a change to it with the drawing tool, and the finder, its
 * keeper, accepts it, and the timeline names the suggester. With a second
 * suggestion waiting, someone signed out reads the line and is sent no
 * suggestion and no suggester's name. Then the keeper hands the marking on,
 * and the member takes it on. Each project works at a place of its own, as
 * both share one database.
 */

const HEADERS = { "X-OpenAntiquity-Client": "web" };
/** In Herefordshire, away from every other spec's places. */
const PLACES = { desktop: { lon: -2.9, lat: 52.1 }, phone: { lon: -2.9, lat: 52.16 } } as const;

function view(at: { lon: number; lat: number }, zoom = 15): string {
  return `#m=${zoom}/${at.lat}/${at.lon}/0/0&v=composite`;
}

interface Detail {
  location: { path: { points: Array<{ lon: number; lat: number; kind: string }> } | null; shape: { revision: number } };
}

/** Letters for digits: a run of digits in a protected finding's title reads as a grid reference, and is refused. */
function lettered(tag: string): string {
  return tag.replace(/\d/g, (digit) => "abcdefghij"[Number(digit)] ?? "");
}

async function moveLastPoint(page: Page, of: number): Promise<void> {
  const handle = page.getByRole("button", { name: new RegExp(`^Point ${of} of ${of},`) });
  await expect(handle).toBeVisible();
  await handle.focus();
  for (let step = 0; step < 3; step++) await page.keyboard.press("Shift+ArrowRight");
}

test("a member suggests a change, the keeper accepts it and hands the marking on, and a signed-out reader sees none of it", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(180_000);
  const project = testInfo.project.name === "phone" ? "phone" : "desktop";
  const at = PLACES[project];
  const tag = `${project.slice(0, 1)}${Date.now() % 1_000_000}`;
  const memberHandle = `Suggester${tag}`;
  const title = `Bank by the brook ${lettered(tag)}`;

  const finder = await helper(browser, page.viewportSize(), `Keeper${tag}`);
  try {
    const created = await finder.page.request.post("/api/v1/findings", {
      headers: HEADERS,
      data: {
        path: {
          closed: false,
          points: [
            { lon: at.lon - 0.003, lat: at.lat, kind: "corner" },
            { lon: at.lon, lat: at.lat + 0.001, kind: "corner" },
            { lon: at.lon + 0.003, lat: at.lat, kind: "corner" },
          ],
        },
        feature_class: "linear",
        sensitivity: "protected",
        title,
        view_state: { layer: "composite", zoom: 15 },
      },
    });
    expect(created.status(), await created.text()).toBe(201);
    const publicId = ((await created.json()) as { public_id: string }).public_id;

    // The member suggests a change with the drawing tool.
    await join(page, memberHandle);
    await openMap(page, `/f/${publicId}${view(at)}`);
    const memberPanel = page.getByRole("complementary", { name: title });
    await memberPanel.getByRole("button", { name: "Suggest a change" }).click();
    await expect(page.getByRole("complementary", { name: "Suggest a change" })).toBeVisible();
    await moveLastPoint(page, 3);
    await page
      .getByRole("complementary", { name: "Suggest a change" })
      .getByRole("button", { name: "Send the suggestion" })
      .click();
    await expect(page.getByText(/Your suggestion is sent/)).toBeVisible();
    await expect(memberPanel.getByRole("list", { name: "Suggested changes" })).toBeVisible();

    // The keeper accepts it, and the timeline names who suggested it.
    await openMap(finder.page, `/f/${publicId}${view(at)}`);
    const keeperPanel = finder.page.getByRole("complementary", { name: title });
    const card = keeperPanel
      .getByRole("list", { name: "Suggested changes" })
      .getByRole("listitem")
      .filter({ hasText: memberHandle });
    await card.getByRole("button", { name: "Accept" }).click();
    await expect(finder.page.getByText(/The suggested change is accepted/)).toBeVisible();
    await expect(keeperPanel.getByText(`Suggested by ${memberHandle}`)).toBeVisible();
    const accepted = (await (await finder.page.request.get(`/api/v1/findings/${publicId}`)).json()) as Detail;
    expect(accepted.location.shape.revision).toBe(1);

    // A second suggestion waits, made straight on the API.
    const points = accepted.location.path?.points ?? [];
    const second = await page.request.post(`/api/v1/findings/${publicId}/suggestions`, {
      headers: HEADERS,
      data: {
        path: { closed: false, points: [...points, { lon: at.lon + 0.006, lat: at.lat + 0.001, kind: "corner" }] },
        path_revision: accepted.location.shape.revision,
      },
    });
    expect(second.status(), await second.text()).toBe(201);

    // Someone signed out reads it: no suggestion, no count, and the suggester named nowhere.
    const outsider = await browser.newContext({
      baseURL: `http://localhost:${WEB_PORT}`,
      viewport: page.viewportSize(),
      locale: "en-GB",
    });
    try {
      const reader = await outsider.newPage();
      await stub(reader);
      const read = await reader.request.get(`/api/v1/findings/${publicId}`);
      const text = await read.text();
      expect(read.status(), text).toBe(200);
      expect(text).not.toContain(memberHandle);
      const shape = (JSON.parse(text) as { location: { shape: { suggestions?: unknown[] } } }).location.shape;
      expect(shape.suggestions ?? []).toEqual([]);
      await openMap(reader, `/f/${publicId}${view(at)}`);
      const readerPanel = reader.getByRole("complementary", { name: title });
      await expect(readerPanel.getByText(/You're seeing the one-kilometre square/)).toBeVisible();
      await expect(readerPanel.getByRole("heading", { name: "Suggested changes" })).toHaveCount(0);
      await expect(readerPanel.getByRole("button", { name: "Suggest a change" })).toHaveCount(0);
      await expect(readerPanel.getByText(memberHandle)).toHaveCount(0);
    } finally {
      await outsider.close();
    }

    // The keeper hands it on, and the member takes it on.
    await keeperPanel.getByRole("button", { name: "Hand it on" }).click();
    const dialog = finder.page.getByRole("dialog", { name: "Hand it on" });
    await dialog.getByLabel("Their handle").fill(memberHandle);
    await dialog.getByRole("button", { name: "Offer it" }).click();
    await expect(keeperPanel.getByText(new RegExp(`Offered to ${memberHandle}`))).toBeVisible();

    await page.reload();
    await expect(memberPanel.getByText(/You've been asked to keep this marking/)).toBeVisible();
    await memberPanel.getByRole("button", { name: "Take it on" }).click();
    await expect(memberPanel.getByText(new RegExp(`Kept by ${memberHandle}`))).toBeVisible();
    await expect(memberPanel.getByText(new RegExp(`Found by Keeper${tag}`))).toBeVisible();
    await expect(memberPanel.getByRole("button", { name: "Change the shape" })).toBeVisible();
  } finally {
    await finder.context.close();
  }
});
