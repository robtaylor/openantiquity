import type {
  ExpressionSpecification,
  LayerSpecification,
  SourceSpecification,
  StyleSpecification,
  TerrainSpecification,
} from "maplibre-gl";
import {
  type DemLayer,
  findOverlay,
  findView,
  type Meta,
  type Overlay,
  type OverlayType,
  type RasterView,
} from "../api/meta.js";
import { clamp } from "../ui/math.js";
import { COLOURS } from "../ui/tokens.js";
import { osmLayers } from "./osmLayers.js";
import {
  coverageLayers,
  findingsLayers,
  type OverlayLayer,
  recordsLayers,
  recordsLiveSourceId,
  recordsSelectionSourceId,
} from "./overlayLayers.js";
import type { OverlayState, SunState, TerrainState } from "./permalink.js";
import { overlayTroubleKey } from "./trouble.js";

export class MapStyleError extends Error {
  constructor(message: string) {
    super(message);
    this.name = "MapStyleError";
  }
}

/** The part of the map state that the style depends on. */
export interface StyleState {
  sun: SunState;
  hillshadeExaggeration: number;
  terrain: TerrainState;
  overlays: Record<string, OverlayState>;
  showRuledOut: boolean;
  /** Sources not loading, by trouble key. An overlay is switched off while its key is set. */
  failing: Record<string, boolean>;
}

/** Every field of `StyleState`, for telling whether a store change could restyle the map. */
const STYLE_FIELDS: Record<keyof StyleState, true> = {
  sun: true,
  hillshadeExaggeration: true,
  terrain: true,
  overlays: true,
  showRuledOut: true,
  failing: true,
};

export const STYLE_KEYS = Object.keys(STYLE_FIELDS) as ReadonlyArray<keyof StyleState>;

/** True when the overlay is switched on and not switched off for failing to load. */
export function overlayShown(state: Pick<StyleState, "overlays" | "failing">, overlayId: string): boolean {
  return state.overlays[overlayId]?.visible === true && !state.failing[overlayTroubleKey(overlayId)];
}

/** True when the elevation data is in use: 3D is on, or a pane shows the raking view. */
export function usesElevation(meta: Meta, terrainEnabled: boolean, viewIds: ReadonlyArray<string | null>): boolean {
  return terrainEnabled || viewIds.some((id) => id !== null && findView(meta, id)?.type === "raking");
}

export interface StyleOptions {
  /** Prefix for root-relative tile paths. Defaults to the page origin. */
  origin?: string;
}

export const BACKGROUND_LAYER = "background";
export const RAKING_BASE_LAYER = "raking-base";
export const RAKING_LAYER = "raking";
export const DEM_SOURCE = "dem";
/**
 * A second source over the same elevation tiles, used only for 3D terrain.
 * MapLibre loads a terrain source at half resolution and warns when a
 * hillshade layer shares it, so raking light keeps its own source.
 */
export const DEM_TERRAIN_SOURCE = "dem-terrain";
/**
 * MapLibre's hillshade works out slopes in a first pass and keeps them in an
 * 8-bit texture spanning -4 to 4, in units of rise over run times the cosine
 * of the latitude. In Britain one step is then nearly 3 degrees of slope,
 * which posterises gentle ground, exactly where faint earthworks are. Feeding
 * the hillshade elevations multiplied by this factor makes the steps that
 * much finer. The layer's exaggeration is divided by the same factor to
 * compensate.
 *
 * The relief strength a person sets is a true vertical exaggeration only
 * where the elevation tiles on screen are zoom 15 or deeper. For shallower
 * tiles MapLibre's first pass steepens every slope again, by
 * 2^(0.3 x (15 - tile zoom)): about 1.9 times at tile zoom 12 and 2.8 times
 * at tile zoom 10. That keeps relief readable when zoomed out, and it is left
 * alone. A finding's `view_state` stores the zoom along with the
 * exaggeration, so the picture it restores is still the one the finder saw.
 *
 * The price of the finer steps is an earlier ceiling. Slopes steeper than
 * 4 / (factor x cos(latitude) x MapLibre's steepening) all shade alike. At
 * 51 degrees north that is 80% at tile zoom 15 and deeper, about 43% at tile
 * zoom 12 and 28% at tile zoom 10.
 */
