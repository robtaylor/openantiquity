// @vitest-environment node
import { describe, expect, it } from "vitest";
import { BAR_CLEARANCE_PX, DOT_RADIUS_PX, liftOverBar } from "./keepClear.js";

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
