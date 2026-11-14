import { openMap } from "./support/app.js";
import { expect, test } from "./support/fixtures.js";

/**
 * A report too long for GitHub's address leaves part of itself out of the
 * issue, so pressing "Open a GitHub issue" also puts the whole text on the
 * clipboard. The copy starts in the click that opens another tab, and a
 * browser may refuse it once that tab has focus, which only a real browser
 * shows.
 */

test("puts the whole of a report too long for the address on the clipboard as the issue opens", async ({
  page,
  context,
}) => {
  await context.grantPermissions(["clipboard-read", "clipboard-write"]);
  // The issue's tab never reaches GitHub.
  const toGitHub: string[] = [];
  await context.route("https://github.com/**", async (route) => {
    toGitHub.push(route.request().url());
    await route.abort();
  });

  await openMap(page, "/about");
  const about = page.getByRole("complementary", { name: "About OpenAntiquity" });
  await about.getByRole("button", { name: "Report a problem" }).click();
  const dialog = page.getByRole("dialog", { name: "Report a problem" });
  // Within the box's limit, but each of these is six characters once in an address.
  await dialog.getByLabel("What were you doing, and what went wrong?").fill("éèêë àâôö ".repeat(190));
  await expect(dialog.getByRole("note")).toContainText("too long to send whole");
  const whole = await dialog.getByLabel("What will be sent").inputValue();

  const opened = context.waitForEvent("page");
  await dialog.getByRole("link", { name: "Open a GitHub issue" }).click();
  const issue = await opened;
  await expect.poll(() => toGitHub.length).toBeGreaterThan(0);
  expect(new URL(toGitHub[0] ?? "").searchParams.get("body")?.length).toBeLessThan(whole.length);

  await page.bringToFront();
  await expect.poll(() => page.evaluate(() => navigator.clipboard.readText())).toBe(whole);
  await expect(dialog.getByRole("status")).toHaveText("Copied. Paste it wherever you're sending the report.");
  await issue.close();
});
