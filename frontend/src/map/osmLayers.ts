import type { ExpressionSpecification, FilterSpecification, LayerSpecification } from "maplibre-gl";
import { COLOURS } from "../ui/tokens.js";
import type { OverlayLayer } from "./overlayLayers.js";

/**
 * Our own styling of an OpenMapTiles-schema source for use over terrain:
 * thin light lines with a dark casing, and labels with dark halos, so the
 * overlay says where you are without hiding the ground.
 *
 * Source layers and fields were checked against OpenFreeMap's TileJSON
 * (https://tiles.openfreemap.org/planet, schema 3.16) and its "liberty" style
 * in November 2026: `transportation` (class, brunnel), `transportation_name`
 * (class, name, ref), `waterway` (class, brunnel, name), `water`,
 * `water_name` (name), `boundary` (admin_level, maritime) and `place`
 * (class, name, rank).
 *
 * The font stacks below must exist on the glyph server named by the overlay.
 * OpenMapTiles hosts serve the Noto Sans family.
 */

const FONT_REGULAR = ["Noto Sans Regular"];
const FONT_BOLD = ["Noto Sans Bold"];
const FONT_ITALIC = ["Noto Sans Italic"];

const LINE = "#f3efe6";
const CASING = COLOURS.bg;
const WATER = "#8cc4e2";
const BOUNDARY = "#d9c9f5";
const HALO = "rgba(20, 22, 26, 0.9)";

const IS_LINE: ExpressionSpecification = ["match", ["geometry-type"], ["LineString", "MultiLineString"], true, false];
const NOT_TUNNEL: ExpressionSpecification = ["!=", ["get", "brunnel"], "tunnel"];
const NAME: ExpressionSpecification = ["coalesce", ["get", "name"], ["get", "name:latin"], ""];

function classIn(classes: string[]): ExpressionSpecification {
  return ["match", ["get", "class"], classes, true, false];
}

function widthByZoom(z10: number, z14: number, z18: number): ExpressionSpecification {
  return ["interpolate", ["linear"], ["zoom"], 10, z10, 14, z14, 18, z18];
}

interface RoadTier {
  id: string;
  classes: string[];
  minzoom: number;
  /** Line widths in pixels at zoom 10, 14 and 18. */
  width: [number, number, number];
  dash?: number[];
}

const ROADS: RoadTier[] = [
  { id: "path", classes: ["path", "pedestrian", "track"], minzoom: 12, width: [0.5, 0.8, 1.6], dash: [3, 2] },
  { id: "minor", classes: ["minor", "service"], minzoom: 11, width: [0.4, 0.9, 2.4] },
  { id: "mid", classes: ["secondary", "tertiary"], minzoom: 8, width: [0.8, 1.3, 3.2] },
  { id: "major", classes: ["motorway", "trunk", "primary"], minzoom: 5, width: [1.2, 1.7, 4] },
];

const CASING_EXTRA = 1.8;