export const HILLSHADE_DEM_SCALE = 8;
/** Records tiles are overzoomed past this level, not refetched. */
const MARKER_TILE_MAXZOOM = 14;

function emptyGeoJson(): SourceSpecification {
  return { type: "geojson", data: { type: "FeatureCollection", features: [] } };
}

export function viewSourceId(viewId: string): string {
  return `view-${viewId}`;
}

export function viewLayerId(viewId: string): string {
  return `view-${viewId}`;
}

export function overlaySourceId(overlayId: string): string {
  return `overlay-${overlayId}`;
}

/**
 * MapLibre fetches vector tiles from a worker, where a root-relative path has
 * nothing to resolve against. Template braces must survive, so this joins
 * strings and does not go through `URL`.
 */
export function absoluteUrl(url: string, origin: string): string {
  if (/^[a-z][a-z0-9+.-]*:/i.test(url) || url.startsWith("//")) return url;
  if (!url.startsWith("/")) throw new MapStyleError(`Tile URL "${url}" is neither absolute nor root-relative`);
  return `${origin.replace(/\/$/, "")}${url}`;
}

function resolveOrigin(options: StyleOptions): string {
  if (options.origin !== undefined) return options.origin;
  if (typeof window === "undefined") throw new MapStyleError("buildStyle needs an origin outside the browser");
  return window.location.origin;
}

function rasterSource(view: RasterView, origin: string): SourceSpecification {
  return {
    type: "raster",
    tiles: view.tiles.map((url) => absoluteUrl(url, origin)),
    tileSize: view.tile_size,
    minzoom: view.minzoom,
    maxzoom: view.maxzoom,
    attribution: view.attribution,
    ...(view.bounds ? { bounds: view.bounds } : {}),
  };
}

/** How each encoding turns a pixel into metres: red, green and blue factors, then a shift to subtract. */
const DEM_UNPACK: Record<DemLayer["encoding"], readonly [number, number, number, number]> = {
  terrarium: [256, 1, 1 / 256, 32768],
  mapbox: [6553.6, 25.6, 0.1, 10000],
};

/**
 * The elevation source. With `scale` 1 it is declared by its own encoding and
 * reads true metres, for 3D terrain. Any other scale declares the same tiles
 * as a custom encoding whose heights come out multiplied by that amount.
 */
function demSource(dem: DemLayer, origin: string, scale = 1): SourceSpecification {
  const base = {
    type: "raster-dem" as const,
    tiles: dem.tiles.map((url) => absoluteUrl(url, origin)),
    tileSize: dem.tile_size,
    minzoom: dem.minzoom,
    maxzoom: dem.maxzoom,
    attribution: dem.attribution,
  };
  if (scale === 1) return { ...base, encoding: dem.encoding };
  const [red, green, blue, shift] = DEM_UNPACK[dem.encoding];
  return {
    ...base,
    encoding: "custom",
    redFactor: red * scale,
    greenFactor: green * scale,
    blueFactor: blue * scale,
    baseShift: shift * scale,
  };
}

/**
 * The grey to paint under the raking hillshade so that level ground comes
 * out mid-grey whatever the sun's height.
 *
 * The "basic" method shades each pixel from 0 to 1, then paints black over
 * the map where the shade is under a half and white where it is over, more
 * strongly the further from a half. Level ground has a shade of
 * sin(altitude), so on a fixed backdrop a low sun turns the whole scene dark.
 * Choosing the backdrop by altitude cancels that: a lower sun then raises
 * contrast and leaves the overall brightness alone. Below about 14.5
 * degrees no backdrop is light enough, and above about 48.6 none is dark
 * enough, so the scene drifts there: dark with burnt-out slopes when low,
 * which is why `LIMITS.sunAltitude` stops the sun at 15.
 */
