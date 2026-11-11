import type { Map as MapLibreMap } from "maplibre-gl";
import {
  Component,
  type ErrorInfo,
  memo,
  type ReactNode,
  type RefObject,
  useCallback,
  useEffect,
  useRef,
  useState,
} from "react";
import "maplibre-gl/dist/maplibre-gl.css";
import { type Meta, viewTitle } from "../api/meta.js";
import { useCoverageOnMap } from "../features/layers/coverage/useCoverageOnMap.js";
import { ProfileCrosshair } from "../features/layers/MapNotices.js";
import { useProfileOnMap } from "../features/layers/profile/useProfileOnMap.js";
import { useRecordsOnMap } from "../features/records/useRecordsOnMap.js";
import { clamp } from "../ui/math.js";
import { MapFailure } from "./MapFailure.js";
import { isMapLive, MapPane } from "./MapPane.js";
import { useMainMapStore } from "./mainMap.js";
import { SwipeHandle } from "./SwipeHandle.js";
import { useMapStore } from "./store.js";
import { syncMaps } from "./syncMaps.js";
import { useTileNotices } from "./tileNotices.js";
import { useTileRefresh } from "./tileRefresh.js";
import { useFindingsOverlay } from "./useFindingsOverlay.js";
import "./map.css";

/** How much of each side of the map is covered, and where floating controls sit on what is left. */
export interface MapInsets {
  /** Width covered on the left, by the mode rail. */
  left: number;
  /** Width covered on the right, by the side panel. */
  right: number;
  /** Width of the strip down the right of the uncovered map that the floating buttons take up. */
  controls?: number;
}

/**
 * The comparison divide stops this far from each edge of the uncovered map,
 * so its 36 px grip is always whole, never under the rail or the panel, and
 * clear of the strip at the screen edge that phones keep for the back gesture.
 */
export const SWIPE_MARGIN = 32;
/** Space kept between a comparison label and the edge of the uncovered map. */
const LABEL_EDGE_GAP = 12;

function useElementWidth(ref: RefObject<HTMLElement | null>): number {
  const [width, setWidth] = useState(() => (typeof window === "undefined" ? 0 : window.innerWidth));
  useEffect(() => {
    const element = ref.current;
    if (!element) return;
    setWidth(element.clientWidth || window.innerWidth);
    if (typeof ResizeObserver === "undefined") return;
    const observer = new ResizeObserver(() => setWidth(element.clientWidth));
    observer.observe(element);
    return () => observer.disconnect();
  }, [ref]);
  return width;
}

interface MapViewProps {
  meta: Meta;
  insets: MapInsets;
}

/**
 * The map. Always mounted, filling the window. When a comparison is on, a
 * second MapLibre instance is laid over the first, clipped to the right of
 * the swipe handle, and the two cameras are kept together.
 */
function MapPanes({ meta, insets }: MapViewProps) {
  const mainView = useMapStore((state) => state.mainView);
  const compareView = useMapStore((state) => state.compareView);
  const swipe = useMapStore((state) => state.swipe);
  const setSwipe = useMapStore((state) => state.setSwipe);
  useTileNotices(meta);
  const findings = useFindingsOverlay(meta);

  const root = useRef<HTMLDivElement>(null);
  const width = useElementWidth(root);
  const [mainMap, setMainMap] = useState<MapLibreMap | null>(null);
  const [compareMap, setCompareMap] = useState<MapLibreMap | null>(null);
  const comparing = compareView !== null;

  // Features that draw on the map or listen to it find the main one here.
  useEffect(() => {
    useMainMapStore.getState().setMap(mainMap);
    return () => useMainMapStore.getState().setMap(null);
  }, [mainMap]);

  useEffect(() => {
    // The comparison can be switched off in the very render that first hands
    // its map over. By then the map has been removed, and must not be touched.
    if (!comparing || !mainMap || !compareMap) return;
    if (!isMapLive(mainMap) || !isMapLive(compareMap)) return;
    return syncMaps(mainMap, compareMap, { isLive: isMapLive });
  }, [comparing, mainMap, compareMap]);

  const shownCompare = comparing ? compareMap : null;
  useRecordsOnMap(meta, mainMap, shownCompare);
  useCoverageOnMap(meta, mainMap, shownCompare);
  useProfileOnMap(mainMap, shownCompare);
  useTileRefresh(meta, [mainMap, shownCompare]);

  // The handle moves within the part of the map that is not under the rail or the panel.
  const usable = Math.max(1, width - insets.left - insets.right);
  const margin = Math.min(0.5, SWIPE_MARGIN / usable);
  const position = clamp(swipe, margin, 1 - margin);
  const handleX = insets.left + position * usable;

  const onHandleMove = useCallback(
    (clientX: number) => {
      const left = root.current?.getBoundingClientRect().left ?? 0;
      setSwipe(clamp((clientX - left - insets.left) / usable, margin, 1 - margin));
    },
    [insets.left, margin, setSwipe, usable],
  );

  const onHandlePosition = useCallback((next: number) => setSwipe(clamp(next, margin, 1 - margin)), [margin, setSwipe]);

  return (
    <div className="fc-map" ref={root} data-comparing={comparing} data-ready={mainMap !== null}>
      <MapPane meta={meta} viewId={mainView} pane="main" findings={findings} onMap={setMainMap} />
      {comparing ? (
        <>
          <MapPane
            meta={meta}
            viewId={compareView}
            pane="compare"
            findings={findings}
            onMap={setCompareMap}
            style={{ clipPath: `inset(0 0 0 ${handleX}px)` }}
          />
          <SwipeHandle
            x={handleX}
            position={position}
            min={margin}
            max={1 - margin}
            labelLeft={insets.left + LABEL_EDGE_GAP}
            labelRight={width - insets.right - Math.max(LABEL_EDGE_GAP, insets.controls ?? 0)}
            leftLabel={viewTitle(meta, mainView)}
            rightLabel={viewTitle(meta, compareView)}
            onMove={onHandleMove}
            onPosition={onHandlePosition}
          />
        </>
      ) : null}
      <ProfileCrosshair />
    </div>
  );
}

interface BoundaryState {
  error: Error | null;
}

/**
 * Keeps a fault in the map from taking the rest of the app with it. React
 * unmounts the whole tree when a render or an effect throws and nothing
 * catches it. Here the map is replaced by a notice with a way to start it
 * again, and the shell around it stays up.
 */
class MapErrorBoundary extends Component<{ children: ReactNode }, BoundaryState> {
  override state: BoundaryState = { error: null };

  static getDerivedStateFromError(error: unknown): BoundaryState {
    return { error: error instanceof Error ? error : new Error(String(error)) };
  }

  override componentDidCatch(error: Error, info: ErrorInfo): void {
    console.error("[map] The map stopped with an error.", error, info.componentStack);
  }

  override render(): ReactNode {
    const { error } = this.state;
    if (!error) return this.props.children;
    return (
      <div className="fc-map" data-ready="false" data-failed="true">
        <MapFailure
          title="The map has stopped"
          actionLabel="Start the map again"
          onAction={() => this.setState({ error: null })}
          detail={error.message}
        >
          <p>Something went wrong while drawing the map. Nothing you've saved is affected.</p>
        </MapFailure>
      </div>
    );
  }
}

/**
 * The map, inside a boundary that turns a crash into a notice. Memoised: it
 * reads the store itself, so the shell re-rendering, on a resize say, need
 * not re-render it.
 */
export const MapView = memo(function MapView(props: MapViewProps) {
  return (
    <MapErrorBoundary>
      <MapPanes {...props} />
    </MapErrorBoundary>
  );
});
