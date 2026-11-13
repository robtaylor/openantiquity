import { useQuery, useQueryClient } from "@tanstack/react-query";
import { CloudOff } from "lucide-react";
import type { GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { useMapStore } from "../../map/store.js";
import { lngLatAtClient, screenPoint, useMapFrame } from "../../map/useMapFrame.js";
import { COLOURS } from "../../ui/tokens.js";
import { useKindDrafts } from "../drafts/savers.js";
import { findingQuery } from "../finding/useFinding.js";
import { findingKeys } from "../findings/keys.js";
import { EMPTY_COLLECTION, type FeatureCollection } from "../records/geojson.js";
import { baseRevision, changeShapeId } from "./editingKey.js";
import { findingDrafts, useSavedDrafts } from "./findingDrafts.js";
import { MidpointDots } from "./MidpointDots.js";
import { hasUnkeptLine, useMarkPath, useMarkStore } from "./markStore.js";
import { PathHandles } from "./PathHandles.js";
import { closesAt, geometryVertices, type LngLat, type Path, pathGeometry, segmentNear } from "./path.js";
import { usePendingFindings } from "./pending.js";
import { draftPath } from "./useSaveMark.js";
import "./mark.css";

/** How far from the drawn line, in pixels, an Alt-click still lands on it. */
export const SEGMENT_REACH_PX = 8;
/** Beyond this many points the path is drawn by the map, not by SVG over it. */
export const SVG_MAX_POINTS = 200;

export const MARK_PATH_SOURCE = "mark-path";
export const MARK_PATH_LAYERS = { fill: "mark-path-fill", casing: "mark-path-casing", line: "mark-path-line" } as const;

/** True on any page of the marking panel. */
export function isMarkPath(pathname: string): boolean {
  return pathname === "/mark" || pathname.startsWith("/mark/");
}

function projector(map: MapLibreMap): (point: LngLat) => { x: number; y: number } {
  return (point) => screenPoint(map, point);
}

/**
 * Taps on the map while marking. Every tap adds a point at the active end,
 * of the kind chosen on the bar, or of the other kind with Shift held. A tap
 * on the far end of an open path of three points or more closes it. An
 * Alt-click on the line inserts a point there. Other findings don't take
 * taps meanwhile (`useFindingClicks` stands down while marking).
 *
 * Double-click and double-tap zoom, and Shift-drag box zoom, are off while
 * marking, so two quick taps are two points and Shift-click is a point.
 * Enter, with the map focused, finishes.
 */
function useMarkingClicks(map: MapLibreMap | null, marking: boolean): void {
  useEffect(() => {
    if (!map || !marking || !isMapLive(map)) return;
    const canvas = map.getCanvas();
    canvas.classList.add("fc-canvas--placing");
    const zoomedByDoubleClick = map.doubleClickZoom.isEnabled();
    const zoomedByBox = map.boxZoom?.isEnabled() ?? false;
    map.doubleClickZoom.disable();
    map.boxZoom?.disable();
    const onClick = (event: MapMouseEvent): void => {
      const mark = useMarkStore.getState();
      const limits = useMapStore.getState().meta?.shapes;
      const path = mark.shape.present;
      const point: LngLat = [event.lngLat.lng, event.lngLat.lat];
      const original = event.originalEvent as Partial<MouseEvent> | undefined;
      if (original?.altKey) {
        const segment = segmentNear(path, event.point, projector(map), SEGMENT_REACH_PX);
        if (segment !== null) mark.insertOnSegment(segment, point);
        return;
      }
      if (!mark.drawing || !limits) return;
      if (closesAt(path, mark.end, event.point, projector(map))) {
        mark.closeShape();
        return;
      }
      mark.add(point, limits, original?.shiftKey === true);
    };
    const onKeyDown = (event: KeyboardEvent): void => {
      if (event.key === "Enter" && useMarkStore.getState().drawing) {
        event.preventDefault();
        useMarkStore.getState().finish();
      }
    };
    map.on("click", onClick);
    canvas.addEventListener("keydown", onKeyDown);
    return () => {
      canvas.classList.remove("fc-canvas--placing");
      canvas.removeEventListener("keydown", onKeyDown);
      if (!isMapLive(map)) return;
      map.off("click", onClick);
      if (zoomedByDoubleClick) map.doubleClickZoom.enable();
      if (zoomedByBox) map.boxZoom?.enable();
    };
  }, [map, marking]);
}

/** The path as the map draws it, once it is too long for SVG. */
export function pathFeatures(path: Path): FeatureCollection {
  if (path.points.length <= SVG_MAX_POINTS) return EMPTY_COLLECTION;
  const geometry = pathGeometry(path);
  if (!geometry) return EMPTY_COLLECTION;
  return { type: "FeatureCollection", features: [{ type: "Feature", geometry, properties: {} }] };
}

function addPathLayers(map: MapLibreMap): void {
  map.addLayer({
    id: MARK_PATH_LAYERS.fill,
    type: "fill",
    source: MARK_PATH_SOURCE,
    filter: ["==", ["geometry-type"], "Polygon"],
    paint: { "fill-color": COLOURS.accent, "fill-opacity": 0.14 },
  });
  map.addLayer({
    id: MARK_PATH_LAYERS.casing,
    type: "line",
    source: MARK_PATH_SOURCE,
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": COLOURS.bg, "line-width": 5.5 },
  });
  map.addLayer({
    id: MARK_PATH_LAYERS.line,
    type: "line",
    source: MARK_PATH_SOURCE,
    layout: { "line-join": "round", "line-cap": "round" },
    paint: { "line-color": COLOURS.accentStrong, "line-width": 2.5 },
  });
}

/**
 * Keep `data` in the map's GeoJSON source `source`. The source, and the
 * layers `addLayers` draws from it, are added the first time there is
 * something to draw. With `clearOnLeave`, the source is emptied when the
 * data changes or the map goes, so nothing is left drawn after the caller.
 */
export function useSourceData(
  map: MapLibreMap | null,
  source: string,
  data: FeatureCollection,
  addLayers: (map: MapLibreMap) => void,
  clearOnLeave = false,
): void {
  useEffect(() => {
    if (!map || !isMapLive(map)) return;
    if (data === EMPTY_COLLECTION && !map.getSource(source)) return;
    if (!map.getSource(source)) {
      map.addSource(source, { type: "geojson", data: EMPTY_COLLECTION });
      addLayers(map);
    }
    (map.getSource(source) as GeoJSONSource | undefined)?.setData(data);
    if (!clearOnLeave) return;
    return () => {
      if (isMapLive(map)) (map.getSource(source) as GeoJSONSource | undefined)?.setData(EMPTY_COLLECTION);
    };
  }, [map, source, data, addLayers, clearOnLeave]);
}

/**
 * A long path is drawn by the map from a GeoJSON source, so a road of
 * thousands of points isn't re-projected into SVG on every frame. A short
 * one is drawn in SVG, which follows a drag at once.
 */
function useLongPathOnMap(map: MapLibreMap | null, path: Path, marking: boolean): void {
  const data = useMemo(() => (marking ? pathFeatures(path) : EMPTY_COLLECTION), [path, marking]);
  useSourceData(map, MARK_PATH_SOURCE, data, addPathLayers);
}

/** The path as it is drawn while short enough for SVG: a line through the curve, lightly filled once closed. */
function PathShape({ map, path }: { map: MapLibreMap; path: Path }) {
  const short = path.points.length <= SVG_MAX_POINTS;
  const drawn = useMemo(() => (short ? geometryVertices(pathGeometry(path)) : []), [path, short]);
  if (drawn.length === 0) return null;
  const text = drawn
    .map((point) => screenPoint(map, point))
    .map(({ x, y }) => `${x},${y}`)
    .join(" ");
  return (
    <g className="fc-mark-outline" data-shape={path.closed ? "polygon" : "line"} data-testid="mark-path">
      {path.closed ? <polygon points={text} /> : <polyline points={text} />}
    </g>
  );
}

/**
 * Findings marked by someone not signed in, as dashed hollow rings with a
 * "not saved" sign, so they can't be taken for real marks. Each opens its
 * draft. The one open in the tool is drawn as its path instead.
 */
function DraftMarks({ map, openDraft }: { map: MapLibreMap; openDraft: string | null }) {
  const drafts = useKindDrafts(findingDrafts);
  const navigate = useNavigate();
  return (
    <>
      {drafts
        .filter((draft) => draft.id !== openDraft)
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

/**
 * Why the server refused the path, beside its last point, so it is read
 * where the change was made. The panel says the same as an alert, which is
 * what a screen reader hears, so this copy is hidden from it.
 */
function PathProblem({ map, path }: { map: MapLibreMap; path: Path }) {
  const problem = useMarkStore((state) => (state.problem?.field === "path" ? state.problem.message : null));
  const last = path.points.at(-1);
  if (!problem || !last) return null;
  const { x, y } = screenPoint(map, [last.lon, last.lat]);
  const { width, height } = map.getContainer().getBoundingClientRect();
  // It goes on the side of the point towards the middle of the map, so it stays on screen.
  const left = width > 0 && x > width / 2;
  const up = height > 0 && y > height / 2;
  const shiftX = left ? `calc(${x}px - 100% - 28px)` : `${x}px`;
  const shiftY = up ? `calc(${y}px - 100% - 28px)` : `${y}px`;
  return (
    <p
      className="fc-path-problem"
      style={{ transform: `translate(${shiftX}, ${shiftY})` }}
      aria-hidden="true"
      data-testid="path-problem"
    >
      {problem}
    </p>
  );
}

/** Where "Add a point at the cross" puts a point: the middle of the part of the map nothing covers. */
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

/** "Add a point at the cross": the way to add a point by keyboard or switch, and precisely on a phone. */
export function addAtReticle(map: MapLibreMap | null): void {
  const at = map ? reticlePlace(map) : null;
  const limits = useMapStore.getState().meta?.shapes;
  if (at && limits) useMarkStore.getState().addAtCross(at, limits);
}

/** When drafts are saved, the map and the list ask again so the new findings show. */
function useRefreshOnSavedDrafts(): void {
  const client = useQueryClient();
  const count = useSavedDrafts((state) => state.count);
  const first = useRef(true);
  // biome-ignore lint/correctness/useExhaustiveDependencies: a newly saved draft is the trigger
  useEffect(() => {
    if (first.current) {
      first.current = false;
      return;
    }
    void client.invalidateQueries({ queryKey: findingKeys.all });
  }, [count, client]);
}

/**
 * The browser's own "leave this page?" while a line or a shape is drawn on
 * a marking page that isn't saved or kept as a draft. Nothing is kept until
 * then, so closing or reloading the page would lose it.
 */
function useAskBeforeLeaving(marking: boolean): void {
  const unkept = useMarkStore(hasUnkeptLine);
  useEffect(() => {
    if (!marking || !unkept) return;
    const ask = (event: BeforeUnloadEvent): void => {
      event.preventDefault();
      // Browsers before the preventDefault() way ask only when this is set.
      event.returnValue = true;
    };
    window.addEventListener("beforeunload", ask);
    return () => window.removeEventListener("beforeunload", ask);
  }, [marking, unkept]);
}

/**
 * At "Change the shape", whether the path in the tool is this finding's and
 * the reader may change it, as the finding's page last said: nothing is
 * drawn otherwise, so a reader who may not see the shape exactly never sees
 * one left in the tool. Null on any other page.
 */
function useChangeShapeAllowed(pathname: string): boolean | null {
  const publicId = changeShapeId(pathname);
  // The panel asks for the finding. This only reads the answer.
  const finding = useQuery({ ...findingQuery(publicId ?? ""), enabled: false }).data;
  const editing = useMarkStore((state) => state.editing);
  if (publicId === null) return null;
  return finding?.actions.edit.allowed === true && baseRevision(editing, publicId) !== null;
}

/**
 * True while the drawing tool is open: on any page of the marking panel,
 * except "Change the shape" for a finding the reader may not change.
 */
export function useMarkingOpen(): boolean {
  const { pathname } = useLocation();
  const changing = useChangeShapeAllowed(pathname);
  return isMarkPath(pathname) && changing !== false;
}

/**
 * Everything marking draws over the map: the path, its midpoint dots and its handles while a
 * finding is being marked, drafts, and findings being saved. Mounted once,
 * by the shell, over the main map.
 */
export function MarkLayer() {
  const map = useMainMap();
  const marking = useMarkingOpen();
  const drawn = useKindDrafts(findingDrafts).length + usePendingFindings((state) => state.pending.length);
  // Follow the map only while there is something on it to keep in place.
  useMapFrame(marking || drawn > 0 ? map : null);
  const path = useMarkPath();
  const drawing = useMarkStore((state) => state.drawing);
  const draftId = useMarkStore((state) => state.draftId);
  useMarkingClicks(map, marking);
  useAskBeforeLeaving(marking);
  useLongPathOnMap(map, path, marking);
  useRefreshOnSavedDrafts();

  if (!map || !isMapLive(map)) return null;
  return (
    <div className="fc-annotations" data-marking={marking}>
      {marking ? (
        <svg className="fc-annotations__shapes" aria-hidden="true">
          <PathShape map={map} path={path} />
        </svg>
      ) : null}
      <DraftMarks map={map} openDraft={marking ? draftId : null} />
      <PendingMarks map={map} />
      {marking && path.points.length > 1 ? <MidpointDots map={map} path={path} /> : null}
      {marking && path.points.length > 0 ? <PathHandles map={map} path={path} /> : null}
      {marking ? <PathProblem map={map} path={path} /> : null}
      {marking && drawing && !path.closed ? <Reticle /> : null}
    </div>
  );
}
