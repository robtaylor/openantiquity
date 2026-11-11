import type { FilterSpecification } from "maplibre-gl";
import { create } from "zustand";
import { RECORD_BASE_FILTERS, RECORD_LAYERS } from "../../map/overlayLayers.js";

/**
 * Which kinds of heritage record the map leaves out. Everything shows until
 * a person turns a category or a source off in the layer panel. The lists
 * hold what is off, so a category or source the catalogue gains later shows
 * without anyone turning it on.
 */
export interface RecordFilterState {
  hiddenCategories: readonly string[];
  hiddenSources: readonly string[];
  setHiddenCategories: (ids: readonly string[]) => void;
  setHiddenSources: (keys: readonly string[]) => void;
}

export const useRecordFilters = create<RecordFilterState>()((set) => ({
  hiddenCategories: [],
  hiddenSources: [],
  setHiddenCategories: (ids) => set({ hiddenCategories: [...new Set(ids)] }),
  setHiddenSources: (keys) => set({ hiddenSources: [...new Set(keys)] }),
}));

/** The layers that draw one stored record each, from the tiles or from squares built from them, which the filters apply to. */
const TILE_RECORD_LAYERS = [
  RECORD_LAYERS.fills,
  RECORD_LAYERS.outlines,
  RECORD_LAYERS.squares,
  RECORD_LAYERS.impreciseFills,
  RECORD_LAYERS.imprecise,
] as const;
const COUNT_LAYERS = [RECORD_LAYERS.counts] as const;
export const FILTERED_RECORD_LAYERS: readonly string[] = [...TILE_RECORD_LAYERS, ...COUNT_LAYERS];

/** True when the comma-separated `sources` of a count names `key`. */
function countNames(key: string): FilterSpecification {
  return ["in", `,${key},`, ["concat", ",", ["coalesce", ["get", "sources"], ""], ","]] as FilterSpecification;
}

/**
 * The filter for one records layer, given what is turned off. `knownSources`
 * is every source the catalogue lists. A record carries one source key and is
 * hidden when that source is off. A count may stand for records of several
 * sources, so it is hidden only when none of the sources it names is still on.
 */
export function recordLayerFilter(
  layerId: string,
  hiddenCategories: readonly string[],
  hiddenSources: readonly string[],
  knownSources: readonly string[],
): FilterSpecification | null {
  const parts: FilterSpecification[] = [];
  const base = RECORD_BASE_FILTERS[layerId];
  if (base) parts.push(base);
  if (hiddenCategories.length > 0) {
    parts.push(["!", ["in", ["get", "category"], ["literal", [...hiddenCategories]]]] as FilterSpecification);
  }
  if (hiddenSources.length > 0) {
    if ((COUNT_LAYERS as readonly string[]).includes(layerId)) {
      const shown = knownSources.filter((key) => !hiddenSources.includes(key));
      parts.push(shown.length > 0 ? (["any", ...shown.map(countNames)] as FilterSpecification) : ["==", 1, 0]);
    } else {
      parts.push(["!", ["in", ["get", "source"], ["literal", [...hiddenSources]]]] as FilterSpecification);
    }
  }
  if (parts.length === 0) return null;
  if (parts.length === 1) return parts[0] ?? null;
  return ["all", ...parts] as FilterSpecification;
}
