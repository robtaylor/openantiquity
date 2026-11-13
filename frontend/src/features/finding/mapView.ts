/**
 * Moving the map to a finding, and showing it as its finder saw it.
 *
 * The map fills the window under the panel, so a finding put at the map's
 * centre would sit behind the side panel or the phone sheet. It is put at
 * the middle of the part of the map nothing covers instead (`.fc-stage`).
 */

import { useEffect, useRef } from "react";
import { findView, type Meta } from "../../api/meta.js";
import { useMainMapStore } from "../../map/mainMap.js";
import { LIMITS } from "../../map/permalink.js";
import { useMapStore } from "../../map/store.js";
import { clamp } from "../../ui/math.js";
import { useSelectedFinding } from "../findings/selection.js";
import type { FindingDetail, ViewState } from "../findings/types.js";

/** How close the map comes to a finding seen exactly, unless it is already closer. */
export const FINDING_ZOOM = 16;
/** How close it comes to a one-kilometre square, so the whole square is in view. */
export const SQUARE_ZOOM = 13.5;

const EARTH_CIRCUMFERENCE_M = 40_075_016.686;
const METRES_PER_DEGREE = 111_320;
/** MapLibre draws the world 512 px across at zoom 0. */
const WORLD_PX = 512;

export interface ScreenOffset {
  /** Pixels from the map's centre to where the finding should be shown: right and down are positive. */
  x: number;
  y: number;
}

/**
 * The map centre that puts `point` at `offset` from the middle of the map,
 * at this zoom and bearing. Good to well under a pixel at finding zooms.
 */
export function centreFor(
  point: [number, number],
  zoom: number,
  bearing: number,
  offset: ScreenOffset,
): [number, number] {
  const [lng, lat] = point;
  const cos = Math.cos((lat * Math.PI) / 180);
  const metresPerPx = (EARTH_CIRCUMFERENCE_M * cos) / (WORLD_PX * 2 ** zoom);
  // The screen is turned by the bearing, so turn the offset back onto the ground.
  const angle = (bearing * Math.PI) / 180;
  const east = offset.x * Math.cos(angle) - offset.y * Math.sin(angle);
  const south = offset.x * Math.sin(angle) + offset.y * Math.cos(angle);
  // The centre is the other way from the finding: if the finding is to be right of centre, the centre is west of it.
  return [lng - (east * metresPerPx) / (METRES_PER_DEGREE * cos), lat + (south * metresPerPx) / METRES_PER_DEGREE];
}

/** Where the uncovered part of the map is, from the map's centre, measured from the page. */
export function uncoveredOffset(): ScreenOffset {
  const canvas = useMainMapStore.getState().map?.getCanvas().getBoundingClientRect();
  const stage = document.querySelector(".fc-stage")?.getBoundingClientRect();
  if (!canvas || !stage || stage.width === 0 || stage.height === 0) return { x: 0, y: 0 };
  return {
    x: stage.left + stage.width / 2 - (canvas.left + canvas.width / 2),
    y: stage.top + stage.height / 2 - (canvas.top + canvas.height / 2),
  };
}

/**
 * Run `then` once the part of the map nothing covers has stopped moving. A
 * panel opening, or the phone sheet going to another stop, slides it for
 * 150 to 200 ms, and a place centred while it slides is centred for where it
 * was. Waits one frame first, so the render that moved it has been drawn.
 * Returns a function that calls the whole thing off.
 */
export function whenStageSettled(then: () => void): () => void {
  let cancelled = false;
  function check(): void {
    if (cancelled) return;
    // Asking for the animations brings the styles up to date, so a slide that has just been set going is among them.
    const moving = document.querySelector(".fc-stage")?.getAnimations?.() ?? [];
    if (moving.length === 0) then();
    else void Promise.allSettled(moving.map((animation) => animation.finished)).then(check);
  }
  const frame = requestAnimationFrame(check);
  return () => {
    cancelled = true;
    cancelAnimationFrame(frame);
  };
}

function bounded(value: number | null | undefined, range: { min: number; max: number }): number | undefined {
  return value === null || value === undefined || !Number.isFinite(value)
    ? undefined
    : clamp(value, range.min, range.max);
}

/** Below this zoom a finding in view is still too small to look at, so the map goes in closer. */
const LOOKING_ZOOM = 14;

/**
 * Whether the finding is already where the person can look at it: in the
 * part of the map nothing covers, close enough in. A link that carries a
 * view of its own, or a click on the finding's marker, leaves the map be.
 */
