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
    ...ring("findings-ruled-out", ruledOut, 3, ruledOutColour, 1.5, true),
    ...ring("findings-known", known, ringRadius, colour, 2.5),
    {
      layer: circle("findings-points", points, {
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
 * Heritage records: small squares coloured by category, so they can never be
 * mistaken for findings, which are round.
 */
export function recordsLayers(meta: Meta, source: string): OverlayLayer[] {
  const colour = matchOn(
    "category",
    meta.vocab.record_categories.map((category) => [category.id, category.colour]),
    COLOURS.textMuted,
  );
  return [
    {
      layer: {
        id: "records-squares",
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
  ];
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
