import { openMap } from "../e2e/support/app.js";
import { solidPng } from "../e2e/support/png.js";
import { expect, test } from "./support/fixtures.js";
import { helper, join } from "./support/people.js";

/**
 * The plan's exit test for collaboration, against the real backend: one
 * account reports a comment, a moderator hides it from the report queue,
 * and on the next load it is gone for a third account. Each project marks
 * its finding at a place of its own.
 */

const PLACES = { desktop: { lon: -1.42, lat: 52.31 }, phone: { lon: -0.42, lat: 52.31 } } as const;
const PHOTO_PLACES = { desktop: { lon: -1.42, lat: 52.36 }, phone: { lon: -0.42, lat: 52.36 } } as const;
const HEADERS = { "X-FieldClub-Client": "web" };

test("a reported comment, hidden by a moderator, is gone for everyone else on the next load", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120_000);
  const project = testInfo.project.name === "phone" ? "phone" : "desktop";
  const at = PLACES[project];
  const tag = `${project.slice(0, 1)}${Date.now() % 1_000_000}`;
  const title = `Hollow way ${tag}`;
  const words = `Park in the farmyard at Lower Barn, ${tag}.`;

  // Someone marks a finding and comments on it.
  const author = await helper(browser, page.viewportSize(), `Poster${tag}`);
  const moderator = await helper(browser, page.viewportSize(), `Mod${tag}`, "moderator");
  const third = await helper(browser, page.viewportSize(), `Reader${tag}`);
  try {
    const created = await author.page.request.post("/api/v1/findings", {
      headers: HEADERS,
      data: {
        location: { type: "Point", coordinates: [at.lon, at.lat] },
        feature_class: "trackway",
        title,
        view_state: { layer: "composite", zoom: 16 },
      },
    });
    expect(created.status(), await created.text()).toBe(201);
    const publicId = ((await created.json()) as { public_id: string }).public_id;
    const commented = await author.page.request.post(`/api/v1/findings/${publicId}/comments`, {
      headers: HEADERS,
      data: { body: words },
    });
    expect(commented.status(), await commented.text()).toBe(201);

    // A member reports it from the finding's page.
    await join(page, `Reporter${tag}`);
    await openMap(page, `/f/${publicId}`);
    const panel = page.getByRole("complementary", { name: title });
    await expect(panel.getByText(words)).toBeVisible();
    await panel.getByRole("button", { name: "Report this comment" }).click();
    const dialog = page.getByRole("dialog", { name: "Report this comment" });
    await dialog.getByRole("radio", { name: /Reveals personal details/ }).check();
    await dialog.getByLabel(/Anything the moderators should know/).fill("Names a farm.");
    await dialog.getByRole("button", { name: "Send report" }).click();
    await expect(page.getByRole("dialog", { name: "Thanks, your report is in" })).toBeVisible();

    // A moderator finds it in the queue, upholds it and hides the comment.
    await openMap(moderator.page, "/mod");
    const queue = moderator.page.getByRole("complementary", { name: "Moderation" });
    const card = queue.getByRole("list", { name: "Open reports" }).getByRole("listitem").filter({ hasText: words });
    await expect(card).toContainText("Reveals personal details");
    await expect(card).toContainText("Names a farm.");
    await card.getByRole("button", { name: "Uphold" }).click();
    const uphold = moderator.page.getByRole("dialog", { name: "Uphold this report?" });
    await expect(uphold.getByRole("checkbox", { name: /Hide it as well/ })).toBeChecked();
    await uphold.getByLabel("Note for the log").fill("Names a private landowner.");
    await uphold.getByRole("button", { name: "Uphold and hide" }).click();
    await expect(moderator.page.getByText("Upheld and hidden.")).toBeVisible();
    await expect(card).toHaveCount(0);

    // The log says so.
    await queue.getByRole("tab", { name: "Log" }).click();
    await expect(queue.getByRole("list", { name: "Moderation log" })).toContainText(`hid a comment on “${title}”`);

    // On the next load, a third account sees it removed, with no author and no words.
    await openMap(third.page, `/f/${publicId}`);
    const theirs = third.page.getByRole("complementary", { name: title });
    await expect(theirs.getByText("This comment was removed.")).toBeVisible();
    await expect(theirs.getByText(words)).toHaveCount(0);
    // The poster found the finding too, so their name is on the page, but not on the comment.
    await expect(theirs.locator(".fc-comment")).not.toContainText(`Poster${tag}`);

    // Its author still sees it, marked as hidden.
    await openMap(author.page, `/f/${publicId}`);
    await expect(
      author.page.getByText(/A moderator hid this comment\. Only you and moderators can still see it\./),
    ).toBeVisible();
  } finally {
    await author.context.close();
    await moderator.context.close();
    await third.context.close();
  }
});

