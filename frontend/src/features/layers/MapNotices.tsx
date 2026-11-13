import { Plus } from "lucide-react";
import type { CSSProperties, ReactNode } from "react";
import type { Meta } from "../../api/meta.js";
import { useMapStore, useViewAreaStore } from "../../map/store.js";
import { useDrawnFindings } from "../../map/useFindingsOverlay.js";
import { useMapCover, visibleOffset } from "../../map/visibleArea.js";
import { useCoverageStore } from "./coverage/store.js";
import { isTerrainView } from "./coverage/useCoverageOnMap.js";
import { useProfileLine } from "./profile/useProfile.js";
import { TERRAIN_DETAIL_ZOOM, useTerrainLoading } from "./terrainLoading.js";
import "./layers.css";

/**
 * Says so on the map when a terrain view has nothing to draw, so a blank or
 * black area isn't read as flat ground: while the terrain is still being
 * prepared, where the whole view or some squares in it have no one-metre
 * elevation, and when zoomed out below the zoom `/meta` gives for the
 * one-metre data, where the words depend on whether the national overview
 * is built.
 */
export function CoverageNotice({ meta }: { meta: Meta }) {
  const terrain = useMapStore((state) => isTerrainView(meta, state.mainView) || isTerrainView(meta, state.compareView));
  const summary = useCoverageStore((state) => state.summary);
  const preparing = useTerrainLoading((state) => state.preparing);
  const detailZoom = meta.terrain?.fine_minzoom ?? TERRAIN_DETAIL_ZOOM;
  const zoomedOut = useViewAreaStore((state) => state.bounds !== null && state.zoom < detailZoom);
  if (!terrain) return null;
  let words: ReactNode;
  if (preparing) {
    words = (
      <>
        <strong>Preparing the terrain here…</strong> The first look at a place can take a few seconds.
      </>
    );
  } else if (summary.status === "ready" && summary.gaps > 0) {
    words =
      summary.gaps === summary.cells ? (
        <>
          <strong>No one-metre LIDAR here.</strong> The terrain views have nothing to show in this area yet.
        </>
      ) : (
        "Shaded squares have no one-metre LIDAR, so they show nothing, not flat ground."
      );
  } else if (zoomedOut) {
    words =
      meta.terrain?.overview.built === true
        ? "Zoomed out this far, the terrain is a coarse overview. Zoom in for the one-metre detail."
        : "Zoomed out this far, only places someone has looked at closely are drawn. Zoom in to see the rest.";
  } else {
    return null;
  }
  return (
    <p className="fc-map-notice" role="status" data-testid="coverage-notice">
      {words}
    </p>
  );
}

/**
 * Says so on the map when the server sent fewer findings than there are in
 * view, as it does past a set number for one box. What came is drawn, and
 * zooming in shows the rest. It goes when an answer is whole again.
 */
export function FindingsCutShortNotice() {
  const cutShort = useDrawnFindings((state) => state.cutShort);
  if (!cutShort) return null;
  return (
    <p className="fc-map-notice" role="status" data-testid="findings-cut-short-notice">
      Not every finding in view is drawn. Zoom in to see the rest.
    </p>
  );
}

/**
 * A cross at the middle of the part of the map that shows, clear of the panel
 * or the sheet, while a profile is drawn, where "Add a point at the cross"
 * puts one.
 */
export function ProfileCrosshair() {
  const { open } = useProfileLine();
  const cover = useMapCover((state) => state.cover);
  if (!open) return null;
  const offset = visibleOffset(cover);
  const style: CSSProperties = { left: `calc(50% + ${offset.x}px)`, top: `calc(50% + ${offset.y}px)` };
  return (
    <span className="fc-map-crosshair" aria-hidden="true" data-testid="profile-crosshair" style={style}>
      <Plus size={28} strokeWidth={1.5} />
    </span>
  );
}