export function osmLayers(source: string): OverlayLayer[] {
  const layers: OverlayLayer[] = [];

  function line(
    id: string,
    sourceLayer: string,
    filter: FilterSpecification,
    minzoom: number,
    paint: Record<string, unknown>,
    opacity: number,
    cap: "round" | "butt" = "round",
  ): void {
    layers.push({
      layer: {
        id: `osm-${id}`,
        type: "line",
        source,
        "source-layer": sourceLayer,
        minzoom,
        filter,
        layout: { "line-cap": cap, "line-join": "round" },
        paint,
      } as LayerSpecification,
      opacity: { "line-opacity": opacity },
    });
  }

  layers.push({
    layer: {
      id: "osm-water-area",
      type: "fill",
      source,
      "source-layer": "water",
      filter: NOT_TUNNEL,
      paint: { "fill-color": WATER, "fill-antialias": false },
    },
    opacity: { "fill-opacity": 0.22 },
  });
  line("water-shore", "water", NOT_TUNNEL, 8, { "line-color": WATER, "line-width": 0.8 }, 0.75);

  const waterway: FilterSpecification = ["all", IS_LINE, NOT_TUNNEL];
  // Rivers are drawn wider than streams, drains and canals.
  function waterwayWidth(extra: number): ExpressionSpecification {
    const at = (river: number, other: number): ExpressionSpecification => [
      "match",
      ["get", "class"],
      "river",
      river + extra,
      other + extra,
    ];
    return ["interpolate", ["linear"], ["zoom"], 9, at(0.9, 0.3), 14, at(1.8, 0.9), 18, at(4, 2)];
  }
  line(
    "waterway-casing",
    "waterway",
    waterway,
    9,
    { "line-color": CASING, "line-width": waterwayWidth(CASING_EXTRA) },
    0.45,
  );
  line("waterway", "waterway", waterway, 9, { "line-color": WATER, "line-width": waterwayWidth(0) }, 0.95);

  // Counties and above from zoom 6. Districts and parishes join in close up.
  const boundary: FilterSpecification = [
    "all",
    ["!=", ["get", "maritime"], 1],
    ["<=", ["get", "admin_level"], ["step", ["zoom"], 6, 11, 8, 13, 10]],
  ];
  line(
    "boundary",
    "boundary",
    boundary,
    6,
    {
      "line-color": BOUNDARY,
      "line-width": ["case", ["<=", ["get", "admin_level"], 6], 1.1, 0.8],
      "line-dasharray": [4, 2, 1, 2],
    },
    0.6,
    "butt",
  );

  const rail: FilterSpecification = ["all", IS_LINE, NOT_TUNNEL, classIn(["rail"])];
  line(
    "rail-casing",
    "transportation",
    rail,
    9,
    { "line-color": CASING, "line-width": widthByZoom(1.8, 2.6, 4.4) },
    0.55,
  );
  line(
    "rail",
    "transportation",
    rail,
    9,
    { "line-color": LINE, "line-width": widthByZoom(0.6, 1, 2), "line-dasharray": [5, 3] },
    0.75,
    "butt",
  );

  for (const road of ROADS) {
    const filter: FilterSpecification = ["all", IS_LINE, NOT_TUNNEL, classIn(road.classes)];
    const [a, b, c] = road.width;
    line(
      `road-${road.id}-casing`,
      "transportation",
      filter,
      road.minzoom,
      { "line-color": CASING, "line-width": widthByZoom(a + CASING_EXTRA, b + CASING_EXTRA, c + CASING_EXTRA) },
      0.6,
    );
  }
  for (const road of ROADS) {
    const filter: FilterSpecification = ["all", IS_LINE, NOT_TUNNEL, classIn(road.classes)];
    const [a, b, c] = road.width;
    line(
      `road-${road.id}`,
      "transportation",
      filter,
      road.minzoom,
      { "line-color": LINE, "line-width": widthByZoom(a, b, c), ...(road.dash ? { "line-dasharray": road.dash } : {}) },
      0.92,
      road.dash ? "butt" : "round",
    );
  }

  function label(
    id: string,
    sourceLayer: string,
    filter: FilterSpecification | null,
    minzoom: number,
    layout: Record<string, unknown>,
    colour: string,
  ): void {
    layers.push({
      layer: {
        id: `osm-${id}`,
        type: "symbol",
        source,
        "source-layer": sourceLayer,
        minzoom,
        ...(filter ? { filter } : {}),
        layout: { "text-field": NAME, "text-font": FONT_REGULAR, "text-size": 12, "text-padding": 4, ...layout },
        paint: { "text-color": colour, "text-halo-color": HALO, "text-halo-width": 1.6, "text-halo-blur": 0.4 },
      } as LayerSpecification,
      opacity: { "text-opacity": 1 },
      // Names are drawn over the records and findings, which would otherwise sit on them.
      onTop: true,
    });
  }

  const alongLine = { "symbol-placement": "line", "symbol-spacing": 320, "text-max-angle": 30 };
  label(
    "waterway-label",
    "waterway",
    IS_LINE,
    12,
    { ...alongLine, "text-font": FONT_ITALIC, "text-size": 11.5, "text-letter-spacing": 0.08 },
    WATER,
  );
  label(
    "water-label",
    "water_name",
    ["match", ["geometry-type"], ["Point", "MultiPoint"], true, false],
    10,
    { "text-font": FONT_ITALIC, "text-size": 12, "text-max-width": 6 },
    WATER,
  );
  label(
    "path-label",
    "transportation_name",
    ["all", IS_LINE, classIn(["path", "pedestrian", "track"])],
    15,
    { ...alongLine, "text-size": 10.5 },
    LINE,
  );
  label(
    "road-label",
    "transportation_name",
    ["all", IS_LINE, classIn(["motorway", "trunk", "primary", "secondary", "tertiary", "minor", "service"])],
    13,
    {
      ...alongLine,
      "text-field": ["coalesce", ["get", "name"], ["get", "ref"], ""],
      "text-size": ["interpolate", ["linear"], ["zoom"], 13, 10.5, 17, 12.5],
    },
    LINE,
  );
  label(
    "place-hamlet",
    "place",
    classIn(["hamlet", "isolated_dwelling", "neighbourhood", "quarter"]),
    13,
    { "text-size": 11.5, "text-max-width": 7, "symbol-sort-key": ["coalesce", ["get", "rank"], 99] },
    LINE,
  );
  label(
    "place-village",
    "place",
    classIn(["village", "suburb"]),
    10,
    {
      "text-size": ["interpolate", ["linear"], ["zoom"], 10, 11, 15, 14],
      "text-max-width": 7,
      "symbol-sort-key": ["coalesce", ["get", "rank"], 99],
    },
    LINE,
  );
  label(
    "place-town",
    "place",
    classIn(["city", "town"]),
    5,
    {
      "text-font": FONT_BOLD,
      "text-size": ["interpolate", ["linear"], ["zoom"], 6, 11, 11, 14, 15, 18],
      "text-max-width": 7,
      "text-letter-spacing": 0.02,
      "symbol-sort-key": ["coalesce", ["get", "rank"], 99],
    },
    "#ffffff",
  );

  return layers;
}
