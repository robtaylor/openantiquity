import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { routeApi } from "../../test/apiRoutes.js";
import { meFixture } from "../../test/fixtures/me.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { json, mapReady, renderShell, setUpShellTests, usePhoneLayout } from "../../test/shellHarness.js";
import { MARK_PATH_SOURCE, SVG_MAX_POINTS } from "./MarkLayer.js";
import { useMarkStore } from "./markStore.js";
import { phoneStatusWords } from "./PhoneBars.js";
import { history, type Path } from "./path.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  window.localStorage.clear();
  useMarkStore.getState().start();
});

async function openMarking() {
  routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
  renderShell("/mark");
  return mapReady();
}

function floatingBar() {
  return within(screen.getByRole("region", { name: "Drawing" }));
}

function at(lon: number, lat: number, kind: "corner" | "smooth" = "corner") {
  return { lon, lat, kind };
}

describe("the phone's status line", () => {
  it("says what a tap does now, and once there are points how many and how long", () => {
    const empty: Path = { closed: false, points: [] };
    expect(phoneStatusWords(empty, "end")).toBe("Tap the map where the feature is.");
    const spot: Path = { closed: false, points: [at(-1.85, 51.43)] };
    expect(phoneStatusWords(spot, "end")).toBe("1 point. Tap again to draw a line from it.");
    const two: Path = { closed: false, points: [at(-1.85, 51.43), at(-1.849, 51.43)] };
    expect(phoneStatusWords(two, "end")).toMatch(/^2 points, \d+ m\. Tap to carry on\.$/);
    const three: Path = { closed: false, points: [...two.points, at(-1.848, 51.431)] };
    expect(phoneStatusWords(three, "end")).toMatch(
      /^3 points, \d+ m\. Tap to carry on, or tap the first point to close it\.$/,
    );
    // Carrying on from the start, the point that closes it is the last.
    expect(phoneStatusWords(three, "start")).toMatch(/or tap the last point to close it\.$/);
  });
});

