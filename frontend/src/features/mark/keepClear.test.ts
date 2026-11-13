// @vitest-environment node
import { describe, expect, it } from "vitest";
import { BAR_CLEARANCE_PX, DOT_RADIUS_PX, liftOverBar, slideIntoView } from "./keepClear.js";

const BAR = { left: 0, right: 400, top: 700, bottom: 800 };

describe("keeping placed points clear of the phone's bar", () => {
  it("lifts the map just enough that no point is under the bar, leaving points beside or below it", () => {
    expect(liftOverBar([{ x: 100, y: 500 }], BAR)).toBe(0);
    expect(
      liftOverBar(
        [
          { x: 100, y: 720 },
          { x: 200, y: 690 },
        ],
        BAR,
      ),
    ).toBe(720 + DOT_RADIUS_PX + BAR_CLEARANCE_PX - 700);
    expect(liftOverBar([{ x: 500, y: 720 }], BAR)).toBe(0);
    expect(liftOverBar([{ x: 100, y: 820 }], BAR)).toBe(0);
  });
});

describe("slideIntoView", () => {
  const box = { left: 0, top: 100, right: 400, bottom: 400 };

  it("leaves a marking alone when all of it is in the box", () => {
    expect(
      slideIntoView(
        [
          { x: 100, y: 150 },
          { x: 300, y: 350 },
        ],
        box,
      ),
    ).toBeNull();
  });

  it("slides a marking that fits by the least that shows all of it", () => {
    // Two of its three points are under the sheet, below the box.
    const line = [
      { x: 100, y: 430 },
      { x: 200, y: 340 },
      { x: 300, y: 440 },
    ];
    expect(slideIntoView(line, box)).toEqual([0, 40]);
    // Off to the left and above.
    expect(
      slideIntoView(
        [
          { x: -30, y: 80 },
          { x: 100, y: 200 },
        ],
        box,
      ),
    ).toEqual([-30, -20]);
  });

  it("leaves a marking too big for the box where it is while part of it is in sight", () => {
    const road = [
      { x: -5000, y: 250 },
      { x: 9000, y: 260 },
    ];
    expect(slideIntoView(road, box)).toBeNull();
  });

  it("brings the nearest point of a marking too big for the box to the middle when none of it is in sight", () => {
    const road = [
      { x: -5000, y: 700 },
      { x: 260, y: 720 },
      { x: 9000, y: 900 },
    ];
    expect(slideIntoView(road, box)).toEqual([260 - 200, 720 - 250]);
  });

  it("does nothing with no points", () => {
    expect(slideIntoView([], box)).toBeNull();
  });
});
