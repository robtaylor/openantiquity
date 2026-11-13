import { screen, waitFor, within } from "@testing-library/react";
import { userEvent } from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { useMapStore } from "../../map/store.js";
import { routeApi } from "../../test/apiRoutes.js";
import { pageFixture, squareFixture, suggestionsFixture } from "../../test/fixtures/findingPage.js";
import { meFixture } from "../../test/fixtures/me.js";
import { json, mapReady, renderShell, setUpShellTests } from "../../test/shellHarness.js";
import { useSelectedFinding } from "../findings/selection.js";
import type { FindingDetail } from "./types.js";

vi.mock("maplibre-gl", async () => {
  const fake = await import("../../test/fakeMapLibre.js");
  return { Map: fake.FakeMap };
});

const harness = setUpShellTests();

beforeEach(() => {
  localStorage.clear();
  useSelectedFinding.getState().clear();
});

const ADDED_VIEW = { lon: -1.81, lat: 51.44, zoom: 13 };

/** A line others have looked at, drawn 4.2 km further since, with a change of shape before that. */
function extendedLine(overrides: Partial<FindingDetail> = {}): FindingDetail {
  const base = pageFixture();
  return {
    ...base,
    location: {
      ...base.location,
      shape: {
        kind: "line",
        length_m: 12_400,
        revision: 3,
        extent: [-1.9, 51.4, -1.8, 51.45],
        changes: [
          { kind: "drawn", on: "2026-11-02" },
          { kind: "reshaped", on: "2026-11-05" },
          { kind: "extended", on: "2026-11-20", added_length_m: 4200, added_view: { lon: -1.8, lat: 51.45, zoom: 15 } },
        ],
        added_since_looked_m: 4200,
        added_view: ADDED_VIEW,
      },
    },
    ...overrides,
  };
}

async function open(finding: FindingDetail) {
  const path = `/findings/${finding.public_id}`;
  routeApi(harness.fetchMock(), {
    "GET /auth/me": () => json(meFixture()),
    [`GET ${path}`]: () => json(finding),
    [`GET ${path}/comments`]: () => json({ items: [], next_cursor: null }),
    [`GET ${path}/suggested-records`]: () => json(suggestionsFixture([])),
    [`GET ${path}/observations`]: () => json({ items: [], next_cursor: null }),
  });
  renderShell(`/f/${finding.public_id}`);
  await mapReady();
  const page = within(await screen.findByRole("complementary", { name: finding.title }));
  // The page moves the map to the finding once, when the panel has settled.
  const zoom = finding.location.obscured ? 13.5 : 16;
  await waitFor(() => expect(useMapStore.getState().camera.zoom).toBe(zoom));
  return page;
}

describe("what was added since the last second look", () => {
  it("says how much, measured from the ground, and opens the map on it", async () => {
    const user = userEvent.setup();
    const page = await open(extendedLine());
    const added = page.getByRole("region", { name: "Added since the last second look" });
    expect(added).toHaveTextContent("4.2 km added since the last second look");
    const before = useMapStore.getState().cameraRequest;
    await user.click(within(added).getByRole("button", { name: "Show the new part on the map" }));
    expect(useMapStore.getState().cameraRequest).toBe(before + 1);
    expect(useMapStore.getState().camera).toMatchObject({ lng: ADDED_VIEW.lon, lat: ADDED_VIEW.lat, zoom: 13 });
  });

  it("says nothing when nothing lies beyond what was looked at", async () => {
    const line = extendedLine();
    const page = await open({
      ...line,
      location: { ...line.location, shape: { ...line.location.shape, added_since_looked_m: null, added_view: null } },
    });
    expect(page.queryByRole("region", { name: "Added since the last second look" })).toBeNull();
    // The timeline still lists the changes.
    expect(page.getByRole("list", { name: "What happened, oldest first" })).toHaveTextContent(
      "Drawn further by 4.2 km",
    );
  });
});

describe("changes of shape on the timeline", () => {
  it("lists each change with its date, oldest first, and an extension's button opens its own view", async () => {
    const user = userEvent.setup();
    const page = await open(extendedLine());
    const timeline = page.getByRole("list", { name: "What happened, oldest first" });
    const entries = within(timeline).getAllByRole("listitem");
    expect(entries.map((entry) => entry.textContent)).toEqual([
      expect.stringMatching(/2 November 2026.*The shape was drawn/),
      expect.stringMatching(/5 November 2026.*The shape was changed/),
      expect.stringMatching(/20 November 2026.*Drawn further by 4.2 km/),
    ]);
    expect(page.queryByText(/Nothing yet\./)).toBeNull();
    const last = entries[2];
    if (!last) throw new Error("No third entry");
    await user.click(within(last).getByRole("button", { name: /^Show what was added/ }));
    // The timeline's view is the change's own, not the finding's.
    expect(useMapStore.getState().camera).toMatchObject({ lng: -1.8, lat: 51.45, zoom: 15 });
  });

  it("tells someone who sees only the square that the shape changed and when, and nothing more", async () => {
    const square = squareFixture();
    const page = await open({
      ...square,
      location: {
        ...square.location,
        shape: { ...square.location.shape, changes: [{ kind: "changed", on: "2026-11-20" }] },
      },
    });
    const timeline = page.getByRole("list", { name: "What happened, oldest first" });
    expect(timeline).toHaveTextContent(/20 November 2026.*The shape was changed/);
    expect(within(timeline).queryByRole("button")).toBeNull();
    expect(page.queryByRole("region", { name: "Added since the last second look" })).toBeNull();
  });
});
