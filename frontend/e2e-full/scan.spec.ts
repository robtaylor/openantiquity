import { openMap, sendDraftsFromBeforeSignIn } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";

/**
 * Scan a square against the real backend: someone signed out is sent to a
 * square near where they are looking, says there's nothing obvious in it,
 * which is kept as a draft, then signs in with the development sign-in and
 * joins through the sheets. The draft is saved, the square counts in the
 * coverage layer, and the next square is a different one. Each project
 * scans at a place of its own, far from the other's, so their squares and
 * coverage never meet.
 */

const PLACES = { desktop: { lon: -1.86, lat: 51.43 }, phone: { lon: -1.2, lat: 52.6 } } as const;

interface Coverage {
  features: Array<{ id: string; properties: { scans: number } }>;
}

test("a signed-out scan is saved after sign-in and counted in coverage", async ({ page }, testInfo) => {
  test.setTimeout(120_000);
  const project = testInfo.project.name === "phone" ? "phone" : "desktop";
  const at = PLACES[project];
  const tag = `${project.slice(0, 1)}${Date.now() % 1_000_000}`;

  await openMap(page, `/scan#m=13/${at.lat}/${at.lon}/0/0&v=composite`);
  const scan = page.getByRole("complementary", { name: "Scan a square" });
  const place = scan.locator(".fc-scan__place .fc-mono");
  await expect(place).toBeVisible();
  const gridRef = (await place.textContent()) ?? "";
  const square = gridRef.replaceAll(" ", "");
  expect(square).toMatch(/^[A-Z]{2}\d{4}$/);

  await scan.getByRole("button", { name: "Nothing obvious" }).click();
  await expect(scan.getByText(`${gridRef} is recorded: nothing obvious.`)).toBeVisible();
  await expect(scan.locator(".fc-scan__thanks .fc-draft-badge")).toHaveText("Not saved yet");

  // Signing in and joining, through the sheets, saves the waiting square.
  await scan.getByRole("button", { name: "Sign in to save it" }).click();
  const sheet = page.getByRole("dialog", { name: "Sign in" });
  await sheet.getByLabel("Development sign-in").fill(`Scanner${tag}`);
  await sheet.getByRole("button", { name: "Sign in", exact: true }).click();
  const welcome = page.getByRole("dialog", { name: "Welcome to OpenAntiquity" });
  await welcome.getByRole("radio", { name: "18 or over" }).click();
  await welcome.getByRole("checkbox", { name: "I accept the contributor terms" }).check();
  await welcome.getByRole("button", { name: "Join OpenAntiquity" }).click();
  await sendDraftsFromBeforeSignIn(page);
  await expect(scan.locator(".fc-scan__thanks .fc-draft-badge")).toHaveCount(0);
  await expect(scan.getByText(/1 square\s*looked over this visit/)).toBeVisible();

  // The server counts it, and the coverage layer shows it.
  const [west, south, east, north] = [at.lon - 0.1, at.lat - 0.1, at.lon + 0.1, at.lat + 0.1];
  await expect
    .poll(async () => {
      const answer = await page.request.get(`/api/v1/squares/coverage?bbox=${west},${south},${east},${north}`);
      const body = (await answer.json()) as Coverage;
      return body.features.find((feature) => feature.id === square)?.properties.scans ?? 0;
    })
    .toBe(1);
  await scan.getByRole("switch", { name: "Scan coverage" }).click();
  await expect(scan.getByText(/1 square around here has been looked over/)).toBeVisible();

  // The next square is another one.
  await scan.getByRole("button", { name: "Next square" }).click();
  await expect(place).not.toHaveText(gridRef);
  await expect(place).toHaveText(/^[A-Z]{2} \d{2} \d{2}$/);
});
