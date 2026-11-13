import { useEffect, useMemo, useRef } from "react";
import { create } from "zustand";
import { findOverlay, type Meta } from "../api/meta.js";
import type { FindingProperties } from "../features/findings/types.js";
import { useFindingsInBox } from "../features/findings/useFindingsInBox.js";
import { type FindingsMapData, findingsMapData } from "./findingsData.js";
import { useFindingsHidden } from "./hiddenFindings.js";
import { useMapStore, useViewAreaStore } from "./store.js";
import { overlayShown } from "./style.js";
import { overlayTroubleKey } from "./trouble.js";

/**
 * What the map has drawn of each finding, by public id, so the chooser
 * between overlapping findings can name each one without asking again, and
 * whether the server left some of the findings in view out of its answer.
 */
export const useDrawnFindings = create<{ byId: ReadonlyMap<string, FindingProperties>; cutShort: boolean }>()(() => ({
  byId: new Map(),
  cutShort: false,
}));

/**
 * The findings to draw: whatever `GET /findings` returns for the area the
 * main map shows, at every zoom, while the findings overlay is on. The
 * server sends at most a set number for a box. When it says there are more,
 * the map draws what came and says so (`FindingsCutShortNotice`), and the
 * rest are not paged through: zooming in shows them.
 *
 * A server without the endpoint is passed over in silence. Any other failure
 * switches the overlay off with the same notice and "Try again" as an
 * overlay whose tiles fail. Trying again clears the mark, and the box is
 * asked for afresh.
 */
export function useFindingsOverlay(meta: Meta): FindingsMapData {
  const overlayId = findOverlay(meta, "findings")?.id;
  const key = overlayId === undefined ? null : overlayTroubleKey(overlayId);
  const shown = useMapStore((state) => overlayId !== undefined && overlayShown(state, overlayId));
  // Raised each time the overlay is tried again, so the box is asked for afresh and not answered from the failure.
  const attempt = useMapStore((state) => (key === null ? 0 : (state.retries[key] ?? 0)));
  const bounds = useViewAreaStore((state) => state.bounds);
  const zoom = useViewAreaStore((state) => state.zoom);
  // A blind second look holds the overlay back, so nothing about the findings near it is fetched or drawn.
  const hidden = useFindingsHidden();

  const wanted = shown && !hidden;
  const { findings, error, errorAt } = useFindingsInBox(wanted ? bounds : null, attempt, zoom);

  // A failure already acted on comes back when the same box is asked for again, so each is handled once.
  const handled = useRef(0);
  useEffect(() => {
    if (key === null || errorAt <= handled.current) return;
    handled.current = errorAt;
    console.warn(`[map] Findings could not be loaded: ${error?.message ?? "unknown error"}`);
    useMapStore.getState().setSourceFailing(key, true);
  }, [key, error, errorAt]);

  useEffect(() => {
    useDrawnFindings.setState({
      byId: new Map(findings.features.map((feature) => [feature.properties.public_id, feature.properties])),
      cutShort: wanted && typeof findings.next_cursor === "string",
    });
  }, [findings, wanted]);

  return useMemo(() => findingsMapData(findings), [findings]);
}
