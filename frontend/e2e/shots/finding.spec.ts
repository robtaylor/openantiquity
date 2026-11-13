import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Locator, type Page, test } from "@playwright/test";
import type { FindingDetail } from "../../src/features/finding/types.js";
import {
  commentFixture,
  EXPERT,
  evidenceFixture,
  FINDER,
  finderView,
  heldFixture,
  MODERATOR_ACTIONS,
  observationFixture,
  pageFixture,
  seenFixture,
  squareFixture,
} from "../../src/test/fixtures/findingPage.js";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindingPage } from "../support/findingPage.js";
import { apiRoute, stubNetwork } from "../support/network.js";
import { solidPng } from "../support/png.js";

/**
 * Screenshots of a finding's page, taken with `pnpm shots`, for looking at
 * the design at desktop and phone width: each viewer, state and form. They
 * stub every tile, so the map behind is plain, and they assert nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";
const MEMBER = meWith({ handle: "KeenLynchet7", display_name: "Mary Anning" });

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(450);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `finding-${name}-${size?.width}x${size?.height}.png`) });
}

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

async function sheetTo(page: Page, stop: "peek" | "half" | "full"): Promise<void> {
  if (!isPhone(page)) return;
  const handle = page.getByRole("button", { name: /Press to resize/ });
  for (let i = 0; i < 3; i++) {
    if ((await page.locator(".fc-shell").getAttribute("data-sheet")) === stop) return;
    await handle.click();
  }
}

async function open(page: Page, finding: FindingDetail): Promise<Locator> {
  await openMap(page, `/f/${finding.public_id}${VIEW}`);
  const panel = page.getByRole("complementary", { name: finding.title });
  await panel.waitFor();
  return panel;
}

async function scrollTo(locator: Locator): Promise<void> {
  await locator.evaluate((element) => element.scrollIntoView({ block: "start" }));
}

/** What the server lets someone do with evidence they added themselves: nothing. */
const OWN_ITEM = {
  vote: { allowed: false, reason: "vote_not_allowed" },
  verify: { allowed: false, reason: "verify_not_allowed" },
};

const RICH = seenFixture({
  evidence: [
    evidenceFixture({ id: 1, actions: OWN_ITEM }),
    evidenceFixture({
      id: 2,
      kind: "aerial",
      title: "Historic England, 1976",
      url: "https://example.org/aerial/1976",
      note: "A dark ring in the barley.",
      contributor: EXPERT,
      vote_total: 2.5,
      endorsements: 3,
      disputes: 1,
    }),
    evidenceFixture({
      id: 3,
      kind: "designation",
      title: "Bowl barrow 600m north of West Kennet",
      reference: "1008391",
      url: null,
      note: null,
      vote_total: 0,
      endorsements: 0,
      independent: false,
      actions: OWN_ITEM,
    }),
  ],
});

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("member", async ({ page }) => {
  await fakeSession(page, MEMBER);
  await fakeFindingPage(page, RICH, {
    comments: [
      commentFixture(),
      commentFixture({ id: 2, parent_id: 1, author: FINDER, body: "Thanks, I'll look at that." }),
    ],
  });
  const panel = await open(page, RICH);
  await shoot(page, "01-member-top");
  await sheetTo(page, "full");
  await shoot(page, "02-member-full");
  await scrollTo(panel.getByRole("heading", { name: "Evidence" }));
  await shoot(page, "03-member-evidence");
  await scrollTo(panel.getByRole("heading", { name: "Discussion" }));
  await shoot(page, "04-member-discussion");
  if (isPhone(page)) {
    await sheetTo(page, "peek");
    await shoot(page, "05-member-peek");
  }
});

test("second look", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = pageFixture();
  await fakeFindingPage(page, finding);
  const panel = await open(page, finding);
  await sheetTo(page, "full");
  const look = panel.getByRole("region", { name: "Your second look" });
  await scrollTo(look);
  await shoot(page, "10-look-ask");
  await look.getByRole("button", { name: "I can see it" }).click();
  await look.getByText(/Your answer is in/).waitFor();
  // On a phone the sheet has come down to half-way, so the place is in sight while the detail is asked.
  await shoot(page, "11-look-answer-in");
  await look.getByRole("radio", { name: "Round barrow or mound" }).click();
  await shoot(page, "11b-look-detail-chosen");
  await sheetTo(page, "full");
  await scrollTo(look);
  await shoot(page, "11c-look-detail-full");
  await look.getByRole("button", { name: "Add this and see how it compares" }).click();
  await look.getByText(/other people can see it/).waitFor();
  await scrollTo(look);
  await shoot(page, "12-look-revealed");
});

