import type { Page } from "@playwright/test";
import type { FindingDetail } from "../src/features/finding/types.js";
import {
  EXPERT,
  FINDER,
  FINDER_ACTIONS,
  lineFixture,
  MODERATOR_ACTIONS,
  OTHER,
  SIGNED_OUT_ACTIONS,
  shapeSuggestionFixture,
  squareFixture,
} from "../src/test/fixtures/findingPage.js";
import { findingSummary, offset } from "../src/test/fixtures/findings.js";
import { fakeSession, meWith } from "./support/account.js";
import { openMap } from "./support/app.js";
import { fakeFindingPage } from "./support/findingPage.js";
import { expect, test } from "./support/fixtures.js";
import { fakeKeeping } from "./support/keeping.js";
import { fakeModeration } from "./support/moderation.js";

/**
 * Keepers, suggestions and an admin's removal, in fixture mode, at desktop
 * and phone width (Decisions 0038 to 0040): suggesting a change, an
 * unfinished suggestion kept and asked about, the keeper deciding, handing a
 * marking on and taking it on, the admins' list and a removal, and a
 * signed-out reader of a protected line, who is shown none of it.
 */

const VIEW = "#m=16/51.4286/-1.8542/0/0&v=composite";
const MEMBER = meWith({ handle: OTHER.handle, display_name: OTHER.display_name });
const THE_FINDER = meWith({ handle: FINDER.handle, display_name: FINDER.display_name });
const ADMIN = meWith({ handle: "AdminAnwen", display_name: "Anwen Price", role: "admin" });
const GONE = { handle: "former-member-1", display_name: "Former member", role: "member" };

function panelOf(page: Page, name: string) {
  return page.getByRole("complementary", { name });
}

function toast(page: Page, text: string | RegExp) {
  return page.locator(".fc-toast").filter({ hasText: text });
}

/** Move the line's last point east by keyboard, which works the same on a phone and a computer. */
async function moveLastPoint(page: Page, of: number): Promise<void> {
  const handle = page.getByRole("button", { name: new RegExp(`^Point ${of} of ${of},`) });
  await expect(handle).toBeVisible();
  await handle.focus();
  for (let step = 0; step < 3; step++) await page.keyboard.press("Shift+ArrowRight");
}

async function suggesting(page: Page, finding: FindingDetail = lineFixture()) {
  await fakeSession(page, MEMBER);
  const fake = await fakeFindingPage(page, finding, { me: MEMBER });
  const keeping = await fakeKeeping(page, fake, { me: OTHER });
  await openMap(page, `/f/f-ring${VIEW}`);
  await panelOf(page, "Ring ditch by the long barrow").getByRole("button", { name: "Suggest a change" }).click();
  await expect(panelOf(page, "Suggest a change")).toBeVisible();
  await moveLastPoint(page, 3);
  return { fake, keeping };
}

test("a member suggests a change, which is sent with the revision it was made on and listed as theirs", async ({
  page,
}) => {
  const { keeping } = await suggesting(page);
  await panelOf(page, "Suggest a change").getByRole("button", { name: "Send the suggestion" }).click();
  await expect(page).toHaveURL(/\/f\/f-ring/);
  await expect(toast(page, "Your suggestion is sent.")).toBeVisible();
  const sent = keeping.sent["POST suggestions"]?.[0] as { path: { points: unknown[] }; path_revision: number };
  expect(sent.path_revision).toBe(3);
  expect(sent.path.points).toHaveLength(3);
  const list = panelOf(page, "Ring ditch by the long barrow").getByRole("list", { name: "Suggested changes" });
  await expect(list.getByRole("button", { name: "Withdraw it" })).toBeVisible();
  await expect(list.getByRole("button", { name: "Accept" })).toHaveCount(0);
});

test("an unfinished suggestion stays on the map when the panel closes, and is asked about before marking", async ({
  page,
}) => {
  await suggesting(page);
  await panelOf(page, "Suggest a change").getByRole("button", { name: "Close panel" }).click();
  await expect(page).toHaveURL(/\/f\/f-ring/);
  const ring = page.getByRole("button", { name: "Carry on with your suggested change" });
  await expect(ring).toBeVisible();
  await expect(page.getByTestId("mark-path")).toHaveAttribute("data-unsaved", "true");

  await ring.click();
  await expect(page).toHaveURL(/\/mark\/suggest\/f-ring/);
  await expect(
    panelOf(page, "Suggest a change").getByText("Carrying on with the change you hadn't sent."),
  ).toBeVisible();
});

