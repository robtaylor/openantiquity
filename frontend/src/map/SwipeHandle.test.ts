// @vitest-environment node
import { describe, expect, it } from "vitest";
import { LABEL_GAP, MIN_LABEL_WIDTH, placeLabels } from "./SwipeHandle.js";

/** A desktop map 1440 wide: the rail takes 56, the labels keep 12 clear of it and 64 clear of the right edge. */
const LEFT = 68;
const RIGHT = 1376;

describe("placeLabels", () => {
  it("sets each label beside the divide, with all the room on its side", () => {
    const labels = placeLabels(748, LEFT, RIGHT);
    expect(labels.left).toEqual({ right: LABEL_GAP, maxWidth: 748 - LABEL_GAP - LEFT });
    expect(labels.right).toEqual({ left: LABEL_GAP, maxWidth: RIGHT - 748 - LABEL_GAP });
  });

  it("narrows a label as its side narrows, then leaves it out", () => {
    const near = placeLabels(LEFT + LABEL_GAP + 80, LEFT, RIGHT);
    expect(near.left).toEqual({ right: LABEL_GAP, maxWidth: 80 });
    const tight = placeLabels(LEFT + LABEL_GAP + MIN_LABEL_WIDTH - 1, LEFT, RIGHT);
    expect(tight.left).toBeNull();
    expect(tight.right).not.toBeNull();
  });

  it("keeps the left label out from under the buttons when the divide is at the right-hand limit", () => {
    // The divide can go to 32 px from the edge of the map, past where the labels may.
    const x = 1440 - 32;
    const labels = placeLabels(x, LEFT, RIGHT);
    expect(labels.right).toBeNull();
    // The left label ends at the labels' own limit, not beside the divide.
    expect(labels.left).toEqual({ right: x - RIGHT, maxWidth: RIGHT - LEFT });
  });

  it("drops the left label at the left-hand limit, where it would run under the rail", () => {
    const labels = placeLabels(56 + 32, LEFT, RIGHT);
    expect(labels.left).toBeNull();
    expect(labels.right).toEqual({ left: LABEL_GAP, maxWidth: RIGHT - (56 + 32) - LABEL_GAP });
  });

  it("copes with a map too narrow for either label", () => {
    expect(placeLabels(60, 12, 100)).toEqual({ left: null, right: null });
  });
});
