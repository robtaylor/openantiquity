import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import type { FakeMap } from "../test/fakeMapLibre.js";
import { findingsData } from "../test/fixtures/findings.js";
import { json, liveMaps, mapReady, renderShell, setUpShellTests } from "../test/shellHarness.js";
import type { FindingsMapData } from "./findingsData.js";
import { SQUARE_IMAGE } from "./overlayLayers.js";
import { overlayTroubleKey, useMapStore } from "./store.js";
import { overlaySourceId } from "./style.js";
import { FINDINGS_MIN_ZOOM } from "./useFindingsOverlay.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();
const SOURCE = overlaySourceId("findings");

function answerFindings(respond: () => Response): void {
  harness.answer("/findings", respond);
}

function drawn(map: FakeMap): FindingsMapData | undefined {
  return map.sourceData(SOURCE) as FindingsMapData | undefined;
}

describe("the findings overlay", () => {
  it("fetches the findings in view once the map is still, and draws them as points and squares", async () => {
    renderShell();
    const map = await mapReady();
    await waitFor(() => expect(drawn(map)?.features.length).toBeGreaterThan(0));
    expect(harness.requestsTo("/findings")).toBe(1);

    const data = drawn(map) as FindingsMapData;
    const points = data.features.filter((f) => f.geometry.type === "Point");
    const squares = data.features.filter((f) => f.geometry.type === "Polygon");
    const exact = findingsData.features.filter((f) => !f.properties.obscured);
    expect(points).toHaveLength(exact.length);
    // The protected and restricted findings, each in its own square.
    expect(squares.map((f) => f.properties.tier).sort()).toEqual(["corroborated", "seen"]);
  });

  it("asks again where the map comes to rest, and draws the same findings in the comparison pane", async () => {
    renderShell();
    const main = await mapReady();
    await waitFor(() => expect(harness.requestsTo("/findings")).toBe(1));

    act(() => main.userMove({ lng: -1.8, lat: 51.4 }));
    await waitFor(() => expect(harness.requestsTo("/findings")).toBe(2));
    const last = harness
      .fetchMock()
      .mock.calls.map(([input]) => new URL(String(input), "http://localhost"))
      .filter((url) => url.pathname === "/api/v1/findings")
      .at(-1);
    const [west, south, east, north] = (last?.searchParams.get("bbox") ?? "").split(",").map(Number);
    expect(west).toBeLessThan(-1.8);
    expect(east).toBeGreaterThan(-1.8);
    expect(south).toBeLessThan(51.4);
    expect(north).toBeGreaterThan(51.4);

    act(() => useMapStore.getState().toggleCompare());
    await waitFor(() => expect(liveMaps()).toHaveLength(2));
    const compare = liveMaps()[1] as FakeMap;
    act(() => compare.fire("styledata", { dataType: "style" }));
    await waitFor(() => expect(drawn(compare)).toEqual(drawn(main)));
  });

  it("asks for nothing while the overlay is off, or the map is zoomed too far out", async () => {
    renderShell("/#m=8/51.4286/-1.8542/0/0&v=composite&s=315/25&x=2&t=0/1.5&o=findings:100:h");
    const map = await mapReady();
    act(() => useMapStore.getState().setOverlayVisible("findings", true));
    act(() => map.userMove({ zoom: FINDINGS_MIN_ZOOM - 0.5 }));
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(harness.requestsTo("/findings")).toBe(0);

    act(() => map.userMove({ zoom: FINDINGS_MIN_ZOOM }));
    await waitFor(() => expect(harness.requestsTo("/findings")).toBe(1));
  });

  it("says nothing and shows nothing when the server has no findings endpoint yet", async () => {
    answerFindings(() => json({ detail: "Not Found" }, 404));
    renderShell("/?panel=layers");
    const map = await mapReady();
    await waitFor(() => expect(harness.requestsTo("/findings")).toBe(1));
    await new Promise((resolve) => setTimeout(resolve, 100));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(useMapStore.getState().failing[overlayTroubleKey("findings")]).toBeFalsy();
    expect(map.isVisible("findings-points")).toBe(true);
    expect(drawn(map)?.features ?? []).toEqual([]);

    // And it is not asked again as the map moves.
    act(() => map.userMove({ lng: -1.8 }));
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(harness.requestsTo("/findings")).toBe(1);
  });

  it("switches the overlay off with a notice when the endpoint fails, and tries again on request", async () => {
    vi.spyOn(console, "warn").mockImplementation(() => {});
    let failing = true;
    answerFindings(() =>
      failing ? json({ error: { code: "internal", message: "Database unavailable." } }, 500) : json(findingsData),
    );
    renderShell("/?panel=layers");
    const map = await mapReady();
    const notice = await screen.findByRole("alert", {}, { timeout: 3000 });
    expect(notice).toHaveTextContent("The Findings layer isn't loading, so it's switched off for now.");
    expect(map.isVisible("findings-points")).toBe(false);
    // Once, and once more because a server error may pass.
    expect(harness.requestsTo("/findings")).toBe(2);

    failing = false;
    fireEvent.click(within(notice).getByRole("button", { name: "Try again" }));
    await waitFor(() => expect(drawn(map)?.features.length).toBeGreaterThan(0));
    expect(screen.queryByRole("alert")).toBeNull();
    expect(map.isVisible("findings-points")).toBe(true);
    expect(harness.requestsTo("/findings")).toBe(3);
  });
});

describe("marker images", () => {
  it("supplies the record square again whenever the map finds it missing", async () => {
    renderShell();
    const map = await mapReady();
    expect(map.addImage).toHaveBeenCalledWith(SQUARE_IMAGE, expect.anything(), expect.anything());
    const resolver = map.missingImageResolver;
    if (!resolver) throw new Error("The map was given no resolver for missing images");
    map.dropImages();
    await resolver(SQUARE_IMAGE);
    expect(map.hasImage(SQUARE_IMAGE)).toBe(true);
    expect(map.addImage).toHaveBeenCalledTimes(2);
    await resolver("something-else");
    expect(map.addImage).toHaveBeenCalledTimes(2);
  });
});
