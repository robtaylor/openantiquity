import type { Page } from "@playwright/test";
import { openMap } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";
import { helper, join } from "./support/people.js";

/**
 * What changes live, against the real backend and its real event stream:
 * a finder has their finding's page open, two other accounts take a second
 * look and say they can see it, and the finder watches it move up to "Seen
 * by others" without reloading, and is told so in their notifications.
 * Each project marks its finding at a place of its own.
 */

const PLACES = { desktop: { lon: -1.62, lat: 52.71 }, phone: { lon: -0.62, lat: 52.71 } } as const;
const HEADERS = { "X-FieldClub-Client": "web" };

async function answerYes(page: Page, publicId: string): Promise<void> {
  const answered = await page.request.put(`/api/v1/findings/${publicId}/observation`, {
    headers: HEADERS,
    data: { visible: "yes", detail_follows: false },
  });
  expect(answered.status(), await answered.text()).toBe(200);
}

test("a second look moves a finding up while its finder's page is open, and the finder sees it without reloading", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120_000);
  const project = testInfo.project.name === "phone" ? "phone" : "desktop";
  const at = PLACES[project];
  const tag = `${project.slice(0, 1)}${Date.now() % 1_000_000}`;
  const title = `Live enclosure ${tag}`;

  await join(page, `Finder${tag}`);
  const created = await page.request.post("/api/v1/findings", {
    headers: HEADERS,
    data: {
      location: { type: "Point", coordinates: [at.lon, at.lat] },
      feature_class: "enclosure",
      title,
      view_state: { layer: "composite", zoom: 16 },
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const publicId = ((await created.json()) as { public_id: string }).public_id;

  // The finder's page is open, and its live stream with it.
  const streamOpen = page.waitForResponse((response) => new URL(response.url()).pathname === "/api/v1/events/stream");
  await openMap(page, `/f/${publicId}`);
  const panel = page.getByRole("complementary", { name: title });
  const badge = panel.locator(".fc-finding__badges");
  await expect(badge).toContainText("Spotted");
  expect((await streamOpen).status()).toBe(200);

  const first = await helper(browser, page.viewportSize(), `Looker${tag}`);
  const second = await helper(browser, page.viewportSize(), `Peerer${tag}`);
  try {
    await answerYes(first.page, publicId);
    await answerYes(second.page, publicId);

    // No reload: the stream's events bring the new step in.
    await expect(badge).toContainText("Seen by others", { timeout: 20_000 });
    await expect(panel.getByRole("status").filter({ hasText: "It has moved up to Seen by others" })).toBeVisible();

    // The finder follows their own finding, so they are told, by a count that names nobody.
    const modes = page.getByRole("navigation", { name: "Modes" });
    const counted =
      project === "phone"
        ? modes.getByRole("button", { name: /^More, \d+ new notifications?$/ })
        : modes.getByRole("link", { name: /^Account, \d+ new notifications?$/ });
    await expect(counted).toBeVisible({ timeout: 20_000 });
    if (project === "phone") await counted.click();
    await modes.getByRole("link", { name: /^Account/ }).click();
    const list = page.getByRole("list", { name: "Your notifications" });
    await expect(list).toContainText(`${title} moved up to Seen by others.`);
    await expect(list).toContainText(`${title} had a second look.`);
    // The finder may see who answered on the page (Decision 0010), but the notifications name nobody.
    await expect(list).not.toContainText(`Looker${tag}`);
    await expect(list).not.toContainText(`Peerer${tag}`);
  } finally {
    await first.context.close();
    await second.context.close();
  }
});
