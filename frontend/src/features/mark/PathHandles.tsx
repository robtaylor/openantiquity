/**
 * The handles of the path being marked: a 12 px dot in a 44 px target for
 * each point, a square for a straight point and a circle for a curved one.
 * They are buttons above the map canvas, so no finding under them takes the
 * tap, and the path is one tab stop with a roving tabindex over them.
 *
 * - A tap or click selects a point. Shift-click switches its kind, and a tap
 *   on the far end of an open path of three points or more closes it.
 * - A drag moves the point, recorded as one change for undo. It starts once
 *   a finger or a pen has moved 8 px, or a mouse 3 px, so a finger's wobble
 *   is still a tap or a press.
 * - A long press by a finger or a pen, 500 ms without moving 8 px, switches
 *   the point's kind (Decision 0031), with a short vibration where the
 *   device has one. A mouse never long-presses.
 * - The arrow keys nudge it, with Shift for bigger steps. `[` and `]` step to
 *   the previous and next point, and Delete removes it.
 *
 * Handles are drawn only for points in view, and only while 150 or fewer
 * are. With more, the ends and the selected point keep theirs.
 */

import type { Map as MapLibreMap } from "maplibre-gl";
import { type KeyboardEvent, type MouseEvent, type PointerEvent, useEffect, useRef } from "react";
import { lngLatAtClient, screenPoint } from "../../map/useMapFrame.js";
import { exactGridRefOf } from "./describe.js";
import { focusAddAtCrossAfter, focusHandleIfLost } from "./focus.js";
import { useMarkStore } from "./markStore.js";
import { canClose, endIndex, otherEnd, type Path, type PathPoint, stepIndex } from "./path.js";

/** How far one press of an arrow key moves a point, in pixels, and with Shift held. */
export const NUDGE_PX = 3;
export const NUDGE_FAST_PX = 24;
/** At most this many handles are drawn at once. */
export const HANDLES_MAX_IN_VIEW = 150;
export const LONG_PRESS_MS = 500;
/** A press that moves further than this, in pixels, is not a long press. */
export const LONG_PRESS_SLOP_PX = 8;
/**
 * A press that moves further than this, in pixels, is a drag: a finger or a
 * pen wobbles as far as the long press allows, and a mouse hardly at all.
 */
const DRAG_START_PX = { mouse: 3, other: LONG_PRESS_SLOP_PX } as const;

function dragStartPx(pointerType: string): number {
  return pointerType === "mouse" ? DRAG_START_PX.mouse : DRAG_START_PX.other;
}

const NUDGES: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
};

/** "straight" or "curved", the words the tool uses for a corner and a smooth point. */
function kindWord(point: PathPoint): string {
  return point.kind === "corner" ? "straight" : "curved";
}

/** How a point is named on its handle and on the selected-point bar. */
export function pointName(path: Path, index: number): string {
  const point = path.points[index];
  if (!point) return "";
  const where = exactGridRefOf([point.lon, point.lat]);
  return `Point ${index + 1} of ${path.points.length}, ${kindWord(point)}${where ? `, ${where}` : ""}`;
}

function mapSize(map: MapLibreMap): { width: number; height: number } {
  const container = map.getContainer();
  return {
    width: container.clientWidth || window.innerWidth,
    height: container.clientHeight || window.innerHeight,
  };
}

export interface HandlesInView {
  indices: number[];
  thinned: boolean;
}

/** Where the map is looking, as far as it decides which points are in view. */
function viewOf(map: MapLibreMap): string {
  const { lng, lat } = map.getCenter();
  const { width, height } = mapSize(map);
  return [lng, lat, map.getZoom(), map.getBearing(), map.getPitch(), width, height].join(",");
}

/** The last answer for each map, so the handles and the status line share one for each frame. */
const lastHandles = new WeakMap<
  MapLibreMap,
  { path: Path; selected: number | null; view: string; handles: HandlesInView }
>();