export function rakingBaseGrey(altitudeDegrees: number): number {
  const flat = Math.sin((clamp(altitudeDegrees, 0, 90) * Math.PI) / 180);
  const grey = flat <= 0.5 ? 0.25 / Math.max(flat, 1e-6) : (1.5 - 2 * flat) / (2 - 2 * flat);
  return clamp(grey, 0, 1);
}

function greyColour(value: number): string {
  const channel = Math.round(value * 255);
  return `rgb(${channel}, ${channel}, ${channel})`;
}

/** The layer's own exaggeration setting for a wanted vertical exaggeration. */
export function hillshadeExaggerationParam(verticalExaggeration: number): number {
  // MapLibre doubles the setting before applying it to the slope.
  return clamp(verticalExaggeration / (2 * HILLSHADE_DEM_SCALE), 0, 1);
}

interface OverlayParts {
  sources: Record<string, SourceSpecification>;
  layers: OverlayLayer[];
}

function overlayParts(meta: Meta, overlay: Overlay, origin: string): OverlayParts {
  const source = overlaySourceId(overlay.id);
  switch (overlay.type) {
    case "openmaptiles":
      return {
        sources: { [source]: { type: "vector", url: absoluteUrl(overlay.tilejson, origin) } },
        layers: osmLayers(source),
      };
    case "records":
      return {
        sources: {
          [source]: {
            type: "vector",
            tiles: overlay.tiles.map((url) => absoluteUrl(url, origin)),
            maxzoom: MARKER_TILE_MAXZOOM,
          },
          // Filled by the records feature: what live sources sent this browser, and the open record.
          [recordsLiveSourceId(source)]: emptyGeoJson(),
          [recordsSelectionSourceId(source)]: emptyGeoJson(),
        },
        layers: recordsLayers(meta, source),
      };
    case "findings":
      // What a viewer may see depends on who they are, so findings come from
      // the API and not from cacheable tiles. The pane fills this source.
      return { sources: { [source]: emptyGeoJson() }, layers: findingsLayers(meta, source) };
    case "coverage":
      return {
        sources: { [source]: emptyGeoJson() },
        layers: coverageLayers(source),
      };
  }
}

/**
 * Drawing order by overlay type, bottom first, whatever order the catalogue
 * lists them in. Coverage shading sits under the map lines, and findings are
 * always on top.
 */
const STACKING: Record<OverlayType, number> = { coverage: 0, openmaptiles: 1, records: 2, findings: 3 };

interface Catalogue {
  sources: Record<string, SourceSpecification>;
  /** Layers in drawing order, each tagged with the overlay that owns it. */
  overlayLayers: Array<OverlayLayer & { overlayId: string }>;
}

const catalogues = new WeakMap<Meta, Map<string, Catalogue>>();

/** Sources and overlay layers for a catalogue. Built once per meta document. */
function catalogueFor(meta: Meta, origin: string): Catalogue {
  let byOrigin = catalogues.get(meta);
  if (!byOrigin) {
    byOrigin = new Map();
    catalogues.set(meta, byOrigin);
  }
  const cached = byOrigin.get(origin);
  if (cached) return cached;

  const sources: Record<string, SourceSpecification> = {};
  for (const view of meta.layers.views) {
    if (view.type === "raster") sources[viewSourceId(view.id)] = rasterSource(view, origin);
  }
  sources[DEM_SOURCE] = demSource(meta.layers.dem, origin, HILLSHADE_DEM_SCALE);
  sources[DEM_TERRAIN_SOURCE] = demSource(meta.layers.dem, origin);

  const overlayLayers: Catalogue["overlayLayers"] = [];
  const stacked = [...meta.layers.overlays].sort((a, b) => STACKING[a.type] - STACKING[b.type]);
  for (const overlay of stacked) {
    const parts = overlayParts(meta, overlay, origin);
    for (const [id, source] of Object.entries(parts.sources)) {
      if (id in sources) throw new MapStyleError(`Two map sources are both called "${id}"`);
      sources[id] = source;
    }
    for (const layer of parts.layers) overlayLayers.push({ ...layer, overlayId: overlay.id });
  }

  const catalogue = { sources, overlayLayers };
  byOrigin.set(origin, catalogue);
  return catalogue;
}

