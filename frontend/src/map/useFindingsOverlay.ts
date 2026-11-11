import { useEffect, useMemo, useRef } from "react";
import { findOverlay, type Meta } from "../api/meta.js";
import { useFindingsInBox } from "../features/findings/useFindingsInBox.js";
import { type FindingsMapData, findingsMapData } from "./findingsData.js";
import { useFindingsHidden } from "./hiddenFindings.js";
import { useMapStore, useViewAreaStore } from "./store.js";
import { overlayShown } from "./style.js";
import { overlayTroubleKey } from "./trouble.js";

/**
 * Below this zoom the findings overlay asks for nothing. The box in view
 * then covers a county or more, which is more than a map of point markers
 * can usefully show and more than the server should be asked for on every
 * drag.
 */
export const FINDINGS_MIN_ZOOM = 9;

/**
 * The findings to draw: whatever `GET /findings` returns for the area the
 * main map shows, while the findings overlay is on.
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

  const wanted = shown && !hidden && zoom >= FINDINGS_MIN_ZOOM;
  const { findings, error, errorAt } = useFindingsInBox(wanted ? bounds : null, attempt);

  // A failure already acted on comes back when the same box is asked for again, so each is handled once.
  const handled = useRef(0);
  useEffect(() => {
    if (key === null || errorAt <= handled.current) return;
    handled.current = errorAt;
    console.warn(`[map] Findings could not be loaded: ${error?.message ?? "unknown error"}`);
    useMapStore.getState().setSourceFailing(key, true);
  }, [key, error, errorAt]);

  return useMemo(() => findingsMapData(findings), [findings]);
}
