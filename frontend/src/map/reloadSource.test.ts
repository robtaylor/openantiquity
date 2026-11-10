// @vitest-environment node
import { describe, expect, it, vi } from "vitest";
import { reloadSource } from "./reloadSource.js";

function fakeMap(options: { internals?: boolean; sources?: Record<string, object> } = {}) {
  const clearTiles = vi.fn();
  const update = vi.fn();
  const refreshTiles = vi.fn();
  const sources: Record<string, object> = options.sources ?? { "view-composite": {}, "overlay-records": {} };
  const managers = Object.fromEntries(Object.keys(sources).map((id) => [id, { clearTiles }]));
  const map = {
    getSource: (id: string) => sources[id],
    refreshTiles,
    ...(options.internals === false ? {} : { style: { tileManagers: managers }, _update: update }),
  };
  return { map, clearTiles, update, refreshTiles };
}

describe("reloadSource", () => {
  it("reloads a raster source's tiles through the public API", () => {
    const { map, clearTiles, update, refreshTiles } = fakeMap();
    reloadSource(map, "view-composite", { type: "raster" });
    expect(refreshTiles).toHaveBeenCalledExactlyOnceWith("view-composite");
    expect(clearTiles).not.toHaveBeenCalled();
    expect(update).not.toHaveBeenCalled();
  });

  it("does the same for elevation", () => {
    const { map, clearTiles, refreshTiles } = fakeMap({ sources: { dem: {} } });
    reloadSource(map, "dem", { type: "raster-dem" });
    expect(refreshTiles).toHaveBeenCalledExactlyOnceWith("dem");
    expect(clearTiles).not.toHaveBeenCalled();
  });

  it("drops a vector source's tiles, because MapLibre's own reload never fetches a failed one again", () => {
    const { map, clearTiles, update, refreshTiles } = fakeMap();
    reloadSource(map, "overlay-records", { type: "vector" });
    expect(clearTiles).toHaveBeenCalledTimes(1);
    expect(update).toHaveBeenCalledTimes(1);
    expect(refreshTiles).not.toHaveBeenCalled();
  });

  it("falls back to refreshTiles for a vector source when MapLibre's undocumented parts are not there", () => {
    const { map, refreshTiles } = fakeMap({ internals: false });
    reloadSource(map, "overlay-records", { type: "vector" });
    expect(refreshTiles).toHaveBeenCalledWith("overlay-records");
  });

  it("drops the tiles of a source declared by address and gives it its address again", () => {
    const setUrl = vi.fn();
    const { map, clearTiles, refreshTiles } = fakeMap({ sources: { "overlay-osm": { setUrl } } });
    reloadSource(map, "overlay-osm", { type: "vector", url: "https://tiles.example/planet" });
    expect(clearTiles).toHaveBeenCalledTimes(1);
    expect(setUrl).toHaveBeenCalledWith("https://tiles.example/planet");
    expect(refreshTiles).not.toHaveBeenCalled();
  });

  it("does nothing for a source the map does not have", () => {
    const { map, clearTiles, refreshTiles } = fakeMap();
    reloadSource(map, "nope", { type: "vector" });
    expect(clearTiles).not.toHaveBeenCalled();
    expect(refreshTiles).not.toHaveBeenCalled();
  });
});
