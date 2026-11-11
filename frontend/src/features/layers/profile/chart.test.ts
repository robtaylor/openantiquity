import { describe, expect, it } from "vitest";
import { type ChartBox, chartModel, niceTicks } from "./chart.js";

const BOX: ChartBox = { width: 340, height: 160, left: 40, right: 10, top: 10, bottom: 30 };

describe("niceTicks", () => {
  it("steps by 1, 2 or 5 times a power of ten", () => {
    expect(niceTicks(0, 556, 4)).toEqual([0, 100, 200, 300, 400, 500]);
    expect(niceTicks(152.1, 161.9, 4)).toEqual([154, 156, 158, 160]);
    expect(niceTicks(0, 1, 4)).toEqual([0, 0.2, 0.4, 0.6, 0.8, 1]);
    expect(niceTicks(0, 4800, 4)).toEqual([0, 1000, 2000, 3000, 4000]);
  });

  it("gives one tick for an empty range and none for nonsense", () => {
    expect(niceTicks(5, 5, 4)).toEqual([5]);
    expect(niceTicks(Number.NaN, 1, 4)).toEqual([]);
  });
});

describe("chartModel", () => {
  const samples = [
    { distance_m: 0, elevation: 150 },
    { distance_m: 50, elevation: 155 },
    { distance_m: 100, elevation: 150 },
  ];

  it("spans the plot from the first sample to the last", () => {
    const model = chartModel(samples, BOX);
    expect(model.x(0)).toBe(40);
    expect(model.x(100)).toBe(330);
    expect(model.lowest).toBe(150);
    expect(model.highest).toBe(155);
    // The highest point is drawn higher up the chart than the lowest.
    expect(model.y(155)).toBeLessThan(model.y(150));
    expect(model.line.startsWith("M40.0 ")).toBe(true);
  });

  it("breaks the line where there is no data", () => {
    const model = chartModel(
      [
        { distance_m: 0, elevation: 150 },
        { distance_m: 10, elevation: 151 },
        { distance_m: 20, elevation: null },
        { distance_m: 30, elevation: 152 },
        { distance_m: 40, elevation: 151 },
      ],
      BOX,
    );
    expect(model.line.match(/M/g)).toHaveLength(2);
    expect(model.area.match(/Z/g)).toHaveLength(2);
  });

  it("draws nothing, without failing, for a line with no data", () => {
    const model = chartModel(
      [
        { distance_m: 0, elevation: null },
        { distance_m: 10, elevation: null },
      ],
      BOX,
    );
    expect(model.line).toBe("");
    expect(model.lowest).toBeNull();
  });

  it("says how much heights are stretched", () => {
    // 100 m across 290 units, and the 5 m rise padded to 5.75 m over 120 units.
    const model = chartModel(samples, BOX);
    expect(model.stretch).toBeCloseTo(100 / 290 / (5.75 / 120), 6);
  });

  it("keeps a flat line from being stretched into noise", () => {
    const model = chartModel(
      [
        { distance_m: 0, elevation: 150 },
        { distance_m: 100, elevation: 150.01 },
      ],
      BOX,
    );
    expect(model.y(150) - model.y(151)).toBeCloseTo(120 / 2, 6);
  });

  it("refuses a box with no room", () => {
    expect(() => chartModel(samples, { ...BOX, width: 40 })).toThrow();
  });
});