/** A layout or paint property whose value follows the map state. */
export interface DynamicProperty {
  layer: string;
  kind: "layout" | "paint";
  name: string;
  value: unknown;
}

function scaleOpacity(base: number | ExpressionSpecification, factor: number): number | ExpressionSpecification {
  if (typeof base === "number") return Math.round(base * factor * 1000) / 1000;
  return ["*", base, factor] as unknown as ExpressionSpecification;
}

function visibility(visible: boolean): "visible" | "none" {
  return visible ? "visible" : "none";
}

/**
 * Every property that changes with the map state, for a pane showing
 * `viewId`. `buildStyle` bakes these into a new style and `applyMapState`
 * sets them on a live map, so the two cannot disagree.
 */
export function dynamicProperties(
  meta: Meta,
  state: StyleState,
  viewId: string,
  options: StyleOptions = {},
): DynamicProperty[] {
  const view = findView(meta, viewId);
  if (!view) throw new MapStyleError(`Unknown view "${viewId}"`);
  const props: DynamicProperty[] = [];

  for (const candidate of meta.layers.views) {
    if (candidate.type !== "raster") continue;
    props.push({
      layer: viewLayerId(candidate.id),
      kind: "layout",
      name: "visibility",
      value: visibility(candidate.id === viewId),
    });
  }

  const raking = view.type === "raking";
  props.push(
    { layer: RAKING_BASE_LAYER, kind: "layout", name: "visibility", value: visibility(raking) },
    { layer: RAKING_LAYER, kind: "layout", name: "visibility", value: visibility(raking) },
    {
      layer: RAKING_LAYER,
      kind: "paint",
      name: "hillshade-illumination-direction",
      // The style specification caps this at 359.
      value: clamp(state.sun.azimuth, 0, 359),
    },
    { layer: RAKING_LAYER, kind: "paint", name: "hillshade-illumination-altitude", value: state.sun.altitude },
    {
      layer: RAKING_LAYER,
      kind: "paint",
      name: "hillshade-exaggeration",
      value: hillshadeExaggerationParam(state.hillshadeExaggeration),
    },
    {
      layer: RAKING_BASE_LAYER,
      kind: "paint",
      name: "background-color",
      value: greyColour(rakingBaseGrey(state.sun.altitude)),
    },
  );

  for (const entry of catalogueFor(meta, resolveOrigin(options)).overlayLayers) {
    const overlay = state.overlays[entry.overlayId];
    const shown = overlayShown(state, entry.overlayId) && (!entry.ruledOutOnly || state.showRuledOut);
    props.push({ layer: entry.layer.id, kind: "layout", name: "visibility", value: visibility(shown) });
    for (const [name, base] of Object.entries(entry.opacity)) {
      props.push({ layer: entry.layer.id, kind: "paint", name, value: scaleOpacity(base, overlay?.opacity ?? 1) });
    }
  }

  return props;
}

function terrainFor(state: StyleState): TerrainSpecification | null {
  return state.terrain.enabled ? { source: DEM_TERRAIN_SOURCE, exaggeration: state.terrain.exaggeration } : null;
}

/**
 * Build the MapLibre style for one pane from the layer catalogue in /meta.
 * Every raster view gets a source and a layer, but only `viewId` is visible,
 * and a hidden layer loads no tiles.
 */
