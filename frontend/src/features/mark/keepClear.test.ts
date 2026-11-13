// @vitest-environment node
import { describe, expect, it } from "vitest";
import { BAR_CLEARANCE_PX, DOT_RADIUS_PX, liftOverBar, lowerUnderGuide } from "./keepClear.js";

const BAR = { left: 0, right: 400, top: 700, bottom: 800 };
const GUIDE = { left: 12, right: 300, top: 12, bottom: 240 };

describe("keeping placed points clear of what floats on the map", () => {
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

  it("lowers the map just enough that no point is under the guide, leaving points beside it", () => {
    expect(lowerUnderGuide([{ x: 100, y: 300 }], GUIDE, null)).toBe(0);
    expect(
      lowerUnderGuide(
        [
          { x: 100, y: 200 },
          { x: 150, y: 100 },
        ],
        GUIDE,
        null,
      ),
    ).toBe(240 + BAR_CLEARANCE_PX - (100 - DOT_RADIUS_PX));
    expect(lowerUnderGuide([{ x: 350, y: 100 }], GUIDE, null)).toBe(0);
  });

  it("leaves the map be when lowering it would put a point under the bar", () => {
    expect(lowerUnderGuide([{ x: 100, y: 200 }], GUIDE, BAR)).toBe(240 + BAR_CLEARANCE_PX - 194);
    expect(
      lowerUnderGuide(
        [
          { x: 100, y: 200 },
          { x: 100, y: 660 },
        ],
        GUIDE,
        BAR,
      ),
    ).toBe(0);
  });
});
