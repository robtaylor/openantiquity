import { act, screen, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { afterEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

setUpShellTests();

const realHeight = window.innerHeight;

function setWindowHeight(height: number): void {
  Object.defineProperty(window, "innerHeight", { configurable: true, value: height });
}

afterEach(() => {
  setWindowHeight(realHeight);
});

function shell(): HTMLElement {
  const element = document.querySelector<HTMLElement>(".fc-shell");
  if (!element) throw new Error("The shell is not on the page");
  return element;
}

function region(selector: string): HTMLElement {
  const element = document.querySelector<HTMLElement>(selector);
  if (!element) throw new Error(`Nothing matches ${selector}`);
  return element;
}

describe("a phone with a sheet open", () => {
  it("floats the primary action, the status bar and the sun dial above a half-open sheet", async () => {
    setWindowHeight(844);
    usePhoneLayout();
    renderShell("/?panel=layers");
    await mapReady();
    act(() => useMapStore.getState().setMainView("raking"));

    // 844 high, less the tab bar and the gap kept for the search field, leaves the sheet 720. Half of that is 360.
    expect(screen.getByRole("complementary", { name: "Layers" })).toHaveAttribute("data-stop", "half");
    expect(shell().style.getPropertyValue("--sheet-clear")).toBe("360px");
    expect(shell()).not.toHaveAttribute("data-stage");
    // The map's own controls centre on what is left: tab bar 56, sheet 360, status bar 28.
    expect(shell().style.getPropertyValue("--map-covered-bottom")).toBe("444px");
    for (const selector of [".fc-stage__primary", ".fc-stage__raking", ".fc-shell__status", ".fc-stage__controls"]) {
      expect(region(selector), selector).not.toHaveAttribute("inert");
    }
    expect(screen.getByRole("slider", { name: "Sun direction" })).toBeInTheDocument();
  });

  it("follows the sheet down to its lowest stop", async () => {
    setWindowHeight(844);
    const user = userEvent.setup();
    usePhoneLayout();
    renderShell("/review");
    await mapReady();
    const sheet = screen.getByRole("complementary", { name: "Second look" });
    const handle = within(sheet).getByRole("button", { name: /Press to resize/ });
    handle.focus();
    await user.keyboard("{ArrowDown}");
    expect(sheet).toHaveAttribute("data-stop", "peek");
    expect(shell().style.getPropertyValue("--sheet-clear")).toBe("76px");
    expect(shell()).not.toHaveAttribute("data-stage");
  });

  it("puts the controls it covers out of reach of the keyboard when the sheet is fully open", async () => {
    setWindowHeight(844);
    const user = userEvent.setup();
    usePhoneLayout();
    renderShell("/?panel=layers");
    await mapReady();
    const sheet = screen.getByRole("complementary", { name: "Layers" });
    const handle = within(sheet).getByRole("button", { name: /Press to resize/ });
    handle.focus();
    await user.keyboard("{ArrowUp}");
    expect(sheet).toHaveAttribute("data-stop", "full");

    expect(shell()).toHaveAttribute("data-stage", "covered");
    expect(shell()).toHaveAttribute("data-sheet", "full");
    expect(shell().style.getPropertyValue("--sheet-clear")).toBe("0px");
    for (const selector of [".fc-stage__primary", ".fc-stage__raking", ".fc-shell__status", ".fc-stage__controls"]) {
      expect(region(selector), selector).toHaveAttribute("inert");
    }
    // The search field stays above the sheet and in use.
    expect(region(".fc-stage__search")).not.toHaveAttribute("inert");

    await user.keyboard("{ArrowDown}");
    expect(shell()).not.toHaveAttribute("data-stage");
    expect(region(".fc-stage__primary")).not.toHaveAttribute("inert");
  });

  it("puts the foot-of-map controls away at half open when the window is too short to hold them", async () => {
    // 568 high: half a sheet leaves under 200 px of map, less than the dial and the button need.
    setWindowHeight(568);
    usePhoneLayout();
    renderShell("/?panel=layers");
    await mapReady();
    expect(screen.getByRole("complementary", { name: "Layers" })).toHaveAttribute("data-stop", "half");
    expect(shell()).toHaveAttribute("data-stage", "covered");
    expect(region(".fc-stage__primary")).toHaveAttribute("inert");
    expect(region(".fc-shell__status")).toHaveAttribute("inert");
    // The buttons at the top are still in the clear.
    expect(region(".fc-stage__controls")).not.toHaveAttribute("inert");
  });

  it("leaves everything in reach when no sheet is open", async () => {
    setWindowHeight(844);
    usePhoneLayout();
    renderShell();
    await mapReady();
    expect(shell().style.getPropertyValue("--sheet-clear")).toBe("0px");
    expect(shell().style.getPropertyValue("--map-covered-bottom")).toBe("84px");
    expect(shell()).not.toHaveAttribute("data-stage");
    expect(shell()).not.toHaveAttribute("data-sheet");
  });
});
