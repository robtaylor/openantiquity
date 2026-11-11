import type { Page } from "@playwright/test";
import { commentFixture, evidenceFixture, OTHER, seenFixture } from "../src/test/fixtures/findingPage.js";
import { findingSummary, findingsData } from "../src/test/fixtures/findings.js";
import {
  actionFixture,
  contributionFixture,
  eligibleFixture,
  mediaFixture,
  ownProfileFixture,
  pointFixture,
  profileFixture,
  queuedPhotoFixture,
  reportFixture,
  targetFixture,
  youngProfileFixture,
} from "../src/test/fixtures/people.js";
import { fakeSession, meWith } from "./support/account.js";
import { openMap, tabTo } from "./support/app.js";
import { fakeFindingPage } from "./support/findingPage.js";
import { expect, test } from "./support/fixtures.js";
import { fakeModeration } from "./support/moderation.js";
import { apiRoute } from "./support/network.js";
import { solidPng } from "./support/png.js";

/**
 * Profiles, reporting, moderation and photos, in fixture mode at desktop and
 * phone width. The API is answered by `support/moderation.ts` and
 * `support/findingPage.ts`.
 */

const SAM = meWith({ handle: "SharpEyedSam", display_name: "Sam Hill" });
const MORAG = meWith({ handle: "ModMorag", display_name: "Morag Kerr", role: "moderator" });
const FOUND = findingsData.features.slice(0, 2).map((feature) => findingSummary(feature));

/** Serve the image behind every photo address, so the browser has something to show. */
async function servePhotos(page: Page): Promise<void> {
  await page.route(/\/api\/v1\/media\/\d+(?:\?|$)/, (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: solidPng(96, 64, [120, 110, 80]) }),
  );
}

test("someone's page shows what they found and helped with, and lets a signed-in member report them", async ({
  page,
}) => {
  await fakeSession(page, SAM);
  const fake = await fakeModeration(page, {
    people: {
      [OTHER.handle]: {
        profile: profileFixture({ role: "trusted" }),
        findings: FOUND,
        helped: [contributionFixture(), contributionFixture({ id: 32, kind: "comment", subkind: null })],
      },
    },
  });
  await openMap(page, `/u/${OTHER.handle}`);
  const panel = page.getByRole("complementary", { name: "Mary Anning" });
  await expect(panel.getByText("Trusted member", { exact: true })).toBeVisible();
  await expect(panel.getByText("Joined October 2026")).toBeVisible();
  await expect(page).toHaveTitle("Mary Anning · Field Club");
  await expect(panel.getByRole("list", { name: "Findings" }).getByRole("link")).toHaveCount(2);
  await expect(panel.getByRole("tab")).toHaveText(["Found", "Helped"]);

  await panel.getByRole("tab", { name: "Helped" }).click();
  await expect(panel.getByRole("list", { name: "Helped with" })).toContainText("Added an aerial photo");

  await panel.getByRole("button", { name: "Report this person" }).click();
  const dialog = page.getByRole("dialog", { name: "Report this person" });
  await dialog.getByText("Under 16", { exact: true }).click();
  await dialog.getByRole("button", { name: "Send report" }).click();
  await expect(page.getByRole("dialog", { name: "Thanks, your report is in" })).toContainText(
    "They aren't told who reported them.",
  );
  expect(fake.sent["POST /reports"]).toEqual([{ target_kind: "user", target_id: OTHER.handle, reason: "under_age" }]);
  await page.keyboard.press("Escape");
  await expect(page.getByRole("dialog")).toHaveCount(0);
});

test("an account aged 16 or 17 shows only its handle, and the page still reads well", async ({ page }) => {
  await fakeModeration(page, { people: { BrightCairn7: { profile: youngProfileFixture() } } });
  await openMap(page, "/u/BrightCairn7");
  const panel = page.getByRole("complementary", { name: "BrightCairn7" });
  await expect(panel.getByText("Nothing they've marked is on the map for you to see.")).toBeVisible();
  await expect(panel.getByText("@BrightCairn7")).toHaveCount(0);
  await expect(panel.getByRole("img", { name: "BrightCairn7" })).toHaveText("BC");
});

