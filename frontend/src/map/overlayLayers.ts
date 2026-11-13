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

/**
 * From this coarseness up a record's position is a square, not a spot, and
 * the map draws the square. It is the same threshold as a record's own page.
 */
export const SQUARE_PRECISION_M = 1000;

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

/**
 * The layers that draw an exact finding's line, and an area's edge, which a
 * tap or click picks by (Decision 0031). An area's inside is drawn too, but
 * never picked, so what lies inside it stays in reach.
 */
export const FINDING_SHAPE_LAYERS = {
  areaFills: "findings-area-fills",
  areaEdges: "findings-area-edges",
  lines: "findings-lines",
  ruledOut: "findings-shapes-ruled-out",
} as const;

/** States that are not drawn as ordinary filled circles. */
const SPECIAL_STATES = ["known", "ruled_out", "withdrawn"];

const STATE: ExpressionSpecification = ["coalesce", ["get", "state"], "open"];
const IS_POINT: ExpressionSpecification = ["==", ["geometry-type"], "Point"];
/** An obscured finding's square. An exact area is a polygon too, and is told apart by having no `square`. */
const IS_SQUARE: ExpressionSpecification = ["all", ["==", ["geometry-type"], "Polygon"], ["has", "square"]];
const IS_LINE: ExpressionSpecification = ["==", ["get", "shape"], "line"];
const IS_AREA: ExpressionSpecification = ["==", ["get", "shape"], "area"];
/** Drawn as they are, not as the ruled-out ones behind their switch, nor withdrawn ones. */
const LIVE: ExpressionSpecification = ["!", ["in", STATE, ["literal", ["ruled_out", "withdrawn"]]]];

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
 * An exact finding with a line is that line in its tier colour over the
 * same dark casing as the markers, with round joins. An area is its edge in
 * the tier colour over the faintest fill, so the terrain inside stays
 * readable, as record outlines are. Known findings' shapes are thinner, and
 * ruled-out ones grey behind the ruled-out switch, as the markers are. Every
 * shape finding keeps its marker at its anchor, drawn above all the shapes.
 *
 * `source` is the GeoJSON built by `findingsMapData`: points for exact
 * positions, lines and areas for exact shapes, and polygons for the squares
 * of obscured ones.
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

  function shapeLayer(id: string, type: "line" | "fill", filter: FilterSpecification, paint: Record<string, unknown>) {
    const layout = type === "line" ? { "line-join": "round", "line-cap": "round" } : undefined;
    return { id, type, source, filter, ...(layout ? { layout } : {}), paint } as LayerSpecification;
  }

  const isKnown: ExpressionSpecification = ["==", STATE, "known"];
  const lineWidth: ExpressionSpecification = ["case", isKnown, 1.5, 2.5];
  const edgeWidth: ExpressionSpecification = ["case", isKnown, 1.25, 2];
  const casing = (width: ExpressionSpecification): ExpressionSpecification =>
    ["+", width, OUTLINE_WIDTH * 2] as unknown as ExpressionSpecification;
  const lines: FilterSpecification = ["all", IS_LINE, LIVE];
  const areas: FilterSpecification = ["all", IS_AREA, LIVE];
  const ruledOutShapes: FilterSpecification = ["all", ["has", "shape"], ["==", STATE, "ruled_out"]];

  const shapes: OverlayLayer[] = [
    {
      layer: shapeLayer(FINDING_SHAPE_LAYERS.areaFills, "fill", areas, {
        "fill-color": colour,
        "fill-antialias": false,
      }),
      opacity: { "fill-opacity": 0.04 },
    },
    {
      layer: shapeLayer(`${FINDING_SHAPE_LAYERS.areaEdges}-casing`, "line", areas, {
        "line-color": OUTLINE,
        "line-width": casing(edgeWidth),
      }),
      opacity: { "line-opacity": 0.75 },
    },
    {
      layer: shapeLayer(FINDING_SHAPE_LAYERS.areaEdges, "line", areas, {
        "line-color": colour,
        "line-width": edgeWidth,
      }),
      opacity: { "line-opacity": 1 },
    },
    {
      layer: shapeLayer(`${FINDING_SHAPE_LAYERS.lines}-casing`, "line", lines, {
        "line-color": OUTLINE,
        "line-width": casing(lineWidth),
      }),
      opacity: { "line-opacity": 0.9 },
    },
    {
      layer: shapeLayer(FINDING_SHAPE_LAYERS.lines, "line", lines, { "line-color": colour, "line-width": lineWidth }),
      opacity: { "line-opacity": 1 },
    },
    {
      layer: shapeLayer(FINDING_SHAPE_LAYERS.ruledOut, "line", ruledOutShapes, {
        "line-color": ruledOutColour,
        "line-width": 1.5,
      }),
      opacity: { "line-opacity": 0.9 },
      ruledOutOnly: true,
    },
  ];

  return [
    ...shapes,
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
  fills: "records-fills",
  outlines: "records-outlines",
  squares: "records-squares",
  /** Records a tile places only to a square, drawn as that square from a GeoJSON source the records feature fills. */
  imprecise: "records-imprecise",
  impreciseFills: "records-imprecise-fills",
  counts: "records-counts",
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

/** The GeoJSON source of squares for the records in view that are placed only to a square. */
export function recordsImpreciseSourceId(source: string): string {
  return `${source}-imprecise`;
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
  // A record with an outline is drawn as its outline alone, so the ground inside it stays in sight.
  [RECORD_LAYERS.fills]: ["in", ["geometry-type"], ["literal", ["Polygon", "MultiPolygon"]]],
  [RECORD_LAYERS.outlines]: ["!=", ["geometry-type"], "Point"],
  // A record placed only to a kilometre square or coarser is drawn as its square instead, never as a spot.
  [RECORD_LAYERS.squares]: [
    "all",
    ["in", ["geometry-type"], ["literal", ["Point", "MultiPoint"]]],
    ["<", ["coalesce", ["get", "precision_m"], 0], SQUARE_PRECISION_M],
  ],
};

/**
 * Records with an outline are drawn from this zoom. Further out most are a
 * few pixels across, and Historic England's aerial mapping alone has half a
 * million of them: drawn from zoom 12 they netted the terrain over and cut
 * the frame rate while panning by two thirds. Their points' squares and the
 * counts still show where records are.
 */
export const OUTLINE_MINZOOM = 15;

/**
 * From this zoom every record that is a point has its square. Further out
 * they are thinned. It is where outlines appear too.
 */
export const SQUARES_ALL_FROM_ZOOM = OUTLINE_MINZOOM;

/** Outlines are a hairline when they first appear and thicken as their shapes become readable. */
const OUTLINE_WIDTH_BY_ZOOM: ExpressionSpecification = ["interpolate", ["linear"], ["zoom"], 15, 0.6, 17, 1.2];

/** The counts' glyphs. They must exist on the glyph server named by the street-map overlay. */
const COUNT_FONT = ["Noto Sans Bold"];

/**
 * Heritage records: small squares coloured by category, so they can never be
 * mistaken for findings, which are round. Only a record that is a point
 * gets a square. One with an outline is that outline alone, a thin line in
 * its category's colour over the faintest fill, so it can still be clicked
 * without hiding the bank or ditch it marks. Where a tile carries counts,
 * each is a square numbered when the map has glyphs. Counts never overlap:
 * where two would touch, the bigger one is drawn, so a zoomed-out view
 * shows a scatter of counts over terrain, not a carpet.
 *
 * Records from a live source are the same squares, hollow, because they
 * have no category and were never stored here. The record whose page is
 * open is ringed in the accent colour. A record whose position is only known
 * to a square, whether on its page or in a tile, is drawn as that square,
 * dashed, never as a point.
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
  const imprecise = recordsImpreciseSourceId(source);

  const layers: OverlayLayer[] = [
    {
      layer: {
        id: RECORD_LAYERS.fills,
        type: "fill",
        source,
        minzoom: OUTLINE_MINZOOM,
        "source-layer": RECORDS_SOURCE_LAYER,
        filter: RECORD_BASE_FILTERS[RECORD_LAYERS.fills],
        paint: { "fill-color": colour, "fill-antialias": false },
      } as LayerSpecification,
      opacity: { "fill-opacity": 0.02 },
    },
    {
      layer: {
        id: RECORD_LAYERS.outlines,
        type: "line",
        source,
        minzoom: OUTLINE_MINZOOM,
        "source-layer": RECORDS_SOURCE_LAYER,
        filter: RECORD_BASE_FILTERS[RECORD_LAYERS.outlines],
        paint: { "line-color": colour, "line-width": OUTLINE_WIDTH_BY_ZOOM },
      } as LayerSpecification,
      opacity: { "line-opacity": 0.6 },
    },
    {
      layer: {
        id: RECORD_LAYERS.counts,
        type: "symbol",
        source,
        "source-layer": RECORD_COUNTS_SOURCE_LAYER,
        layout: {
          "icon-image": SQUARE_IMAGE,
          // From about 11 px across for a handful to 20 px for thousands, so the number fits inside.
          "icon-size": ["interpolate", ["linear"], ["log10", count], 0, 1.4, 1, 1.7, 2, 2.1, 3, 2.7],
          // Counts keep apart, with room between them. Where two would touch, the bigger is placed first.
          "icon-allow-overlap": false,
          "icon-padding": 6,
          "symbol-sort-key": ["-", 0, count],
          ...(hasGlyphs
            ? {
                // A cell holding one record needs no number on it.
                "text-field": [
                  "case",
                  ["<=", count, 1],
                  "",
                  [">=", count, 1000],
                  ["concat", ["to-string", ["/", ["round", ["/", count, 100]], 10]], "k"],
                  ["to-string", count],
                ],
                "text-font": COUNT_FONT,
                "text-size": 11,
                "text-allow-overlap": true,
                "text-ignore-placement": true,
              }
            : {}),
        },
        paint: {
          "icon-color": colour,
          "icon-halo-color": OUTLINE,
          "icon-halo-width": OUTLINE_WIDTH,
          ...(hasGlyphs ? { "text-color": COLOURS.text, "text-halo-color": OUTLINE, "text-halo-width": 1.5 } : {}),
        },
      } as LayerSpecification,
      opacity: hasGlyphs ? { "icon-opacity": 0.7, "text-opacity": 1 } : { "icon-opacity": 0.7 },
    },
  ];
  layers.push(
    {
      layer: {
        id: RECORD_LAYERS.squares,
        type: "symbol",
        source,
        "source-layer": RECORDS_SOURCE_LAYER,
        filter: RECORD_BASE_FILTERS[RECORD_LAYERS.squares],
        layout: {
          "icon-image": SQUARE_IMAGE,
          "icon-size": ["interpolate", ["linear"], ["zoom"], 8, 0.6, 14, 1, 18, 1.3],
          // Further out than SQUARES_ALL_FROM_ZOOM a village's listed buildings
          // would merge into one block over the earthworks round it, so there
          // squares keep apart, with a gap between them. A square must take
          // its place for the next to keep clear of it, so there they take
          // part in placement. Those left out come back as the map zooms in.
          "icon-allow-overlap": ["step", ["zoom"], false, SQUARES_ALL_FROM_ZOOM, true],
          "icon-ignore-placement": ["step", ["zoom"], false, SQUARES_ALL_FROM_ZOOM, true],
          "icon-padding": ["interpolate", ["linear"], ["zoom"], 12, 10, 14, 6, SQUARES_ALL_FROM_ZOOM, 2],
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
      // The faintest fill, so a square can be clicked anywhere inside it.
      layer: {
        id: RECORD_LAYERS.impreciseFills,
        type: "fill",
        source: imprecise,
        paint: { "fill-color": colour, "fill-antialias": false },
      } as LayerSpecification,
      opacity: { "fill-opacity": 0.02 },
    },
    {
      // Dashed, as an obscured finding's square is: a place known only to that square.
      layer: {
        id: RECORD_LAYERS.imprecise,
        type: "line",
        source: imprecise,
        layout: { "line-join": "miter" },
        paint: { "line-color": colour, "line-width": 1.5, "line-dasharray": [3, 2] },
      } as LayerSpecification,
      opacity: { "line-opacity": 0.85 },
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
 * at them. The source is GeoJSON with `scans` on each square (`GET
 * /squares/coverage`). The shading stays light, so the terrain under it is
 * still the thing to look at, and from zoom 12, when a square is big enough
 * to hold it, the count is written in it where the map has glyphs, so the
 * number never rests on the shade alone.
 */
export function coverageLayers(source: string, hasGlyphs = false): OverlayLayer[] {
  const scans: ExpressionSpecification = ["coalesce", ["get", "scans"], ["get", "count"], 0];
  const layers: OverlayLayer[] = [
    {
      layer: {
        id: "coverage-fill",
        type: "fill",
        source,
        paint: { "fill-color": COLOURS.accent, "fill-antialias": false },
      },
      opacity: { "fill-opacity": ["interpolate", ["linear"], scans, 0, 0, 1, 0.1, 3, 0.17, 10, 0.25] },
    },
    {
      layer: {
        id: "coverage-line",
        type: "line",
        source,
        paint: { "line-color": COLOURS.accent, "line-width": 0.75 },
      },
      opacity: { "line-opacity": 0.45 },
    },
  ];
  if (hasGlyphs) {
    layers.push({
      layer: {
        id: "coverage-count",
        type: "symbol",
        source,
        minzoom: 12,
        layout: {
          "text-field": ["to-string", scans],
          "text-font": COUNT_FONT,
          "text-size": 12,
          "text-allow-overlap": true,
          "text-ignore-placement": true,
        },
        paint: { "text-color": COLOURS.text, "text-halo-color": OUTLINE, "text-halo-width": 1.5 },
      },
      opacity: { "text-opacity": 0.85 },
    });
  }
  return layers;
}
