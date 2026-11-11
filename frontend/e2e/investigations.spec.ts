import type { Locator, Page } from "@playwright/test";
import { AVEBURY_AREA, itemFinding } from "../src/test/fixtures/investigations.js";
import { fakeSession, meFixture } from "./support/account.js";
import { openMap } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { ADA, GUS, MARY, serveInvestigations } from "./support/investigations.js";

/**
 * Investigations, the shared notebook tied to the map, in fixture mode: the
 * list, a notebook's page, adding to one from a finding's page, reordering,
 * members and publishing. Every investigation route is answered by the
 * shared in-memory stand-in, which keeps the backend's rules.
 */

function panel(page: Page, title: string | RegExp): Locator {
  return page.getByRole("complementary", { name: title });
}

/** On a phone, open the sheet the whole way, so what's below the fold can be reached. */
async function openSheet(page: Page): Promise<void> {
  if ((page.viewportSize()?.width ?? 0) >= 720) return;
  const sheet = page.locator(".fc-sheet");
  const handle = sheet.getByRole("button", { name: /Press to resize/ });
  await handle.focus();
  while ((await sheet.getAttribute("data-stop")) !== "full") await page.keyboard.press("ArrowUp");
}

test("starts an investigation, adds a note and a finding, reorders them, publishes it and sees it listed signed out", async ({
  page,
}) => {
  const session = await fakeSession(page, meFixture());
  const fake = await serveInvestigations(page, { me: () => (session.current() ? ADA : null) });

  await openMap(page, "/investigations");
  const list = panel(page, "Investigations");
  await expect(list.getByRole("tab", { name: "Yours", selected: true })).toBeVisible();
  await expect(list.getByText("You haven't started one yet")).toBeVisible();

  await list.getByLabel("Start an investigation").fill("Barrows of Overton Down");
  await list.getByRole("button", { name: "Start" }).click();
  await expect(page).toHaveURL(/\/i\/inv1/);
  const notebook = panel(page, "Barrows of Overton Down");
  await expect(notebook.getByText("Nothing in it yet").first()).toBeVisible();

  // A note, from the notebook itself.
  await notebook.getByRole("button", { name: "Add a note" }).click();
  const dialog = page.getByRole("dialog", { name: "Add a note" });
  await dialog.getByLabel("Note").fill("## First walk\n\nThe **north** ditch is *faint*.\n\n- check the 1888 map");
  await dialog.getByRole("button", { name: "Add the note" }).click();
  await expect(notebook.getByRole("heading", { name: "First walk" })).toBeVisible();
  await expect(notebook.locator("strong", { hasText: "north" })).toBeVisible();

  // A finding, from its own page.
  await page.goto(`/f/${itemFinding().public_id}`);
  const finding = panel(page, `Finding ${itemFinding().public_id}`);
  await finding.getByRole("button", { name: "Add to an investigation" }).click();
  const chooser = page.getByRole("dialog", { name: "Add to an investigation" });
  await expect(chooser.getByRole("radio", { name: /Barrows of Overton Down/ })).toBeChecked();
  await chooser.getByRole("button", { name: "Add it" }).click();
  await expect(page.getByText("Added to “Barrows of Overton Down”.")).toBeVisible();
  await page.getByRole("button", { name: "Open it" }).click();
  await expect(page).toHaveURL(/\/i\/inv1/);

  const items = notebook.locator(".fc-inv-items > li");
  await expect(items).toHaveCount(2);
  await expect(items.nth(1)).toContainText("Round barrow on Overton Hill");

  // Up by its button, then back down by the keyboard on its handle, each saved.
  await notebook.getByRole("button", { name: "Move “Round barrow on Overton Hill” up" }).click();
  await expect(items.nth(0)).toContainText("Round barrow on Overton Hill");
  await expect.poll(() => fake.store.get("inv1")?.items.map((item) => item.kind)).toEqual(["finding", "note"]);
  const handle = notebook.getByRole("button", { name: /^Move “Round barrow on Overton Hill”, place 1 of 2/ });
  await handle.focus();
  await page.keyboard.press("ArrowDown");
  await expect(items.nth(1)).toContainText("Round barrow on Overton Hill");
  await expect(
    notebook.getByRole("button", { name: /^Move “Round barrow on Overton Hill”, place 2 of 2/ }),
  ).toBeFocused();
  await expect.poll(() => fake.store.get("inv1")?.items.map((item) => item.kind)).toEqual(["note", "finding"]);

  // Publishing is a deliberate act, said in one sentence first.
  await openSheet(page);
  await notebook.getByRole("button", { name: "Publish it" }).click();
  const publish = page.getByRole("dialog", { name: "Publish this investigation?" });
  await expect(publish).toContainText("lists it for everyone");
  await publish.getByRole("button", { name: "Publish it" }).click();
  await expect(notebook.getByText("Public.", { exact: false }).first()).toBeVisible();
  expect(fake.store.get("inv1")?.visibility).toBe("public");

  // Signed out, it is in the public list.
  session.set(null);
  await openMap(page, "/investigations");
  const signedOut = panel(page, "Investigations");
  await expect(signedOut.getByRole("tab", { name: "Public", selected: true })).toBeVisible();
  await expect(signedOut.getByRole("link", { name: /Barrows of Overton Down/ })).toBeVisible();
});

