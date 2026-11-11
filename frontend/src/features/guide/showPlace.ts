/**
 * Opening a place from a reference page on the map, in the view the page
 * talks about. On a phone the sheet drops to its peek stop first, so the
 * place isn't hidden behind the page that sent someone there.
 */

import type { Meta } from "../../api/meta.js";
import { seeViewAt, whenStageSettled } from "../finding/mapView.js";
import type { PanelEnvironment } from "../shell/panelContext.js";

export interface MapPlace {
  lon: number;
  lat: number;
  /** A view id from `/meta`. One `/meta` doesn't list leaves the map's view as it is. */
  layer?: string;
  zoom: number;
}

/** Move the map to the place, flat and facing north, in its view. Returns a function that calls it off. */
export function showPlace(
  meta: Meta,
  place: MapPlace,
  environment: Pick<PanelEnvironment, "isPhone" | "stop" | "setStop">,
): () => void {
  if (environment.isPhone && environment.stop !== "peek") environment.setStop("peek");
  return whenStageSettled(() => {
    seeViewAt(meta, [place.lon, place.lat], { layer: place.layer ?? null, zoom: place.zoom, bearing: 0, pitch: 0 });
  });
}
