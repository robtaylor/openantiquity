import type { ExpressionSpecification, FilterSpecification, LayerSpecification } from "maplibre-gl";
import type { Meta } from "../api/meta.js";
import { COLOURS, FALLBACK_TIER_COLOUR, STATE_COLOURS, tierColour } from "../ui/tokens.js";

/**
 * A style layer that belongs to an overlay, with the opacity each of its
 * paint properties has when the overlay is at full strength. The overlay's
 * own opacity scales these.
 */
export interface OverlayLayer {
  layer: LayerSpecification;
  opacity: Record<string, number | ExpressionSpecification>;
  /** Drawn only while ruled-out findings are being shown. */
  ruledOutOnly?: boolean;
}

/** The SDF square used for record markers. See `markerImages.ts`. */
export const SQUARE_IMAGE = "fieldclub-square";

/**
 * The vector tile layer name inside the records tiles. The contract fixes the
 * tile path and properties but not this name, so it follows the overlay type.
 */
export const RECORDS_SOURCE_LAYER = "records";

const OUTLINE = COLOURS.bg;
const OUTLINE_WIDTH = 1.5;

/**
 * The circle layers that draw a finding at its exact position, which a tap
 * or click on the map picks findings from. Obscured findings are squares,
 * picked by the square under the tap.
 */
export const FINDING_POINT_LAYERS = {
  points: "findings-points",
  known: "findings-known",
  ruledOut: "findings-ruled-out",
} as const;

/** States that are not drawn as ordinary filled circles. */
const SPECIAL_STATES = ["known", "ruled_out", "withdrawn"];

const STATE: ExpressionSpecification = ["coalesce", ["get", "state"], "open"];
const IS_POINT: ExpressionSpecification = ["==", ["geometry-type"], "Point"];
const IS_SQUARE: ExpressionSpecification = ["==", ["geometry-type"], "Polygon"];

function matchOn(
  property: string,
  cases: Array<[string, string | number]>,
  fallback: string | number,
): ExpressionSpecification | string | number {
  // A match expression needs at least one case.
  if (cases.length === 0) return fallback;
  return ["match", ["get", property], ...cases.flat(), fallback] as unknown as ExpressionSpecification;
}

/** Marker colour by tier id, for every tier in the vocabulary. */
export function tierColourExpression(meta: Meta): ExpressionSpecification | string | number {
  return matchOn(
    "tier",
    meta.vocab.tiers.map((tier) => [tier.id, tierColour(tier.id)]),
    FALLBACK_TIER_COLOUR,
  );
}

/** Marker radius by tier: each step up the ladder adds half a pixel. */
export function tierRadiusExpression(meta: Meta, base: number): ExpressionSpecification | string | number {
  return matchOn(
    "tier",
    meta.vocab.tiers.map((tier, index) => [tier.id, base + index * 0.5]),
    base,
  );
}

/**
 * Findings, styled as docs/UI.md describes: circles coloured by tier with a
 * dark outline, growing slightly with tier. Known findings are hollow rings.
 * Ruled-out findings are small hollow grey rings, hidden unless asked for.
 * A finding whose position this viewer may not see is a dashed
 * one-kilometre square and never a point.
 *
 * `source` is the GeoJSON built by `findingsMapData`: points for exact
 * positions, and polygons for the squares of obscured ones.
 */
