/**
 * The midpoint dots of the path being marked: a faint 8 px dot in a 32 px
 * target half way along each segment, on the curve as drawn. They are a
 * pointer's shortcut for "Insert a point after", which stays in the
 * selected-point bar for the keyboard, so they take no focus and are
 * hidden from screen readers.
 *
 * - A drag inserts a point there and carries straight on as a drag of that
 *   point: one step for undo. It starts as a handle's drag does, once a
 *   finger or a pen has moved 8 px, or a mouse 3 px.
 * - A tap or click without a drag inserts the point and selects it.
 * - A long press by a finger or a pen, held 500 ms without dragging, does
 *   nothing when it lets go.
 * - A drag ends when a move arrives with no button held, or when the path's
 *   point count changes under it, as Undo by another finger does.
 *
 * A dot is shown only where its target keeps clear of every point handle's
 * target, so a handle always wins, and only while the handles themselves
 * aren't thinned and the path has room for another point.
 */

import type { Map as MapLibreMap } from "maplibre-gl";
import { type PointerEvent as ReactPointerEvent, useEffect, useRef } from "react";
import type { ShapeLimits } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { lngLatAtClient, screenPoint } from "../../map/useMapFrame.js";
import { useMarkStore } from "./markStore.js";
import { dragStartPx, LONG_PRESS_MS, mapSize, visibleHandles } from "./PathHandles.js";
import { hasRoomForPoint, type LngLat, type Path, segmentMiddles } from "./path.js";

/** A dot's target, and a point handle's, across in pixels. */
export const DOT_TARGET_PX = 32;
export const HANDLE_TARGET_PX = 44;
/** How far a dot's middle must be from every handle's middle for the two targets not to overlap. */
export const DOT_CLEARANCE_PX = (DOT_TARGET_PX + HANDLE_TARGET_PX) / 2;

export interface Dot {
  /** The segment, named by the index of the point it starts from. */
  index: number;
  x: number;
  y: number;
}

type Project = (point: LngLat) => { x: number; y: number };

/**
 * Which segments get a dot, and where on screen: those whose middle is in
 * view and at least `DOT_CLEARANCE_PX` from the segment's ends and from
 * every handle drawn (`handles`). None while the handles are `thinned`, or
 * without room for one more point under `limits`.
 */
export function dotsInView(
  path: Path,
  project: Project,
  size: { width: number; height: number },
  handles: readonly number[],
  thinned: boolean,
  limits: ShapeLimits | undefined,
): Dot[] {
  if (thinned || !limits || !hasRoomForPoint(path, limits)) return [];
  const middles = segmentMiddles(path);
  if (middles.length === 0) return [];
  const count = path.points.length;
  const at = (index: number) => {
    const point = path.points[index];
    return point ? project([point.lon, point.lat]) : null;
  };
  const handlePlaces = handles.map(at).filter((place) => place !== null);
  const dots: Dot[] = [];
  middles.forEach((middle, index) => {
    const { x, y } = project(middle);
    if (x < 0 || x > size.width || y < 0 || y > size.height) return;
    const near = [at(index), at((index + 1) % count), ...handlePlaces];
    if (near.some((place) => place !== null && Math.hypot(place.x - x, place.y - y) < DOT_CLEARANCE_PX)) return;
    dots.push({ index, x, y });
  });
  return dots;
}

interface DotPress {
  pointerId: number;
  pointerType: string;
  x: number;
  y: number;
  at: number;
  dragging: boolean;
  /** How many points the path had just after the insert. */
  count: number;
  stop: () => void;
}

/**
 * A press on a dot. It is followed on the window, not on the dot, since the
 * dot moves or goes once its point is inserted and the drag carries on.
 */
function useDotPress(map: MapLibreMap): (event: ReactPointerEvent<HTMLElement>, index: number) => void {
  const press = useRef<DotPress | null>(null);
  useEffect(() => () => press.current?.stop(), []);

  return (event, index) => {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    // Keep the map from taking the press as the start of a pan.
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    press.current?.stop();
    const { pointerId, pointerType } = event;

    const onMove = (move: PointerEvent): void => {
      const current = press.current;
      if (!current || move.pointerId !== pointerId) return;
      // A button let go where the page didn't hear it ends the drag.
      if (move.buttons === 0) {
        current.stop();
        return;
      }
      // So does a change to the path from elsewhere, such as Undo by another finger: the point may be gone.
      if (current.dragging && useMarkStore.getState().shape.present.points.length !== current.count) {
        current.stop();
        return;
      }
      if (!current.dragging) {
        const moved = Math.hypot(move.clientX - current.x, move.clientY - current.y);
        if (moved <= dragStartPx(pointerType)) return;
        const limits = useMapStore.getState().meta?.shapes;
        if (!limits || !useMarkStore.getState().insertMidpoint(index, limits, false)) {
          current.stop();
          return;
        }
        current.dragging = true;
        current.count = useMarkStore.getState().shape.present.points.length;
      }
      useMarkStore.getState().move(index + 1, lngLatAtClient(map, move.clientX, move.clientY), true);
    };
    const onUp = (up: PointerEvent): void => {
      const current = press.current;
      if (!current || up.pointerId !== pointerId) return;
      current.stop();
      if (current.dragging) return;
      // A long press is a finger's or a pen's, and on a dot it does nothing.
      const held = pointerType !== "mouse" && performance.now() - current.at >= LONG_PRESS_MS;
      const limits = useMapStore.getState().meta?.shapes;
      if (!held && limits) useMarkStore.getState().insertMidpoint(index, limits, true);
    };
    const onCancel = (cancel: PointerEvent): void => {
      if (cancel.pointerId === pointerId) press.current?.stop();
    };
    const stop = (): void => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
      window.removeEventListener("pointercancel", onCancel);
      if (press.current?.stop === stop) press.current = null;
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
    window.addEventListener("pointercancel", onCancel);
    press.current = {
      pointerId,
      pointerType,
      x: event.clientX,
      y: event.clientY,
      at: performance.now(),
      dragging: false,
      count: 0,
      stop,
    };
  };
}

/** The dots of the path, under its handles. */
export function MidpointDots({ map, path }: { map: MapLibreMap; path: Path }) {
  const selected = useMarkStore((state) => state.selected);
  const limits = useMapStore((state) => state.meta?.shapes);
  const onPointerDown = useDotPress(map);
  const { indices, thinned } = visibleHandles(map, path, selected);
  const dots = dotsInView(path, (point) => screenPoint(map, point), mapSize(map), indices, thinned, limits);
  return (
    <div className="fc-midpoints" aria-hidden="true">
      {dots.map((dot) => (
        // biome-ignore lint/a11y/noStaticElementInteractions: a pointer's shortcut for "Insert a point after", which the keyboard has in the bar
        <div
          // A segment is named by the point it starts from, as a handle is by its point.
          key={dot.index}
          className="fc-midpoint"
          data-segment={dot.index}
          style={{ transform: `translate(${dot.x}px, ${dot.y}px)` }}
          onPointerDown={(event) => onPointerDown(event, dot.index)}
          onContextMenu={(event) => event.preventDefault()}
          data-testid="midpoint-dot"
        >
          <span className="fc-midpoint__dot" />
        </div>
      ))}
    </div>
  );
}