test("an uploaded photo waits for approval, and shows to others once a trusted member approves it", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120_000);
  const project = testInfo.project.name === "phone" ? "phone" : "desktop";
  const at = PHOTO_PLACES[project];
  const tag = `${project.slice(0, 1)}${Date.now() % 1_000_000}`;
  const title = `Hut circle ${tag}`;

  const finder = await helper(browser, page.viewportSize(), `Finder${tag}`);
  const trusted = await helper(browser, page.viewportSize(), `Trusty${tag}`, "trusted");
  const third = await helper(browser, page.viewportSize(), `Looker${tag}`);
  try {
    const created = await finder.page.request.post("/api/v1/findings", {
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

    // A member adds a ground photo: it goes up as soon as it is chosen.
    await join(page, `Snapper${tag}`);
    await openMap(page, `/f/${publicId}`);
    const panel = page.getByRole("complementary", { name: title });
    await panel.getByRole("button", { name: "Add evidence" }).click();
    await panel.locator(".fc-kind-list").getByRole("button", { name: "Ground photo", exact: true }).click();
    const form = panel.getByRole("form", { name: "Add ground photo" });
    await form.getByLabel("The photo").setInputFiles({
      name: "bank.png",
      mimeType: "image/png",
      buffer: solidPng(120, 80, [110, 120, 90]),
    });
    await expect(form.getByText(/bank\.png is uploaded/)).toBeVisible();
    await expect(form.getByText(/It's waiting for approval/)).toBeVisible();
    await form.getByRole("button", { name: "Add it" }).click();
    const mine = panel.getByRole("img", { name: /Ground photo added by/ });
    await expect(mine).toBeVisible();
    await expect(panel.locator(".fc-photo")).toContainText("Waiting for approval.");

    // Before approval, someone else sees only a placeholder.
    await openMap(third.page, `/f/${publicId}`);
    const theirs = third.page.getByRole("complementary", { name: title });
    await theirs.locator(".fc-evidence").first().scrollIntoViewIfNeeded();
    // Said neutrally, as the page can't tell waiting for approval from taken down.
    await expect(
      theirs.getByText(
        "This photo can't be shown to you. It may still be waiting for approval, or have been taken down.",
      ),
    ).toBeVisible();
    await expect(theirs.getByRole("img", { name: /Ground photo added by/ })).toHaveCount(0);

    // A trusted member approves it from the queue.
    await openMap(trusted.page, "/mod/photos");
    const queue = trusted.page.getByRole("complementary", { name: "Photos to approve" });
    const card = queue.locator(".fc-photo-card").filter({ hasText: `Snapper${tag}` });
    await expect(card.getByRole("img", { name: /^Photo uploaded by/ })).toBeVisible();
    await card.getByRole("button", { name: "Approve" }).click();
    await expect(trusted.page.getByText(/Approved\. Everyone who may see its finding/)).toBeVisible();

    // Now the third account sees it.
    await openMap(third.page, `/f/${publicId}`);
    const photo = third.page.getByRole("img", { name: /Ground photo added by/ });
    await photo.scrollIntoViewIfNeeded();
    await expect.poll(() => photo.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(120);
  } finally {
    await finder.context.close();
    await trusted.context.close();
    await third.context.close();
  }
});
