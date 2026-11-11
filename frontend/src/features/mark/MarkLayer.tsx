import { useQueryClient } from "@tanstack/react-query";
import { CloudOff } from "lucide-react";
import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { type KeyboardEvent, type PointerEvent, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { lngLatAtClient, screenPoint, useMapFrame } from "../../map/useMapFrame.js";
import { useKindDrafts } from "../drafts/savers.js";
import { findingKeys } from "../findings/keys.js";
import { exactGridRefOf } from "./describe.js";
import { findingDrafts, useSavedDrafts } from "./findingDrafts.js";
import { useMarkStore } from "./markStore.js";
import type { LngLat } from "./outline.js";
import { usePendingFindings } from "./pending.js";
import { draftPath } from "./useSaveMark.js";
import "./mark.css";

/** A tap this close to the outline's first corner, in pixels, closes the shape. */
export const CLOSE_TOLERANCE_PX = 14;
/** How far one press of an arrow key moves the mark, in pixels, and with Shift held. */
export const NUDGE_PX = 3;
export const NUDGE_FAST_PX = 24;

const NUDGES: Record<string, [number, number]> = {
  ArrowLeft: [-1, 0],
  ArrowRight: [1, 0],
  ArrowUp: [0, -1],
  ArrowDown: [0, 1],
};

/** True on any page of the marking panel. */
export function isMarkPath(pathname: string): boolean {
  return pathname === "/mark" || pathname.startsWith("/mark/");
}

/**
 * Taps on the map while marking: the first places the mark, a later one
 * moves it there, and while the outline tool is on each adds a corner. A tap
 * on the first corner of three or more closes the shape.
 */
function useMarkingClicks(map: MapLibreMap | null, marking: boolean): void {
  useEffect(() => {
    if (!map || !marking || !isMapLive(map)) return;
    const canvas = map.getCanvas();
    canvas.classList.add("fc-canvas--placing");
    const onClick = (event: MapMouseEvent): void => {
      const mark = useMarkStore.getState();
      const point: LngLat = [event.lngLat.lng, event.lngLat.lat];
      if (!mark.drawing) {
        mark.place(point);
        return;
      }
      const first = mark.outline?.points[0];
      if (first && (mark.outline?.points.length ?? 0) >= 3) {
        const at = screenPoint(map, first);
        if (Math.hypot(at.x - event.point.x, at.y - event.point.y) <= CLOSE_TOLERANCE_PX) {
          mark.closeOutline();
          return;
        }
      }
      mark.addOutlinePoint(point);
    };
    map.on("click", onClick);
    return () => {
      canvas.classList.remove("fc-canvas--placing");
      if (isMapLive(map)) map.off("click", onClick);
    };
  }, [map, marking]);
}

/**
 * The mark being placed. It can be dragged with a mouse or a finger, and
 * moved with the arrow keys once it has focus (Shift for bigger steps).
 */
function PointHandle({ map, point }: { map: MapLibreMap; point: LngLat }) {
  const place = useMarkStore((state) => state.place);
  const dragging = useRef<number | null>(null);
  const { x, y } = screenPoint(map, point);
  const where = exactGridRefOf(point);

  function onPointerDown(event: PointerEvent<HTMLButtonElement>): void {
    if (event.button !== 0 && event.pointerType === "mouse") return;
    event.preventDefault();
    dragging.current = event.pointerId;
    event.currentTarget.setPointerCapture?.(event.pointerId);
  }

  function onPointerMove(event: PointerEvent<HTMLButtonElement>): void {
    if (dragging.current !== event.pointerId) return;
    place(lngLatAtClient(map, event.clientX, event.clientY));
  }

  function onPointerEnd(event: PointerEvent<HTMLButtonElement>): void {
    if (dragging.current === event.pointerId) dragging.current = null;
  }

  function onKeyDown(event: KeyboardEvent<HTMLButtonElement>): void {
    const direction = NUDGES[event.key];
    if (!direction) return;
    event.preventDefault();
    const step = event.shiftKey ? NUDGE_FAST_PX : NUDGE_PX;
    const at = screenPoint(map, point);
    const moved = map.unproject([at.x + direction[0] * step, at.y + direction[1] * step]);
    place([moved.lng, moved.lat]);
  }

  return (
    <button
      type="button"
      className="fc-mark-handle"
      style={{ transform: `translate(${x}px, ${y}px)` }}
      aria-label={`Your mark${where ? ` at ${where}` : ""}. Drag it, or use the arrow keys, to move it.`}
      onPointerDown={onPointerDown}
      onPointerMove={onPointerMove}
      onPointerUp={onPointerEnd}
      onPointerCancel={onPointerEnd}
      onKeyDown={onKeyDown}
      data-testid="mark-handle"
    >
      <span className="fc-mark-handle__ring" aria-hidden="true" />
    </button>
  );
}

/** The outline as it is drawn: a line through the corners, closed and lightly filled once it is a shape. */
function OutlineShape({ map }: { map: MapLibreMap }) {
  const outline = useMarkStore((state) => state.outline);
  const drawing = useMarkStore((state) => state.drawing);
  if (!outline || outline.points.length === 0) return null;
  const points = outline.points.map((point) => screenPoint(map, point));
  const text = points.map(({ x, y }) => `${x},${y}`).join(" ");
  const closed = outline.shape === "polygon";
  return (
    <g className="fc-mark-outline" data-shape={outline.shape}>
      {closed ? <polygon points={text} /> : <polyline points={text} />}
      {drawing
        ? points.map(({ x, y }, index) => (
            <circle
              // biome-ignore lint/suspicious/noArrayIndexKey: corners are only added or taken from the end
              key={index}
              cx={x}
              cy={y}
              r={index === 0 && points.length >= 3 ? 7 : 4}
              className={index === 0 ? "fc-mark-outline__first" : undefined}
            />
          ))
        : null}
    </g>
  );
}

/**
 * Findings marked by someone not signed in, as dashed hollow rings with a
 * "not saved" sign, so they can't be taken for real marks. Each opens its
 * draft. The one being edited is drawn as the mark instead.
 */
function DraftMarks({ map, editing }: { map: MapLibreMap; editing: string | null }) {
  const drafts = useKindDrafts(findingDrafts);
  const navigate = useNavigate();
  return (
    <>
      {drafts
        .filter((draft) => draft.id !== editing)
        .map((draft) => {
          const { x, y } = screenPoint(map, draft.data.point);
          return (
            <button
              key={draft.id}
              type="button"
              className="fc-draft-mark"
              style={{ transform: `translate(${x}px, ${y}px)` }}
              aria-label={`${draft.data.title}: a draft, not saved yet`}
              title={`${draft.data.title}: not saved yet`}
              onClick={() => navigate(draftPath(draft.id))}
            >
              <span className="fc-draft-mark__ring" aria-hidden="true" />
              <CloudOff className="fc-draft-mark__sign" size={12} aria-hidden />
            </button>
          );
        })}
    </>
  );
}

/** Findings on their way to the server, drawn as new marks at once. */
function PendingMarks({ map }: { map: MapLibreMap }) {
  const pending = usePendingFindings((state) => state.pending);
  return (
    <>
      {pending.map((finding) => {
        const { x, y } = screenPoint(map, finding.point);
        return (
          <span
            key={finding.id}
            className="fc-pending-mark"
            style={{ transform: `translate(${x}px, ${y}px)` }}
            role="img"
            aria-label={`${finding.title}, saving`}
          />
        );
      })}
    </>
  );
}

/** Where a tap or "Place it here" puts the mark: the middle of the part of the map nothing covers. */
export function Reticle() {
  return (
    <div className="fc-reticle-frame" aria-hidden="true">
      <div className="fc-reticle" data-testid="reticle" />
    </div>
  );
}

/** The place under the reticle, or null when it isn't on screen. */
export function reticlePlace(map: MapLibreMap): LngLat | null {
  const reticle = document.querySelector<HTMLElement>(".fc-reticle");
  if (!reticle) return null;
  const box = reticle.getBoundingClientRect();
  return lngLatAtClient(map, box.left + box.width / 2, box.top + box.height / 2);
}

/** When drafts are saved, the map and the list ask again so the new findings show. */
function useRefreshOnSavedDrafts(): void {
  const client = useQueryClient();
  const saved = useSavedDrafts((state) => state.saved);
  const first = useRef(true);
  // biome-ignore lint/correctness/useExhaustiveDependencies: a newly saved draft is the trigger
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    void client.invalidateQueries({ queryKey: findingKeys.all });
  }, [saved, client]);
}