export function findingsLayers(meta: Meta, source: string): OverlayLayer[] {
  const colour = tierColourExpression(meta);
  const radius = tierRadiusExpression(meta, 5);
  const ringRadius = tierRadiusExpression(meta, 4.5);
  const ruledOutColour = STATE_COLOURS.ruled_out as string;

  const points: FilterSpecification = ["all", IS_POINT, ["!", ["in", STATE, ["literal", SPECIAL_STATES]]]];
  const known: FilterSpecification = ["all", IS_POINT, ["==", STATE, "known"]];
  const ruledOut: FilterSpecification = ["all", IS_POINT, ["==", STATE, "ruled_out"]];
  const liveSquare: FilterSpecification = [
    "all",
    IS_SQUARE,
    ["!", ["in", STATE, ["literal", ["ruled_out", "withdrawn"]]]],
  ];
  const ruledOutSquare: FilterSpecification = ["all", IS_SQUARE, ["==", STATE, "ruled_out"]];

  function circle(id: string, filter: FilterSpecification, paint: Record<string, unknown>): LayerSpecification {
    return { id, type: "circle", source, filter, paint } as LayerSpecification;
  }

  function squareLine(id: string, filter: FilterSpecification, paint: Record<string, unknown>): LayerSpecification {
    return {
      id,
      type: "line",
      source,
      filter,
      layout: { "line-join": "miter" },
      paint,
    } as LayerSpecification;
  }

  // A hollow ring is two circles: a wide dark stroke, then a narrower
  // coloured stroke laid along its middle, leaving a dark edge on both sides.
  function ring(
    id: string,
    filter: FilterSpecification,
    inner: ExpressionSpecification | string | number,
    strokeColour: ExpressionSpecification | string | number,
    strokeWidth: number,
    ruledOutOnly = false,
  ): OverlayLayer[] {
    const casingRadius =
      typeof inner === "number"
        ? inner - OUTLINE_WIDTH
        : (["-", inner, OUTLINE_WIDTH] as unknown as ExpressionSpecification);
    return [
      {
        layer: circle(`${id}-casing`, filter, {
          "circle-radius": casingRadius,
          "circle-color": "rgba(0, 0, 0, 0)",
          "circle-stroke-color": OUTLINE,
          "circle-stroke-width": strokeWidth + OUTLINE_WIDTH * 2,
        }),
        opacity: { "circle-stroke-opacity": 0.9 },
        ruledOutOnly,
      },
      {
        layer: circle(id, filter, {
          "circle-radius": inner,
          "circle-color": "rgba(0, 0, 0, 0)",
          "circle-stroke-color": strokeColour,
          "circle-stroke-width": strokeWidth,
        }),
        opacity: { "circle-stroke-opacity": 1 },
        ruledOutOnly,
      },
    ];
  }

  return [
    {
      layer: squareLine("findings-obscured-casing", liveSquare, { "line-color": OUTLINE, "line-width": 5 }),
      opacity: { "line-opacity": 0.75 },
    },
    {
      layer: squareLine("findings-obscured", liveSquare, {
        "line-color": colour,
        "line-width": 2,
        "line-dasharray": [2.5, 2],
      }),
      opacity: { "line-opacity": 1 },
    },
    {
      layer: squareLine("findings-obscured-ruled-out", ruledOutSquare, {
        "line-color": ruledOutColour,
        "line-width": 1.5,
        "line-dasharray": [2.5, 2],
      }),
      opacity: { "line-opacity": 0.9 },
      ruledOutOnly: true,
    },
    ...ring(FINDING_POINT_LAYERS.ruledOut, ruledOut, 3, ruledOutColour, 1.5, true),
    ...ring(FINDING_POINT_LAYERS.known, known, ringRadius, colour, 2.5),
    {
      layer: circle(FINDING_POINT_LAYERS.points, points, {
        "circle-radius": radius,
        "circle-color": colour,
        "circle-stroke-color": OUTLINE,
        "circle-stroke-width": OUTLINE_WIDTH,
      }),
      opacity: { "circle-opacity": 1, "circle-stroke-opacity": 1 },
    },
  ];
}

/**
 * The layer of a records tile that holds counts instead of records: below
 * zoom 12, and in a tile with too many records to send one by one. Each
 * point is one category in one cell, with `category`, `count` and `sources`
 * (the source keys counted, comma-separated).
 */
export const RECORD_COUNTS_SOURCE_LAYER = "record_counts";

/** Ids of the records overlay's style layers, for the code that filters them and listens to clicks. */
export const RECORD_LAYERS = {
  outlines: "records-outlines",
  squares: "records-squares",
  counts: "records-counts",
  countLabels: "records-count-labels",
  live: "records-live",
  liveCentres: "records-live-centres",
  selectionLine: "records-selection-line",
  selectionSquare: "records-selection-square",
  selectionPoint: "records-selection-point",
} as const;