function handlesFor(map: MapLibreMap, path: Path, selected: number | null): HandlesInView {
  const { width, height } = mapSize(map);
  // The bounds are of the ground at sea level, and terrain lifts a point towards the edge of a pitched view, so they
  // are widened by a quarter on each side. Only a point inside them can be on screen, so the rest are never projected.
  const bounds = map.getBounds();
  const padLon = (bounds.getEast() - bounds.getWest()) / 4;
  const padLat = (bounds.getNorth() - bounds.getSouth()) / 4;
  const west = bounds.getWest() - padLon;
  const east = bounds.getEast() + padLon;
  const south = bounds.getSouth() - padLat;
  const north = bounds.getNorth() + padLat;
  const inView: number[] = [];
  path.points.forEach((point, index) => {
    if (point.lon < west || point.lon > east || point.lat < south || point.lat > north) return;
    const { x, y } = screenPoint(map, [point.lon, point.lat]);
    if (x >= 0 && x <= width && y >= 0 && y <= height) inView.push(index);
  });
  const always = new Set([0, path.points.length - 1, ...(selected === null ? [] : [selected])]);
  if (inView.length > HANDLES_MAX_IN_VIEW) {
    return { indices: [...always].filter((index) => index < path.points.length).sort((a, b) => a - b), thinned: true };
  }
  const shown = new Set([...inView, ...always]);
  return { indices: [...shown].filter((index) => index < path.points.length).sort((a, b) => a - b), thinned: false };
}

/**
 * Which points get a handle: every point in view while there are few
 * enough, otherwise only the ends and the selected point. `thinned` is true
 * when points in view have no handle.
 */
export function visibleHandles(map: MapLibreMap, path: Path, selected: number | null): HandlesInView {
  const view = viewOf(map);
  const last = lastHandles.get(map);
  if (last && last.path === path && last.selected === selected && last.view === view) return last.handles;
  const handles = handlesFor(map, path, selected);
  lastHandles.set(map, { path, selected, view, handles });
  return handles;
}

interface Press {
  pointerId: number;
  pointerType: string;
  x: number;
  y: number;
  dragging: boolean;
  timer: number | null;
}

