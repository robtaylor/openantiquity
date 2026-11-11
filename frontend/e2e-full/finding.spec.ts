import type { Locator, Page } from "@playwright/test";
import { openMap } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";
import { helper, join } from "./support/people.js";

/**
 * The exit test for findings (docs/plans): three accounts take one finding
 * from spotted, to seen by others, to corroborated, against the real
 * backend, and the finder's page shows each change. The two helpers answer
 * second looks and add an aerial photo and an old map through the page,
 * as anyone would. Each project uses handles of its own, because both share
 * one database.
 */

const AVEBURY = { lon: -1.8542, lat: 51.4286 };
const VIEW = "#m=16/51.4286/-1.8542/0/0&v=composite";

function panelFor(page: Page, title: string): Locator {
  return page.getByRole("complementary", { name: title });
}

/** Answer "I can see it", which sends it, then say it's an enclosure and see how it compares. */
async function secondLook(page: Page, publicId: string, title: string): Promise<Locator> {
  await openMap(page, `/f/${publicId}${VIEW}`);
  const look = panelFor(page, title).getByRole("region", { name: "Your second look" });
  await look.getByRole("button", { name: "I can see it" }).click();
  await expect(look.getByText(/Your answer is in/)).toBeVisible();
  await look.getByRole("radio", { name: "Enclosure" }).click();
  await look.getByRole("button", { name: "Add this and see how it compares" }).click();
  await expect(look.getByText("You can see it.")).toBeVisible();
  return look;
}

/** The finder's page, read afresh, shows this step. */
async function finderSees(page: Page, title: string, tier: string): Promise<void> {
  await page.reload();
  await expect(panelFor(page, title).locator(".fc-tier-badge")).toHaveText(tier);
}

test("three people take a finding from spotted to seen by others to corroborated", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120_000);
  const tag = `${testInfo.project.name.slice(0, 1)}${Date.now() % 1_000_000}`;
  const viewport = page.viewportSize();

  // The finder marks it, here through the API, and opens its page.
  await join(page, `Finder${tag}`);
  const title = `Enclosure ${tag}`;
  const created = await page.request.post("/api/v1/findings", {
    headers: { "X-FieldClub-Client": "web" },
    data: {
      location: { type: "Point", coordinates: [AVEBURY.lon, AVEBURY.lat] },
      feature_class: "enclosure",
      title,
      view_state: { layer: "composite", zoom: 16 },
    },
  });
  expect(created.status(), await created.text()).toBe(201);
  const { public_id: publicId } = (await created.json()) as { public_id: string };
  await openMap(page, `/f/${publicId}${VIEW}`);
  const finderPanel = panelFor(page, title);
  await expect(finderPanel.locator(".fc-tier-badge")).toHaveText("Spotted");
  await expect(finderPanel.getByRole("button", { name: "Copy a link to ask others" })).toBeVisible();

  const ann = await helper(browser, viewport, `Ann${tag}`);
  const bob = await helper(browser, viewport, `Bob${tag}`);
  try {
    // One other person can see it: not yet enough.
    await secondLook(ann.page, publicId, title);
    await finderSees(page, title, "Spotted");

    // A second: it is seen by others, and the one who tipped it is told.
    const look = await secondLook(bob.page, publicId, title);
    await expect(look.getByText(/It has moved up to Seen by others\./)).toBeVisible();
    await finderSees(page, title, "Seen by others");
    const answers = finderPanel.getByRole("region", { name: "Second looks" });
    await expect(answers.getByRole("listitem").filter({ hasText: `Ann${tag}` })).toContainText("Can see it");

    // Two more kinds of evidence, each from someone other than the finder.
    const annPanel = panelFor(ann.page, title);
    await ann.page.reload();
    await annPanel.getByRole("button", { name: "Add aerial photo" }).click();
    await annPanel.getByLabel("Source").fill("Historic England, 1976");
    await annPanel.getByLabel("Link", { exact: true }).fill("https://example.org/aerial/1976");
    await annPanel.getByRole("button", { name: "Add it" }).click();
    await expect(annPanel.locator(".fc-evidence").filter({ hasText: "Historic England, 1976" })).not.toContainText(
      "Saving…",
    );
    await finderSees(page, title, "Seen by others");

    const bobPanel = panelFor(bob.page, title);
    await bob.page.reload();
    await bobPanel.getByRole("button", { name: "Add old map" }).click();
    await bobPanel.getByLabel("Which map").fill("OS 6-inch, Wiltshire sheet XXVIII, 1888");
    await bobPanel.getByRole("button", { name: "Add it" }).click();
    await expect(bobPanel.locator(".fc-finding__change")).toContainText("It has moved up to Corroborated.");

    // The finder's page shows it, with who helped.
    await finderSees(page, title, "Corroborated");
    await expect(finderPanel.getByRole("meter", { name: "Confidence" })).toHaveAttribute(
      "aria-valuetext",
      /^Corroborated\./,
    );
    const credits = finderPanel.getByRole("region", { name: "Who helped" });
    await expect(credits).toContainText(`Ann${tag}`);
    await expect(credits).toContainText(`Bob${tag}`);
  } finally {
    await ann.context.close();
    await bob.context.close();
  }
});
