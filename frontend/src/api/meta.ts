/**
 * Hand-written types for `GET /api/v1/meta`, following the shape in
 * docs/ARCHITECTURE.md, with a parser that checks a document at run time.
 * Keys keep the API's snake_case. `pnpm gen:api` generates `schema.d.ts` from
 * the backend and then checks, with `scripts/schema-compat.ts`, that what the
 * backend says it serves still fits these types.
 */

import { isFiniteNumber, isRecord, isStringArray } from "./guards.js";

export class MetaError extends Error {
  constructor(message: string) {
    super(`Unexpected /meta document: ${message}`);
    this.name = "MetaError";
  }
}

export type ViewGroup = "lidar" | "imagery" | "historic" | "map" | "geology";

export const VIEW_GROUPS: readonly ViewGroup[] = ["lidar", "imagery", "historic", "map", "geology"];

interface ViewBase {
  id: string;
  title: string;
  description: string;
  group: ViewGroup;
  attribution: string;
  default?: boolean;
}

/** A tiled image. */
export interface RasterView extends ViewBase {
  type: "raster";
  tiles: string[];
  tile_size: number;
  minzoom: number;
  maxzoom: number;
  /** West, south, east, north in degrees. Null or absent means no limit. */
  bounds?: [number, number, number, number] | null;
}

/** Drawn in the browser as a hillshade of the `dem` source. */
export interface RakingView extends ViewBase {
  type: "raking";
}

export type View = RasterView | RakingView;

export interface DemLayer {
  tiles: string[];
  tile_size: number;
  encoding: "terrarium" | "mapbox";
  minzoom: number;
  maxzoom: number;
  attribution: string;
}

interface OverlayBase {
  id: string;
  title: string;
  default_opacity?: number;
  attribution?: string;
}

/** An OpenMapTiles-schema vector source that the frontend styles itself. */
export interface OpenMapTilesOverlay extends OverlayBase {
  type: "openmaptiles";
  tilejson: string;
  glyphs: string;
}

export interface RecordsOverlay extends OverlayBase {
  type: "records";
  tiles: string[];
}

/**
 * Findings are fetched from `GET /findings?bbox=&format=geojson`, because what
 * a viewer may see depends on who they are. Any `tiles` the server still
 * lists are ignored.
 */
export interface FindingsOverlay extends OverlayBase {
  type: "findings";
}

export interface CoverageOverlay extends OverlayBase {
  type: "coverage";
}

export type Overlay = OpenMapTilesOverlay | RecordsOverlay | FindingsOverlay | CoverageOverlay;
export type OverlayType = Overlay["type"];

export interface MetaLayers {
  views: View[];
  dem: DemLayer;
  overlays: Overlay[];
  initial_view: { center: [number, number]; zoom: number };
}

export interface FeatureClass {
  id: string;
  label: string;
  hint: string;
  fish_term: string;
}

export interface Period {
  id: string;
  label: string;
  hint: string;
}

export interface EvidenceKind {
  id: string;
  label: string;
  strand: string;
  group: string;
  hint: string;
}

export interface Tier {
  id: string;
  label: string;
  description: string;
  base_score: number;
}

export interface FindingState {
  id: string;
  label: string;
  description: string;
}

export interface Check {
  id: string;
  question: string;
  hint: string;
}

export interface Explanation {
  id: string;
  label: string;
  hint: string;
}

export interface MentionKind {
  id: string;
  label: string;
}

export interface RecordCategory {
  id: string;
  label: string;
  colour: string;
}

export interface Vocab {
  feature_classes: FeatureClass[];
  periods: Period[];
  evidence_kinds: EvidenceKind[];
  tiers: Tier[];
  states: FindingState[];
  checks: Check[];
  explanations: Explanation[];
  mention_kinds: MentionKind[];
  record_categories: RecordCategory[];
}

export interface SourceSummary {
  key: string;
  name: string;
  publisher: string;
  licence: string;
  attribution: string;
  homepage: string | null;
  category: string;
  record_count: number | null;
}