function Handle({
  map,
  path,
  index,
  tabbable,
  selected,
  register,
}: {
  map: MapLibreMap;
  path: Path;
  index: number;
  tabbable: boolean;
  selected: boolean;
  register: (index: number, element: HTMLButtonElement | null) => void;
}) {
  const point = path.points[index];
  const press = useRef<Press | null>(null);
  /** True when the click that follows a drag or a long press should do nothing. */
  const swallowClick = useRef(false);
  useEffect(
    () => () => {
      if (press.current?.timer != null) window.clearTimeout(press.current.timer);
    },
    [],
  );
  if (!point) return null;
  const { x, y } = screenPoint(map, [point.lon, point.lat]);

  function endPress(): void {
    const current = press.current;
    if (current?.timer != null) window.clearTimeout(current.timer);
    press.current = null;
  }

  function onPointerDown(event: PointerEvent<HTMLButtonElement>): void {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    // Keep the map from taking the press as the start of a pan.
    event.preventDefault();
    event.currentTarget.setPointerCapture?.(event.pointerId);
    endPress();
    swallowClick.current = false;
    // The long press is a finger's or a pen's gesture. A mouse has Shift-click and the bar's control.
    const timer =
      event.pointerType === "mouse"
        ? null
        : window.setTimeout(() => {
            const current = press.current;
            if (!current || current.dragging) return;
            current.timer = null;
            swallowClick.current = true;
            useMarkStore.getState().switchPointKind(index);
            navigator.vibrate?.(15);
          }, LONG_PRESS_MS);
    press.current = {
      pointerId: event.pointerId,
      pointerType: event.pointerType,
      x: event.clientX,
      y: event.clientY,
      dragging: false,
      timer,
    };
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>): void {
    const current = press.current;
    if (!current || current.pointerId !== event.pointerId) return;
    const moved = Math.hypot(event.clientX - current.x, event.clientY - current.y);
    if (moved > LONG_PRESS_SLOP_PX && current.timer !== null) {
      window.clearTimeout(current.timer);
      current.timer = null;
    }
    if (!current.dragging && moved <= dragStartPx(current.pointerType)) return;
    // A press that has already switched the point's kind doesn't then move it.
    if (!current.dragging && swallowClick.current) return;
    const continuing = current.dragging;
    current.dragging = true;
    swallowClick.current = true;
    useMarkStore.getState().move(index, lngLatAtClient(map, event.clientX, event.clientY), continuing);
  }

  function onClick(event: MouseEvent<HTMLButtonElement>): void {
    if (swallowClick.current) {
      swallowClick.current = false;
      return;
    }
    const mark = useMarkStore.getState();
    if (event.shiftKey) {
      mark.switchPointKind(index);
      return;
    }
    const far = endIndex(path, otherEnd(mark.end));
    // A tap on the far end closes the shape. From the keyboard, Enter selects, and "Close the shape" closes.
    if (event.detail > 0 && mark.drawing && canClose(path) && index === far) {
      mark.closeShape();
      return;
    }
    mark.select(index);
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>): void {
    const mark = useMarkStore.getState();
    const direction = NUDGES[event.key];
    if (direction) {
      event.preventDefault();
      const step = event.shiftKey ? NUDGE_FAST_PX : NUDGE_PX;
      const at = screenPoint(map, [point?.lon ?? 0, point?.lat ?? 0]);
      const moved = map.unproject([at.x + direction[0] * step, at.y + direction[1] * step]);
      mark.move(index, [moved.lng, moved.lat]);
      mark.select(index);
      return;
    }
    if (event.key === "[" || event.key === "]") {
      event.preventDefault();
      mark.select(stepIndex(path, index, event.key === "[" ? -1 : 1));
      return;
    }
    if (event.key === "Delete" || event.key === "Backspace") {
      event.preventDefault();
      const pressed = event.currentTarget;
      mark.remove(index);
      const left = useMarkStore.getState().shape.present.points.length;
      // Focus goes to the neighbouring handle: the one that took this one's place, or the one before it.
      if (left === 0) focusAddAtCrossAfter(pressed);
      else requestAnimationFrame(() => focusHandleIfLost(pressed, Math.min(index, left - 1)));
    }
  }

  const name = pointName(path, index);
  return (
    <button
      ref={(element) => register(index, element)}
      type="button"
      className="fc-path-handle"
      data-kind={point.kind}
      data-index={index}
      data-selected={selected}
      style={{ transform: `translate(${x}px, ${y}px)` }}
      tabIndex={tabbable ? 0 : -1}
      aria-pressed={selected}
      aria-label={`${name}. Drag it, or use the arrow keys, to move it.`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={endPress}
      onPointerCancel={endPress}
      onLostPointerCapture={endPress}
      onClick={onClick}
      onKeyDown={onKeyDown}
      onContextMenu={(event) => event.preventDefault()}
      data-testid="path-handle"
    >
      <span className="fc-path-handle__dot" aria-hidden="true" />
    </button>
  );
}

/** Every handle of the path that is drawn, with the path as one tab stop. */
export function PathHandles({ map, path }: { map: MapLibreMap; path: Path }) {
  const selected = useMarkStore((state) => state.selected);
  const end = useMarkStore((state) => state.end);
  const elements = useRef(new Map<number, HTMLButtonElement>());
  const { indices } = visibleHandles(map, path, selected);
  const tabbable = selected ?? endIndex(path, end);

  // Stepping with [ and ], or deleting, moves the selection: focus follows it while it is on a handle.
  useEffect(() => {
    const active = document.activeElement;
    const onHandle = active instanceof HTMLElement && active.classList.contains("fc-path-handle");
    if (onHandle && selected !== null) elements.current.get(selected)?.focus();
  }, [selected]);

  function register(index: number, element: HTMLButtonElement | null): void {
    if (element) elements.current.set(index, element);
    else elements.current.delete(index);
  }

  return (
    // biome-ignore lint/a11y/useSemanticElements: a fieldset is a form control's frame, and these handles float over the map
    <div className="fc-path-handles" role="group" aria-label="The points of your marking">
      {indices.map((index) => (
        <Handle
          // Points are added and taken out anywhere, so a handle is its position in the path.
          key={index}
          map={map}
          path={path}
          index={index}
          tabbable={index === tabbable}
          selected={index === selected}
          register={register}
        />
      ))}
    </div>
  );
}
