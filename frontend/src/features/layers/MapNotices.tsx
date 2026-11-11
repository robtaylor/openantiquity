import { Plus } from "lucide-react";
import type { Meta } from "../../api/meta.js";
import { useMapStore } from "../../map/store.js";
import { useCoverageStore } from "./coverage/store.js";
import { isTerrainView } from "./coverage/useCoverageOnMap.js";
import { useProfileLine } from "./profile/useProfile.js";
import "./layers.css";

/**
 * Says so on the map when a terrain view has nothing to draw: the whole view
 * has no one-metre elevation, or some squares in it don't. Without it, a
 * blank area would look like flat ground.
 */
export function CoverageNotice({ meta }: { meta: Meta }) {
  const terrain = useMapStore((state) => isTerrainView(meta, state.mainView) || isTerrainView(meta, state.compareView));
  const summary = useCoverageStore((state) => state.summary);
  if (!terrain || summary.status !== "ready" || summary.gaps === 0) return null;
  const none = summary.gaps === summary.cells;
  return (
    <p className="fc-map-notice" role="status" data-testid="coverage-notice">
      {none ? (
        <>
          <strong>No one-metre LIDAR here.</strong> The terrain views have nothing to show in this area yet.
        </>
      ) : (
        "Shaded squares have no one-metre LIDAR, so they show nothing, not flat ground."
      )}
    </p>
  );
}

/** A cross at the middle of the map while a profile is drawn, where "Add a point at the cross" puts one. */
export function ProfileCrosshair() {
  const { open } = useProfileLine();
  if (!open) return null;
  return (
    <span className="fc-map-crosshair" aria-hidden="true" data-testid="profile-crosshair">
      <Plus size={28} strokeWidth={1.5} />
    </span>
  );
}
