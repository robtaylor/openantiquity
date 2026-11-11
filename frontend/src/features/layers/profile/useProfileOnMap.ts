import type { GeoJSONSource, Map as MapLibreMap, MapMouseEvent } from "maplibre-gl";
import { useEffect, useMemo, useRef } from "react";
import { useNavigate, useSearchParams } from "react-router";
import { isMapLive } from "../../../map/MapPane.js";
import { useMapTool } from "../../../map/tool.js";
import { COLOURS } from "../../../ui/tokens.js";
import { EMPTY_COLLECTION, type Feature, type FeatureCollection } from "../../records/geojson.js";
import type { ProfileSample } from "./api.js";
import { type LngLat, MAX_LINE_POINTS, nearestIndex, profilePath } from "./line.js";
import { useProfileHover } from "./store.js";
import { useProfileLine, useProfileQuery } from "./useProfile.js";

export const PROFILE_TOOL = "profile";
export const PROFILE_SOURCE = "profile";
export const PROFILE_LAYERS = {
  casing: "profile-line-casing",
  line: "profile-line",
  points: "profile-points",
  hover: "profile-hover",
} as const;

/** How close, in pixels, the pointer must come to the line for the chart to follow it. */
const HOVER_REACH_PX = 14;

/** What the map draws for a profile: the line, its points, and the sample under the pointer. */
export function profileFeatures(points: readonly LngLat[], hover: ProfileSample | null): FeatureCollection {
  const features: Feature[] = [];
  if (points.length >= 2) {
    features.push({
      type: "Feature",
      geometry: { type: "LineString", coordinates: points.map((point) => [...point]) },
      properties: { kind: "line" },
    });
  }
  for (const point of points) {
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [...point] },
      properties: { kind: "point" },
    });
  }
  if (hover) {
    features.push({
      type: "Feature",
      geometry: { type: "Point", coordinates: [hover.lon, hover.lat] },
      properties: { kind: "hover" },
    });
  }
  return { type: "FeatureCollection", features };
}

/** Add the profile's source and layers to a map that lacks them, on top of everything else. */
function ensureLayers(map: MapLibreMap): void {
  if (map.getSource(PROFILE_SOURCE)) return;
  map.addSource(PROFILE_SOURCE, { type: "geojson", data: EMPTY_COLLECTION });
  const kind = (value: string) => ["==", ["get", "kind"], value] as ["==", ["get", string], string];
  map.addLayer({
    id: PROFILE_LAYERS.casing,
    type: "line",
    source: PROFILE_SOURCE,
    filter: kind("line"),
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": COLOURS.bg, "line-width": 6, "line-opacity": 0.85 },
  });
  map.addLayer({
    id: PROFILE_LAYERS.line,
    type: "line",
    source: PROFILE_SOURCE,
    filter: kind("line"),
    layout: { "line-cap": "round", "line-join": "round" },
    paint: { "line-color": COLOURS.accent, "line-width": 2.5 },
  });
  map.addLayer({
    id: PROFILE_LAYERS.points,
    type: "circle",
    source: PROFILE_SOURCE,
    filter: kind("point"),
    paint: {
      "circle-radius": 5,
      "circle-color": COLOURS.accent,
      "circle-stroke-color": COLOURS.bg,
      "circle-stroke-width": 1.5,
    },
  });
  map.addLayer({
    id: PROFILE_LAYERS.hover,
    type: "circle",
    source: PROFILE_SOURCE,
    filter: kind("hover"),
    paint: {
      "circle-radius": 6,
      "circle-color": COLOURS.text,
      "circle-stroke-color": COLOURS.bg,
      "circle-stroke-width": 2,
    },
  });
}

function liveMaps(maps: ReadonlyArray<MapLibreMap | null>): MapLibreMap[] {
  return maps.filter((map): map is MapLibreMap => map !== null && isMapLive(map));
}

/**
 * The height profile on the map. While the profile panel is open, a click
 * adds a point to the line in the address, and features under it don't open.
 * The line and its points are drawn on both panes, and the pointer near the
 * line moves the chart's marker, as the chart's pointer moves the map's.
 */
export function useProfileOnMap(main: MapLibreMap | null, compare: MapLibreMap | null): void {
  const { open, points } = useProfileLine();
  const [searchParams] = useSearchParams();
  // The layer panel can open over the profile. The line stays in sight, but clicks are the map's again.
  const drawing = open && searchParams.get("panel") === null;
  const profile = useProfileQuery(points);
  const samples = open ? (profile.data?.samples ?? null) : null;
  const hover = useProfileHover((state) => state.hover);
  const setHover = useProfileHover((state) => state.setHover);
  const setTool = useMapTool((state) => state.setTool);
  const navigate = useNavigate();

  const latest = useRef({ points, samples, navigate });
  latest.current = { points, samples, navigate };

  const hoverSample = hover === null ? null : (samples?.[hover] ?? null);
  const data = useMemo(() => profileFeatures(open ? points : [], hoverSample), [open, points, hoverSample]);

  useEffect(() => {
    for (const map of liveMaps([main, compare])) {
      ensureLayers(map);
      (map.getSource(PROFILE_SOURCE) as GeoJSONSource | undefined)?.setData(data);
    }
  }, [main, compare, data]);

  // A hover left over from a line that has gone means nothing.
  useEffect(() => {
    if (samples === null) setHover(null);
  }, [samples, setHover]);

  useEffect(() => {
    if (!drawing) return;
    setTool(PROFILE_TOOL);
    const maps = liveMaps([main, compare]);
    const detach: Array<() => void> = [];
    // The map clears only a marker it put there. A tap on the chart is followed
    // by the browser's made-up mouse events, which leave the map, and must not
    // take away the marker the chart has just placed.
    let placedByMap = false;
    const fromMap = (index: number | null): void => {
      if (index === null && !placedByMap) return;
      placedByMap = index !== null;
      setHover(index);
    };
    for (const map of maps) {
      const onClick = (event: MapMouseEvent): void => {
        const { points: current, navigate: go } = latest.current;
        if (current.length >= MAX_LINE_POINTS) return;
        go(profilePath([...current, [event.lngLat.lng, event.lngLat.lat]]), { replace: true });
      };
      let frame = 0;
      let pending: MapMouseEvent | null = null;
      const onMove = (event: MapMouseEvent): void => {
        if (event.originalEvent?.buttons) return;
        pending = event;
        if (frame !== 0) return;
        frame = requestAnimationFrame(() => {
          frame = 0;
          const { samples: current } = latest.current;
          if (!pending || !current || !isMapLive(map)) return;
          const projected = current.map((sample) => map.project([sample.lon, sample.lat]));
          fromMap(nearestIndex(projected, pending.point, HOVER_REACH_PX));
        });
      };
      const onOut = (): void => fromMap(null);
      map.getCanvas().style.cursor = "crosshair";
      // Two quick clicks are two points, not a zoom.
      map.doubleClickZoom.disable();
      map.on("click", onClick);
      map.on("mousemove", onMove);
      map.on("mouseout", onOut);
      detach.push(() => {
        cancelAnimationFrame(frame);
        map.off("click", onClick);
        map.off("mousemove", onMove);
        map.off("mouseout", onOut);
        if (!isMapLive(map)) return;
        map.getCanvas().style.cursor = "";
        map.doubleClickZoom.enable();
      });
    }
    return () => {
      for (const off of detach) off();
      if (useMapTool.getState().tool === PROFILE_TOOL) setTool(null);
    };
  }, [drawing, main, compare, setTool, setHover]);
}
