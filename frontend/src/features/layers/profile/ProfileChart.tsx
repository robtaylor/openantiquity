import { type KeyboardEvent, type PointerEvent, useMemo, useRef } from "react";
import { heightText } from "../../../map/StatusBar.js";
import type { ProfileSample } from "./api.js";
import { type ChartBox, chartModel } from "./chart.js";
import { distanceText } from "./line.js";

const BOX: ChartBox = { width: 352, height: 180, left: 46, right: 12, top: 12, bottom: 28 };

export interface ProfileChartProps {
  samples: readonly ProfileSample[];
  /** The sample under the pointer, from the chart or the map. */
  hover: number | null;
  onHover: (index: number | null) => void;
}

/** The sample nearest a distance along the line. Samples are in order of distance. */
function nearestSample(samples: readonly ProfileSample[], distance: number): number {
  let lo = 0;
  let hi = samples.length - 1;
  while (hi - lo > 1) {
    const mid = (lo + hi) >> 1;
    if ((samples[mid]?.distance_m ?? 0) < distance) lo = mid;
    else hi = mid;
  }
  const below = samples[lo]?.distance_m ?? 0;
  const above = samples[hi]?.distance_m ?? 0;
  return distance - below <= above - distance ? lo : hi;
}

function sampleText(sample: ProfileSample | undefined): string {
  if (!sample) return "";
  const height = sample.elevation === null ? "no height data" : `${heightText(sample.elevation)} high`;
  return `${distanceText(sample.distance_m)} along, ${height}`;
}

/**
 * A section through the ground along the profile line, drawn by hand in SVG.
 * The pointer, a finger, or the arrow keys move a marker along it, and the
 * same marker follows the pointer along the line on the map.
 */
export function ProfileChart({ samples, hover, onHover }: ProfileChartProps) {
  const model = useMemo(() => chartModel(samples, BOX), [samples]);
  const svg = useRef<SVGSVGElement>(null);
  const last = samples.length - 1;
  const current = hover === null ? undefined : samples[hover];

  function fromPointer(event: PointerEvent<SVGSVGElement>): void {
    const rect = svg.current?.getBoundingClientRect();
    if (!rect || rect.width === 0 || last < 1) return;
    const x = ((event.clientX - rect.left) / rect.width) * BOX.width;
    const length = samples[last]?.distance_m ?? 0;
    const plot = BOX.width - BOX.left - BOX.right;
    const distance = Math.min(length, Math.max(0, ((x - BOX.left) / plot) * length));
    onHover(nearestSample(samples, distance));
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const step = event.shiftKey ? Math.max(1, Math.round(samples.length / 10)) : 1;
    const from = hover ?? 0;
    let next: number;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") next = hover === null ? 0 : from + step;
    else if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = from - step;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = last;
    else if (event.key === "Escape") {
      if (hover === null) return;
      onHover(null);
      event.preventDefault();
      // Escape here clears the marker. It must not also close the panel.
      event.stopPropagation();
      return;
    } else return;
    event.preventDefault();
    onHover(Math.min(last, Math.max(0, next)));
  }

  const markerX = current ? model.x(current.distance_m) : null;
  const markerY = current?.elevation != null ? model.y(current.elevation) : null;
  // The label sits on whichever side of the marker has room.
  const labelOnLeft = markerX !== null && markerX > BOX.width / 2;

  return (
    <div
      className="fc-profile-chart"
      role="slider"
      tabIndex={0}
      aria-label="Height along the line"
      aria-valuemin={0}
      aria-valuemax={Math.round(samples[last]?.distance_m ?? 0)}
      aria-valuenow={Math.round(current?.distance_m ?? 0)}
      aria-valuetext={current ? sampleText(current) : "Use the arrow keys to move along the line"}
      onKeyDown={onKeyDown}
      onBlur={() => onHover(null)}
    >
      <svg
        ref={svg}
        viewBox={`0 0 ${BOX.width} ${BOX.height}`}
        className="fc-profile-chart__svg"
        aria-hidden="true"
        onPointerMove={fromPointer}
        onPointerDown={fromPointer}
        onPointerLeave={(event) => {
          if (event.pointerType === "mouse") onHover(null);
        }}
      >
        {model.heightTicks.map((tick) => (
          <g key={`h${tick.value}`} className="fc-profile-chart__tick">
            <line x1={BOX.left} x2={BOX.width - BOX.right} y1={tick.at} y2={tick.at} />
            <text x={BOX.left - 6} y={tick.at} textAnchor="end" dominantBaseline="central">
              {tick.value} m
            </text>
          </g>
        ))}
        {model.distanceTicks.map((tick) => (
          <g key={`d${tick.value}`} className="fc-profile-chart__tick">
            <line x1={tick.at} x2={tick.at} y1={BOX.height - BOX.bottom} y2={BOX.height - BOX.bottom + 4} />
            <text x={tick.at} y={BOX.height - BOX.bottom + 16} textAnchor="middle">
              {distanceText(tick.value)}
            </text>
          </g>
        ))}
        <path className="fc-profile-chart__area" d={model.area} />
        <path className="fc-profile-chart__line" d={model.line} />
        {markerX !== null ? (
          <g className="fc-profile-chart__marker" data-testid="profile-chart-marker">
            <line x1={markerX} x2={markerX} y1={BOX.top} y2={BOX.height - BOX.bottom} />
            {markerY !== null ? <circle cx={markerX} cy={markerY} r={4.5} /> : null}
            <text
              x={labelOnLeft ? markerX - 8 : markerX + 8}
              y={BOX.top + 10}
              textAnchor={labelOnLeft ? "end" : "start"}
              className="fc-profile-chart__label"
            >
              {distanceText(current?.distance_m ?? 0)} along:{" "}
              {current?.elevation != null ? heightText(current.elevation) : "no data"}
            </text>
          </g>
        ) : null}
      </svg>
    </div>
  );
}
