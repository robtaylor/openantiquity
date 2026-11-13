import { useQueryClient } from "@tanstack/react-query";
import { act, fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import { signedOut } from "../features/account/session.js";
import type { FakeMap } from "../test/fakeMapLibre.js";
import { findingsData } from "../test/fixtures/findings.js";
import { meFixture } from "../test/fixtures/me.js";
import { json, liveMaps, mapReady, renderShell, setUpShellTests } from "../test/shellHarness.js";
import type { FindingsMapData } from "./findingsData.js";
import { SQUARE_IMAGE } from "./overlayLayers.js";
import { overlayTroubleKey, useMapStore, useViewAreaStore } from "./store.js";
import { overlaySourceId } from "./style.js";
import { useDrawnFindings } from "./useFindingsOverlay.js";

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

function SignOutHere() {
  const client = useQueryClient();
  return (
    <button type="button" onClick={() => signedOut(client)}>
      Sign out for the test
    </button>
  );
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
    // The two protected findings, each in its own square.
    expect(squares.map((f) => f.properties.tier).sort()).toEqual(["corroborated", "seen"]);
  });

  it("draws an exact line as a line, and a signed-out reader's obscured line as its square alone", async () => {
    const road = [
      [-1.86, 51.425],
      [-1.85, 51.43],
    ];
    const [exact, hidden] = [
      findingsData.features.find((f) => !f.properties.obscured),
      findingsData.features.find((f) => f.properties.obscured),
    ];
    if (!exact || !hidden) throw new Error("The fixture lacks an exact or an obscured finding");
    // As a signed-out reader is sent them: the exact one with its shape, the obscured one with none. A shape sent
    // by mistake with an obscured one is still never drawn.
    answerFindings(() =>
      json({
        type: "FeatureCollection",
        features: [
          { ...exact, properties: { ...exact.properties, shape: { type: "LineString", coordinates: road } } },
          { ...hidden, properties: { ...hidden.properties, shape: { type: "LineString", coordinates: road } } },
        ],
      }),
    );
    renderShell();
    const map = await mapReady();
    await waitFor(() => expect(drawn(map)?.features.length).toBeGreaterThan(0));
    const data = drawn(map) as FindingsMapData;
    const lines = data.features.filter((f) => f.geometry.type === "LineString");
    expect(lines.map((f) => (f.properties as { public_id: string }).public_id)).toEqual([exact.properties.public_id]);
    expect(JSON.stringify(data)).not.toContain(`"public_id":"${hidden.properties.public_id}"`);
    const url = harness
      .fetchMock()
      .mock.calls.map(([input]) => new URL(String(input), "http://localhost"))
      .find((each) => each.pathname === "/api/v1/findings");
    expect(url?.searchParams.get("zoom")).toMatch(/^\d+$/);
  });

  it("draws nothing it was sent for the last person while the next person's answer is awaited", async () => {
    harness.answer("/auth/me", () => json(meFixture()));
    renderShell(undefined, <SignOutHere />);
    const map = await mapReady();
    await waitFor(() => expect(drawn(map)?.features.length).toBeGreaterThan(0));
    expect(useDrawnFindings.getState().byId.size).toBeGreaterThan(0);

    // What a member was sent holds exact places. The answer for whoever is here now never comes.
    harness.answer("/findings", () => new Promise<Response>(() => {}));
    fireEvent.click(screen.getByRole("button", { name: "Sign out for the test" }));

    await waitFor(() => expect(drawn(map)?.features).toHaveLength(0));
    expect(useDrawnFindings.getState().byId.size).toBe(0);
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

  it("asks for nothing while the overlay is off, and at every zoom once it is on", async () => {
    window.history.replaceState(
      null,
      "",
      "/#m=7/51.4286/-1.8542/0/0&v=composite&s=315/25&x=2&t=0/1.5&o=findings:100:h",
    );
    renderShell("/?panel=none");
    const map = await mapReady();
    expect(useViewAreaStore.getState().zoom).toBe(7);
    await new Promise((resolve) => setTimeout(resolve, 500));
    expect(harness.requestsTo("/findings")).toBe(0);

    act(() => useMapStore.getState().setOverlayVisible("findings", true));
    await waitFor(() => expect(drawn(map)?.features.length).toBeGreaterThan(0));
    // Zoomed out past the zooms the server simplifies for, it asks at the furthest out of them.
    const url = harness
      .fetchMock()
      .mock.calls.map(([input]) => new URL(String(input), "http://localhost"))
      .find((each) => each.pathname === "/api/v1/findings");
    expect(url?.searchParams.get("zoom")).toBe("9");
  });

  it("says once, quietly, when there are more findings in view than were drawn, until the answer is whole", async () => {
    let cut = true;
    answerFindings(() => json({ ...findingsData, next_cursor: cut ? "more" : null }));
    renderShell("/?panel=none");
    const map = await mapReady();
    const notice = await screen.findByText("Not every finding in view is drawn. Zoom in to see the rest.");
    expect(notice).toHaveAttribute("role", "status");
    expect(screen.getAllByText(/Not every finding in view is drawn/)).toHaveLength(1);
    // It is not paged through: one request for the box.
    expect(harness.requestsTo("/findings")).toBe(1);

    cut = false;
    act(() => map.userMove({ lng: -1.8, zoom: 15 }));
    await waitFor(() => expect(harness.requestsTo("/findings")).toBe(2));
    await waitFor(() => expect(screen.queryByText(/Not every finding in view is drawn/)).toBeNull());
  });

  it("says nothing of findings left out while the findings overlay is off", async () => {
    answerFindings(() => json({ ...findingsData, next_cursor: "more" }));
    renderShell("/?panel=none");
    await mapReady();
    await screen.findByText(/Not every finding in view is drawn/);
    act(() => useMapStore.getState().setOverlayVisible("findings", false));
    await waitFor(() => expect(screen.queryByText(/Not every finding in view is drawn/)).toBeNull());
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
