import { describe, expect, it } from "vitest";
import { fillTileTemplate, TileTemplateError, tileAt } from "./tiles.js";

describe("tileAt", () => {
  it("finds the tile that holds Avebury", () => {
    // Checked against the slippy-map formula on the OpenStreetMap wiki.
    const tile = tileAt(-1.8542, 51.4286, 14);
    expect({ z: tile.z, x: tile.x, y: tile.y }).toEqual({ z: 14, x: 8107, y: 5453 });
    expect(tile.fx).toBeGreaterThanOrEqual(0);
    expect(tile.fx).toBeLessThan(1);
    expect(tile.fy).toBeGreaterThanOrEqual(0);
    expect(tile.fy).toBeLessThan(1);
  });

  it("refuses a fractional zoom", () => {
    expect(() => tileAt(0, 0, 1.5)).toThrow(TileTemplateError);
  });
});

describe("fillTileTemplate", () => {
  it("fills z, x and y and keeps the version token", () => {
    expect(fillTileTemplate("/tiles/lidar/composite/{z}/{x}/{y}.png?v=5d6f14c54172", { z: 14, x: 8107, y: 5453 })).toBe(
      "/tiles/lidar/composite/14/8107/5453.png?v=5d6f14c54172",
    );
  });

  it("fills a Web Mercator box for a WMS address", () => {
    const url = fillTileTemplate("https://example.org/wms?bbox={bbox-epsg-3857}", { z: 1, x: 0, y: 0 });
    const [minX, minY, maxX, maxY] = (new URL(url).searchParams.get("bbox") ?? "").split(",").map(Number);
    expect(minX).toBeCloseTo(-20037508.34, 1);
    expect(minY).toBeCloseTo(0, 1);
    expect(maxX).toBeCloseTo(0, 1);
    expect(maxY).toBeCloseTo(20037508.34, 1);
  });

  it("fills a quadkey", () => {
    expect(fillTileTemplate("{quadkey}", { z: 3, x: 3, y: 5 })).toBe("213");
  });

  it("refuses a part it can't fill", () => {
    expect(() => fillTileTemplate("/{s}/{z}/{x}/{y}.png", { z: 1, x: 0, y: 0 })).toThrow(TileTemplateError);
  });
});
