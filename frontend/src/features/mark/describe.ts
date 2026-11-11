/**
 * What a new finding says about itself without the finder typing: what they
 * were looking at, and a title.
 */

import type { Meta } from "../../api/meta.js";
import { formatGridRef, wgs84ToGrid } from "../../map/gridref.js";
import { LIMITS } from "../../map/permalink.js";
import type { MapState } from "../../map/store.js";
import type { ViewState } from "../findings/types.js";
import type { LngLat } from "./outline.js";

/** The server takes a layer id made of these characters only. */
const LAYER_ID = /^[a-z0-9_-]{1,40}$/;
/** The longest title the server takes. */
export const TITLE_MAX = 120;

function rounded(value: number, places: number): number {
  const factor = 10 ** places;
  return Math.round(value * factor) / factor;
}

/**
 * The view the finder was using, from the map store, as the contract's
 * `view_state`: layer, zoom, bearing, pitch, the light's direction and
 * height, and the height exaggeration. Everyone who checks the finding
 * later starts from this picture.
 *
 * The exaggeration is the 3D terrain's when 3D is on, and the raking light's
 * when that is the layer, because each is what shaped the picture. Otherwise
 * there is none to record.
 */
export function viewStateFrom(
  state: Pick<MapState, "meta" | "mainView" | "camera" | "sun" | "terrain" | "hillshadeExaggeration">,
): ViewState {
  const view: ViewState = {
    zoom: rounded(state.camera.zoom, 2),
    bearing: rounded(state.camera.bearing, 1),
    pitch: rounded(Math.min(state.camera.pitch, LIMITS.pitch.max), 1),
    sun_azimuth: rounded(state.sun.azimuth, 1),
    sun_altitude: rounded(state.sun.altitude, 1),
  };
  if (LAYER_ID.test(state.mainView)) view.layer = state.mainView;
  const raking = state.meta?.layers.views.find((candidate) => candidate.id === state.mainView)?.type === "raking";
  if (state.terrain.enabled) view.exaggeration = rounded(state.terrain.exaggeration, 2);
  else if (raking) view.exaggeration = rounded(state.hillshadeExaggeration, 2);
  return view;
}

/** The six-figure grid reference of a point, such as "SU 102 698", or null off both grids. */
export function gridRefOf([lng, lat]: LngLat): string | null {
  const position = wgs84ToGrid(lng, lat);
  return position ? formatGridRef(position, 6) : null;
}

/** A finer reference for showing where the mark is now, such as "SU 1023 6987". */
export function exactGridRefOf([lng, lat]: LngLat): string | null {
  const position = wgs84ToGrid(lng, lat);
  return position ? formatGridRef(position, 8) : null;
}

/**
 * A title that needs no typing: what it looks like, and where. The server
 * can't yet say what the nearest place is, so it is the grid reference.
 */
export function suggestTitle(meta: Meta, featureClass: string | null, point: LngLat | null): string {
  const label = meta.vocab.feature_classes.find((candidate) => candidate.id === featureClass)?.label ?? "Finding";
  const where = point ? gridRefOf(point) : null;
  return (where ? `${label} at ${where}` : label).slice(0, TITLE_MAX);
}
