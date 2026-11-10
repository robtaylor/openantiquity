// @vitest-environment node
import { describe, expect, it } from "vitest";
import { compassPoint } from "./compass.js";

describe("compass", () => {
  it("names the nearest of eight points", () => {
    expect(compassPoint(0)).toBe("north");
    expect(compassPoint(315)).toBe("north-west");
    expect(compassPoint(338)).toBe("north");
    expect(compassPoint(337)).toBe("north-west");
    expect(compassPoint(-90)).toBe("west");
    expect(compassPoint(450)).toBe("east");
  });
});
