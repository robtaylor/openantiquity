import { screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";
import { SOURCE_URL } from "./navigation.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

setUpShellTests();

/** A link out of the app: another tab, and nothing handed to the page it opens. */
function expectOutsideLink(link: HTMLElement): void {
  expect(link).toHaveAttribute("href", SOURCE_URL);
  expect(link).toHaveAttribute("target", "_blank");
  expect(link.getAttribute("rel")?.split(" ")).toEqual(expect.arrayContaining(["noopener", "noreferrer"]));
}

describe("the way to the source code", () => {
  it("is the project's public repository", () => {
    expect(SOURCE_URL).toBe("https://github.com/robtaylor/openantiquity");
  });

  it("sits at the foot of the rail with Guide and About, and opens in another tab", async () => {
    renderShell();
    await mapReady();
    const rail = within(screen.getByRole("navigation", { name: "Modes" }));
    const link = rail.getByRole("link", { name: "Source code on GitHub (opens in a new tab)" });
    expectOutsideLink(link);
    // After the reference pages, before the account.
    const names = rail.getAllByRole("link").map((item) => item.getAttribute("aria-label") ?? item.textContent);
    expect(names.indexOf("Source code on GitHub (opens in a new tab)")).toBeGreaterThan(names.indexOf("About"));
  });

  it("is under More on a phone", async () => {
    usePhoneLayout();
    const user = userEvent.setup();
    renderShell();
    await mapReady();
    const bar = within(screen.getByRole("navigation", { name: "Modes" }));
    await user.click(bar.getByRole("button", { name: /^More/ }));
    const link = bar.getByRole("link", { name: "Source code on GitHub (opens in a new tab)" });
    expectOutsideLink(link);
    // Named as every other link out of the app is: its words, with the rest for a screen reader alone.
    expect(link).not.toHaveAttribute("aria-label");
    expect(link).toHaveTextContent("Source code on GitHub (opens in a new tab)");

    // The link leaves the page where it is, so nothing else closes the menu: it would still be open on coming back.
    link.addEventListener("click", (event) => event.preventDefault());
    await user.click(link);
    expect(bar.queryByRole("link", { name: "Source code on GitHub (opens in a new tab)" })).toBeNull();
    expect(bar.getByRole("button", { name: /^More/ })).toHaveAttribute("aria-expanded", "false");
  });
});