test.describe("when the server refuses", () => {
  // A refused request is logged by the browser as a console error, which this test expects.
  test.use({ pageProblems: "page-errors" });

  test("drags an item to a new place, and puts it back with a toast when the server refuses", async ({ page }) => {
    const session = await fakeSession(page, meFixture());
    const fake = await serveInvestigations(page, { me: () => (session.current() ? ADA : null) });
    fake.seed(
      { public_id: "inv9", title: "Ridges by the river", owner: ADA, visibility: "public", area: AVEBURY_AREA },
      [
        { kind: "note", note: "Alpha note" },
        { kind: "note", note: "Bravo note" },
        { kind: "note", note: "Charlie note" },
      ],
    );
    await openMap(page, "/i/inv9");
    const notebook = panel(page, "Ridges by the river");
    const items = notebook.locator(".fc-inv-items > li");
    await expect(items).toHaveCount(3);
    await openSheet(page);

    const handle = notebook.getByRole("button", { name: /^Move “Alpha note”, place/ });
    const target = await items.nth(2).boundingBox();
    if (!target) throw new Error("The last item isn't on screen");
    await handle.hover();
    await page.mouse.down();
    await page.mouse.move(target.x + 40, target.y + target.height * 0.8, { steps: 8 });
    await page.mouse.up();
    await expect(items.nth(2)).toContainText("Alpha note");
    await expect
      .poll(() => fake.store.get("inv9")?.items.map((item) => item.note))
      .toEqual(["Bravo note", "Charlie note", "Alpha note"]);

    fake.failNext("POST", /\/move$/);
    await notebook.getByRole("button", { name: "Move “Charlie note” up" }).click();
    await expect(page.getByText(/The new order couldn't be saved/)).toBeVisible();
    await expect(items.nth(1)).toContainText("Charlie note");
    await expect(items.nth(0)).toContainText("Bravo note");
  });
});

test("explains that inviting needs it public or unlisted, invites by handle, and asks before removing", async ({
  page,
}) => {
  const session = await fakeSession(page, meFixture());
  const fake = await serveInvestigations(page, { me: () => (session.current() ? ADA : null) });
  fake.seed({ public_id: "inv5", title: "Hollow ways", owner: ADA });
  await openMap(page, "/i/inv5");
  const notebook = panel(page, "Hollow ways");
  await openSheet(page);
  await expect(notebook.getByText(/A private investigation has one member, you/)).toBeVisible();
  await expect(notebook.getByLabel("Invite someone by their handle")).toHaveCount(0);

  await notebook.getByRole("button", { name: "Make it unlisted" }).click();
  await page
    .getByRole("dialog", { name: "Make it unlisted?" })
    .getByRole("button", { name: "Make it unlisted" })
    .click();
  await notebook.getByLabel("Invite someone by their handle").fill("@KeenLynchet7");
  await notebook.getByRole("button", { name: "Invite", exact: true }).click();
  await expect(
    notebook
      .getByText("Reader · invited, hasn't accepted yet")
      .or(notebook.getByText("Editor · invited, hasn't accepted yet")),
  ).toBeVisible();
  // With someone invited, it can't be made private, so that isn't offered.
  await expect(notebook.getByRole("button", { name: "Make it private" })).toHaveCount(0);

  await notebook.getByRole("button", { name: `Take back ${MARY.display_name}` }).click();
  const confirm = page.getByRole("dialog", { name: "Take back this invitation?" });
  await confirm.getByRole("button", { name: "Take it back" }).click();
  await expect(notebook.getByText(MARY.display_name)).toHaveCount(0);
  expect(fake.store.get("inv5")?.members).toHaveLength(1);
});

test("an invited person accepts from the list, and items they may not see say so in a line", async ({ page }) => {
  const mary = meFixture({ id: 7, handle: MARY.handle, display_name: MARY.display_name });
  const session = await fakeSession(page, mary);
  const fake = await serveInvestigations(page, { me: () => (session.current() ? MARY : null) });
  fake.seed({ public_id: "inv7", title: "Enclosures of the Kennet", owner: GUS, visibility: "unlisted" });
  fake.invite("inv7", MARY, "editor");
  const stored = fake.store.get("inv7");
  stored?.items.push({
    id: 900,
    kind: "finding",
    position: 0,
    title: null,
    note: null,
    unavailable: "withdrawn",
    added_by: GUS,
    created_at: "2026-11-10T10:00:00Z",
  });

  await openMap(page, "/investigations?list=invited");
  const list = panel(page, "Investigations");
  await expect(list.getByRole("link", { name: /Enclosures of the Kennet/ })).toBeVisible();
  await list.getByRole("button", { name: "Accept" }).click();
  await expect(page).toHaveURL(/\/i\/inv7/);
  const notebook = panel(page, "Enclosures of the Kennet");
  await expect(notebook.getByText("Its finder has withdrawn this finding.")).toBeVisible();
  await expect(notebook.getByRole("button", { name: "Add a note" })).toBeVisible();
  await openSheet(page);
  await notebook.getByRole("button", { name: "Leave this investigation" }).click();
  await expect(page.getByRole("dialog", { name: "Leave this investigation?" })).toBeVisible();
});
