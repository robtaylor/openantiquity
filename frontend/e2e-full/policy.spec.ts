import { expect, test } from "./support/fixtures.js";

/**
 * The interface is served by the backend with its security headers, and the
 * check every test makes for policy violations really sees one.
 */

test("the app is served with its security headers", async ({ page }) => {
  const response = await page.goto("/");
  const headers = response?.headers() ?? {};
  const policy = headers["content-security-policy"] ?? "";
  expect(policy).toContain("script-src 'self'");
  expect(policy).toContain("frame-ancestors 'none'");
  expect(policy).not.toContain("unsafe-inline");
  expect(headers["x-frame-options"]).toBe("DENY");
  expect(headers["x-content-type-options"]).toBe("nosniff");
  // The interface started under it.
  await expect(page.getByRole("button", { name: "Layers" })).toBeVisible();
});

test("a violation of the policy is caught", async ({ page, csp }) => {
  await page.goto("/");
  await expect(page.getByRole("button", { name: "Layers" })).toBeVisible();
  await page.evaluate(() => {
    const image = document.createElement("img");
    image.src = "https://not-allowed.example/pixel.png";
    document.body.append(image);
  });
  await expect.poll(() => csp.some((line) => line.includes("not-allowed.example"))).toBe(true);
  // Caused on purpose: the fixture's own check would fail the test otherwise.
  csp.length = 0;
});
