import type { Page } from "@playwright/test";
import { answerJson, fakeSession, meWith, newcomerFixture } from "./support/account.js";
import { boxOf, describeFocus, openMap, tabTo } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";
import { apiRoute } from "./support/network.js";

/**
 * Joining, in fixture mode: the sign-in sheet, a failed provider sign-in,
 * the emailed link, the welcome sheet and the account page, at desktop and
 * phone width and by keyboard alone. `e2e-full/` signs in against a real
 * backend.
 */

const TOKEN = "e2e-token-that-must-not-leak";

function isPhone(page: Page): boolean {
  return (page.viewportSize()?.width ?? 0) < 720;
}

async function focusIsInside(page: Page, selector: string): Promise<boolean> {
  return page.evaluate((query) => document.activeElement?.closest(query) !== null, selector);
}

/** Every Tab press keeps focus inside the open dialog. */
async function expectFocusTrapped(page: Page, presses = 12): Promise<void> {
  for (let press = 0; press < presses; press++) {
    await page.keyboard.press("Tab");
    expect(
      await focusIsInside(page, "dialog[open]"),
      `Tab ${press + 1} left the dialog: ${await describeFocus(page)}`,
    ).toBe(true);
  }
}

/** A dialog that fits the window, and on a phone rises from its foot. */
async function expectSheetFits(page: Page, name: string): Promise<void> {
  const dialog = page.getByRole("dialog", { name });
  // Wait out the dialog's 180 ms entrance, which starts it 8 px low.
  await expect.poll(() => dialog.evaluate((element) => element.getAnimations().length)).toBe(0);
  const box = await boxOf(dialog);
  const viewport = page.viewportSize() ?? { width: 0, height: 0 };
  expect(box.x).toBeGreaterThanOrEqual(0);
  expect(box.x + box.width).toBeLessThanOrEqual(viewport.width + 0.5);
  expect(box.y).toBeGreaterThanOrEqual(0);
  if (isPhone(page)) expect(Math.round(box.y + box.height)).toBe(viewport.height);
  const overflows = await page.evaluate(() => document.documentElement.scrollWidth > window.innerWidth);
  expect(overflows, "the page scrolls sideways").toBe(false);
}

