import { openMap } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";
import { join } from "./support/people.js";

/**
 * A member adds a mention to a finding against the real backend, sees it on
 * the finding's page, and finds it in the recent mentions across the map.
 * The address is on the loopback interface, which the server refuses to
 * fetch, so the test never reaches the internet and shows the mention saved
 * by its address alone.
 */

const AVEBURY = { lon: -1.8542, lat: 51.4286 };
const VIEW = "#m=16/51.4286/-1.8542/0/0&v=composite";

test("a member adds a mention to a finding and sees it on the page and in the recent feed", async ({
  page,
}, testInfo) => {
  const tag = `${testInfo.project.name.slice(0, 1)}${Date.now() % 1_000_000}`;
  await join(page, `Teller${tag}`);
  const title = `Barrow ${tag}`;
  const created = await page.request.post("/api/v1/findings", {
    headers: { "X-OpenAntiquity-Client": "web" },
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
  const panel = page.getByRole("complementary", { name: title });
  const section = panel.getByRole("region", { name: "Mentions" });
  await expect(section.getByText(/Nobody has said where it was talked about yet/)).toBeVisible();

  const address = `https://127.0.0.1/field-club-e2e/${tag}`;
  await section.getByRole("button", { name: "Add a mention" }).click();
  await section.getByRole("textbox", { name: "Address" }).fill(address);
  await section.getByRole("button", { name: "Look it up" }).click();
  await expect(
    section.getByText("We don't fetch pages from that site, so it will be listed by its address alone."),
  ).toBeVisible();
  const form = section.getByRole("form", { name: "Add a mention" });
  await form.getByRole("radio", { name: "Article" }).click();
  await form.getByLabel("Note (optional)").fill(`Says the ring ditch is clear ${tag}.`);
  await form.getByRole("button", { name: "Save the mention" }).click();

  const shortAddress = `127.0.0.1/field-club-e2e/${tag}`;
  const onPage = section.getByRole("list", { name: "Mentions of this finding" }).getByRole("article");
  await expect(onPage).toHaveCount(1);
  await expect(onPage.getByRole("link", { name: new RegExp(shortAddress) })).toHaveAttribute("href", address);
  await expect(onPage).toContainText(`Says the ring ditch is clear ${tag}.`);
  await expect(onPage).toContainText(`Added by Teller${tag}`);

  // Read again from the server, it is still there.
  await page.reload();
  await expect(
    page.getByRole("complementary", { name: title }).getByRole("link", { name: new RegExp(shortAddress) }),
  ).toBeVisible();

  await page
    .getByRole("complementary", { name: title })
    .getByRole("link", { name: "Recent mentions everywhere" })
    .click();
  const feed = page.getByRole("complementary", { name: "Recent mentions" });
  const item = feed.getByRole("article").filter({ hasText: shortAddress });
  await expect(item).toHaveCount(1);
  await expect(item.getByRole("link", { name: /About the finding/ })).toContainText(title);
  await item.getByRole("link", { name: /About the finding/ }).click();
  await expect(page.getByRole("complementary", { name: title })).toBeVisible();
});
