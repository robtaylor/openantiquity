import { openMap } from "../e2e/support/app.js";
import { expect, test } from "./support/fixtures.js";
import { helper } from "./support/people.js";

/**
 * Second look against the real backend: one account marks a finding, and a
 * second, starting signed out, gets it from the blind queue, answers before
 * signing in, signs in and joins through the sheets, says to send the
 * answer, and sees the reveal. The answer is saved exactly once. Each project marks its finding at a
 * place of its own, far from every other test's, so the queue, which puts
 * nearby findings first, offers it first.
 */

const PLACES = { desktop: { lon: -0.52, lat: 52.31 }, phone: { lon: 0.48, lat: 52.31 } } as const;

test("a second account answers a finding through the queue, signing in on the way, and sees the reveal", async ({
  page,
  browser,
}, testInfo) => {
  test.setTimeout(120_000);
  const project = testInfo.project.name === "phone" ? "phone" : "desktop";
  const at = PLACES[project];
  const tag = `${project.slice(0, 1)}${Date.now() % 1_000_000}`;
  const title = `Queue enclosure ${tag}`;

  // The finder marks it, in a browser of their own.
  const finder = await helper(browser, page.viewportSize(), `Finder${tag}`);
  let publicId = "";
  try {
    const created = await finder.page.request.post("/api/v1/findings", {
      headers: { "X-OpenAntiquity-Client": "web" },
      data: {
        location: { type: "Point", coordinates: [at.lon, at.lat] },
        feature_class: "enclosure",
        title,
        view_state: { layer: "composite", zoom: 16 },
      },
    });
    expect(created.status(), await created.text()).toBe(201);
    publicId = ((await created.json()) as { public_id: string }).public_id;

    // The reviewer, signed out, opens the queue where they are looking.
    await openMap(page, `/review#m=13/${at.lat}/${at.lon}/0/0&v=composite`);
    const look = page.getByRole("complementary", { name: "Second look" });
    await expect(look.getByRole("group", { name: "Can you see it?" })).toBeVisible();
    await expect(page).toHaveURL(/#m=16\//);
    expect(await page.content()).not.toContain(title);

    // Signed out, the answer and its detail are kept as a draft.
    await page.keyboard.press("1");
    await look.getByRole("radio", { name: "Enclosure" }).click();
    await look.getByRole("button", { name: "Sign in to see how it compares" }).click();

    // Signing in and joining, through the sheets, saves the answer, then its detail with the reveal.
    const sheet = page.getByRole("dialog", { name: "Sign in" });
    await sheet.getByLabel("Development sign-in").fill(`Reviewer${tag}`);
    await sheet.getByRole("button", { name: "Sign in", exact: true }).click();
    const welcome = page.getByRole("dialog", { name: "Welcome to OpenAntiquity" });
    await welcome.getByRole("radio", { name: "18 or over" }).click();
    await welcome.getByRole("checkbox", { name: "I accept the contributor terms" }).check();
    await welcome.getByRole("button", { name: "Join OpenAntiquity" }).click();

    // An answer given before signing in waits for the person to say it is theirs: it is final once sent.
    await expect(look.getByText(/given in this browser before you signed in/)).toBeVisible();
    await page.waitForTimeout(300);
    const before = await finder.page.request.get(`/api/v1/findings/${publicId}/observations`);
    expect(((await before.json()) as { items: unknown[] }).items).toEqual([]);
    await look.getByRole("button", { name: "Send it and see how it compares" }).click();

    await expect(look.getByRole("heading", { name: title })).toBeVisible();
    await expect(look.getByText(/The finder marked it as: Enclosure\. So did you\./)).toBeVisible();
    await expect(look.getByText(/Nobody else has answered yet\./)).toBeVisible();

    // The finder sees exactly one answer, and it is this one.
    await page.waitForTimeout(500);
    const answers = await finder.page.request.get(`/api/v1/findings/${publicId}/observations`);
    expect(answers.status(), await answers.text()).toBe(200);
    const { items } = (await answers.json()) as { items: Array<{ visible: string; feature_class: string | null }> };
    expect(items).toEqual([expect.objectContaining({ visible: "yes", feature_class: "enclosure" })]);

    // Answered, it isn't offered again.
    const queue = await page.request.get(`/api/v1/review/next?lon=${at.lon}&lat=${at.lat}`);
    const cards = (await queue.json()) as { items: Array<{ public_id: string }> };
    expect(cards.items.map((card) => card.public_id)).not.toContain(publicId);
  } finally {
    await finder.context.close();
  }
});
