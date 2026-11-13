import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { useLocation, useNavigate } from "react-router";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { routeApi } from "../../test/apiRoutes.js";
import { meFixture } from "../../test/fixtures/me.js";
import { GEO_RESULTS } from "../../test/fixtures/records.js";
import { json, mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";
import { GUIDE_FOLDED_KEY } from "./guideRows.js";
import { useMarkStore } from "./markStore.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

let go: ((to: string) => void) | null = null;

function Address() {
  const location = useLocation();
  go = useNavigate();
  return <output data-testid="address">{location.pathname}</output>;
}

function address(): string {
  return screen.getByTestId("address").textContent ?? "";
}

beforeEach(() => {
  window.localStorage.clear();
  useMarkStore.getState().start();
  routeApi(harness.fetchMock(), {
    "GET /auth/me": () => json(meFixture()),
    "GET /geo/search": () => json({ items: GEO_RESULTS }),
  });
});

afterEach(() => {
  vi.restoreAllMocks();
});

function guide() {
  return screen.getByRole("region", { name: "How to draw" });
}

function rows(): string[] {
  return within(guide())
    .queryAllByRole("listitem")
    .map((item) => item.textContent ?? "");
}

function searchBox() {
  return screen.queryByRole("combobox", { name: /Search for a place/ });
}

async function openAt(path: string) {
  renderShell(path, <Address />);
  return mapReady();
}

describe("the drawing guide on the map", () => {
  it("takes the search box's place while the tool is open, and gives it back when it closes", async () => {
    const user = userEvent.setup();
    await openAt("/");
    expect(searchBox()).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "How to draw" })).toBeNull();

    act(() => go?.("/mark"));
    expect(searchBox()).toBeNull();
    expect(guide().closest(".fc-stage__search")).not.toBeNull();
    expect(within(guide()).getByRole("heading", { name: "How to draw" })).toBeInTheDocument();
    expect(within(guide()).getByRole("list")).toBeInTheDocument();
    expect(rows()).toEqual(["Click the map: Marks a spot where the feature is", "Click again: Draws a line from it"]);
    // The panel no longer says it in prose.
    const panel = screen.getByRole("complementary", { name: "Mark a finding" });
    expect(within(panel).queryByRole("region", { name: "How to mark it" })).toBeNull();

    await user.click(within(panel).getByRole("button", { name: "Close panel" }));
    await waitFor(() => expect(address()).toBe("/"));
    expect(searchBox()).toBeInTheDocument();
    expect(screen.queryByRole("region", { name: "How to draw" })).toBeNull();
  });

  it("follows the marking as it grows, and shows keys as keys", async () => {
    const map = await openAt("/mark");
    act(() => map.click(300, 300));
    expect(rows()[0]).toBe("Click again: Draws a line from the spot");
    act(() => map.click(500, 300));
    act(() => map.click(500, 500));
    expect(rows()).toEqual([
      "Click the map: Adds the next point",
      "Click the first point: Closes it into a shape",
      "Drag a point: Moves it",
      "Drag a dot on the line: Adds a point there to bend it",
      "Shift-click: Adds a curved point, or on a point switches its kind",
      "Click a point: Selects it, to delete it",
    ]);
    const shift = within(guide()).getAllByText("Shift")[0];
    expect(shift?.tagName).toBe("KBD");
    // Every row's icon is hidden from a screen reader, which reads the words.
    for (const icon of guide().querySelectorAll("li svg")) expect(icon).toHaveAttribute("aria-hidden", "true");
  });

  it("names the keys once a point has keyboard focus", async () => {
    const user = userEvent.setup();
    const map = await openAt("/mark");
    act(() => map.click(300, 300));
    screen.getByRole("button", { name: /^Point 1 of 1/ }).focus();
    await user.keyboard("{ArrowRight}");
    expect(rows()[0]).toBe("Arrow keys on a point: Move it");
    expect(within(guide()).getByText("Delete").tagName).toBe("KBD");
  });

  it("names a phone's gestures, in the same place", async () => {
    usePhoneLayout();
    const map = await openAt("/mark");
    expect(searchBox()).toBeNull();
    expect(rows()[0]).toBe("Tap the map: Marks a spot where the feature is");
    act(() => map.click(300, 300));
    expect(rows()).toContain("Press and hold the point: Switches it between straight and curved");
  });

  it("is also there to change a saved shape", async () => {
    await openAt("/mark");
    act(() =>
      useMarkStore.getState().edit("finding:x:1", {
        closed: true,
        points: [
          { lon: -1.85, lat: 51.4, kind: "corner" },
          { lon: -1.84, lat: 51.41, kind: "corner" },
          { lon: -1.83, lat: 51.4, kind: "smooth" },
        ],
      }),
    );
    expect(rows().at(-1)).toBe("Click a point: Selects it, to delete it");
  });
});