/**
 * A way to sign in, such as Google or an emailed link. The server lists every
 * provider it knows, in display order. Only those with `enabled` set have
 * credentials and a working flow, and the sign-in sheet offers only those.
 */
export interface SignInProvider {
  id: string;
  label: string;
  enabled: boolean;
}

export interface Meta {
  app: { name: string; version: string; contribution_licence: string };
  /** Every provider, in the order the sign-in sheet shows them. Offer only the enabled ones. Saving anything needs an account. */
  auth: { providers: SignInProvider[] };
  vocab: Vocab;
  layers: MetaLayers;
  sources: SourceSummary[];
  notices: { field_visit: Record<string, string[]>; field_visit_16_17: string; sensitivity: string };
}

function check(condition: boolean, message: string): asserts condition {
  if (!condition) throw new MetaError(message);
}

function checkTiles(value: unknown, where: string): void {
  check(isStringArray(value) && value.length > 0, `${where} needs a non-empty "tiles" list`);
}

function checkZoomRange(layer: Record<string, unknown>, where: string): void {
  check(isFiniteNumber(layer.minzoom) && isFiniteNumber(layer.maxzoom), `${where} needs a numeric minzoom and maxzoom`);
  check(layer.minzoom >= 0 && layer.minzoom <= layer.maxzoom, `${where} has a zoom range that runs backwards`);
}

