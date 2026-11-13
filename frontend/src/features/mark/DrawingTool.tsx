/**
 * The drawing tool's controls in the mark panel: the guidance block, the
 * drawing bar and the selected-point bar (Decision 0031). Every gesture on
 * the map has a control here that does the same. On a phone the bars float
 * above the sheet's peek stop (`MarkButton`), so they are in reach while the
 * map is free to tap.
 *
 * The tool takes a path and reports a path. How the path is saved is the
 * form's business.
 */

import {
  ArrowLeft,
  ArrowRight,
  Check,
  Crosshair,
  Diamond,
  Plus,
  Redo2,
  Spline,
  Trash2,
  Undo2,
  Waypoints,
} from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect, useMemo, useState } from "react";
import { isMapLive } from "../../map/MapPane.js";
import { useMapFrame } from "../../map/useMapFrame.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { ADD_AT_CROSS, focusFirstControlAfter } from "./focus.js";
import { addAtReticle } from "./MarkLayer.js";
import { useMarkPath, useMarkStore } from "./markStore.js";
import { pointName, visibleHandles } from "./PathHandles.js";
import {
  canClose,
  endDirection,
  endIndex,
  endWord,
  lengthM,
  otherEnd,
  type Path,
  type PathEnd,
  stepIndex,
} from "./path.js";

/** A length as the readout gives it: metres under a kilometre, otherwise kilometres to one place. */
export function lengthWords(metres: number): string {
  if (metres < 1000) return `${Math.round(metres)} m`;
  return `${(metres / 1000).toLocaleString("en-GB", { maximumFractionDigits: 1, minimumFractionDigits: 1 })} km`;
}

function pointsWord(count: number): string {
  return `${count} ${count === 1 ? "point" : "points"}`;
}

/** The state of a marking, as the guidance names it. */
export type MarkingStage = "empty" | "spot" | "line" | "shape";

export function stageOf(path: Path): MarkingStage {
  if (path.points.length === 0) return "empty";
  if (path.closed) return "shape";
  return path.points.length === 1 ? "spot" : "line";
}

/** The device in hand, for the line of guidance that names its gestures. */
export type Device = "computer" | "phone" | "keys";

/**
 * Whether the map has keyboard focus: the last input was a key, and focus
 * is on the map's canvas or one of the path's handles.
 */
function useKeysInMap(map: MapLibreMap | null): boolean {
  const [keys, setKeys] = useState(false);
  useEffect(() => {
    let byKeyboard = false;
    const update = (): void => {
      const active = document.activeElement;
      const inMap =
        active instanceof Element &&
        ((map !== null && isMapLive(map) && active === map.getCanvas()) || active.closest(".fc-annotations") !== null);
      setKeys(byKeyboard && inMap);
    };
    const onKey = (): void => {
      byKeyboard = true;
      update();
    };
    const onPointer = (): void => {
      byKeyboard = false;
      update();
    };
    document.addEventListener("keydown", onKey, true);
    document.addEventListener("pointerdown", onPointer, true);
    document.addEventListener("focusin", update);
    document.addEventListener("focusout", update);
    return () => {
      document.removeEventListener("keydown", onKey, true);
      document.removeEventListener("pointerdown", onPointer, true);
      document.removeEventListener("focusin", update);
      document.removeEventListener("focusout", update);
    };
  }, [map]);
  return keys;
}

export function useDevice(map: MapLibreMap | null, isPhone: boolean): Device {
  const keys = useKeysInMap(map);
  if (keys) return "keys";
  return isPhone ? "phone" : "computer";
}

/** What a tap does now, and what else can be done, as the marking stands. */
export function guidanceFor(stage: MarkingStage, drawing: boolean, end: PathEnd, isPhone: boolean): string {
  const tap = isPhone ? "Tap" : "Click";
  const far = endWord(otherEnd(end));
  if (stage === "empty") return `${tap} the map where the feature is. One ${tap.toLowerCase()} marks a spot.`;
  if (stage === "shape") return "Drag a point to move it, and select one to change or delete it.";
  if (!drawing) {
    return "Select an end point and press “Continue from this end” to add more. Drag a point to move it, and select one to change or delete it.";
  }
  if (stage === "spot") {
    return `This is a spot. ${tap} again to draw a line from it, or drag the point to move it.`;
  }
  return `${tap} to carry the line on, or ${tap.toLowerCase()} the ${far} point to close it into a shape. Drag a point to move it, and select one to change or delete it.`;
}