describe("searching while drawing", () => {
  it("swaps the guide for the search box, with focus in it, and back on Escape in the empty box, still drawing", async () => {
    const user = userEvent.setup();
    await openAt("/mark");
    await user.click(within(guide()).getByRole("button", { name: "Search for a place" }));
    const box = searchBox();
    expect(box).toHaveFocus();
    expect(screen.queryByRole("region", { name: "How to draw" })).toBeNull();

    await user.type(box as HTMLElement, "x");
    await user.keyboard("{Escape}{Escape}");
    // The first Escape closes the list and the second clears the text: the box stays.
    expect(searchBox()).toHaveValue("");
    await user.keyboard("{Escape}");
    expect(guide()).toBeInTheDocument();
    expect(searchBox()).toBeNull();
    expect(within(guide()).getByRole("button", { name: "Search for a place" })).toHaveFocus();
    expect(address()).toBe("/mark");
  });

  it("brings the guide back once a result is chosen", async () => {
    const user = userEvent.setup();
    await openAt("/mark");
    await user.click(within(guide()).getByRole("button", { name: "Search for a place" }));
    await user.type(searchBox() as HTMLElement, "ave");
    await user.click(await screen.findByRole("option", { name: /Avebury Trusloe/ }));
    expect(guide()).toBeInTheDocument();
    expect(address()).toBe("/mark");
  });

  it("brings the guide back when the empty box loses focus, and keeps the box while it holds text", async () => {
    const user = userEvent.setup();
    await openAt("/mark");
    await user.click(within(guide()).getByRole("button", { name: "Search for a place" }));
    const box = searchBox() as HTMLElement;
    await user.type(box, "ave");
    fireEvent.blur(box);
    expect(searchBox()).toBeInTheDocument();
    await user.clear(box);
    fireEvent.blur(box);
    expect(guide()).toBeInTheDocument();
  });
});

describe("folding the guide", () => {
  it("folds to its header and back, and remembers the choice in the browser", async () => {
    const user = userEvent.setup();
    await openAt("/mark");
    const fold = within(guide()).getByRole("button", { name: "Gestures" });
    expect(fold).toHaveAttribute("aria-expanded", "true");
    await user.click(fold);
    expect(within(guide()).queryByRole("list")).toBeNull();
    expect(within(guide()).getByRole("heading", { name: "How to draw" })).toBeInTheDocument();
    // One name, folded or not: aria-expanded carries the state.
    expect(fold).toHaveAttribute("aria-expanded", "false");
    expect(fold).toHaveAccessibleName("Gestures");
    expect(window.localStorage.getItem(GUIDE_FOLDED_KEY)).toBe("folded");

    // Opened again later, it is still folded.
    act(() => go?.("/"));
    act(() => go?.("/mark"));
    expect(within(guide()).queryByRole("list")).toBeNull();
    await user.click(within(guide()).getByRole("button", { name: "Gestures" }));
    expect(within(guide()).getByRole("list")).toBeInTheDocument();
    expect(window.localStorage.getItem(GUIDE_FOLDED_KEY)).toBe("open");
  });

  it("starts unfolded, and still folds in a browser that refuses storage", async () => {
    const user = userEvent.setup();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new Error("refused");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new Error("refused");
    });
    await openAt("/mark");
    expect(within(guide()).getByRole("list")).toBeInTheDocument();
    await user.click(within(guide()).getByRole("button", { name: "Gestures" }));
    expect(within(guide()).queryByRole("list")).toBeNull();
  });
});
