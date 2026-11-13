import { MapPinPlus } from "lucide-react";
import type { Map as MapLibreMap } from "maplibre-gl";
import { type RefObject, useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import { isMapLive } from "../../map/MapPane.js";
import { useMainMap } from "../../map/mainMap.js";
import { Button } from "../../ui/Button.js";
import { clearPointsOfBar } from "./keepClear.js";
import { isMarkPath } from "./MarkLayer.js";
import { MARK_PATH } from "./MarkPanel.js";
import { isAdding, useMarkStore } from "./markStore.js";
import { PhoneDrawingBar, PhoneSelectedPointBar } from "./PhoneBars.js";

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