export function inView(point: [number, number]): boolean {
  const map = useMainMapStore.getState().map;
  return map !== null && map.getZoom() >= LOOKING_ZOOM && onUncoveredMap(point);
}

/** Whether the point is on the part of the map nothing covers, at any zoom. */
function onUncoveredMap(point: [number, number]): boolean {
  const map = useMainMapStore.getState().map;
  const stage = document.querySelector(".fc-stage")?.getBoundingClientRect();
  if (!map || !stage || stage.width === 0) return false;
  const canvas = map.getCanvas().getBoundingClientRect();
  const at = map.project(point);
  const x = canvas.left + at.x;
  const y = canvas.top + at.y;
  return x >= stage.left && x <= stage.right && y >= stage.top && y <= stage.bottom;
}

/** A box on the page, by its edges, in pixels. */
export interface Edges {
  left: number;
  top: number;
  right: number;
  bottom: number;
}

/**
 * The part of `stage` clear of every box floating on it. Each box that
 * still overlaps what is left is cut off along whichever side loses the
 * least of it: a search box across the top comes off the top, a column of
 * buttons at the side comes off that side, a bar at the foot off the foot.
 */
export function clearOf(stage: Edges, covers: readonly Edges[]): Edges {
  // Copied edge by edge: a DOMRect's edges are getters, which spreading would lose.
  let clear: Edges = { left: stage.left, top: stage.top, right: stage.right, bottom: stage.bottom };
  for (const box of covers) {
    const overlaps =
      box.right > box.left &&
      box.bottom > box.top &&
      box.left < clear.right &&
      box.right > clear.left &&
      box.top < clear.bottom &&
      box.bottom > clear.top;
    if (!overlaps) continue;
    const width = clear.right - clear.left;
    const height = clear.bottom - clear.top;
    const cuts: Array<[number, Edges]> = [
      [(box.bottom - clear.top) * width, { ...clear, top: box.bottom }],
      [(clear.bottom - box.top) * width, { ...clear, bottom: box.top }],
      [(box.right - clear.left) * height, { ...clear, left: box.right }],
      [(clear.right - box.left) * height, { ...clear, right: box.left }],
    ];
    cuts.sort((a, b) => a[0] - b[0]);
    clear = cuts[0]?.[1] ?? clear;
  }
  return clear;
}

/** What floats on the map and would cover a handle: the search box, the map's buttons, the drawing bar and the rest. */
const FLOATING = ".fc-stage > *, .fc-mark-float";

/** The part of the map nothing covers, less what floats on it, in page pixels. Null before the page is laid out. */
export function clearArea(): Edges | null {
  const stage = document.querySelector(".fc-stage")?.getBoundingClientRect();
  if (!stage || stage.width === 0 || stage.height === 0) return null;
  const covers = [...document.querySelectorAll(FLOATING)].map((element) => element.getBoundingClientRect());
  return clearOf(stage, covers);
}

/** Space kept between a framed shape and whatever is round it, in pixels: half a handle's 44 px target, and some. */
const FRAME_MARGIN = 36;

/**
 * Move the map so every point is on the part of it nothing covers, clear
 * of the controls floating on it, as close as `maxZoom` and the points
 * allow. Fewer than two points leave it be.
 */
export function frameExtent(points: ReadonlyArray<readonly [number, number]>, maxZoom = 18): void {
  if (points.length < 2) return;
  const clear = clearArea();
  const canvas = useMainMapStore.getState().map?.getCanvas().getBoundingClientRect();
  if (!clear || !canvas) return;
  const lons = points.map(([lon]) => lon);
  const lats = points.map(([, lat]) => lat);
  const [west, east, south, north] = [Math.min(...lons), Math.max(...lons), Math.min(...lats), Math.max(...lats)];
  // Web Mercator, as the map draws it, in parts of the world's width.
  const x = (lon: number): number => (lon + 180) / 360;
  const y = (lat: number): number => {
    const sin = Math.sin((lat * Math.PI) / 180);
    return 0.5 - Math.log((1 + sin) / (1 - sin)) / (4 * Math.PI);
  };
  const width = Math.max(1, clear.right - clear.left - FRAME_MARGIN * 2);
  const height = Math.max(1, clear.bottom - clear.top - FRAME_MARGIN * 2);
  const across = Math.max(1e-12, (x(east) - x(west)) * WORLD_PX);
  const down = Math.max(1e-12, (y(south) - y(north)) * WORLD_PX);
  const zoom = Math.min(maxZoom, Math.log2(width / across), Math.log2(height / down));
  const offset = {
    x: (clear.left + clear.right) / 2 - (canvas.left + canvas.width / 2),
    y: (clear.top + clear.bottom) / 2 - (canvas.top + canvas.height / 2),
  };
  const { camera, requestCamera } = useMapStore.getState();
  // The extent is measured as if the map faced north.
  const [lng, lat] = centreFor([(west + east) / 2, (south + north) / 2], zoom, camera.bearing, offset);
  requestCamera({ lng, lat, zoom });
}

