import { memo, useId, useMemo, useRef, useState } from "react";
import type { Meta } from "../api/meta.js";
import { USE_FIXTURES } from "../api/useMeta.js";
import { useDismiss } from "../ui/useDismiss.js";
import { Attribution, attributionText, useAttributions } from "./attribution.js";
import { formatGridRef, wgs84ToGrid } from "./gridref.js";
import { useMapStore, usePointerStore } from "./store.js";
import { usePointDetail } from "./usePointDetail.js";

/**
 * Figures in the grid reference shown in the readout: six, a 100 m square.
 * The conversion behind it is out by up to six metres in Great Britain (see
 * gridref.ts), which is enough to put the last digit of a 10 m reference in
 * the wrong square. The exact reference comes from the backend's
 * `/geo/point` once the pointer rests, and is given in the readout's title.
 */
export const READOUT_FIGURES = 6;

/** A grid reference for display, or null where neither grid applies. */
export function gridRefText(lng: number, lat: number): string | null {
  const position = wgs84ToGrid(lng, lat);
  return position ? formatGridRef(position, READOUT_FIGURES) : null;
}

export function coordinateText(lng: number, lat: number): string {
  return `${lat.toFixed(5)}, ${lng.toFixed(5)}`;
}

/** Ground height for the readout, to the nearest 10 cm, or a dash while it is not known. */
export function heightText(metres: number | null): string {
  return metres === null ? "– m" : `${metres.toFixed(1)} m`;
}

/**
 * The parts of the readout that follow the pointer. Kept apart from the
 * credits so that a pointer move re-renders only these.
 */
function PointerReadout({ compact }: { compact: boolean }) {
  const pointer = usePointerStore((state) => state.position);
  const camera = useMapStore((state) => state.camera);

  const position = pointer ?? { lng: camera.lng, lat: camera.lat };
  const gridRef = gridRefText(position.lng, position.lat);
  const where = pointer ? "under the pointer" : "at the centre of the map";
  const { detail, missing } = usePointDetail(compact ? null : position);
  const exactRef = detail?.grid_ref ?? null;
  const height = detail?.elevation ?? null;
  const heightTitle =
    detail === null
      ? `Ground height ${where}, shown once the pointer rests`
      : height === null
        ? `No height data ${where}`
        : `Ground height ${where}, in metres above sea level`;

  return (
    <>
      <span
        className="fc-status__gridref fc-mono"
        title={exactRef ? `Grid reference ${where}: ${exactRef}` : `Grid reference ${where}`}
        data-testid="status-gridref"
      >
        {gridRef ?? "Off the grid"}
      </span>
      {compact ? null : (
        <>
          <span
            className="fc-status__item fc-mono"
            title={`Latitude and longitude ${where}`}
            data-testid="status-coords"
          >
            {coordinateText(position.lng, position.lat)}
          </span>
          {missing ? null : (
            <span className="fc-status__item fc-mono" title={heightTitle} data-testid="status-height">
              {heightText(height)}
            </span>
          )}
          <span className="fc-status__item fc-mono" title="Zoom level" data-testid="status-zoom">
            z{camera.zoom.toFixed(1)}
          </span>
        </>
      )}
    </>
  );
}

/**
 * The readout along the bottom edge: grid reference, latitude and longitude,
 * ground height, zoom and attribution. It follows the pointer, and falls back
 * to the centre of the map on touch screens, where there is no pointer to
 * follow. The height comes from the server once the pointer has rested, and
 * is left out if the server cannot give one. The compact form, for phones,
 * keeps the grid reference and attribution only, and asks the server nothing.
 */
export const StatusBar = memo(function StatusBar({ meta, compact }: { meta: Meta; compact: boolean }) {
  const attributions = useAttributions(meta);
  const creditText = useMemo(() => attributions.map(attributionText).join(" · "), [attributions]);
  const [expanded, setExpanded] = useState(false);
  const creditsId = useId();
  const creditsRef = useRef<HTMLDivElement>(null);
  useDismiss(creditsRef, expanded, () => setExpanded(false));

  return (
    <footer className={compact ? "fc-status fc-status--compact" : "fc-status"}>
      <PointerReadout compact={compact} />
      {USE_FIXTURES ? (
        <span className="fc-status__flag" title="Running on fixture data with no backend">
          {compact ? "Fixtures" : "Fixture data"}
        </span>
      ) : null}
      <div className="fc-status__credits" ref={creditsRef}>
        <button
          type="button"
          className="fc-status__credits-button"
          aria-expanded={expanded}
          aria-controls={creditsId}
          title="Show all map credits"
          onClick={() => setExpanded((open) => !open)}
        >
          {creditText || "Map credits"}
        </button>
        {expanded ? (
          <div className="fc-status__credits-list" id={creditsId}>
            <p className="fc-status__credits-title">Map data</p>
            <ul>
              {attributions.map((line) => (
                <li key={line}>
                  <Attribution html={line} />
                </li>
              ))}
            </ul>
          </div>
        ) : null}
      </div>
    </footer>
  );
});