export function buildStyle(
  meta: Meta,
  state: StyleState,
  viewId: string,
  options: StyleOptions = {},
): StyleSpecification {
  const origin = resolveOrigin(options);
  const catalogue = catalogueFor(meta, origin);

  const layers: LayerSpecification[] = [
    { id: BACKGROUND_LAYER, type: "background", paint: { "background-color": COLOURS.bg } },
    // The "basic" hillshade paints white where a slope is lit and black where
    // it is shaded, with transparency in between. This grey backdrop turns
    // that into a greyscale image. Its shade follows the sun: see rakingBaseGrey.
    { id: RAKING_BASE_LAYER, type: "background", paint: {} },
    {
      id: RAKING_LAYER,
      type: "hillshade",
      source: DEM_SOURCE,
      paint: {
        // Of MapLibre's single-light methods, "basic" is the one that models
        // the sun's altitude as well as its direction, which is what raking
        // light needs. "standard" and "igor" ignore altitude altogether.
        "hillshade-method": "basic",
        "hillshade-illumination-anchor": "map",
        "hillshade-highlight-color": "#ffffff",
        "hillshade-shadow-color": "#000000",
      },
    },
  ];
  for (const view of meta.layers.views) {
    if (view.type !== "raster") continue;
    layers.push({ id: viewLayerId(view.id), type: "raster", source: viewSourceId(view.id) });
  }
  // Each layer is copied so the cached catalogue is never mutated.
  for (const entry of catalogue.overlayLayers) layers.push(structuredClone(entry.layer));

  const byId = new Map(layers.map((layer) => [layer.id, layer as LayerSpecification & Record<string, unknown>]));
  if (byId.size !== layers.length) throw new MapStyleError("Two map layers share an id");
  for (const prop of dynamicProperties(meta, state, viewId, options)) {
    const layer = byId.get(prop.layer);
    if (!layer) throw new MapStyleError(`Dynamic property for missing layer "${prop.layer}"`);
    const bag = (layer[prop.kind] ?? {}) as Record<string, unknown>;
    bag[prop.name] = prop.value;
    layer[prop.kind] = bag;
  }

  const glyphs = findOverlay(meta, "openmaptiles")?.glyphs;
  const terrain = terrainFor(state);

  return {
    version: 8,
    name: "Field Club",
    // Sliders and the sun dial drive paint properties directly, so changes must not ease in.
    transition: { duration: 0, delay: 0 },
    ...(glyphs ? { glyphs: absoluteUrl(glyphs, origin) } : {}),
    // Copied so that neither pane can alter the cached catalogue.
    sources: structuredClone(catalogue.sources),
    layers,
    ...(terrain ? { terrain } : {}),
    sky: {
      "sky-color": COLOURS.surface,
      "horizon-color": COLOURS.raised,
      "fog-color": COLOURS.bg,
      "sky-horizon-blend": 0.6,
      "horizon-fog-blend": 0.6,
      "fog-ground-blend": 0.4,
    },
  };
}

/** The slice of a MapLibre map that `applyMapState` drives. */
export interface StyleTarget {
  getLayer(id: string): unknown;
  setLayoutProperty(layer: string, name: string, value: unknown): unknown;
  setPaintProperty(layer: string, name: string, value: unknown): unknown;
  getTerrain(): TerrainSpecification | null;
  setTerrain(options: TerrainSpecification | null): unknown;
}

/**
 * What a live map's 3D terrain needs to match the state. "switch" turns it
 * on or off. "rebuild" replaces terrain that is already on, which is costly
 * enough that a caller following a slider should wait for it to settle.
 */
export type TerrainChange = "none" | "switch" | "rebuild";

export function terrainChange(map: Pick<StyleTarget, "getTerrain">, state: StyleState): TerrainChange {
  const wanted = terrainFor(state);
  const current = map.getTerrain();
  if (!wanted) return current ? "switch" : "none";
  if (!current) return "switch";
  return current.source !== wanted.source || current.exaggeration !== wanted.exaggeration ? "rebuild" : "none";
}