/** The GeoJSON source of records a live source sent to this browser (Decision 0007). */
export function recordsLiveSourceId(source: string): string {
  return `${source}-live`;
}

/** The GeoJSON source holding the record whose page is open. */
export function recordsSelectionSourceId(source: string): string {
  return `${source}-selection`;
}

/**
 * The filter each records layer is built with. Filters set later, for the
 * categories and sources a person has turned off, are combined with these
 * and never replace them.
 */
export const RECORD_BASE_FILTERS: Readonly<Record<string, FilterSpecification>> = {
  [RECORD_LAYERS.outlines]: ["!=", ["geometry-type"], "Point"],
  // A cell holding one record needs no number on it.
  [RECORD_LAYERS.countLabels]: [">", ["coalesce", ["get", "count"], 1], 1],
};

/** The counts' glyphs. They must exist on the glyph server named by the street-map overlay. */
const COUNT_FONT = ["Noto Sans Bold"];

/**
 * Heritage records: small squares coloured by category, so they can never be
 * mistaken for findings, which are round. A record with an outline has it
 * drawn as a thin line in the same colour. Where a tile carries counts, each
 * count is a larger, softer square, numbered when the map has glyphs.
 *
 * Records from a live source are the same squares, hollow, because they
 * have no category and were never stored here. The record whose page is
 * open is ringed in the accent colour, and a record whose position is only
 * known to a square is drawn as that square, dashed, never as a point.
 */
