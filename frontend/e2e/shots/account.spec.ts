import { mkdirSync } from "node:fs";
import { join } from "node:path";
import { type Page, test } from "@playwright/test";
import { DRAFTS_STORAGE_KEY, DRAFTS_VERSION } from "../../src/features/drafts/store.js";
import { answerJson, fakeSession, meWith, newcomerFixture } from "../support/account.js";
import { openMap } from "../support/app.js";
import { apiRoute, stubNetwork } from "../support/network.js";

/**
 * Screenshots of joining and drafts, taken with `pnpm shots`, for looking at
 * the design: every sheet, page and state at desktop and phone width. These
 * stub every tile, so the map behind is plain, and they assert nothing.
 */

const OUT = process.env.FIELDCLUB_SHOTS_DIR ?? "test-results/shots";
mkdirSync(OUT, { recursive: true });

async function shoot(page: Page, name: string): Promise<void> {
  // Let the dialog's entrance and any fade finish.
  await page.waitForTimeout(400);
  const size = page.viewportSize();
  await page.screenshot({ path: join(OUT, `account-${name}-${size?.width}x${size?.height}.png`) });
}

function never(): Promise<never> {
  return new Promise(() => {});
}

/** Two drafts, made signed out unless `owner` says whose they are. */
async function seed(page: Page, failed = false, owner: object = { signedOut: "shot" }): Promise<void> {
  const now = new Date().toISOString();
  const drafts = ["Ring ditch by the barn", "Hollow way to the ford"].map((note, index) => ({
    id: `shot-${index}`,
    kind: "fixture_probe",
    data: { note },
    owner,
    createdAt: now,
    updatedAt: now,
    state: failed ? "failed" : "waiting",
    ...(failed ? { failure: { code: "validation_error", message: "That square isn't in Britain." } } : {}),
  }));
  await page.evaluate(([key, value]) => localStorage.setItem(key, value), [
    DRAFTS_STORAGE_KEY,
    JSON.stringify({ version: DRAFTS_VERSION, epoch: "shot", drafts }),
  ] as const);
}

test.beforeEach(async ({ page }) => {
  await stubNetwork(page);
});

test("sign-in sheet", async ({ page }) => {
  await fakeSession(page);
  await answerJson(page, "/auth/email/start", { status: "sent", message: "x" }, { status: 202 });
  await openMap(page, "/account");
  await page.getByRole("complementary", { name: "Account" }).getByRole("button", { name: "Sign in" }).click();
  await shoot(page, "signin");
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await sheet.getByRole("button", { name: "Email me a link" }).click();
  await sheet.getByRole("button", { name: "Email me a link" }).click();
  await shoot(page, "signin-email-error");
  await sheet.getByLabel("Email address").fill("ann@example.org");
  await sheet.getByRole("button", { name: "Email me a link" }).click();
  await sheet.getByText("Check your inbox").waitFor();
  await shoot(page, "signin-email-sent");
});

test("sign-in sheet after a failed provider sign-in", async ({ page }) => {
  await fakeSession(page);
  await openMap(page, "/?signin_error=state_mismatch");
  await page.getByRole("dialog", { name: "Sign in" }).waitFor();
  await shoot(page, "signin-error");
});

test("welcome sheet", async ({ page }) => {
  await fakeSession(page, newcomerFixture());
  await openMap(page, "/");
  const sheet = page.getByRole("dialog", { name: "Welcome to Open Antiquity" });
  await sheet.waitFor();
  await shoot(page, "welcome");
  await sheet.getByRole("button", { name: "Join Open Antiquity" }).click();
  await shoot(page, "welcome-errors");
  await sheet.getByRole("radio", { name: "16 or 17" }).click();
  await shoot(page, "welcome-16-17");
  await sheet.getByRole("radio", { name: "Under 16" }).click();
  await shoot(page, "welcome-under-16");
});

test("account page", async ({ page }) => {
  const session = await fakeSession(page);
  await openMap(page, "/account");
  await page.getByRole("heading", { name: "You're not signed in" }).waitFor();
  await shoot(page, "page-signed-out");

  session.set(meWith({ bio: "Walks the Ridgeway on Sundays, looking for lynchets." }));
  await page.reload();
  await page.getByText("@QuietBarrow42").waitFor();
  await shoot(page, "page-signed-in");
  if ((page.viewportSize()?.width ?? 0) < 720) {
    const handle = page.getByRole("button", { name: /Panel is/ });
    await handle.click();
    await shoot(page, "page-signed-in-full");
    await handle.click();
    await shoot(page, "page-signed-in-peek");
    await handle.click();
  }

  await page.getByRole("button", { name: "Delete my account" }).click();
  await page.getByRole("dialog", { name: "Delete your account?" }).waitFor();
  await shoot(page, "delete-dialog");
});

