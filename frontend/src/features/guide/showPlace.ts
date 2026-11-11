/**
 * Opening a place from a reference page on the map, in the view the page
 * talks about. On a phone the sheet drops to its peek stop first, so the
 * place isn't hidden behind the page that sent someone there. The marks
 * Open Antiquity draws over the ground (heritage records, findings, scan
 * coverage) are turned off, because they would sit on the very feature the
 * page asks someone to look at, and a toast says how to turn them back on.
 */

import type { Meta, Overlay } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { toast } from "../../ui/toastStore.js";
import { seeViewAt, whenStageSettled } from "../finding/mapView.js";
import type { PanelEnvironment } from "../shell/panelContext.js";

/** Overlays drawn on top of the ground that hide what a guide example shows. */
const COVERS_THE_GROUND = new Set<Overlay["type"]>(["records", "findings", "coverage"]);

/** "A", "A and B", "A, B and C", each but the first in lower case. */
function andList(items: readonly string[]): string {
  const words = items.map((item, index) => (index === 0 ? item : item.charAt(0).toLowerCase() + item.slice(1)));
  if (words.length <= 1) return words.join("");
  return `${words.slice(0, -1).join(", ")} and ${words.at(-1)}`;
}

/** Turn off the overlays that would cover the ground, and say so. Returns the ids turned off. */
export function clearTheGround(meta: Meta): string[] {
  const store = useMapStore.getState();
  const covering = meta.layers.overlays.filter(
    (overlay) => COVERS_THE_GROUND.has(overlay.type) && store.overlays[overlay.id]?.visible,
  );
  for (const overlay of covering) store.setOverlayVisible(overlay.id, false);
  if (covering.length > 0) {
    const titles = andList(covering.map((overlay) => overlay.title));
    const one = covering.length === 1;
    toast(
      `${titles} ${one ? "is" : "are"} hidden so the ground shows. Turn ${one ? "it" : "them"} on again in Layers.`,
    );
  }
  return covering.map((overlay) => overlay.id);
}

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
    clearTheGround(meta);
    seeViewAt(meta, [place.lon, place.lat], { layer: place.layer ?? null, zoom: place.zoom, bearing: 0, pitch: 0 });
  });
}
