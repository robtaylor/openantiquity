import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import { commentFixture, evidenceFixture, OTHER, seenFixture } from "../../src/test/fixtures/findingPage.js";
import { findingSummary, findingsData } from "../../src/test/fixtures/findings.js";
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
} from "../../src/test/fixtures/people.js";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindingPage } from "../support/findingPage.js";
import { fakeModeration } from "../support/moderation.js";
import { apiRoute, stubNetwork } from "../support/network.js";
import { solidPng } from "../support/png.js";

/**
 * Screenshots of profiles, reporting, moderation and photos, taken with
 * `pnpm shots`, at desktop and phone width: each screen with content, empty,
 * loading and failed, and the phone sheet's stops.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(400);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `people-${name}-${size?.width}x${size?.height}.png`) });
}

const isPhone = (page: Page) => (page.viewportSize()?.width ?? 1440) < 720;
const MORAG = meWith({ handle: "ModMorag", display_name: "Morag Kerr", role: "moderator" });
const FOUND = findingsData.features.slice(0, 3).map((feature) => findingSummary(feature));

async function fullSheet(page: Page): Promise<void> {
  if (!isPhone(page)) return;
  const grip = page.getByRole("button", { name: /Panel is .* Press to resize\./ });
  await grip.click();
}

async function servePhotos(page: Page): Promise<void> {
  await page.route(/\/api\/v1\/media\/\d+(?:\?|$)/, (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: solidPng(640, 420, [118, 112, 84]) }),
  );
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("profile", async ({ page }) => {
  await fakeSession(page, meWith({ handle: "SharpEyedSam", display_name: "Sam Hill" }));
  await fakeModeration(page, {
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
  await panel.getByRole("list", { name: "Findings" }).waitFor();
  await shoot(page, "profile");
  await fullSheet(page);
  await shoot(page, "profile-full");
  await panel.getByRole("tab", { name: /Helped/ }).click();
  await panel.getByRole("list", { name: "Helped with" }).waitFor();
  await shoot(page, "profile-helped");
  await panel.getByRole("button", { name: "Report this person" }).click();
  await page.getByRole("dialog", { name: "Report this person" }).waitFor();
  await shoot(page, "report-dialog");
  const dialog = page.getByRole("dialog", { name: "Report this person" });
  await dialog.getByText("Under 16", { exact: true }).click();
  await dialog.getByRole("button", { name: "Send report" }).click();
  await page.getByRole("dialog", { name: "Thanks, your report is in" }).waitFor();
  await shoot(page, "report-sent");
});

test("profile young and own", async ({ page }) => {
  await fakeSession(page, meWith());
  await fakeModeration(page, {
    people: {
      BrightCairn7: { profile: youngProfileFixture() },
      QuietBarrow42: {
        profile: ownProfileFixture(),
        findings: FOUND.slice(0, 1),
        points: [
          pointFixture(),
          pointFixture({ id: 6, delta: 1, reason: "evidence_endorsed_4" }),
          pointFixture({ id: 7, delta: 5, reason: "tier_corroborated", finding: null }),
        ],
      },
    },
  });
  await openMap(page, "/u/BrightCairn7");
  await page.getByText("Nothing they've marked is on the map for you to see.").waitFor();
  await shoot(page, "profile-young");
  await openMap(page, "/u/QuietBarrow42");
  const panel = page.getByRole("complementary", { name: "Ada Lovelace" });
  await panel.getByRole("tab", { name: "Points" }).click();
  await panel.getByRole("list", { name: "Where your points came from" }).waitFor();
  await fullSheet(page);
  await shoot(page, "profile-points");
});

test("profile states", async ({ page }) => {
  await page.route(apiRoute("/users/Slow"), () => new Promise(() => {}));
  await openMap(page, "/u/Slow");
  await shoot(page, "profile-loading");
  await page.route(apiRoute("/users/Broken"), (route) =>
    route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "bad_request", message: "The server tripped over." } }),
    }),
  );
  await openMap(page, "/u/Broken");
  await page.getByText("This page couldn't be loaded").waitFor();
  await shoot(page, "profile-failed");
  await fakeModeration(page);
  await openMap(page, "/u/Nobody");
  await page.getByText("There's nobody here").waitFor();
  await shoot(page, "profile-missing");
});

test("moderation queue", async ({ page }) => {
  await fakeSession(page, MORAG);
  await servePhotos(page);
  const due = new Date(Date.now() + 30 * 3600_000).toISOString();
  await fakeModeration(page, {
    reports: [
      reportFixture(),
      reportFixture({
        id: 2,
        reason: "defamation",
        due_at: due,
        note: null,
        open_on_target: 2,
        target: targetFixture({
          id: 502,
          ref: "502",
          body: "He made that barrow up to sell books, everyone knows it.",
        }),
      }),
      reportFixture({
        id: 3,
        reason: "intimate_image",
        due_at: new Date(Date.now() + 40 * 3600_000).toISOString(),
        note: "Not a photo of the site at all.",
        target: targetFixture({
          kind: "photo",
          id: 77,
          ref: "77",
          body: null,
          photo_url: "/api/v1/media/77",
        }),
      }),
      reportFixture({
        id: 4,
        reason: "spam",
        note: null,
        target: targetFixture({
          kind: "user",
          id: 12,
          ref: "CheapDetectors",
          finding: null,
          title: "CheapDetectors",
          owner: { handle: "CheapDetectors", display_name: "CheapDetectors", avatar_url: null, role: "member" },
          body: "Best metal detectors, ships free. https://example.com/shop",
        }),
      }),
    ],
    photos: [queuedPhotoFixture(), queuedPhotoFixture({ id: 78, url: "/api/v1/media/78", findings: [] })],
    eligible: [eligibleFixture()],
    actions: [
      actionFixture(),
      actionFixture({
        id: 8,
        action: "change_role",
        reason: "Careful, independent work over two months.",
        target: targetFixture({ kind: "user", ref: OTHER.handle, finding: null, title: "Mary Anning", body: null }),
        data: { from: "member", to: "trusted" },
      }),
      actionFixture({
        id: 7,
        action: "change_sensitivity",
        reason: "A field boundary, not a barrow.",
        target: targetFixture({ kind: "finding", ref: "f-ring", title: "Ring ditch by the long barrow", body: null }),
        data: { from: "protected", to: "open" },
      }),
    ],
  });
  await openMap(page, "/mod");
  const panel = page.getByRole("complementary", { name: "Moderation" });
  await panel.getByRole("list", { name: "Open reports" }).waitFor();
  await shoot(page, "mod-reports");
  await fullSheet(page);
  await shoot(page, "mod-reports-full");
  await panel.getByRole("button", { name: "Uphold" }).first().click();
  await page.getByRole("dialog", { name: "Uphold this report?" }).waitFor();
  await shoot(page, "mod-uphold");
  await page.keyboard.press("Escape");

  await panel.getByRole("tab", { name: "Photos" }).click();
  await panel.getByRole("list", { name: "Photos waiting for approval" }).waitFor();
  await shoot(page, "mod-photos");
  await panel.getByRole("tab", { name: "Members" }).click();
  await panel.getByRole("list", { name: "Members who could be trusted" }).waitFor();
  await shoot(page, "mod-members");
  await panel.getByLabel("Handle").fill("Gone");
  await panel.getByRole("button", { name: "Look up" }).click();
  await panel.getByText(/Nobody can be found as/).scrollIntoViewIfNeeded();
  await shoot(page, "mod-lookup");
  await panel.getByRole("tab", { name: "Log" }).click();
  await panel.getByRole("list", { name: "Moderation log" }).waitFor();
  await shoot(page, "mod-log");
});

test("moderation states", async ({ page }) => {
  const session = await fakeSession(page, MORAG);
  await fakeModeration(page);
  await openMap(page, "/mod");
  await page.getByText("No reports are waiting").waitFor();
  await shoot(page, "mod-empty");
  await page.route(apiRoute("/mod/reports"), () => new Promise(() => {}));
  await openMap(page, "/mod");
  await shoot(page, "mod-loading");
  await page.unroute(apiRoute("/mod/reports"));
  await page.route(apiRoute("/mod/reports"), (route) =>
    route.fulfill({
      status: 400,
      contentType: "application/json",
      body: JSON.stringify({ error: { code: "bad_request", message: "The queue is stuck." } }),
    }),
  );
  await openMap(page, "/mod");
  await page.getByText("The reports couldn't be loaded").waitFor();
  await shoot(page, "mod-failed");
  session.set(meWith());
  await openMap(page, "/mod");
  await page.getByText("This part is for moderators").waitFor();
  await shoot(page, "mod-not-yours");
});

test("finding page as a moderator", async ({ page }) => {
  await fakeSession(page, MORAG);
  await fakeModeration(page);
  await servePhotos(page);
  const finding = seenFixture({
    evidence: [evidenceFixture({ id: 9, kind: "photo", media_id: 77, title: null, contributor: OTHER })],
  });
  await fakeFindingPage(page, finding, {
    comments: [commentFixture({ id: 501 }), commentFixture({ id: 502, hidden: true })],
  });
  await openMap(page, `/f/${finding.public_id}`);
  const panel = page.getByRole("complementary", { name: finding.title });
  await fullSheet(page);
  await panel.locator(".fc-evidence").first().scrollIntoViewIfNeeded();
  await shoot(page, "finding-evidence");
  await panel.locator(".fc-comment").first().scrollIntoViewIfNeeded();
  await shoot(page, "finding-comments");
  await panel.getByRole("heading", { name: "Moderation" }).scrollIntoViewIfNeeded();
  await shoot(page, "finding-moderation");
  await panel.getByRole("button", { name: "Change its level" }).click();
  await page.getByRole("dialog", { name: "Change its level" }).getByRole("radio", { name: "Restricted" }).click();
  await shoot(page, "finding-level");
});

test("photo upload", async ({ page }) => {
  await fakeSession(page, meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" }));
  await servePhotos(page);
  const finding = seenFixture({ evidence: [evidenceFixture({ id: 8, kind: "photo", media_id: null, title: null })] });
  await fakeFindingPage(page, finding);
  let answer: "hold" | "busy" | "ok" = "hold";
  await page.route(apiRoute("/media"), (route) => {
    if (answer === "hold") return new Promise(() => {});
    if (answer === "busy")
      return route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ error: { code: "uploads_busy", message: "Busy." } }),
      });
    return route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify(mediaFixture()) });
  });
  await openMap(page, `/f/${finding.public_id}`);
  const panel = page.getByRole("complementary", { name: finding.title });
  await fullSheet(page);
  await panel.locator(".fc-evidence").first().scrollIntoViewIfNeeded();
  await shoot(page, "photo-placeholder");
  await panel.getByRole("button", { name: "Add evidence" }).click();
  await panel.locator(".fc-kind-list").getByRole("button", { name: "Ground photo", exact: true }).click();
  const form = panel.getByRole("form", { name: "Add ground photo" });
  const file = { name: "east-bank.png", mimeType: "image/png", buffer: solidPng(640, 420, [118, 112, 84]) };
  await form.getByLabel("The photo").setInputFiles(file);
  await form.getByRole("progressbar").scrollIntoViewIfNeeded();
  await shoot(page, "photo-sending");
  await form.getByRole("button", { name: "Stop" }).click();
  answer = "busy";
  await form.getByLabel("The photo").setInputFiles(file);
  await form.getByRole("alert").waitFor();
  await shoot(page, "photo-busy");
  answer = "ok";
  await form.getByRole("button", { name: "Try again" }).click();
  await form.getByText(/is uploaded/).waitFor();
  await shoot(page, "photo-uploaded");
});
