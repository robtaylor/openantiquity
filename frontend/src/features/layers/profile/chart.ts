/**
 * The geometry of the height profile chart: scales, axis ticks and the line,
 * worked out apart from the SVG so it can be tested on its own.
 */

export interface Sample {
  distance_m: number;
  /** Metres above Ordnance Datum Newlyn, or null where there is no data. */
  elevation: number | null;
}

export interface ChartBox {
  width: number;
  height: number;
  /** Room for the height labels on the left. */
  left: number;
  right: number;
  top: number;
  /** Room for the distance labels underneath. */
  bottom: number;
}

export interface Tick {
  value: number;
  /** Where it falls along its axis, in chart units. */
  at: number;
}

export interface ChartModel {
  /** The SVG path of the ground, broken wherever there is no data. */
  line: string;
  /** The same, closed down to the foot of the chart, for a fill under it. */
  area: string;
  heightTicks: Tick[];
  distanceTicks: Tick[];
  /** Lowest and highest ground on the line, or null when it has no data at all. */
  lowest: number | null;
  highest: number | null;
  /** How much taller the chart draws heights than distances. */
  stretch: number;
  x: (distance: number) => number;
  y: (elevation: number) => number;
}

/** Round steps of 1, 2 or 5 times a power of ten, about `count` of them from `min` to `max`. */
export function niceTicks(min: number, max: number, count: number): number[] {
  if (!Number.isFinite(min) || !Number.isFinite(max) || count < 1) return [];
  if (max <= min) return [min];
  const rough = (max - min) / count;
  const power = 10 ** Math.floor(Math.log10(rough));
  // The round step nearest the rough one, measured as a ratio.
  const factor = [1, 2, 5, 10].reduce((best, candidate) =>
    Math.abs(Math.log(candidate * power) - Math.log(rough)) < Math.abs(Math.log(best * power) - Math.log(rough))
      ? candidate
      : best,
  );
  const step = factor * power;
  const ticks: number[] = [];
  for (let value = Math.ceil(min / step) * step; value <= max + step * 1e-9; value += step) {
    // Repeated addition drifts. Rounding to the step's own precision keeps labels clean.
    ticks.push(Number(value.toFixed(Math.max(0, -Math.floor(Math.log10(step))))));
  }
  return ticks;
}

/** Least height range drawn, in metres, so a flat line is not stretched into noise. */
const MIN_RANGE_M = 2;

export function chartModel(samples: readonly Sample[], box: ChartBox): ChartModel {
  const plotWidth = box.width - box.left - box.right;
  const plotHeight = box.height - box.top - box.bottom;
  if (plotWidth <= 0 || plotHeight <= 0) throw new Error("The chart box leaves no room to draw in");

  const length = samples.at(-1)?.distance_m ?? 0;
  const heights = samples.flatMap((sample) => (sample.elevation === null ? [] : [sample.elevation]));
  const lowest = heights.length > 0 ? Math.min(...heights) : null;
  const highest = heights.length > 0 ? Math.max(...heights) : null;

  // A little room above and below the ground, and never less than MIN_RANGE_M in all.
  const middle = lowest === null || highest === null ? 0 : (lowest + highest) / 2;
  const half = Math.max(MIN_RANGE_M, ((highest ?? 0) - (lowest ?? 0)) * 1.15) / 2;
  const floor = middle - half;
  const ceiling = middle + half;

  const x = (distance: number): number => box.left + (length > 0 ? (distance / length) * plotWidth : 0);
  const y = (elevation: number): number => box.top + ((ceiling - elevation) / (ceiling - floor)) * plotHeight;

  const runs: Array<Array<[number, number]>> = [];
  let run: Array<[number, number]> = [];
  for (const sample of samples) {
    if (sample.elevation === null) {
      if (run.length > 0) runs.push(run);
      run = [];
      continue;
    }
    run.push([x(sample.distance_m), y(sample.elevation)]);
  }
  if (run.length > 0) runs.push(run);

  const point = ([px, py]: [number, number]): string => `${px.toFixed(1)} ${py.toFixed(1)}`;
  const line = runs.map((part) => `M${part.map(point).join("L")}`).join("");
  const base = (box.top + plotHeight).toFixed(1);
  const area = runs
    .map((part) => {
      const first = part[0] as [number, number];
      const last = part.at(-1) as [number, number];
      return `M${first[0].toFixed(1)} ${base}L${part.map(point).join("L")}L${last[0].toFixed(1)} ${base}Z`;
    })
    .join("");

  const metresPerUnitAcross = length > 0 ? length / plotWidth : 1;
  const metresPerUnitUp = (ceiling - floor) / plotHeight;

  return {
    line,
    area,
    heightTicks: niceTicks(floor, ceiling, 4).map((value) => ({ value, at: y(value) })),
    distanceTicks: niceTicks(0, length, 4).map((value) => ({ value, at: x(value) })),
    lowest,
    highest,
    stretch: metresPerUnitAcross / metresPerUnitUp,
    x,
    y,
  };
}
