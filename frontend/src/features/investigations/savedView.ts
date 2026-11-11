/**
 * A saved map view: where the map was centred and how it was set, so an
 * investigation can take someone back to exactly that picture. The centre
 * kept is the middle of the part of the map nobody's panel covered, and
 * going back puts it there again, so a view saved beside a side panel
 * opens the same under a phone's sheet.
 */

import { findView, type Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { type MapCover, visibleCentre } from "../../map/visibleArea.js";
import { seeViewAt } from "../finding/mapView.js";
import type { SavedView } from "./api.js";

/** Six decimal places is about ten centimetres; more is noise. */
function round(value: number, places: number): number {
  return Number(value.toFixed(places));
}

/** The parts of the map's state a view keeps. */
export interface ViewSource {
  camera: { lng: number; lat: number; zoom: number; bearing: number; pitch: number };
  mainView: string;
  compareView: string | null;
  sun: { azimuth: number; altitude: number };
  hillshadeExaggeration: number;
  terrain: { enabled: boolean; exaggeration: number };
}

/** The view the map shows now, as an investigation keeps it. */
export function captureView(meta: Meta, state: ViewSource, cover: MapCover): SavedView {
  const centre = visibleCentre(state.camera, cover);
  const raking = findView(meta, state.mainView)?.type === "raking";
  const tilted = state.terrain.enabled && state.camera.pitch > 0;
  const view: SavedView = {
    centre: [round(centre.lng, 6), round(centre.lat, 6)],
    zoom: round(state.camera.zoom, 2),
    bearing: round(state.camera.bearing, 1),
    pitch: tilted ? round(state.camera.pitch, 1) : 0,
    layer: state.mainView,
    sun_azimuth: round(state.sun.azimuth, 1),
    sun_altitude: round(state.sun.altitude, 1),
  };
  if (state.compareView !== null) view.compare_layer = state.compareView;
  // The one exaggeration the picture depends on: the raking light's, or the tilted terrain's.
  if (raking) view.exaggeration = state.hillshadeExaggeration;
  else if (tilted) view.exaggeration = state.terrain.exaggeration;
  return view;
}

/** The map as it is now, kept as a view. */
export function currentView(meta: Meta, cover: MapCover): SavedView {
  return captureView(meta, useMapStore.getState(), cover);
}

/**
 * Put the map back as the view was: its layer and comparison layer, light,
 * tilt and place. A layer the catalogue no longer has is left as it is.
 */
export function showSavedView(meta: Meta, view: SavedView): void {
  seeViewAt(meta, view.centre, view);
  const compare = view.compare_layer && findView(meta, view.compare_layer) ? view.compare_layer : null;
  const now = useMapStore.getState();
  if (compare !== now.compareView && compare !== now.mainView) now.setCompareView(compare);
}

/** The view's layer, and its comparison layer if it had one, by their titles. */
export function viewLayers(meta: Meta, view: SavedView): string | null {
  const title = (id: string | null | undefined) => (id ? findView(meta, id)?.title : undefined);
  const main = title(view.layer);
  const compare = title(view.compare_layer);
  if (main && compare) return `${main}, compared with ${compare}`;
  return main ?? null;
}