/**
 * Everything marking draws over the map: the mark and its outline while a
 * finding is being marked, drafts, and findings being saved. Mounted once,
 * by the shell, over the main map.
 */
export function MarkLayer() {
  const map = useMainMap();
  const { pathname } = useLocation();
  const marking = isMarkPath(pathname);
  const drawn = useKindDrafts(findingDrafts).length + usePendingFindings((state) => state.pending.length);
  // Follow the map only while there is something on it to keep in place.
  useMapFrame(marking || drawn > 0 ? map : null);
  const point = useMarkStore((state) => state.point);
  const drawing = useMarkStore((state) => state.drawing);
  const editing = useMarkStore((state) => state.draftId);
  useMarkingClicks(map, marking);
  useRefreshOnSavedDrafts();

  if (!map || !isMapLive(map)) return null;
  return (
    <div className="fc-annotations" data-marking={marking}>
      {marking ? (
        <svg className="fc-annotations__shapes" aria-hidden="true">
          <OutlineShape map={map} />
        </svg>
      ) : null}
      <DraftMarks map={map} editing={marking ? editing : null} />
      <PendingMarks map={map} />
      {marking && point ? <PointHandle map={map} point={point} /> : null}
      {marking && (point === null || drawing) ? <Reticle /> : null}
    </div>
  );
}