test("account page while loading, failed, and owing the welcome step", async ({ page }) => {
  let mode: "slow" | "down" | "newcomer" = "slow";
  await page.route(apiRoute("/auth/me"), async (route) => {
    if (mode === "slow") return never();
    if (mode === "down") {
      const error = { code: "unavailable", message: "The server isn't answering right now. It may be restarting." };
      return route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ error }) });
    }
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(newcomerFixture()) });
  });
  await openMap(page, "/account");
  await shoot(page, "page-loading");
  mode = "down";
  await page.reload();
  await page.getByRole("heading", { name: "We couldn't check whether you're signed in" }).waitFor();
  await shoot(page, "page-failed");
  mode = "newcomer";
  await page.reload();
  const welcome = page.getByRole("dialog", { name: "Welcome to Open Antiquity" });
  await welcome.getByRole("button", { name: "Close" }).click();
  await shoot(page, "page-newcomer");
});

test("emailed link page", async ({ page }) => {
  await fakeSession(page);
  let answer: "slow" | "confirm" | "invalid" | "down" = "slow";
  await page.route(apiRoute("/auth/email/verify"), async (route) => {
    const codes = {
      confirm: [409, "confirmation_required", { email: "a***@example.org" }],
      invalid: [400, "link_invalid", undefined],
      down: [503, "unavailable", undefined],
    } as const;
    if (answer === "slow") return never();
    const [status, code, details] = codes[answer];
    const error = { code, message: "The server isn't answering right now. It may be restarting.", details };
    return route.fulfill({ status, contentType: "application/json", body: JSON.stringify({ error }) });
  });
  const shown = {
    slow: "Checking your link…",
    confirm: "Sign in as a***@example.org?",
    invalid: "This link can't be used",
    down: "We couldn't check your link",
  } as const;
  for (const state of ["slow", "confirm", "invalid", "down"] as const) {
    answer = state;
    // A full load each time: a change of fragment alone wouldn't reload the page.
    await page.goto("about:blank");
    await page.goto("/signin/email?next=%2F#token=shot");
    await page.getByRole("complementary", { name: "Signing in" }).getByText(shown[state]).waitFor();
    await shoot(page, `link-${state}`);
  }
  await page.goto("/signin/email");
  await page.getByRole("heading", { name: "This link is incomplete" }).waitFor();
  await shoot(page, "link-missing");
});

test("drafts bar", async ({ page }) => {
  const session = await fakeSession(page);
  await openMap(page, "/");
  await seed(page);
  await page.reload();
  await page.getByRole("region", { name: "Drafts" }).waitFor();
  await shoot(page, "drafts-bar");
  await page.getByRole("button", { name: "Show drafts" }).click();
  await shoot(page, "drafts-list");
  await page.goto("/account");
  await page.getByRole("region", { name: "Drafts" }).waitFor();
  await shoot(page, "drafts-with-panel");

  session.set(meWith());
  await seed(page, true, { account: meWith().created_at });
  await page.goto("/");
  await page.getByRole("region", { name: "Drafts" }).waitFor();
  await page.getByRole("button", { name: "Show drafts" }).click();
  await shoot(page, "drafts-failed");

  // Someone else's, left behind: asked about, not saved.
  await seed(page, false, { account: "someone-else" });
  await page.goto("/");
  await page.getByRole("button", { name: "Check" }).waitFor();
  await shoot(page, "drafts-others-bar");
  await page.getByRole("button", { name: "Check" }).click();
  await shoot(page, "drafts-others-list");
});

test("signing out and deleting with drafts in the browser", async ({ page }) => {
  await fakeSession(page, meWith());
  await openMap(page, "/account");
  await seed(page, false, { account: "someone-else" });
  await page.reload();
  await page.getByText("@QuietBarrow42").waitFor();
  await page.getByRole("button", { name: "Sign out" }).click();
  await page.getByRole("dialog", { name: "Keep your drafts?" }).waitFor();
  await shoot(page, "signout-dialog");
  await page.keyboard.press("Escape");
  await page.getByRole("button", { name: "Delete my account" }).click();
  await page.getByRole("dialog", { name: "Delete your account?" }).waitFor();
  await shoot(page, "delete-dialog-with-drafts");
});

test("Account item when signed in", async ({ page }) => {
  await fakeSession(page, meWith());
  await openMap(page, "/");
  if ((page.viewportSize()?.width ?? 0) < 720) await page.getByRole("button", { name: "More" }).click();
  await shoot(page, "rail-avatar");
});
