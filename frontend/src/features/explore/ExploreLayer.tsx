import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { useEffect } from "react";
import { useLocation, useNavigate } from "react-router";
import { findOverlay, type Meta } from "../../api/meta.js";
import { findingPointAt } from "../../map/findingHits.js";
import { kmSquareAt } from "../../map/gridref.js";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { useMapStore } from "../../map/store.js";
import { overlaySourceId } from "../../map/style.js";
import { mapToolActive } from "../../map/tool.js";
import { screenPoint, useMapFrame } from "../../map/useMapFrame.js";
import { findingPath, useSelectedFinding } from "../findings/selection.js";
import { isMarkPath } from "../mark/MarkLayer.js";
import { recordUnder } from "../records/useRecordsOnMap.js";
import "../mark/mark.css";
import "./explore.css";

/** Zoom to go to when a square holding several findings is chosen, so they can be told apart in the list. */
const SQUARE_ZOOM = 14;

/** The obscured findings in the grid square under a point, by their square's public ids. */
function squareFindingsAt(
  map: MapLibreMap,
  meta: Meta,
  event: MapMouseEvent,
): { ids: string[]; centre: [number, number] } | null {
  const overlay = findOverlay(meta, "findings");
  const square = kmSquareAt(event.lngLat.lng, event.lngLat.lat);
  if (!overlay || !square) return null;
  const ids = new Set<string>();
  for (const feature of map.querySourceFeatures(overlaySourceId(overlay.id), {
    filter: ["==", ["get", "square"], square.ref],
  })) {
    const text = feature.properties?.public_ids;
    if (typeof text === "string") for (const id of text.split(" ")) if (id) ids.add(id);
  }
  if (ids.size === 0) return null;
  const corners = square.ring.slice(0, 4);
  const centre: [number, number] = [
    corners.reduce((sum, [lng]) => sum + lng, 0) / corners.length,
    corners.reduce((sum, [, lat]) => sum + lat, 0) / corners.length,
  ];
  return { ids: [...ids], centre };
}

/**
 * Clicking a finding on the map opens its page, as choosing it from the list
 * does. A square holding one obscured finding opens it. A square holding
 * several brings Explore to it, where they are listed. Findings sit above
 * heritage records: a finding's marker wins a click over a record under it,
 * but a record's marker inside an obscured finding's square opens the record,
 * because the square is only an outline. While a finding is being marked, or
 * a map tool such as the height profile has the clicks, taps belong to them.
 */
function useFindingClicks(map: MapLibreMap | null, meta: Meta, marking: boolean): void {
  const navigate = useNavigate();
  useEffect(() => {
    if (!map || marking || !isMapLive(map)) return;
    const canvas = map.getCanvas();
    const onClick = (event: MapMouseEvent): void => {
      if (mapToolActive()) return;
      const select = useSelectedFinding.getState().select;
      const point = findingPointAt(map, event);
      if (point) {
        select(point.publicId, point.at, false);
        navigate(findingPath(point.publicId));
        return;
      }
      if (recordUnder(map, event.point)) return;
      const square = squareFindingsAt(map, meta, event);
      if (!square) return;
      const [only] = square.ids;
      if (square.ids.length === 1 && only) {
        select(only, square.centre, true);
        navigate(findingPath(only));
        return;
      }
      const { camera, requestCamera } = useMapStore.getState();
      requestCamera({ lng: square.centre[0], lat: square.centre[1], zoom: Math.max(camera.zoom, SQUARE_ZOOM) });
      navigate("/");
    };
    const onMove = (event: MapMouseEvent): void => {
      canvas.classList.toggle("fc-canvas--finding", findingPointAt(map, event) !== null);
    };
    map.on("click", onClick);
    map.on("mousemove", onMove);
    return () => {
      canvas.classList.remove("fc-canvas--finding");
      if (!isMapLive(map)) return;
      map.off("click", onClick);
      map.off("mousemove", onMove);
    };
  }, [map, meta, marking, navigate]);
}

/** A ring round the chosen finding, or its square drawn bright when its position is obscured. */
function Highlight({ map }: { map: MapLibreMap }) {
  const selected = useSelectedFinding((state) => state.selected);
  const { pathname } = useLocation();
  const shown = selected !== null && pathname === findingPath(selected.publicId);
  useMapFrame(shown ? map : null);
  if (!shown) return null;
  if (selected.square) {
    const points = selected.square.map((corner) => screenPoint(map, corner));
    return (
      <svg className="fc-annotations__shapes" aria-hidden="true">
        <polygon className="fc-highlight-square" points={points.map(({ x, y }) => `${x},${y}`).join(" ")} />
      </svg>
    );
  }
  const { x, y } = screenPoint(map, selected.point);
  return <span className="fc-highlight-ring" style={{ transform: `translate(${x}px, ${y}px)` }} aria-hidden="true" />;
}

/**
 * What Explore adds to the map: findings that open when clicked, and a mark
 * on the one whose page is open. Mounted once, by the shell, over the main map.
 */
export function ExploreLayer({ meta }: { meta: Meta }) {
  const map = useMainMap();
  const { pathname } = useLocation();
  useFindingClicks(map, meta, isMarkPath(pathname));
  if (!map || !isMapLive(map)) return null;
  return (
    <div className="fc-annotations">
      <Highlight map={map} />
    </div>
  );
}