export function recordsLayers(meta: Meta, source: string): OverlayLayer[] {
  const colour = matchOn(
    "category",
    meta.vocab.record_categories.map((category) => [category.id, category.colour]),
    COLOURS.textMuted,
  );
  const count: ExpressionSpecification = ["coalesce", ["get", "count"], 1];
  const hasGlyphs = meta.layers.overlays.some((overlay) => overlay.type === "openmaptiles");
  const live = recordsLiveSourceId(source);
  const selection = recordsSelectionSourceId(source);

  const layers: OverlayLayer[] = [
    {
      layer: {
        id: RECORD_LAYERS.outlines,
        type: "line",
        source,
        "source-layer": RECORDS_SOURCE_LAYER,
        filter: RECORD_BASE_FILTERS[RECORD_LAYERS.outlines],
        paint: { "line-color": colour, "line-width": 1.25 },
      } as LayerSpecification,
      opacity: { "line-opacity": 0.85 },
    },
    {
      layer: {
        id: RECORD_LAYERS.counts,
        type: "symbol",
        source,
        "source-layer": RECORD_COUNTS_SOURCE_LAYER,
        layout: {
          "icon-image": SQUARE_IMAGE,
          // From about 14 px across for a handful to 26 px for thousands, so the number fits inside.
          "icon-size": ["interpolate", ["linear"], ["log10", count], 0, 1.8, 1, 2.2, 2, 2.8, 3, 3.6],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
          // Bigger counts underneath, so a small one sharing the cell still shows.
          "symbol-sort-key": ["-", 0, count],
        },
        paint: {
          "icon-color": colour,
          "icon-halo-color": OUTLINE,
          "icon-halo-width": OUTLINE_WIDTH,
        },
      } as LayerSpecification,
      opacity: { "icon-opacity": 0.9 },
    },
  ];
  if (hasGlyphs) {
    layers.push({
      layer: {
        id: RECORD_LAYERS.countLabels,
        type: "symbol",
        source,
        "source-layer": RECORD_COUNTS_SOURCE_LAYER,
        filter: RECORD_BASE_FILTERS[RECORD_LAYERS.countLabels],
        layout: {
          "text-field": [
            "case",
            [">=", count, 1000],
            ["concat", ["to-string", ["/", ["round", ["/", count, 100]], 10]], "k"],
            ["to-string", count],
          ],
          "text-font": COUNT_FONT,
          "text-size": 11,
          "text-allow-overlap": false,
        },
        paint: { "text-color": COLOURS.text, "text-halo-color": OUTLINE, "text-halo-width": 1.5 },
      } as LayerSpecification,
      opacity: { "text-opacity": 1 },
    });
  }
  layers.push(
    {
      layer: {
        id: RECORD_LAYERS.squares,
        type: "symbol",
        source,
        "source-layer": RECORDS_SOURCE_LAYER,
        layout: {
          "icon-image": SQUARE_IMAGE,
          "icon-size": ["interpolate", ["linear"], ["zoom"], 8, 0.6, 14, 1, 18, 1.3],
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: {
          "icon-color": colour,
          "icon-halo-color": OUTLINE,
          "icon-halo-width": OUTLINE_WIDTH,
        },
      } as LayerSpecification,
      opacity: { "icon-opacity": 1 },
    },
    {
      // A live record is a square ring: a light square with a dark one laid in its middle.
      layer: {
        id: RECORD_LAYERS.live,
        type: "symbol",
        source: live,
        layout: {
          "icon-image": SQUARE_IMAGE,
          "icon-size": 1.1,
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: { "icon-color": COLOURS.info, "icon-halo-color": OUTLINE, "icon-halo-width": OUTLINE_WIDTH },
      } as LayerSpecification,
      opacity: { "icon-opacity": 1 },
    },
    {
      layer: {
        id: RECORD_LAYERS.liveCentres,
        type: "symbol",
        source: live,
        layout: {
          "icon-image": SQUARE_IMAGE,
          "icon-size": 0.45,
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: { "icon-color": OUTLINE },
      } as LayerSpecification,
      opacity: { "icon-opacity": 1 },
    },
    {
      layer: {
        id: RECORD_LAYERS.selectionLine,
        type: "line",
        source: selection,
        filter: ["all", ["!=", ["geometry-type"], "Point"], ["!=", ["get", "imprecise"], true]],
        layout: { "line-join": "miter" },
        paint: { "line-color": COLOURS.accentStrong, "line-width": 2.5 },
      } as LayerSpecification,
      opacity: { "line-opacity": 1 },
    },
    {
      layer: {
        id: RECORD_LAYERS.selectionSquare,
        type: "line",
        source: selection,
        filter: ["==", ["get", "imprecise"], true],
        layout: { "line-join": "miter" },
        paint: { "line-color": COLOURS.accentStrong, "line-width": 2.5, "line-dasharray": [2.5, 2] },
      } as LayerSpecification,
      opacity: { "line-opacity": 1 },
    },
    {
      layer: {
        id: RECORD_LAYERS.selectionPoint,
        type: "symbol",
        source: selection,
        filter: ["==", ["geometry-type"], "Point"],
        layout: {
          "icon-image": SQUARE_IMAGE,
          "icon-size": 1.6,
          "icon-allow-overlap": true,
          "icon-ignore-placement": true,
        },
        paint: { "icon-color": "rgba(0, 0, 0, 0)", "icon-halo-color": COLOURS.accentStrong, "icon-halo-width": 2.5 },
      } as LayerSpecification,
      opacity: { "icon-opacity": 1 },
    },
  );
  return layers;
}

/**
 * Scan coverage: one-kilometre squares shaded by how many people have looked
 * at them. The source is GeoJSON with a `count` on each square.
 */
export function coverageLayers(source: string): OverlayLayer[] {
  const count: ExpressionSpecification = ["coalesce", ["get", "count"], 0];
  return [
    {
      layer: {
        id: "coverage-fill",
        type: "fill",
        source,
        paint: { "fill-color": COLOURS.accent, "fill-antialias": false },
      },
      opacity: { "fill-opacity": ["interpolate", ["linear"], count, 0, 0, 1, 0.14, 5, 0.3, 20, 0.45] },
    },
    {
      layer: {
        id: "coverage-line",
        type: "line",
        source,
        paint: { "line-color": COLOURS.accent, "line-width": 0.75 },
      },
      opacity: { "line-opacity": 0.5 },
    },
  ];
}