test("signs in from the account page by keyboard alone, and Escape puts focus back", async ({ page }) => {
  await fakeSession(page);
  await openMap(page, "/account");
  const panel = page.getByRole("complementary", { name: "Account" });
  await expect(panel.getByRole("heading", { name: "You're not signed in" })).toBeVisible();

  const signIn = panel.getByRole("button", { name: "Sign in" });
  await tabTo(page, signIn);
  await page.keyboard.press("Enter");
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await expect(sheet).toBeVisible();
  expect(await focusIsInside(page, "dialog[open]")).toBe(true);
  await expectSheetFits(page, "Sign in");

  const google = sheet.getByRole("link", { name: "Continue with Google" });
  const href = new URL((await google.getAttribute("href")) ?? "", "http://localhost");
  expect(href.pathname).toBe("/api/v1/auth/oauth/google/start");
  expect(href.searchParams.get("next")).toMatch(/^\/account#m=/);
  await expect(sheet.getByRole("link", { name: "Sign in with OpenStreetMap" })).toBeVisible();
  await expect(sheet.getByText("Continue with Apple")).toHaveCount(0);
  await expectFocusTrapped(page);

  await page.keyboard.press("Escape");
  await expect(sheet).toBeHidden();
  await expect(signIn).toBeFocused();
});

test("explains a failed provider sign-in, then takes the code out of the address", async ({ page }) => {
  await fakeSession(page);
  await openMap(page, "/?panel=layers&signin_error=state_mismatch#m=13/51.4/-1.85/0/0&v=composite");
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await expect(sheet.getByRole("alert")).toContainText("That sign-in timed out");
  await expect(page).not.toHaveURL(/signin_error/);
  await expect(page).toHaveURL(/\?panel=layers#m=13\/51\.4\/-1\.85\//);
  await expectSheetFits(page, "Sign in");
});

test("gives a general message for a code it doesn't know, and never shows it", async ({ page }) => {
  await fakeSession(page);
  await openMap(page, "/?signin_error=Your%20account%20is%20hacked%2C%20call%2001234");
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await expect(sheet.getByRole("alert")).toContainText("Signing in didn't work");
  await expect(page.getByText(/hacked|01234/)).toHaveCount(0);
  await expect(page).not.toHaveURL(/signin_error/);
});

test("emails a link, and says the same thing whatever the address", async ({ page }) => {
  await fakeSession(page);
  const sent: unknown[] = [];
  await page.route(apiRoute("/auth/email/start"), (route) => {
    sent.push(route.request().postDataJSON());
    return route.fulfill({ status: 202, contentType: "application/json", body: '{"status":"sent","message":"x"}' });
  });
  await openMap(page, "/account");
  await page.getByRole("complementary", { name: "Account" }).getByRole("button", { name: "Sign in" }).click();
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await sheet.getByRole("button", { name: "Email me a link" }).click();
  await sheet.getByLabel("Email address").fill("ann@example.org");
  await sheet.getByLabel("Email address").press("Enter");
  await expect(sheet.getByText("Check your inbox")).toBeVisible();
  expect(sent).toEqual([{ email: "ann@example.org", next: expect.stringMatching(/^\/account#m=/) }]);
  await expectSheetFits(page, "Sign in");
});

test.describe("the emailed link", () => {
  // The browser logs the 409 and 400 answers these tests are built on.
  test.use({ pageProblems: "page-errors" });

  test("asks for the address of a link from another browser, and keeps the token to the exchange", async ({ page }) => {
    const session = await fakeSession(page);
    const verifies: Array<{ token: string; email?: string }> = [];
    await page.route(apiRoute("/auth/email/verify"), (route) => {
      const body = route.request().postDataJSON() as { token: string; email?: string };
      verifies.push(body);
      if (body.email === undefined) {
        const error = { code: "confirmation_required", message: "x", details: { email: "a***@example.org" } };
        return route.fulfill({ status: 409, contentType: "application/json", body: JSON.stringify({ error }) });
      }
      session.set(meWith());
      const reply = { ...meWith(), asked_here: false };
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(reply) });
    });

    await page.goto(`/signin/email?next=%2Ff%2Fabc#token=${TOKEN}`);
    expect(page.url()).not.toContain(TOKEN);
    const panel = page.getByRole("complementary", { name: "Signing in" });
    await expect(panel.getByRole("heading", { name: "Which email address is this link for?" })).toBeVisible();
    await expect(panel).not.toContainText("a***@example.org");
    await page.waitForTimeout(500);
    expect(verifies).toEqual([{ token: TOKEN }]);

    const field = panel.getByLabel("Your email address");
    await tabTo(page, field);
    await page.keyboard.type("ada@example.org");
    await page.keyboard.press("Enter");
    await expect(page).toHaveURL(/\/f\/abc(#|$)/);
    expect(verifies).toEqual([{ token: TOKEN }, { token: TOKEN, email: "ada@example.org" }]);

    // The token went to the exchange and nowhere else.
    for (const request of session.requests) {
      if (new URL(request.url()).pathname === "/api/v1/auth/email/verify") continue;
      expect(request.url()).not.toContain(TOKEN);
      expect(request.postData() ?? "").not.toContain(TOKEN);
    }
    const stored = await page.evaluate(
      () => JSON.stringify({ ...localStorage }) + JSON.stringify({ ...sessionStorage }),
    );
    expect(stored).not.toContain(TOKEN);
    expect(page.url()).not.toContain(TOKEN);
    if (!isPhone(page)) {
      await expect(page.getByRole("navigation", { name: "Modes" }).getByTestId("account-avatar")).toHaveText("AL");
    }
  });

  for (const [label, next] of [
    ["another origin", "https://evil.example/"],
    ["scheme-relative", "//evil.example"],
    ["backslashes", "/\\\\evil.example"],
    ["javascript:", "javascript:alert(document.domain)"],
    ["an encoded slash pair", "/%2F%2Fevil.example"],
  ] as const) {
    test(`stays on the site when next is ${label}`, async ({ page, baseURL }) => {
      const session = await fakeSession(page);
      await page.route(apiRoute("/auth/email/verify"), (route) => {
        session.set(meWith());
        return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(meWith()) });
      });
      await page.goto(`/signin/email?next=${encodeURIComponent(next)}#token=${TOKEN}`);
      await expect.poll(() => new URL(page.url()).pathname).toBe("/");
      expect(new URL(page.url()).origin).toBe(new URL(baseURL ?? "").origin);
      await expect(page.getByRole("complementary", { name: "Signing in" })).toHaveCount(0);
    });
  }

  test("explains a used or expired link and offers another", async ({ page }) => {
    await fakeSession(page);
    await answerJson(page, "/auth/email/verify", { error: { code: "link_invalid", message: "x" } }, { status: 400 });
    await page.goto(`/signin/email#token=${TOKEN}`);
    const panel = page.getByRole("complementary", { name: "Signing in" });
    await expect(panel.getByRole("heading", { name: "This link can't be used" })).toBeVisible();
    await panel.getByRole("button", { name: "Ask for a new link" }).click();
    await expect(page.getByRole("dialog", { name: "Sign in" })).toBeVisible();
  });

  test("keeps the link's next when asking for a new one", async ({ page }) => {
    await fakeSession(page);
    await answerJson(page, "/auth/email/verify", { error: { code: "link_invalid", message: "x" } }, { status: 400 });
    await page.goto(`/signin/email?next=%2Freview#token=${TOKEN}`);
    const panel = page.getByRole("complementary", { name: "Signing in" });
    await panel.getByRole("button", { name: "Ask for a new link" }).click();
    const google = page.getByRole("dialog", { name: "Sign in" }).getByRole("link", { name: /Google/ });
    const href = new URL((await google.getAttribute("href")) ?? "", "http://x");
    expect(href.searchParams.get("next")).toBe("/review");
  });

  test("takes the token out of the address at a path the router also matches", async ({ page }) => {
    const session = await fakeSession(page);
    session.set(null);
    await answerJson(page, "/auth/email/verify", meWith());
    await page.goto(`/Signin/Email/?next=%2Fabout#token=${TOKEN}`);
    await expect(page).toHaveURL((url) => !url.href.includes(TOKEN));
    await expect(page).toHaveURL(/\/about/);
  });
});

test("offers to discard this browser's drafts when signing out, in a dialog that holds focus", async ({ page }) => {
  const session = await fakeSession(page, meWith());
  await page.route(apiRoute("/auth/logout"), (route) => {
    session.set(null);
    return route.fulfill({ status: 204 });
  });
  await openMap(page, "/account");
  // A draft someone else left, which isn't saved for this person unasked.
  await page.evaluate(() =>
    localStorage.setItem(
      "fieldclub.drafts",
      JSON.stringify({
        version: 3,
        drafts: [
          {
            id: "left",
            kind: "fixture_probe",
            data: { note: "left behind" },
            owner: { account: "someone-else" },
            createdAt: "2026-11-10T10:00:00.000Z",
            updatedAt: "2026-11-10T10:00:00.000Z",
            state: "waiting",
          },
        ],
      }),
    ),
  );
  await page.reload();
  const panel = page.getByRole("complementary", { name: "Account" });
  await expect(page.getByRole("region", { name: "Drafts" }).getByRole("status")).toHaveText("1 draft left here");
  await panel.getByRole("button", { name: "Sign out", exact: true }).click();
  const dialog = page.getByRole("dialog", { name: "Keep your drafts?" });
  await expect(dialog).toContainText("whoever uses this browser next will see that it's here, though not what it says");
  await expectSheetFits(page, "Keep your drafts?");
  await expectFocusTrapped(page, 4);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  expect(session.current()).not.toBeNull();

  await panel.getByRole("button", { name: "Sign out", exact: true }).click();
  await dialog.getByRole("button", { name: "Discard and sign out" }).click();
  await expect(panel.getByRole("heading", { name: "You're not signed in" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Drafts" })).toHaveCount(0);
  expect(await page.evaluate(() => JSON.parse(localStorage.getItem("fieldclub.drafts") ?? "{}").drafts)).toEqual([]);
});

test("completes the welcome sheet by keyboard alone", async ({ page }) => {
  const session = await fakeSession(page, newcomerFixture());
  const welcomes: unknown[] = [];
  await page.route(apiRoute("/auth/welcome"), (route) => {
    welcomes.push(route.request().postDataJSON());
    session.set(meWith());
    return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(meWith()) });
  });
  await openMap(page, "/");
  const sheet = page.getByRole("dialog", { name: "Welcome to Open Antiquity" });
  await expect(sheet).toBeVisible();
  await expectSheetFits(page, "Welcome to Open Antiquity");
  expect(await focusIsInside(page, "dialog[open]")).toBe(true);

  await tabTo(page, sheet.getByRole("radio", { name: "Under 16" }));
  await page.keyboard.press("ArrowRight");
  await page.keyboard.press("ArrowRight");
  await expect(sheet.getByRole("radio", { name: "18 or over" })).toHaveAttribute("aria-checked", "true");
  await tabTo(page, sheet.getByRole("checkbox", { name: "I accept the contributor terms" }));
  await page.keyboard.press("Space");
  await tabTo(page, sheet.getByRole("button", { name: "Join Open Antiquity" }));
  await page.keyboard.press("Enter");
  await expect(sheet).toBeHidden();
  expect(welcomes).toEqual([{ age_band: "18_plus", accept_terms: true }]);
});

test("turns away someone under 16 without storing anything", async ({ page }) => {
  const session = await fakeSession(page, newcomerFixture());
  const calls: string[] = [];
  await page.route(apiRoute("/auth/welcome"), (route) => {
    calls.push("welcome");
    return route.fulfill({ status: 500 });
  });
  await page.route(apiRoute("/auth/me"), (route) => {
    if (route.request().method() !== "DELETE") return route.fallback();
    calls.push("delete");
    session.set(null);
    return route.fulfill({ status: 204 });
  });
  await openMap(page, "/");
  const sheet = page.getByRole("dialog", { name: "Welcome to Open Antiquity" });
  await sheet.getByRole("radio", { name: "Under 16" }).click();
  await expect(sheet.getByText("Open Antiquity is for people aged 16 and over")).toBeVisible();
  await expect(sheet.getByRole("button", { name: "Join Open Antiquity" })).toHaveCount(0);
  await expectSheetFits(page, "Welcome to Open Antiquity");
  await sheet.getByRole("button", { name: "Remove my sign-in" }).click();
  await expect(sheet).toBeHidden();
  expect(calls).toEqual(["delete"]);
});

test("edits details, signs out, signs in again and deletes the account behind a dialog", async ({ page }) => {
  const session = await fakeSession(page, meWith());
  const patches: unknown[] = [];
  await page.route(apiRoute("/auth/me"), (route) => {
    const method = route.request().method();
    if (method === "PATCH") {
      const body = route.request().postDataJSON() as Record<string, unknown>;
      patches.push(body);
      const me = meWith(body);
      session.set(me);
      return route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(me) });
    }
    if (method === "DELETE") {
      session.set(null);
      return route.fulfill({ status: 204 });
    }
    return route.fallback();
  });
  await page.route(apiRoute("/auth/logout"), (route) => {
    session.set(null);
    return route.fulfill({ status: 204 });
  });

  await openMap(page, "/account");
  const panel = page.getByRole("complementary", { name: "Account" });
  await expect(panel.getByText("@QuietBarrow42")).toBeVisible();
  await panel.getByLabel("Display name").fill("Ada L.");
  await panel.getByRole("button", { name: "Save changes" }).click();
  await expect(panel.locator(".fc-account-who__name")).toHaveText("Ada L.");
  expect(patches).toEqual([{ display_name: "Ada L." }]);

  await panel.getByRole("button", { name: "Sign out", exact: true }).click();
  await expect(panel.getByRole("heading", { name: "You're not signed in" })).toBeVisible();

  // Back in, as another tab or a provider would leave things.
  session.set(meWith());
  await page.reload();
  await expect(panel.getByText("@QuietBarrow42")).toBeVisible();

  const remove = panel.getByRole("button", { name: "Delete my account" });
  await tabTo(page, remove);
  await page.keyboard.press("Enter");
  const dialog = page.getByRole("dialog", { name: "Delete your account?" });
  await expect(dialog).toBeVisible();
  await expect(dialog).toContainText("credited to “Former member”");
  await expectSheetFits(page, "Delete your account?");
  await expectFocusTrapped(page, 6);
  await page.keyboard.press("Escape");
  await expect(dialog).toBeHidden();
  await expect(remove).toBeFocused();
  expect(session.current()).not.toBeNull();

  await page.keyboard.press("Enter");
  await tabTo(page, dialog.getByRole("button", { name: "Delete my account" }));
  await page.keyboard.press("Enter");
  await expect(panel.getByRole("heading", { name: "You're not signed in" })).toBeVisible();
  await expect(page.getByText("Your account has been deleted.")).toBeVisible();
});

test("shows the person's initials on the Account item", async ({ page }) => {
  await fakeSession(page, meWith());
  await openMap(page, "/");
  if (isPhone(page)) {
    await page.getByRole("button", { name: "More" }).click();
    await expect(page.locator(".fc-tabbar__menu").getByTestId("account-avatar")).toHaveText("AL");
  } else {
    const link = page.getByRole("navigation", { name: "Modes" }).getByRole("link", { name: "Account" });
    await expect(link.getByTestId("account-avatar")).toHaveText("AL");
  }
});