/** Named colours are letters only. Anything with other characters must be hex or a colour function. */
const COLOUR_PATTERN = /^(#(?:[0-9a-f]{3,4}|[0-9a-f]{6}|[0-9a-f]{8})|(?:rgb|hsl)a?\([^()]+\)|[a-z]+)$/i;

/**
 * Whether MapLibre will take this as a colour. It reads CSS hex, rgb() and
 * hsl() notations and the named colours. A name is taken on trust here, and
 * a misspelt one is caught when the map refuses the style.
 */
export function isColour(value: unknown): value is string {
  return typeof value === "string" && COLOUR_PATTERN.test(value.trim());
}

/**
 * Check the parts of the document the map cannot work without and return it
 * typed. The map is built entirely from `layers`, so a malformed catalogue
 * should fail here with a clear message, not as a blank canvas.
 */
export function parseMeta(value: unknown): Meta {
  check(isRecord(value), "not an object");
  const { app, auth, vocab, layers, sources, notices } = value;
  check(isRecord(app) && typeof app.name === "string", '"app.name" is missing');
  check(isRecord(auth) && Array.isArray(auth.providers), '"auth.providers" is missing');
  for (const provider of auth.providers as unknown[]) {
    check(
      isRecord(provider) &&
        typeof provider.id === "string" &&
        typeof provider.label === "string" &&
        typeof provider.enabled === "boolean",
      'each of "auth.providers" needs an id, a label and an enabled flag',
    );
  }
  check(isRecord(vocab), '"vocab" is missing');
  for (const key of [
    "feature_classes",
    "periods",
    "evidence_kinds",
    "tiers",
    "states",
    "checks",
    "explanations",
    "mention_kinds",
    "record_categories",
  ]) {
    check(Array.isArray(vocab[key]), `"vocab.${key}" is not a list`);
  }
  // Category colours go straight into the map style, which MapLibre refuses whole if one does not parse.
  for (const category of vocab.record_categories as unknown[]) {
    check(isRecord(category) && typeof category.id === "string", "a record category has no id");
    check(isColour(category.colour), `record category "${category.id}" has a colour the map cannot read`);
  }
  check(Array.isArray(sources), '"sources" is not a list');
  check(isRecord(notices), '"notices" is missing');
  check(typeof notices.field_visit_16_17 === "string", '"notices.field_visit_16_17" is missing');

  check(isRecord(layers), '"layers" is missing');
  const { views, dem, overlays, initial_view: initialView } = layers;
  check(Array.isArray(views) && views.length > 0, '"layers.views" is empty');
  const viewIds = new Set<string>();
  let rakingCount = 0;
  for (const view of views as unknown[]) {
    check(isRecord(view) && typeof view.id === "string" && view.id !== "", "a view has no id");
    const where = `view "${view.id}"`;
    check(!viewIds.has(view.id), `${where} appears twice`);
    viewIds.add(view.id);
    check(typeof view.title === "string", `${where} has no title`);
    check((VIEW_GROUPS as readonly unknown[]).includes(view.group), `${where} has unknown group "${view.group}"`);
    if (view.type === "raster") {
      checkTiles(view.tiles, where);
      check(isFiniteNumber(view.tile_size) && view.tile_size > 0, `${where} has no tile_size`);
      checkZoomRange(view, where);
      check(
        view.bounds === null ||
          view.bounds === undefined ||
          (Array.isArray(view.bounds) && view.bounds.length === 4 && view.bounds.every(isFiniteNumber)),
        `${where} has bounds that are not four numbers`,
      );
    } else {
      check(view.type === "raking", `${where} has unknown type "${view.type}"`);
      rakingCount += 1;
    }
  }
  check(rakingCount <= 1, "more than one raking view");

  check(isRecord(dem), '"layers.dem" is missing');
  checkTiles(dem.tiles, '"layers.dem"');
  check(isFiniteNumber(dem.tile_size) && dem.tile_size > 0, '"layers.dem" has no tile_size');
  checkZoomRange(dem, '"layers.dem"');
  check(dem.encoding === "terrarium" || dem.encoding === "mapbox", `unknown dem encoding "${dem.encoding}"`);

  check(Array.isArray(overlays), '"layers.overlays" is not a list');
  const overlayIds = new Set<string>();
  const overlayTypes = new Set<unknown>();
  for (const overlay of overlays as unknown[]) {
    check(isRecord(overlay) && typeof overlay.id === "string" && overlay.id !== "", "an overlay has no id");
    const where = `overlay "${overlay.id}"`;
    check(!overlayIds.has(overlay.id), `${where} appears twice`);
    overlayIds.add(overlay.id);
    check(typeof overlay.title === "string", `${where} has no title`);
    // Each kind of overlay is drawn by one fixed set of map layers, so the catalogue can hold one of each.
    check(!overlayTypes.has(overlay.type), `more than one overlay of type "${overlay.type}"`);
    overlayTypes.add(overlay.type);
    if (overlay.type === "openmaptiles") {
      check(typeof overlay.tilejson === "string", `${where} has no tilejson`);
      check(typeof overlay.glyphs === "string", `${where} has no glyphs`);
    } else if (overlay.type === "records") {
      checkTiles(overlay.tiles, where);
    } else {
      check(overlay.type === "findings" || overlay.type === "coverage", `${where} has unknown type "${overlay.type}"`);
    }
  }

  check(isRecord(initialView), '"layers.initial_view" is missing');
  const { center, zoom } = initialView;
  check(
    Array.isArray(center) && center.length === 2 && center.every(isFiniteNumber),
    '"layers.initial_view.center" is not [lon, lat]',
  );
  check(isFiniteNumber(zoom), '"layers.initial_view.zoom" is not a number');

  return value as unknown as Meta;
}

export function findView(meta: Meta, id: string): View | undefined {
  return meta.layers.views.find((view) => view.id === id);
}

/** A view's title for display, or its id when the catalogue does not have it. */
export function viewTitle(meta: Meta, id: string): string {
  return findView(meta, id)?.title ?? id;
}

/** The overlay of this type. `parseMeta` allows at most one of each. */
export function findOverlay<T extends OverlayType>(meta: Meta, type: T): Extract<Overlay, { type: T }> | undefined {
  return meta.layers.overlays.find((overlay): overlay is Extract<Overlay, { type: T }> => overlay.type === type);
}

/** The raking view. `parseMeta` allows at most one. */
export function rakingView(meta: Meta): RakingView | undefined {
  return meta.layers.views.find((view): view is RakingView => view.type === "raking");
}

export function defaultView(meta: Meta): View {
  const view = meta.layers.views.find((v) => v.default === true) ?? meta.layers.views[0];
  if (!view) throw new MetaError('"layers.views" is empty');
  return view;
}
