/**
 * The chooser between overlapping findings (Decision 0031): "3 findings
 * here", each with its title, step and class, in the order the picking
 * rules rank them, at most 8 and then "Show all in Explore". Hovering or
 * focusing an entry highlights its shape on the map. Escape closes it and
 * puts focus back on the map.
 */

import type { Map as MapLibreMap } from "maplibre-gl";
import { useEffect } from "react";
import { useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useFindingHighlight } from "../../map/findingHighlight.js";
import type { FindingCandidate } from "../../map/findingHits.js";
import { isMapLive } from "../../map/MapPane.js";
import { useMapStore } from "../../map/store.js";
import { useDrawnFindings } from "../../map/useFindingsOverlay.js";
import { Chooser, type ChooserEntry } from "../../ui/Chooser.js";
import { TierBadge } from "../../ui/TierBadge.js";
import { labelOf } from "../finding/describe.js";
import { findingPath, useSelectedFinding } from "../findings/selection.js";

/** At most this many entries, then "Show all in Explore". */
export const CHOOSER_MAX_ENTRIES = 8;
/** Explore is opened at least this close, so the findings there can be told apart in its list. */
const EXPLORE_ZOOM = 15;

export interface ChooserRequest {
  /** Where the tap was, in pixels from the window's top left. */
  at: { x: number; y: number };
  /** Where the tap was on the ground. */
  lngLat: [number, number];
  candidates: FindingCandidate[];
}

/** "1 finding here", "3 findings here". */
export function findingsHereWords(count: number): string {
  return `${count} ${count === 1 ? "finding" : "findings"} here`;
}

export function FindingChooser({
  meta,
  map,
  request,
  sheet,
  onClose,
}: {
  meta: Meta;
  map: MapLibreMap;
  request: ChooserRequest;
  sheet: boolean;
  onClose: () => void;
}) {
  const navigate = useNavigate();
  const drawn = useDrawnFindings((state) => state.byId);
  const shown = request.candidates.slice(0, CHOOSER_MAX_ENTRIES);
  // Every way out unmounts the chooser, so the highlight of the entry last pointed at goes with it.
  useEffect(() => () => useFindingHighlight.getState().set(null), []);

  const entries: ChooserEntry[] = shown.map((candidate) => {
    const finding = drawn.get(candidate.publicId);
    const tier = { id: finding?.tier ?? "", label: labelOf(meta.vocab.tiers, finding?.tier ?? "") };
    const featureClass = labelOf(meta.vocab.feature_classes, finding?.feature_class ?? "");
    const title = finding?.title ?? "A finding";
    return {
      id: candidate.publicId,
      label: `${title}, ${tier.label}, ${featureClass}`,
      content: (
        <span className="fc-chooser__finding">
          <span className="fc-chooser__title">{title}</span>
          <span className="fc-chooser__meta">
            <TierBadge tier={tier} size="sm" />
            <span>{featureClass}</span>
          </span>
        </span>
      ),
    };
  });

  function finish(): void {
    onClose();
    // Focus goes back to the map, where the tap was.
    requestAnimationFrame(() => {
      if (isMapLive(map)) map.getCanvas().focus({ preventScroll: true });
    });
  }

  function choose(publicId: string): void {
    const candidate = request.candidates.find((each) => each.publicId === publicId);
    onClose();
    useSelectedFinding.getState().select(publicId, candidate?.at ?? request.lngLat, false);
    navigate(findingPath(publicId));
  }

  function showAll(): void {
    onClose();
    const { camera, requestCamera } = useMapStore.getState();
    requestCamera({ lng: request.lngLat[0], lat: request.lngLat[1], zoom: Math.max(camera.zoom, EXPLORE_ZOOM) });
    navigate("/");
  }

  return (
    <Chooser
      open
      title={findingsHereWords(request.candidates.length)}
      at={request.at}
      sheet={sheet}
      entries={entries}
      more={
        request.candidates.length > CHOOSER_MAX_ENTRIES ? { label: "Show all in Explore", onClick: showAll } : undefined
      }
      onChoose={choose}
      onActive={(publicId) => useFindingHighlight.getState().set(publicId)}
      onClose={finish}
    />
  );
}
