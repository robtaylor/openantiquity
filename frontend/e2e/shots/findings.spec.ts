import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import { fakeSession, meWith } from "../support/account.js";
import { openMap } from "../support/app.js";
import { fakeFindings } from "../support/findings.js";
import { apiRoute, stubNetwork } from "../support/network.js";

/**
 * Screenshots of Explore and of marking a finding, taken with `pnpm shots`,
 * for looking at the design at desktop and phone width: every panel and
 * state. These stub every tile, so the map behind is plain, and they assert
 * nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

const VIEW = "#m=15/51.4286/-1.8542/0/0&v=composite";

async function shoot(page: Page, name: string): Promise<void> {
  await page.waitForTimeout(500);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `findings-${name}-${size?.width}x${size?.height}.png`) });
}

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("explore", async ({ page }) => {
  await fakeFindings(page);
  await openMap(page, `/${VIEW}`);
  await page.getByRole("list", { name: "Findings in view" }).waitFor();
  await shoot(page, "01-explore");
  if (isPhone(page)) {
    await page.getByRole("button", { name: /Press to resize/ }).click();
    await shoot(page, "02-explore-half");
  }
  await page.getByRole("button", { name: "Filters" }).click();
  await shoot(page, "03-explore-filters");
  await page.getByRole("group", { name: "Step" }).getByRole("button", { name: "Seen by others" }).click();
  await shoot(page, "04-explore-filtered");
});

test("explore states", async ({ page }) => {
  await fakeFindings(page, []);
  await openMap(page, `/${VIEW}`);
  if (isPhone(page)) await page.getByRole("button", { name: /Press to resize/ }).click();
  await page.getByRole("heading", { name: "No findings here yet" }).waitFor();
  await shoot(page, "05-explore-empty");

  await page.unroute(apiRoute("/findings"));
  await page.route(apiRoute("/findings"), (route) =>
    route.fulfill({
      status: 500,
      contentType: "application/json",
      body: '{"error":{"code":"x","message":"The database isn\'t answering."}}',
    }),
  );
  await page.reload();
  if (isPhone(page)) await page.getByRole("button", { name: /Press to resize/ }).click();
  await page.getByRole("heading", { name: "The findings couldn't be loaded" }).waitFor({ timeout: 15_000 });
  await shoot(page, "06-explore-error");

  await page.goto(`/#m=7/52/-1.8/0/0&v=composite`);
  if (isPhone(page)) await page.getByRole("button", { name: /Press to resize/ }).click();
  await page.getByRole("heading", { name: "Zoom in to see findings" }).waitFor();
  await shoot(page, "07-explore-zoomed-out");
});

test("marking", async ({ page }) => {
  await fakeFindings(page);
  await fakeSession(page, meWith());
  await openMap(page, `/?panel=none${VIEW}`);
  await page.getByRole("button", { name: "Mark a finding" }).click();
  await shoot(page, "10-mark-placing");

  const panel = page.getByRole("complementary", { name: "Mark a finding" });
  // The first point at the cross, then a tap at each further corner.
  await page.getByRole("button", { name: "Add a point at the cross" }).click();
  const first = await page.getByRole("button", { name: /^Point 1 of / }).boundingBox();
  if (first) {
    const cx = first.x + first.width / 2;
    const cy = first.y + first.height / 2;
    const corners: Array<[number, number]> = [
      [100, 0],
      [110, 70],
    ];
    for (const [dx, dy] of corners) {
      await page.mouse.click(cx + dx, cy + dy);
    }
  }
  await shoot(page, "13-mark-outline");
  // Closing it stops drawing, and on a phone the sheet rises for the form.
  await page.getByRole("button", { name: "Close the shape" }).click();
  await shoot(page, "11-mark-form");
  await panel.getByRole("radio", { name: "Round barrow or mound" }).click();
  await shoot(page, "12-mark-protected");
  await panel.getByText(/This map is for earthworks, not objects/).scrollIntoViewIfNeeded();
  await shoot(page, "12b-mark-finds-notice");
  await panel.getByRole("button", { name: "Save finding" }).scrollIntoViewIfNeeded();
  await shoot(page, "14-mark-outline-closed");
});

test("marking signed out, and failing", async ({ page }) => {
  const findings = await fakeFindings(page);
  await fakeSession(page);
  await openMap(page, `/mark${VIEW}`);
  const panel = page.getByRole("complementary", { name: "Mark a finding" });
  await page.getByRole("button", { name: "Place it here" }).click();
  await panel.getByRole("radio", { name: "Enclosure" }).click();
  await panel.getByRole("button", { name: "Save finding" }).click();
  await page.getByRole("dialog", { name: "Sign in" }).waitFor();
  await shoot(page, "20-mark-signin");
  await page.getByRole("dialog", { name: "Sign in" }).getByRole("button", { name: "Close" }).click();
  await shoot(page, "21-mark-draft");
  await page.goto(`/${VIEW}`);
  await page.getByRole("list", { name: "Your marks" }).waitFor();
  await shoot(page, "22-explore-with-draft");

  // Signed in, a save the server refuses.
  await page.evaluate(() => localStorage.clear());
  await fakeSession(page, meWith());
  findings.failNextCreate(422, "outside_british_isles", "That position is outside them.");
  await page.goto(`/mark${VIEW}`);
  await page.getByRole("button", { name: "Place it here" }).click();
  await panel.getByRole("radio", { name: "Enclosure" }).click();
  await panel.getByRole("button", { name: "Save finding" }).click();
  await page.getByText("Your finding couldn't be saved.").waitFor();
  await shoot(page, "23-mark-refused");

  // A protected finding's title that says where it is: refused, and said beside the title.
  await page.route(apiRoute("/findings"), (route) =>
    route.request().method() === "POST"
      ? route.fulfill({
          status: 422,
          contentType: "application/json",
          body: JSON.stringify({
            error: {
              code: "position_in_text",
              message: "A protected or restricted finding's title and description can't say where it is.",
              details: [{ field: "body.title", message: "The title gives a position." }],
            },
          }),
        })
      : route.fallback(),
  );
  // The same address again changes only the hash, so the page is loaded afresh to start a new mark.
  await page.reload();
  await page.getByRole("button", { name: "Place it here" }).click();
  await panel.getByRole("radio", { name: "Round barrow or mound" }).click();
  await panel.getByLabel("Title").fill("Barrow at SU 1025 6996");
  await panel.getByRole("button", { name: "Save finding" }).click();
  await panel.getByText(/out of the title/).waitFor();
  await panel.getByLabel("Title").scrollIntoViewIfNeeded();
  await shoot(page, "24-mark-position-refused");
});
