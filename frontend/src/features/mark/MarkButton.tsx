import { MapPinPlus } from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { type RefObject, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { screenPoint } from "../../map/useMapFrame.js";
import { Button } from "../../ui/Button.js";
import { isMarkPath } from "./MarkLayer.js";
import { MARK_PATH } from "./MarkPanel.js";
import { isAdding, useMarkStore } from "./markStore.js";
import { PhoneDrawingBar, PhoneSelectedPointBar } from "./PhoneBars.js";

/** Half a handle's dot, in pixels. */
const DOT_RADIUS_PX = 6;
/** Room kept between a point's dot and the floating bar's top, in pixels. */
const BAR_CLEARANCE_PX = 8;

/**
 * The map is moved up by as little as clears every point under the floating
 * bar, or within `BAR_CLEARANCE_PX` of its top. Asked whenever the bar
 * appears or changes size: its status line wraps as the path grows, and the
 * selected-point bar takes the drawing bar's place. Points below the bar, in
 * the sheet's reach, are left alone.
 */
export function clearPointsOfBar(map: MapLibreMap, bar: DOMRect): void {
  if (bar.height === 0) return;
  const frame = map.getContainer().getBoundingClientRect();
  let lowest: number | null = null;
  for (const point of useMarkStore.getState().shape.present.points) {
    const at = screenPoint(map, [point.lon, point.lat]);
    const x = frame.left + at.x;
    const y = frame.top + at.y;
    const beside = x + DOT_RADIUS_PX < bar.left || x - DOT_RADIUS_PX > bar.right;
    const clear = y + DOT_RADIUS_PX < bar.top - BAR_CLEARANCE_PX || y - DOT_RADIUS_PX > bar.bottom;
    if (beside || clear) continue;
    lowest = lowest === null ? y : Math.max(lowest, y);
  }
  if (lowest !== null) map.panBy([0, lowest + DOT_RADIUS_PX + BAR_CLEARANCE_PX - bar.top], { duration: 0 });
}

function useBarKeepsPointsClear(map: MapLibreMap | null, float: RefObject<HTMLDivElement | null>, on: boolean): void {
  useEffect(() => {
    const element = float.current;
    if (!on || !map || !element || !isMapLive(map)) return;
    const clear = (): void => {
      if (isMapLive(map)) clearPointsOfBar(map, element.getBoundingClientRect());
    };
    clear();
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(clear);
    observer.observe(element);
    return () => observer.disconnect();
  }, [map, float, on]);
}

/**
 * The primary action at the foot of the map: "Mark a finding", which opens
 * the marking panel over the same view with the map taking taps at once.
 *
 * While points are being added on a phone, a compact drawing bar takes its
 * place, or the selected-point bar while a point is selected: one row of
 * icon buttons and one line (`PhoneBars`), above the sheet's peek stop, so
 * the map stays free to tap. Whenever the bar appears or grows, the map is
 * moved so that no point already placed is under it. Once drawing stops the
 * sheet rises and the bars are in it, as on a computer, where they are
 * always in the panel.
 */
export function MarkButton({ isPhone }: { isPhone: boolean }) {
  const navigate = useNavigate();
  const { pathname } = useLocation();
  const map = useMainMap();
  const selected = useMarkStore((state) => state.selected !== null);
  const adding = useMarkStore(isAdding);
  const float = useRef<HTMLDivElement>(null);
  const floating = isMarkPath(pathname) && isPhone && adding;
  useBarKeepsPointsClear(map, float, floating);

  if (!isMarkPath(pathname)) {
    return (
      <Button
        variant="primary"
        size="lg"
        icon={<MapPinPlus size={20} aria-hidden />}
        onClick={() => navigate(MARK_PATH)}
      >
        Mark a finding
      </Button>
    );
  }
  if (!floating) return null;
  return (
    <div className="fc-mark-float" ref={float} data-floats-on-map="">
      {selected ? <PhoneSelectedPointBar map={map} /> : <PhoneDrawingBar map={map} />}
    </div>
  );
}
