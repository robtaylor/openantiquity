import { act, screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

setUpShellTests();

/** Let the shell finish starting up. Until it has, a panel on screen is part of the page as loaded and leaves focus alone. */
async function settled(): Promise<void> {
  await act(async () => {
    await new Promise((resolve) => setTimeout(resolve, 0));
  });
}

async function tabUntil(user: ReturnType<typeof userEvent.setup>, done: () => boolean, limit = 40): Promise<number> {
  let presses = 0;
  while (!done()) {
    if (presses >= limit) throw new Error(`Focus did not arrive within ${limit} presses of Tab`);
    await user.tab();
    presses += 1;
  }
  return presses;
}

describe("keyboard focus around panels", () => {
  it("moves focus into the layer panel when it opens, and back to the Layers button when it closes", async () => {
    const user = userEvent.setup();
    renderShell();
    await mapReady();
    await settled();

    const layers = screen.getByRole("button", { name: "Layers" });
    layers.focus();
    await user.keyboard("{Enter}");
    const panel = screen.getByRole("complementary", { name: "Layers" });
    expect(within(panel).getByRole("heading", { name: "Layers" })).toHaveFocus();

    // One press of Tab reaches the panel's first control. It used to take fourteen.
    await user.tab();
    expect(within(panel).getByRole("button", { name: "Close panel" })).toHaveFocus();
    await user.tab();
    expect(panel).toContainElement(document.activeElement as HTMLElement);

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(layers).toHaveFocus();
  });

  it("hands focus back when the panel is closed with its own button", async () => {
    const user = userEvent.setup();
    renderShell();
    await mapReady();
    await settled();

    const layers = screen.getByRole("button", { name: "Layers" });
    layers.focus();
    await user.keyboard("{Enter}");
    await user.tab();
    await user.keyboard("{Enter}");
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(layers).toHaveFocus();
  });

  it("does the same for a mode opened from the rail", async () => {
    const user = userEvent.setup();
    renderShell();
    await mapReady();
    await settled();

    const rail = screen.getByRole("navigation", { name: "Modes" });
    const link = within(rail).getByRole("link", { name: "Second look" });
    link.focus();
    await user.keyboard("{Enter}");
    const panel = screen.getByRole("complementary", { name: "Second look" });
    expect(within(panel).getByRole("heading", { name: "Second look" })).toHaveFocus();

    // Going from one mode to the next moves focus to the new panel.
    const next = within(rail).getByRole("link", { name: "Scan a square" });
    next.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("heading", { name: "Scan a square" })).toHaveFocus();

    await user.keyboard("{Escape}");
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(next).toHaveFocus();
  });

  it("leaves focus alone when the page loads with a panel already open", async () => {
    renderShell("/review");
    await mapReady();
    await settled();
    expect(screen.getByRole("complementary", { name: "Second look" })).toBeInTheDocument();
    expect(document.body).toHaveFocus();
  });

  it("gives focus to the map when the panel closes and nothing is known to have opened it", async () => {
    const user = userEvent.setup();
    renderShell("/review");
    const map = await mapReady();
    await settled();
    map.getCanvas().tabIndex = 0;

    const close = screen.getByRole("button", { name: "Close panel" });
    close.focus();
    await user.keyboard("{Enter}");
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(map.getCanvas()).toHaveFocus();
  });

  it("does not pull focus away from where the person has put it", async () => {
    const user = userEvent.setup();
    renderShell();
    await mapReady();
    await settled();

    const layers = screen.getByRole("button", { name: "Layers" });
    await user.click(layers);
    // Closing from the Layers button itself leaves focus on that button.
    await user.click(layers);
    expect(screen.queryByRole("complementary")).toBeNull();
    expect(layers).toHaveFocus();
  });

  it("keeps focus on the Layers button when closing the layer panel uncovers a mode's panel", async () => {
    const user = userEvent.setup();
    renderShell("/review");
    await mapReady();
    await settled();

    const layers = screen.getByRole("button", { name: "Layers" });
    layers.focus();
    await user.keyboard("{Enter}");
    expect(screen.getByRole("heading", { name: "Layers" })).toHaveFocus();
    await user.keyboard("{Escape}");
    // The mode's panel is back, but it did not just open, so it does not take focus.
    expect(screen.getByRole("complementary", { name: "Second look" })).toBeInTheDocument();
    expect(layers).toHaveFocus();
  });

  it("puts the panel straight after the map's own controls in the Tab order", async () => {
    const user = userEvent.setup();
    renderShell("/?panel=layers");
    await mapReady();
    await settled();
    const panel = screen.getByRole("complementary", { name: "Layers" });

    screen.getByRole("button", { name: "Mark a finding" }).focus();
    const presses = await tabUntil(user, () => panel.contains(document.activeElement));
    // The status bar's credits button is the only stop in between.
    expect(presses).toBeLessThanOrEqual(2);
  });
});

describe("the More menu on a phone", () => {
  it("gives focus back to the More button when Escape closes it", async () => {
    const user = userEvent.setup();
    usePhoneLayout();
    renderShell();
    await mapReady();
    await settled();

    const tabs = screen.getByRole("navigation", { name: "Modes" });
    const more = within(tabs).getByRole("button", { name: "More" });
    more.focus();
    await user.keyboard("{Enter}");
    await user.tab();
    expect(within(tabs).getByRole("link", { name: "Investigations" })).toHaveFocus();
    await user.keyboard("{Escape}");
    expect(within(tabs).queryByRole("link", { name: "Investigations" })).toBeNull();
    expect(more).toHaveFocus();
  });
});