/** The one line for the device in hand. */
export function deviceLine(device: Device, stage: MarkingStage): string {
  if (device === "keys") {
    return "On the map, Enter finishes and Escape stops drawing. On a point, the arrow keys move it, Shift moves it further, [ and ] step between points, and Delete removes it.";
  }
  if (device === "phone") return "Press and hold a point to switch it between straight and curved.";
  if (stage === "shape") return "Shift-click a point to switch it between straight and curved.";
  return "Shift-click adds the other kind of point, and Shift-click on a point switches its kind. Alt-click on the line adds a point there.";
}

/** The guidance block at the top of the mark panel. Plain text, there every time, read by a screen reader. */
export function Guidance({ map, isPhone }: { map: MapLibreMap | null; isPhone: boolean }) {
  const path = useMarkPath();
  const drawing = useMarkStore((state) => state.drawing);
  const end = useMarkStore((state) => state.end);
  const device = useDevice(map, isPhone);
  const stage = stageOf(path);
  return (
    <section className="fc-mark__guidance" aria-label="How to mark it" data-stage={stage} data-device={device}>
      <p>{guidanceFor(stage, drawing, end, isPhone)}</p>
      <p className="fc-mark__hint">{deviceLine(device, stage)}</p>
    </section>
  );
}

/**
 * "12 points, 4.3 km. Tap the map to add the next one at the north end."
 * `length` is `lengthM(path)`, which a component works out once per path.
 */
export function statusWords(
  path: Path,
  drawing: boolean,
  end: PathEnd,
  isPhone: boolean,
  length = lengthM(path),
): string {
  const count = path.points.length;
  const tap = isPhone ? "Tap" : "Click";
  if (count === 0) return "Nothing placed yet.";
  if (path.closed) return `A closed shape of ${pointsWord(count)}, ${lengthWords(length)} round.`;
  const size = count === 1 ? "1 point" : `${pointsWord(count)}, ${lengthWords(length)}`;
  if (!drawing) return `${size}.`;
  if (count === 1) return `${size}. ${tap} the map to add the next one.`;
  const direction = endDirection(path, end);
  return `${size}. ${tap} the map to add the next one at the ${direction ?? endWord(end)} end.`;
}

/** The length of the path, worked out again only when the path changes, not on every frame of the map. */
export function usePathLength(path: Path): number {
  return useMemo(() => lengthM(path), [path]);
}

/** Said after the status when points in view have no handle. */
export const THINNED_WORDS = " Zoom in to change points.";

/**
 * What the status lines read, the panel's and the phone's: the path, its
 * length, the active end, and whether points in view have no handle, which
 * changes as the map moves.
 */
export function usePathStatus(map: MapLibreMap | null) {
  useMapFrame(map);
  const path = useMarkPath();
  const length = usePathLength(path);
  const end = useMarkStore((state) => state.end);
  const selected = useMarkStore((state) => state.selected);
  const thinned = map && isMapLive(map) && path.points.length > 0 ? visibleHandles(map, path, selected).thinned : false;
  return { path, length, end, thinned };
}

function StatusLine({ map, isPhone }: { map: MapLibreMap | null; isPhone: boolean }) {
  const { path, length, end, thinned } = usePathStatus(map);
  const drawing = useMarkStore((state) => state.drawing);
  return (
    <p className="fc-mark__status" role="status">
      {statusWords(path, drawing, end, isPhone, length)}
      {thinned ? THINNED_WORDS : ""}
    </p>
  );
}

/**
 * The drawing bar: the kind of the next point, the point at the cross, undo
 * and redo, closing and finishing, and the status line.
 */
export function DrawingBar({ map, isPhone }: { map: MapLibreMap | null; isPhone: boolean }) {
  const path = useMarkPath();
  const drawing = useMarkStore((state) => state.drawing);
  const nextKind = useMarkStore((state) => state.nextKind);
  const canUndo = useMarkStore((state) => state.shape.past.length > 0);
  const canRedo = useMarkStore((state) => state.shape.future.length > 0);
  const store = useMarkStore.getState();
  const adding = drawing && !path.closed;
  return (
    <section className="fc-mark__drawing" aria-label="Drawing">
      <div className="fc-mark__row">
        <Button size="sm" icon={<Undo2 size={14} aria-hidden />} disabled={!canUndo} onClick={() => store.undo()}>
          Undo
        </Button>
        <Button size="sm" icon={<Redo2 size={14} aria-hidden />} disabled={!canRedo} onClick={() => store.redo()}>
          Redo
        </Button>
        <Button
          size="sm"
          icon={<Crosshair size={14} aria-hidden />}
          disabled={!adding}
          onClick={() => addAtReticle(map)}
        >
          {ADD_AT_CROSS}
        </Button>
      </div>
      <div className="fc-mark__kind">
        <span className="fc-mark__kind-label" aria-hidden="true">
          Next point
        </span>
        <ChipGroup
          label="Next point"
          value={nextKind}
          onChange={(kind) => store.setNextKind(kind === "smooth" ? "smooth" : "corner")}
          options={[
            { id: "corner", label: "Straight", icon: <Diamond size={14} aria-hidden /> },
            { id: "smooth", label: "Curved", icon: <Spline size={14} aria-hidden /> },
          ]}
        />
      </div>
      <div className="fc-mark__row">
        <Button size="sm" disabled={!canClose(path)} onClick={() => store.closeShape()}>
          Close the shape
        </Button>
        <Button
          size="sm"
          icon={<Check size={14} aria-hidden />}
          disabled={!adding || path.points.length === 0}
          onClick={() => store.finish()}
        >
          Finish
        </Button>
      </div>
      <StatusLine map={map} isPhone={isPhone} />
    </section>
  );
}