test("'Mark a finding' asks before it takes the map from an unfinished suggestion", async ({ page }) => {
  await suggesting(page);
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/\/f\/f-ring/);
  await page.getByRole("button", { name: "Mark a finding" }).click();
  const mark = panelOf(page, "Mark a finding");
  await expect(
    mark.getByText(
      "You have a suggested change to a finding's shape that isn't sent. Marking a finding would discard it.",
    ),
  ).toBeVisible();
  await mark.getByRole("button", { name: "Go back to it" }).click();
  await expect(page).toHaveURL(/\/mark\/suggest\/f-ring/);
  await expect(
    panelOf(page, "Suggest a change").getByText("Carrying on with the change you hadn't sent."),
  ).toBeVisible();
});

test("after 'Go back to it', Back then Forward leave the suggestion tool working", async ({ page }) => {
  await suggesting(page);
  await page.keyboard.press("Escape");
  await expect(page).toHaveURL(/\/f\/f-ring/);
  await page.getByRole("button", { name: "Mark a finding" }).click();
  await panelOf(page, "Mark a finding").getByRole("button", { name: "Go back to it" }).click();
  await expect(page).toHaveURL(/\/mark\/suggest\/f-ring/);
  await page.goBack();
  await expect(panelOf(page, "Mark a finding").getByRole("button", { name: "Go back to it" })).toBeVisible();
  await page.goForward();
  await expect(panelOf(page, "Suggest a change")).toBeVisible();
  await expect(page.getByRole("button", { name: "Carry on with your suggested change" })).toHaveCount(0);

  // The tool takes taps again: carried on from its end, a tap adds a point.
  await page.getByRole("button", { name: /^Point 3 of 3,/ }).click();
  await page.getByRole("button", { name: "Continue from this end" }).first().click();
  const at = (page.viewportSize()?.width ?? 0) < 720 ? { x: 120, y: 330 } : { x: 300, y: 450 };
  if ((page.viewportSize()?.width ?? 0) < 720) await page.touchscreen.tap(at.x, at.y);
  else await page.mouse.click(at.x, at.y);
  await expect(page.locator(".fc-path-handle")).toHaveCount(4);
});

test.describe("the keeper deciding", () => {
  test.use({ pageProblems: "page-errors" });

  test("accepts one after a refusal shown beside it, and declines another", async ({ page }) => {
    const mine = shapeSuggestionFixture();
    const theirs = shapeSuggestionFixture({ id: 72, by: EXPERT, kind: "reshaped", length_m: 230 });
    await fakeSession(page, THE_FINDER);
    const fake = await fakeFindingPage(
      page,
      lineFixture({ actions: FINDER_ACTIONS }, { suggestions: [theirs, mine] }),
      { me: THE_FINDER },
    );
    const keeping = await fakeKeeping(page, fake, { me: FINDER });
    await openMap(page, `/f/f-ring${VIEW}`);
    const panel = panelOf(page, "Ring ditch by the long barrow");
    const list = panel.getByRole("list", { name: "Suggested changes" });
    const card = (by: string) => list.getByRole("listitem").filter({ hasText: by });

    await card("Mary Anning").getByRole("button", { name: "Show on the map" }).click();
    await expect(card("Mary Anning").getByRole("button", { name: "Show on the map" })).toHaveAttribute(
      "aria-pressed",
      "true",
    );

    const refusal = "This change keeps 40% of the ground others gave second looks on within 25 m. It has to keep 80%.";
    keeping.refuseNextAccept(refusal);
    await card("Mary Anning").getByRole("button", { name: "Accept" }).click();
    await expect(card("Mary Anning").getByRole("alert")).toHaveText(refusal);

    await card("Dr Ditch").getByRole("button", { name: "Decline" }).click();
    await expect(toast(page, "The suggestion is declined.")).toBeVisible();
    await expect(card("Dr Ditch")).toHaveCount(0);

    await card("Mary Anning").getByRole("button", { name: "Accept" }).click();
    await expect(toast(page, "The suggested change is accepted")).toBeVisible();
    await expect(panel.getByRole("heading", { name: "Suggested changes" })).toHaveCount(0);
    await expect(panel.getByText("Suggested by Mary Anning")).toBeVisible();
    expect(keeping.sent["POST accept"]).toEqual([{ shape_revision: 3 }, { shape_revision: 3 }]);
  });
});

