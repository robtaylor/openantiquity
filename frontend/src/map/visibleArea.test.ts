import { describe, expect, it } from "vitest";
import {
  centreForVisible,
  framePoints,
  NO_COVER,
  uncoveredBounds,
  visibleCentre,
  visibleOffset,
} from "./visibleArea.js";

describe("the uncovered map", () => {
  const phone = { left: 0, right: 0, top: 68, bottom: 450 };

  it("finds the middle of what the chrome leaves showing", () => {
    expect(visibleOffset(NO_COVER)).toEqual({ x: 0, y: 0 });
    expect(visibleOffset({ left: 56, right: 400, top: 0, bottom: 28 })).toEqual({ x: -172, y: -14 });
    // A phone with a half-open sheet: well above the middle of the window.
    expect(visibleOffset(phone).y).toBe(-191);
  });

  it("trims the view's bounds to the part that isn't covered", () => {
    const bounds = [-2, 51, -1, 52] as const;
    expect(uncoveredBounds(bounds, { width: 1000, height: 800 }, NO_COVER).map((v) => Number(v.toFixed(9)))).toEqual([
      -2, 51, -1, 52,
    ]);
    const [west, south, east, north] = uncoveredBounds(
      bounds,
      { width: 1000, height: 800 },
      { left: 100, right: 400, top: 0, bottom: 400 },
    );
    expect(west).toBeCloseTo(-1.9, 9);
    expect(east).toBeCloseTo(-1.4, 9);
    expect(north).toBeCloseTo(52, 9);
    // Half way down the screen is a little north of half way in latitude, as Mercator stretches the north.
    expect(south).toBeGreaterThan(51.5);
    expect(south).toBeLessThan(51.51);
  });

  it("points the camera so a spot lands in the middle of what shows", () => {
    const same = centreForVisible(-1.85, 51.43, 15, NO_COVER);
    expect(same.lng).toBeCloseTo(-1.85, 9);
    expect(same.lat).toBeCloseTo(51.43, 9);
    const centre = centreForVisible(-1.85, 51.43, 15, phone);
    // The spot is to show above the middle of the window, so the camera points south of it.
    expect(centre.lng).toBeCloseTo(-1.85, 9);
    expect(centre.lat).toBeLessThan(51.43);
  });

  it("finds the ground at the middle of what's showing, the other way from centreForVisible", () => {
    const desktop = { left: 56, right: 400, top: 0, bottom: 28 };
    const camera = { lng: -1.85, lat: 51.43, zoom: 16 };
    expect(visibleCentre(camera, NO_COVER)).toEqual({ lng: -1.85, lat: 51.43 });
    const middle = visibleCentre(camera, desktop);
    // The panel is on the right, so the middle of what's showing is west of the camera, and a little north.
    expect(middle.lng).toBeLessThan(camera.lng);
    expect(middle.lat).toBeGreaterThan(camera.lat);
    const back = centreForVisible(middle.lng, middle.lat, camera.zoom, desktop);
    expect(back.lng).toBeCloseTo(camera.lng, 9);
    expect(back.lat).toBeCloseTo(camera.lat, 9);
  });

  it("turns the offset with the map", () => {
    // East up: the panel on the right covers the south, so the middle of what's showing is to the north.
    const turned = visibleCentre(
      { lng: -1.85, lat: 51.43, zoom: 16, bearing: 90 },
      { left: 0, right: 400, top: 0, bottom: 0 },
    );
    expect(turned.lng).toBeCloseTo(-1.85, 9);
    expect(turned.lat).toBeGreaterThan(51.43);
  });
});

describe("framing a shape that is being changed", () => {
  const size = { width: 1000, height: 800 };
  const open = { top: 0, right: 0, bottom: 0, left: 0 };
  const working = { pixels: 240, closest: 22 };
  // A square `metres` across at Avebury's latitude.
  const square = (metres: number): Array<[number, number]> => {
    const lat = 51.4286;
    const dLat = metres / 111_320;
    const dLng = metres / (111_320 * Math.cos((lat * Math.PI) / 180));
    return [
      [-1.8542, lat],
      [-1.8542 + dLng, lat],
      [-1.8542 + dLng, lat + dLat],
      [-1.8542, lat + dLat],
    ];
  };
  // How many pixels `metres` take at `zoom`, 512 px a tile, at that latitude.
  const pixels = (metres: number, zoom: number): number =>
    metres / ((40_075_016.7 * Math.cos((51.4286 * Math.PI) / 180)) / (512 * 2 ** zoom));

  it("comes closer than the usual limit for a small shape, until it is a workable size", () => {
    const framed = framePoints(square(10), size, open, { maxZoom: 18, workingSpan: working });
    expect(framed?.zoom).toBeGreaterThan(18);
    expect(framed?.zoom).toBeLessThan(22);
    expect(pixels(10, framed?.zoom ?? 0)).toBeCloseTo(240, -1);
  });

  it("stops at the closest the map goes for a very small one", () => {
    expect(framePoints(square(2), size, open, { maxZoom: 18, workingSpan: working })?.zoom).toBe(22);
  });

  it("leaves a shape that is already a workable size at the usual limit, and a big one fitted", () => {
    const usual = (metres: number) => framePoints(square(metres), size, open, { maxZoom: 18 })?.zoom;
    const worked = (metres: number) =>
      framePoints(square(metres), size, open, { maxZoom: 18, workingSpan: working })?.zoom;
    expect(pixels(100, 18)).toBeGreaterThan(240);
    expect(worked(100)).toBe(18);
    expect(worked(100)).toBe(usual(100));
    expect(worked(2000)).toBe(usual(2000));
    expect(worked(2000)).toBeLessThan(18);
  });

  it("keeps one point alone at the usual limit, since it has no size to bring up", () => {
    const spot: Array<[number, number]> = [[-1.8542, 51.4286]];
    expect(framePoints(spot, size, open, { maxZoom: 18, workingSpan: working })?.zoom).toBe(18);
  });
});