test("your own page shows where your points came from and your second looks, and nobody else's does", async ({
  page,
}) => {
  await fakeSession(page, meWith());
  await fakeModeration(page, {
    people: {
      QuietBarrow42: {
        profile: ownProfileFixture(),
        findings: FOUND.slice(0, 1),
        points: [pointFixture(), pointFixture({ id: 6, delta: 1, reason: "evidence_endorsed_4" })],
      },
    },
  });
  await openMap(page, "/account");
  await page.getByRole("link", { name: "See your public profile" }).click();
  const panel = page.getByRole("complementary", { name: "Ada Lovelace" });
  await expect(panel.getByText(/This is your page as others see it/)).toBeVisible();
  await panel.getByRole("tab", { name: "Points" }).click();
  await expect(panel.getByRole("list", { name: "Where your points came from" }).getByRole("listitem")).toHaveText([
    /^\+2Your finding reached Seen by others/,
    /^\+1Two people endorsed evidence you added/,
  ]);
  await panel.getByRole("tab", { name: "Second looks" }).click();
  await expect(panel.getByText("You haven't taken a second look yet")).toBeVisible();
  await expect(panel.getByRole("button", { name: /^Report/ })).toHaveCount(0);
});

test("a comment is reported from its finding's page, by keyboard, with what happens next said plainly", async ({
  page,
}) => {
  await fakeSession(page, SAM);
  const fake = await fakeModeration(page);
  const finding = seenFixture();
  await fakeFindingPage(page, finding, { comments: [commentFixture({ id: 501 })] });
  await openMap(page, `/f/${finding.public_id}`);
  const panel = page.getByRole("complementary", { name: finding.title });
  const report = panel.getByRole("button", { name: "Report this comment" });
  await report.scrollIntoViewIfNeeded();
  await report.focus();
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Report this comment" });
  await expect(dialog).toBeVisible();
  // Tab stays inside the dialog.
  await tabTo(page, dialog.getByRole("button", { name: "Send report" }));
  await page.keyboard.press("Tab");
  await expect(dialog.getByRole("button", { name: "Close" })).toBeFocused();
  await dialog.getByRole("radio", { name: /Abusive/ }).check();
  await dialog.getByLabel(/Anything the moderators should know/).fill("Rude about the finder.");
  await dialog.getByRole("button", { name: "Send report" }).click();
  await expect(page.getByRole("dialog", { name: "Thanks, your report is in" })).toBeVisible();
  expect(fake.sent["POST /reports"]).toEqual([
    { target_kind: "comment", target_id: "501", reason: "abuse", note: "Rude about the finder." },
  ]);
  await page.getByRole("button", { name: "Done" }).click();
  await expect(report).toBeFocused();
});

test("signed out, the report button asks you to sign in first", async ({ page }) => {
  const finding = seenFixture();
  await fakeFindingPage(page, finding);
  await openMap(page, `/f/${finding.public_id}`);
  await page
    .getByRole("complementary", { name: finding.title })
    .getByRole("button", { name: "Report this finding" })
    .click();
  await expect(page.getByRole("dialog", { name: /Sign in/ })).toBeVisible();
  await expect(page.getByRole("dialog", { name: "Report this finding" })).toHaveCount(0);
});