/**
 * Bring a live map's 3D terrain into line with the state.
 *
 * Terrain is always cleared before it is replaced. MapLibre 5 freed a
 * terrain's framebuffers, textures and depth buffers only when terrain was
 * set to null, and setting a new specification over an old one stranded the
 * old set: 18 framebuffers, 21 textures and 18 renderbuffers per rebuild,
 * counted in a browser. MapLibre 6.1.0 destroys the old terrain itself, and
 * the same count on 6.17.0 stays flat either way. Clearing first is kept
 * because it also releases the render-to-texture pool at once, where a
 * replacement leaves that until the map is at rest.
 */
export function applyTerrain(map: Pick<StyleTarget, "getTerrain" | "setTerrain">, state: StyleState): void {
  const change = terrainChange(map, state);
  if (change === "none") return;
  if (map.getTerrain()) map.setTerrain(null);
  const wanted = terrainFor(state);
  if (wanted) map.setTerrain(wanted);
}

export interface ApplyOptions extends StyleOptions {
  /** "leave" skips the 3D terrain, for a caller that applies it on its own schedule. Defaults to "apply". */
  terrain?: "apply" | "leave";
  /**
   * The values this map was last given, by layer, kind and name. When passed,
   * a property whose value has not changed is not sent again, and the map is
   * spared comparing it. Keep one per map, for the life of its style.
   */
  applied?: Map<string, unknown>;
}

function sameValue(a: unknown, b: unknown): boolean {
  if (a === b) return true;
  // The only objects here are small expressions, such as ["*", base, factor].
  return typeof a === "object" && typeof b === "object" && JSON.stringify(a) === JSON.stringify(b);
}

/**
 * Bring a live map into line with the state. MapLibre ignores a property set
 * to the value it already has, so this can be called on every change.
 */
export function applyMapState(
  map: StyleTarget,
  meta: Meta,
  state: StyleState,
  viewId: string,
  options: ApplyOptions = {},
): void {
  const { applied } = options;
  for (const prop of dynamicProperties(meta, state, viewId, options)) {
    const key = `${prop.layer}|${prop.kind}|${prop.name}`;
    if (applied?.has(key) && sameValue(applied.get(key), prop.value)) continue;
    if (!map.getLayer(prop.layer)) throw new MapStyleError(`The map has no layer "${prop.layer}"`);
    if (prop.kind === "layout") map.setLayoutProperty(prop.layer, prop.name, prop.value);
    else map.setPaintProperty(prop.layer, prop.name, prop.value);
    applied?.set(key, prop.value);
  }
  if (options.terrain !== "leave") applyTerrain(map, state);
}

/**
 * Attribution lines for everything currently drawn, without repeats: the
 * main and comparison views, the elevation data when it is in use, each
 * visible overlay, and every source behind the heritage records while they
 * are showing. The records overlay has no attribution of its own in the
 * catalogue. Its credits are the `sources` list in /meta: those named in
 * `recordSources`, the keys of the sources drawn on screen, or all of them
 * while that is not known.
 */
export function visibleAttributions(
  meta: Meta,
  state: Pick<StyleState, "overlays" | "terrain" | "failing">,
  viewIds: ReadonlyArray<string | null>,
  recordSources: readonly string[] | null = null,
): string[] {
  const lines: string[] = [];
  const add = (line: string | undefined): void => {
    const trimmed = line?.trim();
    if (trimmed && !lines.includes(trimmed)) lines.push(trimmed);
  };
  for (const id of viewIds) add(id === null ? undefined : findView(meta, id)?.attribution);
  if (usesElevation(meta, state.terrain.enabled, viewIds)) add(meta.layers.dem.attribution);
  for (const overlay of meta.layers.overlays) {
    if (!overlayShown(state, overlay.id)) continue;
    add(overlay.attribution);
    if (overlay.type === "records") {
      for (const source of meta.sources) {
        if (recordSources === null || recordSources.includes(source.key)) add(source.attribution);
      }
    }
  }
  return lines;
}