test.describe("handing a marking on", () => {
  test.use({ pageProblems: "page-errors" });

  test("the keeper offers it, an unknown handle is refused in one sentence, and the offer is shown", async ({
    page,
  }) => {
    await fakeSession(page, THE_FINDER);
    const fake = await fakeFindingPage(page, lineFixture({ actions: FINDER_ACTIONS }), { me: THE_FINDER });
    const keeping = await fakeKeeping(page, fake, { me: FINDER, people: { [OTHER.handle]: OTHER } });
    await openMap(page, `/f/f-ring${VIEW}`);
    const panel = panelOf(page, "Ring ditch by the long barrow");
    await panel.getByRole("button", { name: "Hand it on" }).click();
    const dialog = page.getByRole("dialog", { name: "Hand it on" });
    await dialog.getByLabel("Their handle").fill("NobodyByThisName");
    await dialog.getByRole("button", { name: "Offer it" }).click();
    await expect(dialog.getByRole("alert")).toHaveText(
      "It can't be offered to that handle. Check the handle and try again.",
    );
    await dialog.getByLabel("Their handle").fill(OTHER.handle);
    await dialog.getByRole("button", { name: "Offer it" }).click();
    await expect(dialog).toHaveCount(0);
    await expect(panel.getByText(/Offered to Mary Anning/)).toBeVisible();
    expect(keeping.sent["PUT offer"]).toEqual([{ handle: "NobodyByThisName" }, { handle: OTHER.handle }]);
  });

  for (const answer of ["Take it on", "No thanks"] as const) {
    test(`the person offered answers "${answer}"`, async ({ page }) => {
      await fakeSession(page, MEMBER);
      const offered = lineFixture({
        keeping: { offered_to: OTHER, offered_at: "2026-11-12T08:00:00Z" },
        actions: { ...lineFixture().actions, take_keeping: { allowed: true, reason: null } },
      });
      const fake = await fakeFindingPage(page, offered, { me: MEMBER });
      await fakeKeeping(page, fake, { me: OTHER });
      await openMap(page, `/f/f-ring${VIEW}`);
      const panel = panelOf(page, "Ring ditch by the long barrow");
      await expect(panel.getByText(/You've been asked to keep this marking/)).toBeVisible();
      await panel.getByRole("button", { name: answer }).click();
      await expect(panel.getByRole("button", { name: "Take it on" })).toHaveCount(0);
      if (answer === "Take it on") {
        await expect(panel.getByText(/Kept by Mary Anning/)).toBeVisible();
        await expect(panel.getByRole("button", { name: "Change the shape" })).toBeVisible();
      } else {
        await expect(panel.getByText(/Kept by/)).toHaveCount(0);
      }
    });
  }
});

test("an admin finds a marking without a keeper in the list and puts back an earlier shape", async ({ page }) => {
  await fakeSession(page, ADMIN);
  // The finding's page shows a moderator its own entries in the log.
  await fakeModeration(page);
  const orphaned = lineFixture({
    keeper: GONE,
    actions: {
      ...MODERATOR_ACTIONS,
      hand_on: { allowed: true, reason: null },
      remove_marking: { allowed: true, reason: null },
    },
  });
  const fake = await fakeFindingPage(page, orphaned, { me: ADMIN });
  const before = [offset(-100, 0), offset(0, -40)];
  const keeping = await fakeKeeping(page, fake, {
    me: ADMIN,
    orphaned: [
      {
        finding: findingSummary(
          {
            type: "Feature",
            geometry: { type: "Point", coordinates: [offset(0, 0).lon, offset(0, 0).lat] },
            properties: { public_id: "f-ring", tier: "seen", state: "open", obscured: false },
          },
          { title: "Ring ditch by the long barrow" },
        ),
        keeper: GONE,
        keeper_gone: "deleted",
      },
    ],
    earlier: [
      {
        revision: 3,
        kind: "extended",
        by: GONE,
        created_at: "2026-11-09T10:00:00Z",
        path_before: {
          closed: false,
          curve: "catmull-rom-centripetal-1",
          points: before.map(({ lon, lat }) => ({ lon, lat, kind: "corner" as const })),
        },
        restorable: true,
      },
    ],
  });
  await openMap(page, `/mod/markings${VIEW}`);
  const mod = panelOf(page, "Moderation");
  const list = mod.getByRole("list", { name: "Markings without a keeper" });
  await expect(list.getByText(/Kept by Former member, whose account is deleted/)).toBeVisible();
  await list.getByRole("link", { name: /Remove the marking/ }).click();

  const removal = panelOf(page, "Remove the marking");
  await expect(removal.getByText(/The finding, its second looks and its evidence stay/)).toBeVisible();
  await removal.getByRole("radio", { name: /As it was until 9 November 2026/ }).check();
  await removal.getByLabel("Why").fill("Drawn across a farm track after a dispute.");
  await removal.getByRole("button", { name: "Put this shape back" }).click();
  await expect(page).toHaveURL(/\/f\/f-ring/);
  await expect(toast(page, "The marking is taken back.")).toBeVisible();
  expect(keeping.sent["PUT marking"]).toEqual([
    { to_revision: 2, shape_revision: 3, reason: "Drawn across a farm track after a dispute." },
  ]);
});

test("a signed-out reader of a protected line is shown no suggestion and no keeping control", async ({ page }) => {
  const square: FindingDetail = squareFixture({ keeper: OTHER, actions: SIGNED_OUT_ACTIONS });
  const session = await fakeSession(page, null);
  await fakeFindingPage(page, square);
  await openMap(page, `/f/f-ring${VIEW}`);
  const panel = panelOf(page, "Ring ditch by the long barrow");
  await expect(panel.getByText(/Found by Ada Lovelace/)).toBeVisible();
  for (const name of [
    "Suggest a change",
    "Change the shape",
    "Hand it on",
    "Take it on",
    "Offer it to someone",
    "Remove the marking",
    "Show on the map",
  ]) {
    await expect(panel.getByRole("button", { name })).toHaveCount(0);
  }
  await expect(panel.getByRole("heading", { name: "Suggested changes" })).toHaveCount(0);
  await expect(panel.getByText(/keeper/i)).toHaveCount(0);

  // The tool's address shows them nothing of the shape either.
  await page.goto(`/mark/suggest/f-ring${VIEW}`);
  await expect(panelOf(page, "Suggest a change").getByText("Sign in to suggest a change")).toBeVisible();
  await expect(page.locator(".fc-path-handle")).toHaveCount(0);
  await expect(page.getByTestId("mark-path")).toHaveCount(0);
  const asked = session.requests.map((request) => new URL(request.url()).pathname);
  expect(asked.filter((path) => /suggestions|keeping|\/mod\//.test(path))).toEqual([]);
});

test.describe("refusals as the person meets them", () => {
  test.use({ pageProblems: "page-errors" });

  function sendButton(page: Page) {
    return panelOf(page, "Suggest a change").getByRole("button", { name: "Send the suggestion" });
  }

  test("a suggestion made while the keeper changed the shape keeps its drawing, and goes when told", async ({
    page,
  }) => {
    const { keeping } = await suggesting(page);
    keeping.changeShapeElsewhere();
    await sendButton(page).click();
    const panel = panelOf(page, "Suggest a change");
    await expect(panel.getByText(/Your suggestion hasn't been sent, and your drawing is still here/)).toBeVisible();
    await expect(page.locator(".fc-path-handle")).toHaveCount(3);
    await expect(panel.getByRole("button", { name: "Undo" })).toBeEnabled();
    await panel.getByRole("button", { name: "Send it against the shape as it is now" }).click();
    await expect(toast(page, "Your suggestion is sent.")).toBeVisible();
    expect(
      (keeping.sent["POST suggestions"] ?? []).map((body) => (body as { path_revision: number }).path_revision),
    ).toEqual([3, 4]);
  });

  test("a suggestion refused for too many waiting, or for the hourly limit, says why and keeps the drawing", async ({
    page,
  }) => {
    const crowd = Array.from({ length: 20 }, (_, index) =>
      shapeSuggestionFixture({
        id: 100 + index,
        by: { handle: `Walker${index}`, display_name: `Walker ${index}`, role: "member" },
      }),
    );
    const { keeping } = await suggesting(page, lineFixture({}, { suggestions: crowd }));
    await sendButton(page).click();
    await expect(toast(page, /20 suggestions waiting for its keeper/)).toBeVisible();
    await expect(page).toHaveURL(/\/mark\/suggest\/f-ring/);
    await expect(page.locator(".fc-path-handle")).toHaveCount(3);

    keeping.limitNext();
    await sendButton(page).click();
    await expect(toast(page, /You're doing that too often/)).toBeVisible();
    await expect(page.locator(".fc-path-handle")).toHaveCount(3);
  });

  test("an accept on a shape changed meanwhile is said beside the suggestion, which then asks as one behind", async ({
    page,
  }) => {
    await fakeSession(page, THE_FINDER);
    const fake = await fakeFindingPage(
      page,
      lineFixture({ actions: FINDER_ACTIONS }, { suggestions: [shapeSuggestionFixture()] }),
      { me: THE_FINDER },
    );
    const keeping = await fakeKeeping(page, fake, { me: FINDER });
    await openMap(page, `/f/f-ring${VIEW}`);
    const card = panelOf(page, "Ring ditch by the long barrow")
      .getByRole("list", { name: "Suggested changes" })
      .getByRole("listitem")
      .filter({ hasText: "Mary Anning" });
    keeping.changeShapeElsewhere();
    await card.getByRole("button", { name: "Accept" }).click();
    await expect(card.getByRole("alert")).toHaveText(/The shape was changed while you were looking/);
    await expect(card.getByText(/Made on an earlier shape/)).toBeVisible();
    await card.getByRole("button", { name: "Accept" }).click();
    await page
      .getByRole("dialog", { name: "Accept a suggestion made on an earlier shape?" })
      .getByRole("button", { name: "Accept it" })
      .click();
    await expect(toast(page, "The suggested change is accepted")).toBeVisible();
    expect(keeping.sent["POST accept"]).toEqual([{ shape_revision: 3 }, { shape_revision: 4 }]);
  });

  test("an offer to the person who keeps it already says so", async ({ page }) => {
    await fakeSession(page, THE_FINDER);
    const fake = await fakeFindingPage(page, lineFixture({ actions: FINDER_ACTIONS }), { me: THE_FINDER });
    await fakeKeeping(page, fake, { me: FINDER, people: { [FINDER.handle]: FINDER } });
    await openMap(page, `/f/f-ring${VIEW}`);
    await panelOf(page, "Ring ditch by the long barrow").getByRole("button", { name: "Hand it on" }).click();
    const dialog = page.getByRole("dialog", { name: "Hand it on" });
    await dialog.getByLabel("Their handle").fill(FINDER.handle);
    await dialog.getByRole("button", { name: "Offer it" }).click();
    await expect(dialog.getByRole("alert")).toHaveText("They keep this marking already.");
  });

  for (const refused of ["not orphaned", "changed meanwhile"] as const) {
    test(`a removal of a marking ${refused} says so and keeps the reason`, async ({ page }) => {
      await fakeSession(page, ADMIN);
      await fakeModeration(page);
      const fake = await fakeFindingPage(
        page,
        lineFixture({
          keeper: GONE,
          actions: {
            ...MODERATOR_ACTIONS,
            hand_on: { allowed: true, reason: null },
            remove_marking: { allowed: true, reason: null },
          },
        }),
        { me: ADMIN },
      );
      const keeping = await fakeKeeping(page, fake, { me: ADMIN, earlier: [], isOrphaned: refused !== "not orphaned" });
      await openMap(page, `/mod/markings/f-ring${VIEW}`);
      const removal = panelOf(page, "Remove the marking");
      await removal.getByRole("radio", { name: /No line or shape/ }).check();
      await removal.getByLabel("Why").fill("Spam drawn over the down.");
      if (refused === "changed meanwhile") keeping.changeShapeElsewhere();
      await removal.getByRole("button", { name: "Remove the marking" }).click();
      await expect(removal.getByRole("alert")).toHaveText(
        refused === "not orphaned" ? /keeper is still a member/ : /changed while you were looking/,
      );
      await expect(removal.getByLabel("Why")).toHaveValue("Spam drawn over the down.");
    });
  }
});
