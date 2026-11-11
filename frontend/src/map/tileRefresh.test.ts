import { describe, expect, it, vi } from "vitest";
import type { Meta, RasterView } from "../api/meta.js";
import { metaFixture } from "../test/fixtures/meta.js";
import { DEM_SOURCE, DEM_TERRAIN_SOURCE, overlaySourceId, viewSourceId } from "./style.js";
import { applyTileChanges, changedTiles, tileAddresses } from "./tileRefresh.js";

/** The fixture with every terrain address given a new version token. */
function withNewToken(meta: Meta, token: string): Meta {
  const next = structuredClone(meta);
  for (const view of next.layers.views) {
    if (view.type === "raster" && view.group === "lidar") view.tiles = view.tiles.map((url) => `${url}&v=${token}`);
  }
  next.layers.dem.tiles = next.layers.dem.tiles.map((url) => `${url}?v=${token}`);
  return next;
}

/** The fixture with the records tiles' token changed, as a finished ingest run changes it. */
function withNewRecordsToken(meta: Meta, token: string): Meta {
  const next = structuredClone(meta);
  for (const overlay of next.layers.overlays) {
    if (overlay.type === "records") overlay.tiles = overlay.tiles.map((url) => url.replace(/\?v=.*$/, `?v=${token}`));
  }
  return next;
}

describe("tileAddresses", () => {
  it("lists every tiled source the map builds, and no hand-made address", () => {
    const addresses = tileAddresses(metaFixture);
    const composite = metaFixture.layers.views.find((view) => view.id === "composite") as RasterView;
    expect(addresses.get(viewSourceId("composite"))).toBe(composite.tiles);
    expect(addresses.get(DEM_SOURCE)).toBe(metaFixture.layers.dem.tiles);
    expect(addresses.get(DEM_TERRAIN_SOURCE)).toBe(metaFixture.layers.dem.tiles);
    // The raking view is drawn from the elevation, so it has no tiles of its own.
    expect(addresses.has(viewSourceId("raking"))).toBe(false);
  });
});

describe("changedTiles", () => {
  it("finds nothing when the catalogue is the same", () => {
    expect(changedTiles(metaFixture, structuredClone(metaFixture)).size).toBe(0);
  });

  it("finds every terrain source whose token changed, and leaves the rest", () => {
    const changes = changedTiles(metaFixture, withNewToken(metaFixture, "new"));
    expect([...changes.keys()].sort()).toEqual(
      [
        DEM_SOURCE,
        DEM_TERRAIN_SOURCE,
        ...["composite", "local_relief", "sky_view", "multi_shade", "slope", "openness"].map(viewSourceId),
      ].sort(),
    );
    expect(changes.has(viewSourceId("osm_standard"))).toBe(false);
    expect(changes.get(DEM_SOURCE)?.[0]).toMatch(/\?v=new$/);
  });

  it("finds the heritage records' tiles when their token changes", () => {
    const changes = changedTiles(metaFixture, withNewRecordsToken(metaFixture, "after-ingest"));
    expect([...changes.keys()]).toEqual([overlaySourceId("records")]);
    expect(changes.get(overlaySourceId("records"))?.[0]).toMatch(/\.mvt\?v=after-ingest$/);
  });

  it("leaves a source the new catalogue doesn't have", () => {
    const fresh = structuredClone(metaFixture);
    fresh.layers.views = fresh.layers.views.filter((view) => view.id !== "slope");
    expect(changedTiles(metaFixture, fresh).has(viewSourceId("slope"))).toBe(false);
  });
});

describe("applyTileChanges", () => {
  it("gives a source its new addresses, made absolute, which reloads it", () => {
    const setTiles = vi.fn();
    const map = { getSource: vi.fn((id: string) => (id === DEM_SOURCE ? { setTiles } : undefined)) };
    applyTileChanges(
      map as never,
      new Map([
        [DEM_SOURCE, ["/tiles/dem/{z}/{x}/{y}.png?v=new"]],
        ["missing", ["/x"]],
      ]),
      "http://localhost:5173",
    );
    expect(setTiles).toHaveBeenCalledWith(["http://localhost:5173/tiles/dem/{z}/{x}/{y}.png?v=new"]);
  });
});
