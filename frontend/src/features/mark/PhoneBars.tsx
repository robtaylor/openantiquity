/**
 * The drawing bars as they float on a phone while points are being added:
 * one row of icon buttons and one status line, so the bar stays under about
 * 100 px and the map above it is free to tap. The panel's guidance block,
 * and the full bars, are in the sheet for whoever opens it. On a computer
 * the bars are in the panel (`DrawingTool`).
 */

import {
  ArrowLeft,
  ArrowRight,
  Check,
  CircleCheck,
  Crosshair,
  Diamond,
  Plus,
  Redo2,
  Spline,
  SquareDashed,
  Trash2,
  Undo2,
  Waypoints,
} from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import type { ReactNode } from "react";
import { isMapLive } from "../../map/MapPane.js";
import { useMapFrame } from "../../map/useMapFrame.js";
import { IconButton } from "../../ui/IconButton.js";
import { lengthWords, usePathLength, useSelectedPointActions } from "./DrawingTool.js";
import { ADD_AT_CROSS, focusFirstControlAfter } from "./focus.js";
import { addAtReticle } from "./MarkLayer.js";
import { useMarkPath, useMarkStore } from "./markStore.js";
import { pointName, visibleHandles } from "./PathHandles.js";
import { canClose, lengthM, type Path, type PathEnd } from "./path.js";

/**
 * What a tap does now, in one line, and once there are points how many and
 * how long: "3 points, 254 m. Tap to carry on, or tap the first point to
 * close it." The same words as the panel's guidance where they fit.
 */
export function phoneStatusWords(path: Path, end: PathEnd, length = lengthM(path)): string {
  const count = path.points.length;
  if (count === 0) return "Tap the map where the feature is.";
  if (count === 1) return "1 point. Tap again to draw a line from it.";
  const size = `${count} points, ${lengthWords(length)}`;
  if (!canClose(path)) return `${size}. Tap to carry on.`;
  return `${size}. Tap to carry on, or tap the ${end === "end" ? "first" : "last"} point to close it.`;
}

function BarButton({
  label,
  onClick,
  disabled = false,
  children,
}: {
  label: string;
  onClick: () => void;
  disabled?: boolean;
  children: ReactNode;
}) {
  return (
    <IconButton className="fc-mark-float__button" label={label} disabled={disabled} onClick={onClick}>
      {children}
    </IconButton>
  );
}

function PhoneStatus({ map }: { map: MapLibreMap | null }) {
  // The handles in view, and so whether they are thinned, change as the map moves.
  useMapFrame(map);
  const path = useMarkPath();
  const length = usePathLength(path);
  const end = useMarkStore((state) => state.end);
  const selected = useMarkStore((state) => state.selected);
  const thinned = map && isMapLive(map) && path.points.length > 0 ? visibleHandles(map, path, selected).thinned : false;
  return (
    <p className="fc-mark-float__line" role="status">
      {phoneStatusWords(path, end, length)}
      {thinned ? " Zoom in to change points." : ""}
    </p>
  );
}

/** Undo, Redo, a point at the cross, the next point's kind, Close and Finish, over one status line. */
export function PhoneDrawingBar({ map }: { map: MapLibreMap | null }) {
  const path = useMarkPath();
  const nextKind = useMarkStore((state) => state.nextKind);
  const canUndo = useMarkStore((state) => state.shape.past.length > 0);
  const canRedo = useMarkStore((state) => state.shape.future.length > 0);
  const store = useMarkStore.getState();
  const straight = nextKind === "corner";
  return (
    <section className="fc-mark-float__bar" aria-label="Drawing">
      <div className="fc-mark-float__row">
        <BarButton label="Undo" disabled={!canUndo} onClick={() => store.undo()}>
          <Undo2 size={20} aria-hidden />
        </BarButton>
        <BarButton label="Redo" disabled={!canRedo} onClick={() => store.redo()}>
          <Redo2 size={20} aria-hidden />
        </BarButton>
        <BarButton label={ADD_AT_CROSS} onClick={() => addAtReticle(map)}>
          <Crosshair size={20} aria-hidden />
        </BarButton>
        <IconButton
          className="fc-mark-float__button fc-mark-float__kind"
          label={`Next point: ${straight ? "straight" : "curved"}`}
          title={`The next point is ${straight ? "straight" : "curved"}. Press for ${straight ? "curved" : "straight"}.`}
          onClick={() => store.setNextKind(straight ? "smooth" : "corner")}
        >
          {straight ? <Diamond size={18} aria-hidden /> : <Spline size={18} aria-hidden />}
          <span aria-hidden="true">{straight ? "Straight" : "Curved"}</span>
        </IconButton>
        <BarButton label="Close the shape" disabled={!canClose(path)} onClick={() => store.closeShape()}>
          <SquareDashed size={20} aria-hidden />
        </BarButton>
        <BarButton
          label="Finish"
          disabled={path.points.length === 0}
          onClick={() => {
            const pressed = document.activeElement;
            store.finish();
            // The floating bar goes as the sheet rises with the full bars.
            focusFirstControlAfter(pressed, ".fc-mark .fc-mark__drawing");
          }}
        >
          <Check size={20} aria-hidden />
        </BarButton>
      </div>
      <PhoneStatus map={map} />
    </section>
  );
}

/** The selected point's actions in one row, over one line that names the point. */
export function PhoneSelectedPointBar({ map }: { map: MapLibreMap | null }) {
  const path = useMarkPath();
  const actions = useSelectedPointActions(map);
  if (!actions) return null;
  const { index, point, canInsert, end, isFirst, isLast } = actions;
  const straight = point.kind === "corner";
  return (
    <section className="fc-mark-float__bar" aria-label="Selected point">
      <div className="fc-mark-float__row">
        <BarButton label={straight ? "Make it curved" : "Make it straight"} onClick={actions.switchKind}>
          {straight ? <Spline size={20} aria-hidden /> : <Diamond size={20} aria-hidden />}
        </BarButton>
        <BarButton label="Delete point" onClick={actions.remove}>
          <Trash2 size={20} aria-hidden />
        </BarButton>
        <BarButton label="Insert a point after" disabled={!canInsert} onClick={actions.insertAfter}>
          <Plus size={20} aria-hidden />
        </BarButton>
        {end ? (
          <BarButton label="Continue from this end" onClick={() => actions.continueFrom(end)}>
            <Waypoints size={20} aria-hidden />
          </BarButton>
        ) : null}
        <BarButton label="Previous point" disabled={isFirst} onClick={() => actions.step(-1)}>
          <ArrowLeft size={20} aria-hidden />
        </BarButton>
        <BarButton label="Next point" disabled={isLast} onClick={() => actions.step(1)}>
          <ArrowRight size={20} aria-hidden />
        </BarButton>
        <BarButton label="Done" onClick={actions.done}>
          <CircleCheck size={20} aria-hidden />
        </BarButton>
      </div>
      <p className="fc-mark-float__line fc-mark__selected-name">{pointName(path, index)}</p>
    </section>
  );
}