test("second look with a long title, and focus after the reveal", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = pageFixture({
    title: "Possible ring ditch and outer bank beside the long barrow, faint in the low evening light",
  });
  await fakeFindingPage(page, finding);
  const panel = await open(page, finding);
  const look = panel.getByRole("region", { name: "Your second look" });
  await scrollTo(look);
  await look.getByRole("button", { name: "I can see it" }).click();
  await look.getByText(/Your answer is in/).waitFor();
  await shoot(page, "16-look-long-title-detail");
  await page.keyboard.press("Tab");
  await look.getByRole("button", { name: "See how it compares" }).click();
  await look.getByText(/other people can see it/).waitFor();
  await shoot(page, "17-look-long-title-revealed");
});

test("second look left between the steps, and signed out", async ({ page }) => {
  const session = await fakeSession(page, MEMBER);
  const held = heldFixture("unsure", { answers_visible: false });
  await fakeFindingPage(page, held);
  const panel = await open(page, held);
  const look = panel.getByRole("region", { name: "Your second look" });
  await scrollTo(look);
  await shoot(page, "14-look-held");

  session.set(null);
  const fresh = pageFixture({ public_id: "f-draft" });
  await fakeFindingPage(page, fresh);
  const signedOut = await open(page, fresh);
  const draftLook = signedOut.getByRole("region", { name: "Your second look" });
  await draftLook.getByRole("button", { name: "Not sure" }).click();
  await draftLook.locator(".fc-draft-badge").waitFor();
  await scrollTo(draftLook);
  await shoot(page, "15-look-draft");
});

test("second look from what would move it up", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = pageFixture();
  await fakeFindingPage(page, finding);
  const panel = await open(page, finding);
  await sheetTo(page, "half");
  await panel.getByRole("button", { name: "Give a second look" }).first().click();
  await shoot(page, "13-look-from-steps");
});

test("viewers", async ({ page }) => {
  const square = squareFixture();
  await fakeFindingPage(page, square);
  await open(page, square);
  await shoot(page, "20-signed-out-square");

  const session = await fakeSession(page, meWith({ handle: FINDER.handle, display_name: FINDER.display_name }));
  const mine = finderView({ public_id: "f-mine" });
  await fakeFindingPage(page, mine);
  const panel = await open(page, mine);
  await shoot(page, "22-finder-top");
  await sheetTo(page, "full");
  await scrollTo(panel.getByRole("heading", { name: "Your finding" }));
  await shoot(page, "23-finder-tools");
  await panel.getByRole("button", { name: "Protect it" }).click();
  await shoot(page, "24-finder-protect");
  await page.keyboard.press("Escape");
  await panel.getByRole("button", { name: "Edit" }).click();
  await shoot(page, "25-finder-edit");
  // A protected finding's note that says where it is: the server refuses it, and the dialog says so beside it.
  await page.route(apiRoute("/findings/f-mine"), (route) =>
    route.request().method() === "PATCH"
      ? route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "position_in_text",
              message: "A protected finding's title and description can't say where it is.",
              details: [{ field: "body.description", message: "The description gives a position." }],
            },
          }),
        })
      : route.fallback(),
  );
  const dialog = page.getByRole("dialog", { name: "Edit your finding" });
  await dialog.getByLabel("Note (optional)").fill("Clearest at SU 1025 6996, with the light from the north-west.");
  await dialog.getByRole("button", { name: "Save changes" }).click();
  await dialog.getByText(/out of the note/).waitFor();
  await shoot(page, "25b-finder-edit-refused");
  await page.keyboard.press("Escape");

  session.set(meWith({ handle: "Keeper", display_name: "Kit Keeper", role: "moderator" }));
  const guarded = pageFixture({
    public_id: "f-guarded",
    sensitivity: "protected",
    actions: { ...MODERATOR_ACTIONS, raise_level: { allowed: false, reason: "highest_level" } },
  });
  await fakeFindingPage(page, guarded);
  const moderated = await open(page, guarded);
  await sheetTo(page, "full");
  await scrollTo(moderated.getByRole("heading", { name: "Protecting it" }));
  await shoot(page, "29-moderator-tools");
  await moderated.getByRole("button", { name: "Lower its protection" }).click();
  await shoot(page, "29b-moderator-lower");
});

