import { describe, expect, it } from "vitest";
import { centreForVisible, NO_COVER, uncoveredBounds, visibleOffset } from "./visibleArea.js";

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
});
