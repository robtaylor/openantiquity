import { type KeyboardEvent, type PointerEvent, useRef } from "react";
import { compassPoint } from "./compass.js";
import { wrapDegrees } from "./permalink.js";

export interface SunDialProps {
  /** Degrees clockwise from north. */
  azimuth: number;
  onChange: (azimuth: number) => void;
  /**
   * Which way the map is turned: the compass bearing at the top of the
   * screen. The dial turns with the map, so the sun is always drawn on the
   * side of the screen the light really comes from.
   */
  bearing?: number;
  size?: number;
}

/** Bearing from the centre of a box to a point, in degrees clockwise from north. */
export function bearingFromCentre(
  rect: { left: number; top: number; width: number; height: number },
  clientX: number,
  clientY: number,
): number {
  const dx = clientX - (rect.left + rect.width / 2);
  const dy = clientY - (rect.top + rect.height / 2);
  return wrapDegrees((Math.atan2(dx, -dy) * 180) / Math.PI);
}

/** Compass points marked with a tick. North has the letter N in place of one. */
const TICKS = [45, 90, 135, 180, 225, 270, 315];
/**
 * Distance of the N from the centre of the dial, in the 100-unit box it is
 * drawn in. Just inside the ring of ticks, so the sun never sits on it.
 */
const NORTH_RADIUS = 22;

/** Where a compass bearing falls on the dial, `radius` out from the centre, when the map is turned to `mapBearing`. */
export function dialPoint(compassBearing: number, mapBearing: number, radius: number): { x: number; y: number } {
  const angle = ((compassBearing - mapBearing) * Math.PI) / 180;
  return { x: 50 + radius * Math.sin(angle), y: 50 - radius * Math.cos(angle) };
}

/**
 * A compass dial with the sun on its rim. Drag the sun, or anywhere on the
 * dial, to say where the light comes from. With the keyboard, the arrow keys
 * turn it five degrees at a time, or fifteen with Shift.
 */
export function SunDial({ azimuth, onChange, bearing = 0, size = 96 }: SunDialProps) {
  const ref = useRef<HTMLDivElement>(null);
  const dragging = useRef(false);

  function update(event: PointerEvent<HTMLDivElement>): void {
    const rect = ref.current?.getBoundingClientRect();
    if (!rect) return;
    // The pointer gives a direction on screen. Adding the map's bearing makes it a compass direction.
    onChange(Math.round(wrapDegrees(bearingFromCentre(rect, event.clientX, event.clientY) + bearing)) % 360);
  }

  function onKeyDown(event: KeyboardEvent<HTMLDivElement>): void {
    const step = event.shiftKey ? 15 : 5;
    let next: number;
    if (event.key === "ArrowRight" || event.key === "ArrowUp") next = azimuth + step;
    else if (event.key === "ArrowLeft" || event.key === "ArrowDown") next = azimuth - step;
    else if (event.key === "Home") next = 0;
    else if (event.key === "End") next = 180;
    else return;
    event.preventDefault();
    onChange(wrapDegrees(Math.round(next)));
  }

  const rim = 37;
  const sun = dialPoint(azimuth, bearing, rim);
  const north = dialPoint(0, bearing, NORTH_RADIUS);
  const rounded = Math.round(wrapDegrees(azimuth)) % 360;

  return (
    <div
      ref={ref}
      className="fc-sundial"
      style={{ width: size, height: size }}
      role="slider"
      tabIndex={0}
      aria-label="Sun direction"
      aria-valuemin={0}
      aria-valuemax={359}
      aria-valuenow={rounded}
      aria-valuetext={`Light from the ${compassPoint(rounded)}, ${rounded} degrees`}
      onKeyDown={onKeyDown}
      onPointerDown={(event) => {
        dragging.current = true;
        event.currentTarget.setPointerCapture?.(event.pointerId);
        update(event);
      }}
      onPointerMove={(event) => {
        if (dragging.current) update(event);
      }}
      onPointerUp={() => {
        dragging.current = false;
      }}
      onPointerCancel={() => {
        dragging.current = false;
      }}
    >
      <svg width={size} height={size} viewBox="0 0 100 100" aria-hidden="true">
        <circle className="fc-sundial__face" cx="50" cy="50" r="46" />
        <circle className="fc-sundial__rim" cx="50" cy="50" r={rim} />
        {TICKS.map((tick) => {
          const inner = dialPoint(tick, bearing, tick % 90 === 0 ? 27 : 30);
          const outer = dialPoint(tick, bearing, 33);
          return <line key={tick} className="fc-sundial__tick" x1={inner.x} y1={inner.y} x2={outer.x} y2={outer.y} />;
        })}
        {/* The letter stays upright and moves round the dial as the map turns. */}
        <text
          className="fc-sundial__north"
          x={north.x}
          y={north.y}
          textAnchor="middle"
          dominantBaseline="central"
          data-testid="sundial-north"
        >
          N
        </text>
        {/* The beam shows which way the light travels across the ground. */}
        <line className="fc-sundial__beam" x1={sun.x} y1={sun.y} x2={50} y2={50} />
        <circle className="fc-sundial__hub" cx="50" cy="50" r="3" />
        <g className="fc-sundial__sun" transform={`translate(${sun.x} ${sun.y})`}>
          <circle r="9" />
          <circle className="fc-sundial__sun-core" r="4.5" />
        </g>
      </svg>
    </div>
  );
}
