/**
 * Which findings the Explore panel and the map show. The two ask the server
 * with the same box and the same filters, so the list and the markers agree.
 *
 * Ruled-out findings are hidden on the map unless the layer panel's "show
 * explained findings" is on (`showRuledOut` in the map store). The map
 * fetches them anyway and hides their layer, so the switch acts at once. The
 * list leaves them out of what it asks for instead, so a ruled-out finding
 * is never listed while its marker is hidden. Withdrawn findings are never
 * shown: the server leaves them out unless asked.
 */

import { useMemo } from "react";
import { create } from "zustand";
import type { QueryParam } from "../../api/client.js";
import { useMapStore } from "../../map/store.js";

export interface FindingFilters {
  tier: readonly string[];
  state: readonly string[];
  feature_class: readonly string[];
}

export type FilterKey = keyof FindingFilters;

export const NO_FILTERS: FindingFilters = { tier: [], state: [], feature_class: [] };

const RULED_OUT = "ruled_out";
const WITHDRAWN = "withdrawn";

/** The states a person can filter by: every state except withdrawn. */
export function filterableStates<T extends { id: string }>(states: readonly T[]): T[] {
  return states.filter((state) => state.id !== WITHDRAWN);
}

/** What is actually asked for once the ruled-out setting is applied. */
export interface EffectiveFilters extends FindingFilters {
  /** True when the filters leave nothing to ask for: only ruled-out findings, while they are hidden. */
  empty: boolean;
}

/**
 * The filters to send, given the person's choice, whether ruled-out findings
 * are shown, and every state id in `/meta`. An empty state list means "the
 * server's default", which is every state but withdrawn.
 */
export function effectiveFilters(
  chosen: FindingFilters,
  showRuledOut: boolean,
  stateIds: readonly string[],
): EffectiveFilters {
  const sorted = (values: readonly string[]) => [...new Set(values)].sort();
  let state = sorted(chosen.state);
  // Before /meta has arrived there is no list of states to leave ruled-out out of.
  if (!showRuledOut && (state.length > 0 || stateIds.length > 0)) {
    const base = state.length > 0 ? state : stateIds.filter((id) => id !== WITHDRAWN);
    const kept = base.filter((id) => id !== RULED_OUT);
    if (kept.length === 0) return { tier: [], state: [], feature_class: [], empty: true };
    state = sorted(kept);
  }
  return { tier: sorted(chosen.tier), state, feature_class: sorted(chosen.feature_class), empty: false };
}

/** The filters as query parameters, for `apiFetch`. */
export function filterParams(filters: FindingFilters): Record<string, QueryParam> {
  return { tier: filters.tier, state: filters.state, feature_class: filters.feature_class };
}

/** The filters as one stable string, for a query key. */
export function filtersKey(filters: FindingFilters): string {
  return [filters.tier.join(","), filters.state.join(","), filters.feature_class.join(",")].join("|");
}

export function hasFilters(filters: FindingFilters): boolean {
  return filters.tier.length > 0 || filters.state.length > 0 || filters.feature_class.length > 0;
}

interface FilterState {
  filters: FindingFilters;
  setFilter: (key: FilterKey, values: readonly string[]) => void;
  clear: () => void;
}

/** The person's choice of filters, shared by the Explore panel and the map. */
export const useFindingFilters = create<FilterState>()((set) => ({
  filters: NO_FILTERS,
  setFilter: (key, values) => set((state) => ({ filters: { ...state.filters, [key]: [...values] } })),
  clear: () => set({ filters: NO_FILTERS }),
}));

/**
 * The filters to ask the server with, kept current. The list leaves out
 * findings the map is hiding. The map passes `forMap`, to fetch them
 * anyway and hide them itself.
 */
export function useEffectiveFilters({ forMap = false }: { forMap?: boolean } = {}): EffectiveFilters {
  const chosen = useFindingFilters((state) => state.filters);
  const showRuledOut = useMapStore((state) => forMap || state.showRuledOut);
  const states = useMapStore((state) => state.meta?.vocab.states);
  return useMemo(
    () =>
      effectiveFilters(
        chosen,
        showRuledOut,
        (states ?? []).map((state) => state.id),
      ),
    [chosen, showRuledOut, states],
  );
}
