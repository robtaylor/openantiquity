import type { Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { useEffect, useState } from "react";
import { useLocation, useNavigate } from "react-router";
import { create } from "zustand";
import { findOverlay, type Meta } from "../../api/meta.js";
import { useFindingHighlight, useFindingHighlightOnMap } from "../../map/findingHighlight.js";
import { findingCandidatesAt, pickAt, pickFinding, REACH_PX } from "../../map/findingHits.js";
import { kmSquareAt } from "../../map/gridref.js";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { overlaySourceId } from "../../map/style.js";
import { mapToolActive } from "../../map/tool.js";
import { screenPoint, useMapFrame } from "../../map/useMapFrame.js";
import { findingPath, useSelectedFinding } from "../findings/selection.js";
import { isMarkPath } from "../mark/MarkLayer.js";
import { recordUnder } from "../records/useRecordsOnMap.js";
import { useIsPhone } from "../shell/useIsPhone.js";
import { type ChooserRequest, FindingChooser, findingsHereWords } from "./FindingChooser.js";
import { useOpenExploreAt } from "./openExplore.js";
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

/** The pointer's place on the window, from a point on the map. */
function onWindow(map: MapLibreMap, point: { x: number; y: number }): { x: number; y: number } {
  const box = map.getContainer().getBoundingClientRect();
  return { x: box.left + point.x, y: box.top + point.y };
}

/** What a computer's pointer would open where it rests: a finding, highlighted, or "3 findings here". */
interface HoverHint {
  at: { x: number; y: number };
  words: string;
}

/**
 * The hint as the pointer last left it. It is checked once a frame while
 * the pointer moves, and kept here rather than in the layer's state so only
 * the hint itself is drawn again, and only when it has changed.
 */
const useHoverHint = create<{ hint: HoverHint | null; show: (hint: HoverHint | null) => void }>()((set, get) => ({
  hint: null,
  show: (hint) => {
    const now = get().hint;
    const same =
      now === hint ||
      (now !== null && hint !== null && now.words === hint.words && now.at.x === hint.at.x && now.at.y === hint.at.y);
    if (!same) set({ hint });
  },
}));

/** "3 findings here" beside the pointer, unless the chooser is open. */
function HoverHintNote({ hidden }: { hidden: boolean }) {
  const hint = useHoverHint((state) => state.hint);
  if (!hint || hidden) return null;
  return (
    <p className="fc-hover-hint" style={{ transform: `translate(${hint.at.x}px, ${hint.at.y}px)` }} role="status">
      {hint.words}
    </p>
  );
}

/**
 * Clicking a finding on the map opens its page, as choosing it from the list
 * does. Which finding is picked by `findingHits` (Decision 0031): markers,
 * then lines, then areas' edges, within the reach of a mouse or a finger,
 * with the chooser for those alike. A square holding one obscured finding
 * opens it, and one holding several brings Explore to it. Findings sit above
 * heritage records: a finding in reach wins over a record, but a record
 * inside an obscured finding's square opens the record, because the square
 * is only an outline. While a finding is being marked, or a map tool such as
 * the height profile has the clicks, taps belong to them.
 *
 * On a computer, as the pointer moves, what a click would open is
 * highlighted, or a hint says how many findings a click would offer.
 */
function useFindingClicks(
  map: MapLibreMap | null,
  meta: Meta,
  marking: boolean,
  onChoose: (request: ChooserRequest) => void,
  onHint: (hint: HoverHint | null) => void,
): void {
  const navigate = useNavigate();
  const openExploreAt = useOpenExploreAt();
  useEffect(() => {
    if (!map || marking || !isMapLive(map)) return;
    const canvas = map.getCanvas();
    const onClick = (event: MapMouseEvent): void => {
      if (mapToolActive()) return;
      const select = useSelectedFinding.getState().select;
      const pick = pickAt(map, event);
      const lngLat: [number, number] = [event.lngLat.lng, event.lngLat.lat];
      if (pick.kind === "one") {
        select(pick.candidate.publicId, pick.candidate.at ?? lngLat, false);
        navigate(findingPath(pick.candidate.publicId));
        return;
      }
      if (pick.kind === "choose") {
        onHint(null);
        onChoose({ at: onWindow(map, event.point), lngLat, candidates: pick.candidates });
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
      openExploreAt(square.centre, SQUARE_ZOOM);
    };
    // The pointer is checked at most once a frame, however often it moves.
    let pending: MapMouseEvent | null = null;
    let frame = 0;
    let highlighted: string | null = null;
    const settle = (): void => {
      frame = 0;
      const event = pending;
      if (!event || !isMapLive(map)) return;
      const pick = pickFinding(findingCandidatesAt(map, event.point, REACH_PX.mouse));
      canvas.classList.toggle("fc-canvas--finding", pick.kind !== "none");
      const next = pick.kind === "one" ? pick.candidate.publicId : null;
      if (next !== highlighted) {
        if (highlighted !== null) useFindingHighlight.getState().clear(highlighted);
        if (next !== null) useFindingHighlight.getState().set(next);
        highlighted = next;
      }
      onHint(
        pick.kind === "choose"
          ? { at: onWindow(map, event.point), words: findingsHereWords(pick.candidates.length) }
          : null,
      );
    };
    const onMove = (event: MapMouseEvent): void => {
      // A drag moves the map, not the pointer over it. A tool that has the clicks sets its own cursor.
      if ((event.originalEvent as MouseEvent | undefined)?.buttons || mapToolActive()) return;
      pending = event;
      if (frame === 0) frame = requestAnimationFrame(settle);
    };
    const onLeave = (): void => {
      pending = null;
      if (highlighted !== null) useFindingHighlight.getState().clear(highlighted);
      highlighted = null;
      onHint(null);
    };
    map.on("click", onClick);
    map.on("mousemove", onMove);
    map.on("mouseout", onLeave);
    return () => {
      cancelAnimationFrame(frame);
      onLeave();
      canvas.classList.remove("fc-canvas--finding");
      if (!isMapLive(map)) return;
      map.off("click", onClick);
      map.off("mousemove", onMove);
      map.off("mouseout", onLeave);
    };
  }, [map, meta, marking, navigate, openExploreAt, onChoose, onHint]);
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
 * What Explore adds to the map: findings that open when clicked, the
 * chooser between overlapping ones, a highlight on what a click would open,
 * and a mark on the one whose page is open. Mounted once, by the shell,
 * over the main map.
 */
export function ExploreLayer({ meta }: { meta: Meta }) {
  const map = useMainMap();
  const { pathname } = useLocation();
  const isPhone = useIsPhone();
  const [chooser, setChooser] = useState<ChooserRequest | null>(null);
  const marking = isMarkPath(pathname);
  useFindingClicks(map, meta, marking, setChooser, useHoverHint.getState().show);
  useFindingHighlightOnMap(map);
  // A chooser left open when the page changes, such as on Back, goes with it.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the address changing is the trigger
  useEffect(() => setChooser(null), [pathname]);
  if (!map || !isMapLive(map)) return null;
  return (
    <div className="fc-annotations">
      <Highlight map={map} />
      <HoverHintNote hidden={chooser !== null} />
      {chooser ? (
        <FindingChooser meta={meta} map={map} request={chooser} sheet={isPhone} onClose={() => setChooser(null)} />
      ) : null}
    </div>
  );
}