/**
 * Bring the point back onto the uncovered map if a panel or the sheet now
 * covers it, keeping the zoom, bearing and tilt the person has. Left alone
 * when it is already in sight.
 */
export function panIntoView(point: [number, number]): void {
  if (onUncoveredMap(point)) return;
  const { camera, requestCamera } = useMapStore.getState();
  const [lng, lat] = centreFor(point, camera.zoom, camera.bearing, uncoveredOffset());
  requestCamera({ lng, lat });
}

/** Go to the finding, keeping a closer zoom the person already has, unless it is already in view. */
export function goToFinding(finding: FindingDetail): void {
  const { camera, requestCamera } = useMapStore.getState();
  const { lon, lat, obscured } = finding.location;
  if (!obscured && inView([lon, lat])) return;
  const zoom = obscured ? SQUARE_ZOOM : Math.max(camera.zoom, FINDING_ZOOM);
  const [lng, centreLat] = centreFor([lon, lat], zoom, camera.bearing, uncoveredOffset());
  requestCamera({ lng, lat: centreLat, zoom });
}

/**
 * Restore the finder's view: their layer, zoom, bearing, tilt, light and
 * height exaggeration, at the finding. Values the map can't take are left
 * as they are, and a layer the catalogue no longer has is skipped.
 */
export function seeAsFinderDid(meta: Meta, finding: FindingDetail): void {
  seeViewAt(meta, [finding.location.lon, finding.location.lat], finding.view_state);
}

/**
 * Restore a finder's view at a place, with nothing else about the finding:
 * how a blind second-look card is shown (Decision 0008).
 */
export function seeViewAt(meta: Meta, point: [number, number], view: ViewState): void {
  const store = useMapStore.getState();
  if (view.layer && findView(meta, view.layer)) store.setMainView(view.layer);
  const raking = view.layer ? findView(meta, view.layer)?.type === "raking" : false;
  const azimuth = bounded(view.sun_azimuth, { min: 0, max: 360 });
  const altitude = bounded(view.sun_altitude, LIMITS.sunAltitude);
  if (azimuth !== undefined || altitude !== undefined) store.setSun({ azimuth, altitude });
  const pitch = bounded(view.pitch, LIMITS.pitch) ?? 0;
  const exaggeration = view.exaggeration ?? null;
  if (exaggeration !== null && Number.isFinite(exaggeration)) {
    if (raking) store.setHillshadeExaggeration(exaggeration);
    else if (pitch > 0) store.setTerrainExaggeration(exaggeration);
  }
  // A tilted view was taken in 3D.
  if (pitch > 0 !== store.terrain.enabled) store.setTerrainEnabled(pitch > 0);
  const zoom = bounded(view.zoom, LIMITS.zoom) ?? Math.max(store.camera.zoom, FINDING_ZOOM);
  const bearing = bounded(view.bearing, { min: -360, max: 360 }) ?? 0;
  const [lng, lat] = centreFor(point, zoom, bearing, uncoveredOffset());
  useMapStore.getState().requestCamera({ lng, lat, zoom, bearing, pitch });
}

/**
 * When a finding's page opens: mark the finding on the map, as a ring or as
 * its square, and move the map to it once. A later refresh of the same
 * finding leaves the map where the person has put it.
 */
export function useFindingOnMap(finding: FindingDetail): void {
  const moved = useRef<string | null>(null);
  const { public_id: publicId } = finding;
  const { lon, lat, obscured } = finding.location;
  useEffect(() => {
    useSelectedFinding.getState().select(publicId, [lon, lat], obscured);
  }, [publicId, lon, lat, obscured]);
  useEffect(() => {
    if (moved.current === publicId) return;
    return whenStageSettled(() => {
      moved.current = publicId;
      goToFinding(finding);
    });
  }, [publicId, finding]);
}