describe("the phone's drawing bar", () => {
  it("isn't offered for a marking that is set aside, so nothing can be added to one that is out of sight", async () => {
    usePhoneLayout();
    await openMarking();
    act(() =>
      useMarkStore.setState({
        shape: history({ closed: false, points: [at(-1.2, 52.1), at(-1.201, 52.1)] } satisfies Path),
        drawing: true,
        setAside: true,
      }),
    );
    expect(screen.queryByRole("region", { name: "Drawing" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add a point at the cross" })).toBeNull();

    act(() => useMarkStore.setState({ setAside: false }));
    expect(await screen.findByRole("region", { name: "Drawing" })).toBeInTheDocument();
  });

  it("isn't offered at a saved finding's shape while a new marking is in the way of it", async () => {
    usePhoneLayout();
    routeApi(harness.fetchMock(), { "GET /auth/me": () => json(meFixture()) });
    act(() =>
      useMarkStore.setState({
        shape: history({ closed: false, points: [at(-1.2, 52.1), at(-1.201, 52.1)] } satisfies Path),
        drawing: true,
      }),
    );
    renderShell("/mark/finding/f-ring");
    await mapReady();
    // The tool isn't open on the saved shape, nor on the marking, so there is nothing for the bar to work on.
    await new Promise((resolve) => setTimeout(resolve, 50));
    expect(screen.queryByRole("region", { name: "Drawing" })).toBeNull();
    expect(screen.queryByRole("button", { name: "Add a point at the cross" })).toBeNull();
  });

  it("is one row of named icon buttons and one status line, and nothing else", async () => {
    usePhoneLayout();
    const map = await openMarking();
    const bar = floatingBar();
    const names = bar.getAllByRole("button").map((button) => button.getAttribute("aria-label"));
    expect(names).toEqual([
      "Undo",
      "Redo",
      "Add a point at the cross",
      "Next point: straight",
      "Close the shape",
      "Finish",
    ]);
    // Disabled ones stay in place, so nothing jumps, and every one can be reached by Tab.
    for (const button of bar.getAllByRole("button")) {
      expect(button).not.toHaveAttribute("tabindex", "-1");
      expect(button).toHaveClass("fc-icon-button");
    }
    expect(bar.getByRole("button", { name: "Undo" })).toBeDisabled();
    expect(bar.getByRole("status")).toHaveTextContent(/^Tap the map where the feature is\.$/);
    expect(bar.queryByText(/don't take taps while you draw/)).toBeNull();
    expect(bar.queryByText("Nothing placed yet.")).toBeNull();
    expect(bar.queryByRole("radiogroup")).toBeNull();
    // The hint about other findings stays in the sheet.
    const sheet = within(screen.getByRole("complementary", { name: "Mark a finding" }));
    expect(sheet.getByText(/Findings already on the map don't take taps while you draw/)).toBeInTheDocument();

    act(() => map.click(300, 300));
    expect(bar.getByRole("status")).toHaveTextContent("1 point. Tap again to draw a line from it.");
    act(() => map.click(340, 300));
    act(() => map.click(340, 340));
    expect(bar.getByRole("status")).toHaveTextContent(
      /^3 points, \d+ m\. Tap to carry on, or tap the first point to close it\.$/,
    );
    expect(bar.getByRole("button", { name: "Undo" })).toBeEnabled();
    expect(bar.getByRole("button", { name: "Close the shape" })).toBeEnabled();
  });

  it("switches the kind of the next point with one button that says which it is", async () => {
    const user = userEvent.setup();
    usePhoneLayout();
    await openMarking();
    const bar = floatingBar();
    const kind = bar.getByRole("button", { name: "Next point: straight" });
    expect(kind).toHaveTextContent("Straight");
    await user.click(kind);
    expect(useMarkStore.getState().nextKind).toBe("smooth");
    expect(bar.getByRole("button", { name: "Next point: curved" })).toHaveTextContent("Curved");
  });

  it("finishes from the bar, and the sheet takes the full tool", async () => {
    usePhoneLayout();
    const map = await openMarking();
    act(() => map.click(300, 300));
    fireEvent.click(floatingBar().getByRole("button", { name: "Finish" }));
    const sheet = within(screen.getByRole("complementary", { name: "Mark a finding" }));
    expect(sheet.getByRole("radiogroup", { name: "Next point" })).toBeInTheDocument();
  });
});

describe("focus as the phone's bars and the sheet swap", () => {
  it("goes to the first control of the sheet's drawing bar after Finish, and of the floating bar after Continue", async () => {
    const user = userEvent.setup();
    usePhoneLayout();
    const map = await openMarking();
    act(() => map.click(300, 300));
    act(() => map.click(340, 300));
    floatingBar().getByRole("button", { name: "Finish" }).focus();
    await user.keyboard("{Enter}");
    const sheet = within(screen.getByRole("complementary", { name: "Mark a finding" }));
    const drawing = within(sheet.getByRole("region", { name: "Drawing" }));
    await waitFor(() => expect(drawing.getByRole("button", { name: "Undo" })).toHaveFocus());

    await user.click(screen.getByRole("button", { name: /^Point 2 of 2/ }));
    const selected = within(sheet.getByRole("region", { name: "Selected point" }));
    selected.getByRole("button", { name: "Continue from this end" }).focus();
    await user.keyboard("{Enter}");
    const floating = await screen.findByRole("region", { name: "Selected point" });
    expect(floating.closest(".fc-mark-float")).not.toBeNull();
    await waitFor(() => expect(within(floating).getByRole("button", { name: "Make it curved" })).toHaveFocus());
  });
});

describe("the phone's selected-point bar", () => {
  it("is one row of named icon buttons and one line that names the point", async () => {
    const user = userEvent.setup();
    usePhoneLayout();
    const map = await openMarking();
    act(() => map.click(300, 300));
    act(() => map.click(340, 300));
    act(() => map.click(380, 300));
    await user.click(screen.getByRole("button", { name: /^Point 3 of 3/ }));
    const bar = within(screen.getByRole("region", { name: "Selected point" }));
    expect(bar.getAllByRole("button").map((button) => button.getAttribute("aria-label"))).toEqual([
      "Make it curved",
      "Delete point",
      "Insert a point after",
      "Continue from this end",
      "Previous point",
      "Next point",
      "Done",
    ]);
    expect(bar.getByText(/^Point 3 of 3, straight, SU \d{4} \d{4}$/)).toBeInTheDocument();
    await user.click(bar.getByRole("button", { name: "Make it curved" }));
    expect(useMarkStore.getState().shape.present.points[2]?.kind).toBe("smooth");
    expect(bar.getByRole("button", { name: "Make it straight" })).toBeInTheDocument();
    await user.click(bar.getByRole("button", { name: "Done" }));
    expect(screen.queryByRole("region", { name: "Selected point" })).toBeNull();
  });
});

describe("the preview of a long path", () => {
  it("is still on the map after the layer is changed while drawing", async () => {
    const map = await openMarking();
    const many: Path = {
      closed: false,
      points: Array.from({ length: SVG_MAX_POINTS + 1 }, (_, i) => {
        const point = map.unproject([100 + i * 4, 300 + (i % 2) * 4]);
        return at(point.lng, point.lat);
      }),
    };
    act(() => useMarkStore.setState({ shape: history(many) }));
    const other = metaFixture.layers.views.find((view) => view.id !== useMapStore.getState().mainView);
    if (!other) throw new Error("The fixture has one view");
    act(() => useMapStore.getState().setMainView(other.id));
    const data = map.sourceData(MARK_PATH_SOURCE) as { features: unknown[] } | undefined;
    expect(data?.features).toHaveLength(1);
    expect(map.getLayer("mark-path-line")).toBeDefined();
  });
});