test("a moderator works through the report queue, deadline first, and hides what they uphold", async ({ page }) => {
  await fakeSession(page, MORAG);
  const urgent = reportFixture({
    id: 2,
    reason: "defamation",
    due_at: new Date(Date.now() + 30 * 3600_000).toISOString(),
    note: null,
    target: targetFixture({ id: 502, ref: "502", body: "He made that barrow up to sell books." }),
  });
  const fake = await fakeModeration(page, { reports: [reportFixture(), urgent] });
  await openMap(page, "/account");
  await page.getByRole("link", { name: "Moderation" }).click();
  await expect(page).toHaveURL(/\/mod(?:#|$)/);
  const panel = page.getByRole("complementary", { name: "Moderation" });
  const cards = panel.getByRole("list", { name: "Open reports" }).getByRole("listitem");
  await expect(cards).toHaveCount(2);
  await expect(cards.first()).toContainText("Untrue about a person");
  await expect(cards.first()).toContainText("Legal deadline · Due by");
  await expect(cards.nth(1)).toContainText("It names the farm and the farmer.");

  await cards.first().getByRole("button", { name: "Uphold" }).click();
  const dialog = page.getByRole("dialog", { name: "Uphold this report?" });
  await expect(dialog.getByRole("checkbox", { name: /Hide it as well/ })).toBeChecked();
  await dialog.getByLabel("Note for the log").fill("Untrue claim about a named person.");
  await dialog.getByRole("button", { name: "Uphold and hide" }).click();
  await expect(cards).toHaveCount(1);
  await expect(page.getByText("Upheld and hidden.")).toBeVisible();
  expect(fake.sent["POST /mod/comments/502/hide"]).toEqual([{ reason: "Untrue claim about a named person." }]);
  expect(fake.sent["POST /mod/reports/2/resolve"]).toEqual([
    { outcome: "upheld", note: "Untrue claim about a named person." },
  ]);
});

test("a moderator makes a member trusted, and reads the log", async ({ page }) => {
  await fakeSession(page, MORAG);
  const fake = await fakeModeration(page, { eligible: [eligibleFixture()], actions: [actionFixture()] });
  await openMap(page, "/mod/members");
  const panel = page.getByRole("complementary", { name: "Moderation" });
  const member = panel.getByRole("list", { name: "Members who could be trusted" }).locator(":scope > li");
  await expect(member).toContainText("Also on it: Sam Hill");
  await member.getByRole("button", { name: "Make trusted" }).click();
  const dialog = page.getByRole("dialog", { name: "Change KeenLynchet7's role" });
  await dialog.getByLabel("Why").fill("Careful, independent work.");
  await dialog.getByRole("button", { name: "Make them trusted member" }).click();
  await expect(panel.getByText("Nobody is waiting")).toBeVisible();
  expect(fake.sent["PUT /mod/users/KeenLynchet7/role"]).toEqual([
    { role: "trusted", reason: "Careful, independent work." },
  ]);

  await panel.getByRole("tab", { name: "Log" }).click();
  await expect(page).toHaveURL(/\/mod\/log(?:#|$)/);
  await expect(panel.getByRole("list", { name: "Moderation log" })).toContainText(
    "Morag Kerr hid a comment on “Ring ditch by the long barrow”.",
  );
});

test("a trusted member approves photos, and a member is told moderation isn't for them", async ({ page }) => {
  const session = await fakeSession(page, meWith({ role: "trusted" }));
  await servePhotos(page);
  const fake = await fakeModeration(page, { photos: [queuedPhotoFixture()] });
  await openMap(page, "/account");
  await page.getByRole("link", { name: "Photos waiting for approval" }).click();
  await expect(page).toHaveURL(/\/mod\/photos(?:#|$)/);
  const panel = page.getByRole("complementary", { name: "Photos to approve" });
  const photo = panel.getByRole("img", { name: "Photo uploaded by Mary Anning" });
  await expect.poll(() => photo.evaluate((image: HTMLImageElement) => image.naturalWidth)).toBe(96);
  await panel.getByRole("button", { name: "Approve" }).click();
  await expect(panel.getByText("No photos are waiting")).toBeVisible();
  expect(Object.keys(fake.sent)).toEqual(["POST /mod/media/77/approve"]);

  session.set(meWith());
  await page.reload();
  await expect(page.getByRole("complementary", { name: "Moderation" })).toContainText("This part is for moderators");
});

test("a moderator hides someone else's comment on a finding's page and can show it again", async ({ page }) => {
  await fakeSession(page, MORAG);
  const fake = await fakeModeration(page);
  const finding = seenFixture({ evidence: [evidenceFixture({ contributor: OTHER })] });
  await fakeFindingPage(page, finding, { comments: [commentFixture({ id: 501 })] });
  await openMap(page, `/f/${finding.public_id}`);
  const panel = page.getByRole("complementary", { name: finding.title });
  const comment = panel.locator(".fc-comment").first();
  await expect(comment.getByRole("button", { name: "Remove" })).toHaveCount(0);
  await comment.getByRole("button", { name: "Hide this comment" }).click();
  const dialog = page.getByRole("dialog", { name: "Hide this comment?" });
  await dialog.getByLabel("Why").fill("Names a landowner.");
  await dialog.getByRole("button", { name: "Hide it" }).click();
  await expect(comment).toContainText("A moderator hid this comment.");
  expect(fake.sent["POST /mod/comments/501/hide"]).toEqual([{ reason: "Names a landowner." }]);
  await expect(panel.getByRole("heading", { name: "Moderation" })).toBeVisible();
});

test.describe("photos that are refused or not yet approved", () => {
  // These answer with errors on purpose, which the browser logs.
  test.use({ pageProblems: "page-errors" });

  test("an upload the server is too busy for is tried again, and then waits for approval", async ({ page }) => {
    await fakeSession(page, meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" }));
    await servePhotos(page);
    const finding = seenFixture();
    const fake = await fakeFindingPage(page, finding);
    let tries = 0;
    await page.route(apiRoute("/media"), (route) => {
      tries += 1;
      return tries === 1
        ? route.fulfill({
            status: 503,
            contentType: "application/json",
            body: JSON.stringify({ error: { code: "uploads_busy", message: "Busy." } }),
          })
        : route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(mediaFixture()) });
    });
    await openMap(page, `/f/${finding.public_id}`);
    const panel = page.getByRole("complementary", { name: finding.title });
    await panel.getByRole("button", { name: "Add evidence" }).click();
    await panel.locator(".fc-kind-list").getByRole("button", { name: "Ground photo", exact: true }).click();
    const form = panel.getByRole("form", { name: "Add ground photo" });
    await form.getByLabel("The photo").setInputFiles({
      name: "barrow.png",
      mimeType: "image/png",
      buffer: solidPng(96, 64, [120, 110, 80]),
    });
    await expect(form.getByRole("alert")).toHaveText(/The server is busy with other photos/);
    await form.getByRole("button", { name: "Try again" }).click();
    await expect(form.getByText(/barrow\.png is uploaded/)).toBeVisible();
    await expect(form.getByText(/only you, moderators and trusted members can see it/)).toBeVisible();
    await form.getByRole("button", { name: "Add it" }).click();
    const item = panel
      .locator(".fc-evidence")
      .filter({ has: page.getByRole("img", { name: /Ground photo added by/ }) });
    await expect(item).toContainText("Waiting for approval.");
    expect(fake.sent["POST evidence"]).toEqual([{ kind: "photo", stance: "supports", media_id: 77 }]);
  });

  test("a photo this viewer may not see yet shows a placeholder that says why", async ({ page }) => {
    // One the server sends no id for, because this viewer may not see it, and one it answers 404 for.
    const finding = seenFixture({
      evidence: [
        evidenceFixture({ id: 8, kind: "photo", media_id: null, title: null }),
        evidenceFixture({ id: 9, kind: "photo", media_id: 78, title: null }),
      ],
    });
    await fakeFindingPage(page, finding);
    await page.route(apiRoute("/media/78"), (route) =>
      route.fulfill({
        status: 404,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "media_not_found", message: "No such photo." } }),
      }),
    );
    await openMap(page, `/f/${finding.public_id}`);
    const panel = page.getByRole("complementary", { name: finding.title });
    // The photo is asked for once it is near the screen.
    await panel.locator(".fc-evidence").last().scrollIntoViewIfNeeded();
    await expect(panel.getByText("This photo shows here once it has been approved.")).toHaveCount(2);
    await expect(panel.getByRole("img", { name: /Ground photo added by/ })).toHaveCount(0);
    // A photo nobody may show this viewer can't be reported by them either.
    await expect(panel.getByRole("button", { name: "Report this photo" })).toHaveCount(0);
  });
});
