import { Crosshair, Link2, Spline, Trash2, Undo2, Unplug } from "lucide-react";
import { type ReactNode, useEffect, useMemo, useRef } from "react";
import { useNavigate } from "react-router";
import { ApiError } from "../../../api/client.js";
import { heightText } from "../../../map/StatusBar.js";
import { useMapStore, useViewAreaStore } from "../../../map/store.js";
import { Button } from "../../../ui/Button.js";
import { copyWithToast } from "../../../ui/clipboard.js";
import { EmptyState } from "../../../ui/EmptyState.js";
import { Skeleton } from "../../../ui/Skeleton.js";
import { useDocumentTitle } from "../../placeholders.js";
import { PanelFrame } from "../../shell/PanelFrame.js";
import type { ProfileOut } from "./api.js";
import { distanceText, framingFor, lineLengthM, MAX_LINE_POINTS, PROFILE_PATH, profilePath } from "./line.js";
import { ProfileChart } from "./ProfileChart.js";
import { useProfileHover } from "./store.js";
import { useProfileLine, useProfileQuery } from "./useProfile.js";
import "./profile.css";

function resolutionText(metres: number): string {
  return metres <= 1 ? "every metre" : `every ${Number(metres.toFixed(1))} m`;
}

function Facts({ profile }: { profile: ProfileOut }) {
  const heights = profile.samples.flatMap((sample) => (sample.elevation === null ? [] : [sample.elevation]));
  const lowest = heights.length > 0 ? Math.min(...heights) : null;
  const highest = heights.length > 0 ? Math.max(...heights) : null;
  const gaps = heights.length < profile.samples.length;
  return (
    <>
      <dl className="fc-profile__facts">
        <div>
          <dt>Length</dt>
          <dd className="fc-mono">{distanceText(profile.length_m)}</dd>
        </div>
        <div>
          <dt>Heights read</dt>
          <dd className="fc-mono">{resolutionText(profile.resolution_m)}</dd>
        </div>
        <div>
          <dt>Lowest</dt>
          <dd className="fc-mono">{heightText(lowest)}</dd>
        </div>
        <div>
          <dt>Highest</dt>
          <dd className="fc-mono">{heightText(highest)}</dd>
        </div>
        {lowest !== null && highest !== null ? (
          <div>
            <dt>Difference</dt>
            <dd className="fc-mono">{heightText(highest - lowest)}</dd>
          </div>
        ) : null}
      </dl>
      <p className="fc-field__hint">
        Heights are metres above sea level, read from the 1 m LIDAR where the line is short enough.
        {profile.resolution_m > 1
          ? " This line is long, so they come from a coarser grid; draw a shorter one for detail."
          : ""}
        {gaps ? " Gaps in the line are places with no height data." : ""}
      </p>
    </>
  );
}

/**
 * The height profile: draw a line on the map, see the shape of the ground
 * along it. The line lives in the address, so a profile can be shared.
 */
export function ProfilePanel() {
  useDocumentTitle("Height profile");
  const navigate = useNavigate();
  const { points } = useProfileLine();
  const profile = useProfileQuery(points);
  const hover = useProfileHover((state) => state.hover);
  const setHover = useProfileHover((state) => state.setHover);
  const camera = useMapStore((state) => state.camera);
  const length = useMemo(() => lineLengthM(points), [points]);

  // A profile opened from a link may be somewhere else. The map goes to it,
  // once, so drawing more of it later doesn't move the map under the pointer.
  // It waits for the map to say what it shows, so a link that also carries the view keeps it.
  const framed = useRef(false);
  const viewBounds = useViewAreaStore((state) => state.bounds);
  useEffect(() => {
    if (framed.current || points.length === 0 || viewBounds === null) return;
    framed.current = true;
    const [west, south, east, north] = viewBounds;
    if (points.every(([lng, lat]) => lng >= west && lng <= east && lat >= south && lat <= north)) return;
    const framing = framingFor(points, window.innerWidth, window.innerHeight);
    if (framing) useMapStore.getState().requestCamera(framing);
  }, [points, viewBounds]);

  const setPoints = (next: typeof points): void => {
    setHover(null);
    navigate(profilePath(next), { replace: true });
  };

  let body: ReactNode;
  if (points.length < 2) {
    body = (
      <EmptyState
        icon={<Spline size={22} />}
        title={points.length === 0 ? "Draw a line on the map" : "Add one more point"}
      >
        {points.length === 0 ? (
          <>
            <p>
              A height profile is a slice through the ground along a line. Draw one across a bank or ditch to see its
              shape.
            </p>
            <p>
              Click or tap the map where the line starts, then again for each bend. Or move the map until the cross is
              on the spot and press "Add a point at the cross".
            </p>
          </>
        ) : (
          <p>Click or tap where the line goes next. Two points are enough.</p>
        )}
      </EmptyState>
    );
  } else if (profile.isError) {
    const refused = profile.error instanceof ApiError && profile.error.status === 400;
    body = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title={refused ? "That line can't be profiled" : "The heights couldn't be loaded"}
        action={
          refused ? undefined : (
            <Button variant="primary" onClick={() => void profile.refetch()}>
              Try again
            </Button>
          )
        }
      >
        <p>{profile.error.message}</p>
      </EmptyState>
    );
  } else if (!profile.data) {
    body = (
      <div role="status" className="fc-profile__loading">
        <span className="fc-visually-hidden">Reading the heights along the line</span>
        <Skeleton height={180} />
      </div>
    );
  } else {
    body = (
      <>
        <ProfileChart samples={profile.data.samples} hover={hover} onHover={setHover} />
        <p className="fc-field__hint">
          Move along the chart, or along the line on the map, to read the height at each point. With the keyboard, focus
          the chart and use the arrow keys.
        </p>
        <Facts profile={profile.data} />
      </>
    );
  }

  return (
    <PanelFrame
      panelKey={PROFILE_PATH}
      title="Height profile"
      subtitle={
        points.length >= 2
          ? `${distanceText(profile.data?.length_m ?? length)}, ${points.length} points`
          : "Draw a line on the map"
      }
    >
      <div className="fc-profile">
        <div className="fc-profile__tools">
          <Button
            size="sm"
            icon={<Crosshair size={16} aria-hidden />}
            disabled={points.length >= MAX_LINE_POINTS}
            onClick={() => setPoints([...points, [camera.lng, camera.lat]])}
          >
            Add a point at the cross
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<Undo2 size={16} aria-hidden />}
            disabled={points.length === 0}
            onClick={() => setPoints(points.slice(0, -1))}
          >
            Remove the last point
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<Trash2 size={16} aria-hidden />}
            disabled={points.length === 0}
            onClick={() => setPoints([])}
          >
            Start again
          </Button>
        </div>
        {body}
        {profile.data ? (
          <Button
            size="sm"
            variant="ghost"
            icon={<Link2 size={16} aria-hidden />}
            onClick={() => void copyWithToast(window.location.href, "Link to this profile copied")}
          >
            Copy a link to this profile
          </Button>
        ) : null}
      </div>
    </PanelFrame>
  );
}