test("states", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const base = pageFixture().assessment;
  const states: Array<[string, Partial<FindingDetail>]> = [
    ["30-known", { assessment: { ...base, state: "known", tier: "seen", score: 34 } }],
    ["31-disputed", { assessment: { ...base, state: "disputed", tier: "seen", score: 31 } }],
    ["32-ruled-out", { assessment: { ...base, state: "ruled_out", state_reason: "modern", score: 0, next_steps: [] } }],
    ["33-withdrawn", { assessment: { ...base, state: "withdrawn" } }],
    [
      "34-confirmed",
      {
        assessment: { ...base, tier: "confirmed", score: 100, next_tier: null, next_steps: [] },
        my_observation: observationFixture(),
      },
    ],
  ];
  for (const [name, overrides] of states) {
    const finding = pageFixture({ public_id: `f-${name}`, ...overrides });
    await fakeFindingPage(page, finding);
    await open(page, finding);
    await shoot(page, name);
  }

  await page.route(/\/api\/v1\/findings\/gone(\?|$)/, (route) =>
    route.fulfill({
      status: 404,
      contentType: "application/json",
      body: '{"error":{"code":"finding_not_found","message":"x"}}',
    }),
  );
  await openMap(page, `/f/gone${VIEW}`);
  await page.getByRole("heading", { name: "There's no finding at this address" }).waitFor();
  await shoot(page, "35-not-found");

  await page.route(/\/api\/v1\/findings\/broken(\?|$)/, (route) =>
    route.fulfill({
      status: 400,
      contentType: "application/json",
      body: '{"error":{"code":"x","message":"The server sent something odd."}}',
    }),
  );
  await openMap(page, `/f/broken${VIEW}`);
  await page.getByRole("heading", { name: "This finding couldn't be loaded" }).waitFor();
  await shoot(page, "36-failed");

  let release = (): void => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(/\/api\/v1\/findings\/slow(\?|$)/, async (route) => {
    await held;
    await route.fulfill({ status: 404, contentType: "application/json", body: "{}" });
  });
  await openMap(page, `/f/slow${VIEW}`);
  await shoot(page, "37-loading");
  release();
});

test("a ground photo, a hidden comment and the nearest place", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture({
    evidence: [
      evidenceFixture({ id: 5, kind: "photo", title: null, url: null, media_id: 77, note: "From the east bank." }),
      evidenceFixture({ id: 6, kind: "photo", title: null, url: null, media_id: 78, note: "Waiting for approval." }),
    ],
  });
  await fakeFindingPage(page, finding, {
    comments: [
      commentFixture({
        id: 3,
        author: { handle: MEMBER.handle, display_name: MEMBER.display_name, role: "member" },
        body: "This one was hidden by a moderator.",
        hidden: true,
      }),
    ],
  });
  await page.route(apiRoute("/media/77"), (route) =>
    route.fulfill({ status: 200, contentType: "image/png", body: solidPng(480, 320, [96, 112, 72]) }),
  );
  await page.route(apiRoute("/media/78"), (route) =>
    route.fulfill({ status: 404, contentType: "application/json", body: "{}" }),
  );
  await page.route(apiRoute("/geo/point"), (route) =>
    route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({
        grid_ref: "SU 1025 6996",
        nation: "england",
        elevation: 160,
        place: { name: "Avebury", kind: "village", distance_m: 640, source: null },
      }),
    }),
  );
  const panel = await open(page, finding);
  await sheetTo(page, "full");
  await panel.getByText("Avebury, 640 m away").waitFor();
  await shoot(page, "26-nearest-place");
  await scrollTo(panel.getByRole("heading", { name: "Evidence" }));
  await shoot(page, "27-photo-evidence");
  await scrollTo(panel.getByRole("heading", { name: "Discussion" }));
  await shoot(page, "28-hidden-comment");
});

test("evidence forms", async ({ page }) => {
  await fakeSession(page, MEMBER);
  const finding = seenFixture();
  await fakeFindingPage(page, finding);
  const panel = await open(page, finding);
  await sheetTo(page, "full");
  for (const [name, button] of [
    ["40-form-old-map", "Add old map"],
    ["41-form-aerial", "Add aerial photo"],
    ["42-form-record", "Add heritage record"],
  ] as const) {
    await panel.getByRole("button", { name: button }).first().click();
    const add = panel.locator(".fc-evidence-add");
    await scrollTo(add);
    await shoot(page, name);
    await add.getByRole("button", { name: "Cancel" }).click();
  }
  for (const [name, kind] of [
    ["43-form-site-visit", "Site visit"],
    ["44-form-her", "HER entry"],
    ["45-form-lidar", "LIDAR view"],
    ["46-form-photo", "Ground photo"],
  ] as const) {
    await panel.getByRole("button", { name: "Add evidence" }).click();
    await panel.locator(".fc-kind-list").getByRole("button", { name: kind, exact: true }).click();
    const add = panel.locator(".fc-evidence-add");
    await scrollTo(add);
    await shoot(page, name);
    await add.getByRole("button", { name: "Cancel" }).click();
  }
  await panel.getByRole("button", { name: "Add evidence" }).click();
  await scrollTo(panel.locator(".fc-evidence-add"));
  await shoot(page, "47-form-kinds");
});