/** What the selected point's bar can do, shared by the panel's bar and the phone's. Null with nothing selected. */
export function useSelectedPointActions(map: MapLibreMap | null) {
  const path = useMarkPath();
  const selected = useMarkStore((state) => state.selected);
  if (selected === null) return null;
  const point = path.points[selected];
  if (!point) return null;
  const store = useMarkStore.getState();
  const count = path.points.length;
  const isStart = selected === 0;
  const isEnd = selected === count - 1;
  const lastSegment = path.closed ? count - 1 : count - 2;
  const end: PathEnd | null = path.closed ? null : isEnd ? "end" : isStart ? "start" : null;
  return {
    index: selected,
    point,
    canInsert: selected <= lastSegment,
    /** The end of an open path this point is, which "Continue from this end" carries on from. */
    end,
    isFirst: !path.closed && isStart,
    isLast: !path.closed && isEnd,
    switchKind: () => store.switchPointKind(selected),
    remove: () => store.remove(selected),
    insertAfter: () => store.insertAfterPoint(selected),
    continueFrom: (from: PathEnd) => {
      const pressed = document.activeElement;
      store.continueFrom(from);
      // On a phone the sheet's bar goes as the floating one comes up.
      focusFirstControlAfter(pressed, ".fc-mark-float");
      const at = path.points[endIndex(path, from)];
      if (at && map && isMapLive(map)) map.easeTo({ center: [at.lon, at.lat] });
    },
    step: (by: 1 | -1) => store.select(stepIndex(path, selected, by)),
    done: () => store.select(null),
  };
}

/** The bar for the selected point: its kind, deleting it, inserting after it, continuing from it and stepping on. */
export function SelectedPointBar({ map }: { map: MapLibreMap | null }) {
  const path = useMarkPath();
  const actions = useSelectedPointActions(map);
  if (!actions) return null;
  const { index, point, end } = actions;
  const straight = point.kind === "corner";
  return (
    <section className="fc-mark__selected" aria-label="Selected point">
      <p className="fc-mark__selected-name">{pointName(path, index)}</p>
      <div className="fc-mark__row">
        <Button
          size="sm"
          icon={straight ? <Spline size={14} aria-hidden /> : <Diamond size={14} aria-hidden />}
          onClick={actions.switchKind}
        >
          {straight ? "Make it curved" : "Make it straight"}
        </Button>
        <Button size="sm" icon={<Trash2 size={14} aria-hidden />} onClick={actions.remove}>
          Delete point
        </Button>
        <Button
          size="sm"
          icon={<Plus size={14} aria-hidden />}
          disabled={!actions.canInsert}
          onClick={actions.insertAfter}
        >
          Insert a point after
        </Button>
        {end ? (
          <Button size="sm" icon={<Waypoints size={14} aria-hidden />} onClick={() => actions.continueFrom(end)}>
            Continue from this end
          </Button>
        ) : null}
      </div>
      <div className="fc-mark__row">
        <Button
          size="sm"
          variant="ghost"
          icon={<ArrowLeft size={14} aria-hidden />}
          disabled={actions.isFirst}
          onClick={() => actions.step(-1)}
        >
          Previous point
        </Button>
        <Button
          size="sm"
          variant="ghost"
          icon={<ArrowRight size={14} aria-hidden />}
          disabled={actions.isLast}
          onClick={() => actions.step(1)}
        >
          Next point
        </Button>
        <Button size="sm" variant="ghost" onClick={actions.done}>
          Done
        </Button>
      </div>
    </section>
  );
}
