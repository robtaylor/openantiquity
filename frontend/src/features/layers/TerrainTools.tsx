import { useQueryClient } from "@tanstack/react-query";
import { Spline } from "lucide-react";
import { Link } from "react-router";
import { useMapStore } from "../../map/store.js";
import { viewTroubleKey } from "../../map/trouble.js";
import { Button } from "../../ui/Button.js";
import { Switch } from "../../ui/Switch.js";
import { yearsText } from "./coverage/coverage.js";
import { useCoverageStore } from "./coverage/store.js";
import { terrainKeys } from "./keys.js";
import { PROFILE_PATH } from "./profile/line.js";
import "./layers.css";

function CoverageDetail() {
  const summary = useCoverageStore((state) => state.summary);
  // Coverage is what Defra publishes, not what could be drawn. When a view on screen isn't loading, it says so.
  const drawing = useMapStore(
    (state) =>
      !state.failing[viewTroubleKey(state.mainView)] &&
      (state.compareView === null || !state.failing[viewTroubleKey(state.compareView)]),
  );
  const queryClient = useQueryClient();
  switch (summary.status) {
    case "idle":
      return null;
    case "wide":
      return <p className="fc-field__hint">Zoom in to see the squares.</p>;
    case "loading":
      return <p className="fc-field__hint">Finding out where there is data…</p>;
    case "failed":
      return (
        <p className="fc-overlay-row__notice" role="status">
          Where the data is couldn't be loaded.
          <Button
            size="sm"
            variant="ghost"
            onClick={() => void queryClient.resetQueries({ queryKey: terrainKeys.allCoverage })}
          >
            Try again
          </Button>
        </p>
      );
    case "ready": {
      if (summary.gaps === summary.cells) {
        return (
          <p className="fc-field__hint" data-testid="coverage-summary">
            No one-metre LIDAR in view.
          </p>
        );
      }
      const what = [
        summary.captures.length > 0 ? summary.captures.join(", ") : "one-metre LIDAR",
        yearsText(summary.years),
      ];
      if (summary.gaps > 0) what.push(`with ${summary.gaps} of ${summary.cells} squares empty`);
      return (
        <p className="fc-field__hint" data-testid="coverage-summary">
          In view: {what.filter(Boolean).join(", ")}.
          {drawing
            ? null
            : " The terrain isn't loading here at the moment, so the map may be blank where these say there is data."}
        </p>
      );
    }
  }
}

/** The layer panel's terrain tools: the height profile, and where one-metre elevation exists. */
export function TerrainTools() {
  const visible = useCoverageStore((state) => state.visible);
  const setVisible = useCoverageStore((state) => state.setVisible);
  return (
    <section className="fc-layers__section" aria-labelledby="terrain-tools-heading">
      <h3 className="fc-layers__heading" id="terrain-tools-heading">
        Terrain tools
      </h3>
      <div className="fc-terrain-tool">
        <Link className="fc-button fc-button--secondary fc-button--sm" to={PROFILE_PATH}>
          <Spline size={16} aria-hidden />
          Draw a height profile
        </Link>
        <p className="fc-field__hint">
          A slice through the ground along a line you draw. Good for reading how high a bank is or how deep a ditch.
        </p>
      </div>
      <div className="fc-overlay-row">
        <Switch
          label="Where there's one-metre LIDAR"
          hint="Outlines the squares the terrain views are drawn from. Shaded squares on the terrain have no data, so they aren't flat ground."
          checked={visible}
          onChange={setVisible}
        />
        {visible ? (
          <div className="fc-overlay-row__detail">
            <CoverageDetail />
          </div>
        ) : null}
      </div>
    </section>
  );
}
