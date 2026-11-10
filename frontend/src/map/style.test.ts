// @vitest-environment node
import { validateStyleMin } from "@maplibre/maplibre-gl-style-spec";
import type { LayerSpecification, StyleSpecification, TerrainSpecification } from "maplibre-gl";
import { describe, expect, it, vi } from "vitest";
import type { Meta } from "../api/meta.js";
import { metaFixture } from "../test/fixtures/meta.js";
import { TIER_COLOURS } from "../ui/tokens.js";
import { LIMITS } from "./permalink.js";
import { defaultsFromMeta, overlayTroubleKey } from "./store.js";
import {
  absoluteUrl,
  applyMapState,
  applyTerrain,
  buildStyle,
  DEM_SOURCE,
  DEM_TERRAIN_SOURCE,
  dynamicProperties,
  HILLSHADE_DEM_SCALE,
  hillshadeExaggerationParam,
  MapStyleError,
  overlaySourceId,
  RAKING_BASE_LAYER,
  RAKING_LAYER,
  rakingBaseGrey,
  type StyleState,
  type StyleTarget,
  terrainChange,
  viewLayerId,
  viewSourceId,
  visibleAttributions,
} from "./style.js";

const ORIGIN = "https://fieldclub.test";
const OPTIONS = { origin: ORIGIN };

/** The contract's own example paths, to exercise root-relative URLs. */
const contractMeta: Meta = {
  ...metaFixture,
  layers: {
    ...metaFixture.layers,
    views: [
      {
        id: "composite",
        title: "Composite",
        description: "",
        group: "lidar",
        type: "raster",
        tiles: ["/tiles/lidar/composite/{z}/{x}/{y}.png"],
        tile_size: 512,
        minzoom: 7,
        maxzoom: 16,
        attribution: "LIDAR © Environment Agency",
        bounds: null,
        default: true,
      },
      {
        id: "raking",
        title: "Raking light",
        description: "",
        group: "lidar",
        type: "raking",
        attribution: "Elevation © Environment Agency",
      },
    ],
    dem: {
      tiles: ["/tiles/dem/{z}/{x}/{y}.png"],
      tile_size: 512,
      encoding: "terrarium",
      minzoom: 7,
      maxzoom: 16,
      attribution: "Elevation © Environment Agency",
    },
  },
};

function stateFor(meta: Meta, overrides: Partial<StyleState> = {}): StyleState {
  const defaults = defaultsFromMeta(meta);
  return {
    sun: defaults.sun,
    hillshadeExaggeration: defaults.hillshadeExaggeration,
    terrain: defaults.terrain,
    overlays: defaults.overlays,
    showRuledOut: false,
    failing: {},
    ...overrides,
  };
}

/** A layer with its property bags typed loosely, for reading in assertions. */
interface LooseLayer {
  id: string;
  type: string;
  source?: string;
  "source-layer"?: string;
  filter?: unknown;
  layout: Record<string, unknown>;
  paint: Record<string, unknown>;
}

function rawLayer(style: StyleSpecification, id: string): LayerSpecification {
  const found = style.layers.find((candidate) => candidate.id === id);
  if (!found) throw new Error(`No layer "${id}" in the style`);
  return found;
}

function layer(style: StyleSpecification, id: string): LooseLayer {
  return { layout: {}, paint: {}, ...rawLayer(style, id) } as unknown as LooseLayer;
}

function visible(style: StyleSpecification, id: string): boolean {
  return layer(style, id).layout?.visibility !== "none";
}

describe("buildStyle", () => {
  it("produces a style MapLibre accepts, for every view", () => {
    for (const meta of [metaFixture, contractMeta]) {
      for (const view of meta.layers.views) {
        const style = buildStyle(meta, stateFor(meta), view.id, OPTIONS);
        expect(validateStyleMin(style), view.id).toEqual([]);
      }
    }
  });

  it("stays valid with 3D on, ruled-out findings shown and overlays faded", () => {
    const base = stateFor(metaFixture);
    const overlays = Object.fromEntries(Object.keys(base.overlays).map((id) => [id, { visible: true, opacity: 0.35 }]));
    const style = buildStyle(
      metaFixture,
      stateFor(metaFixture, { overlays, showRuledOut: true, terrain: { enabled: true, exaggeration: 2 } }),
      "raking",
      OPTIONS,
    );
    expect(validateStyleMin(style)).toEqual([]);
  });

  it("adds one raster source and layer per raster view and shows only the chosen one", () => {
    const style = buildStyle(metaFixture, stateFor(metaFixture), "slope", OPTIONS);
    const rasterViews = metaFixture.layers.views.filter((view) => view.type === "raster");
    expect(rasterViews.length).toBeGreaterThan(1);
    for (const view of rasterViews) {
      const source = style.sources[viewSourceId(view.id)];
      expect(source?.type, view.id).toBe("raster");
      const rasterLayer = layer(style, viewLayerId(view.id));
      expect(rasterLayer.type).toBe("raster");
      expect(rasterLayer.source).toBe(viewSourceId(view.id));
      expect(visible(style, viewLayerId(view.id)), view.id).toBe(view.id === "slope");
    }
    expect(style.sources[viewSourceId("raking")]).toBeUndefined();
    expect(visible(style, RAKING_LAYER)).toBe(false);
    expect(visible(style, RAKING_BASE_LAYER)).toBe(false);
  });

  it("carries tile size, zoom range, bounds and attribution into raster sources", () => {
    const style = buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    expect(style.sources[viewSourceId("composite")]).toMatchObject({
      type: "raster",
      tileSize: 512,
      minzoom: 10,
      maxzoom: 16,
      bounds: [-7.11, 49.85, 2.09, 55.88],
    });
    const osm = style.sources[viewSourceId("osm_standard")] as Record<string, unknown>;
    expect(osm.tileSize).toBe(256);
    expect("bounds" in osm).toBe(false);
  });

  it("makes root-relative tile paths absolute and leaves templates alone", () => {
    const style = buildStyle(contractMeta, stateFor(contractMeta), "composite", OPTIONS);
    expect(style.sources[viewSourceId("composite")]).toMatchObject({
      tiles: ["https://fieldclub.test/tiles/lidar/composite/{z}/{x}/{y}.png"],
    });
    expect(style.sources[DEM_SOURCE]).toMatchObject({ tiles: ["https://fieldclub.test/tiles/dem/{z}/{x}/{y}.png"] });
    expect(style.sources[overlaySourceId("records")]).toMatchObject({
      type: "vector",
      tiles: ["https://fieldclub.test/tiles/records/{z}/{x}/{y}.mvt"],
    });
  });

  it("fills findings from the API, not from tiles, even if the catalogue still lists some", () => {
    const withTiles = {
      ...metaFixture,
      layers: {
        ...metaFixture.layers,
        overlays: metaFixture.layers.overlays.map((overlay) =>
          overlay.type === "findings" ? { ...overlay, tiles: ["/tiles/findings/{z}/{x}/{y}.mvt"] } : overlay,
        ),
      },
    } as Meta;
    const style = buildStyle(withTiles, stateFor(withTiles), "composite", OPTIONS);
    const findings = style.sources[overlaySourceId("findings")];
    expect(findings).toEqual({ type: "geojson", data: { type: "FeatureCollection", features: [] } });
    for (const layer of style.layers.filter((candidate) => candidate.id.startsWith("findings-"))) {
      expect((layer as { source?: string }).source, layer.id).toBe(overlaySourceId("findings"));
    }
  });

  it("builds the elevation source as Terrarium raster-dem, with a twin for terrain", () => {
    const style = buildStyle(contractMeta, stateFor(contractMeta), "composite", OPTIONS);
    for (const id of [DEM_SOURCE, DEM_TERRAIN_SOURCE]) {
      expect(style.sources[id]).toMatchObject({
        type: "raster-dem",
        tiles: ["https://fieldclub.test/tiles/dem/{z}/{x}/{y}.png"],
        tileSize: 512,
        minzoom: 7,
        maxzoom: 16,
      });
    }
    // 3D terrain reads true metres.
    expect(style.sources[DEM_TERRAIN_SOURCE]).toMatchObject({ encoding: "terrarium" });
    expect(style.terrain).toBeUndefined();
  });

  it("feeds the hillshade Terrarium heights scaled up, for finer slopes", () => {
    const style = buildStyle(contractMeta, stateFor(contractMeta), "composite", OPTIONS);
    const dem = style.sources[DEM_SOURCE] as unknown as Record<string, number | string>;
    expect(dem.encoding).toBe("custom");
    // Terrarium is red * 256 + green + blue / 256 - 32768.
    expect(dem.redFactor).toBe(256 * HILLSHADE_DEM_SCALE);
    expect(dem.greenFactor).toBe(HILLSHADE_DEM_SCALE);
    expect(dem.blueFactor).toBe(HILLSHADE_DEM_SCALE / 256);
    expect(dem.baseShift).toBe(32768 * HILLSHADE_DEM_SCALE);
    // A pixel of (128, 10, 128) is 10.5 m, and must decode to that times the scale.
    const decoded =
      128 * (dem.redFactor as number) +
      10 * (dem.greenFactor as number) +
      128 * (dem.blueFactor as number) -
      (dem.baseShift as number);
    expect(decoded).toBeCloseTo(10.5 * HILLSHADE_DEM_SCALE, 9);
  });

  it("scales Mapbox-encoded elevation the same way", () => {
    const meta: Meta = {
      ...contractMeta,
      layers: { ...contractMeta.layers, dem: { ...contractMeta.layers.dem, encoding: "mapbox" } },
    };
    const style = buildStyle(meta, stateFor(meta), "composite", OPTIONS);
    const dem = style.sources[DEM_SOURCE] as unknown as Record<string, number | string>;
    // Mapbox is (red * 65536 + green * 256 + blue) * 0.1 - 10000, so (1, 134, 160) is 0 m.
    const decoded =
      1 * (dem.redFactor as number) +
      134 * (dem.greenFactor as number) +
      160 * (dem.blueFactor as number) -
      (dem.baseShift as number);
    expect(decoded).toBeCloseTo(0, 6);
    expect(style.sources[DEM_TERRAIN_SOURCE]).toMatchObject({ encoding: "mapbox" });
    expect(validateStyleMin(style)).toEqual([]);
  });

  it("applies changes at once, with no easing", () => {
    const style = buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    expect(style.transition).toEqual({ duration: 0, delay: 0 });
  });

  it("draws the raking view as a hillshade of the dem source, lit by the sun state", () => {
    const state = stateFor(metaFixture, { sun: { azimuth: 120, altitude: 18 }, hillshadeExaggeration: 4 });
    const style = buildStyle(metaFixture, state, "raking", OPTIONS);
    const raking = layer(style, RAKING_LAYER);
    expect(raking.type).toBe("hillshade");
    expect(raking.source).toBe(DEM_SOURCE);
    expect(raking.paint).toMatchObject({
      "hillshade-method": "basic",
      "hillshade-illumination-anchor": "map",
      "hillshade-illumination-direction": 120,
      "hillshade-illumination-altitude": 18,
      // A vertical exaggeration of 4, over the DEM scale, halved for MapLibre's own doubling.
      "hillshade-exaggeration": 4 / (2 * HILLSHADE_DEM_SCALE),
    });
    // The backdrop is lighter than mid-grey for a low sun, to hold level ground at mid-grey.
    expect(layer(style, RAKING_BASE_LAYER).paint["background-color"]).toBe("rgb(206, 206, 206)");
    expect(visible(style, RAKING_LAYER)).toBe(true);
    expect(visible(style, RAKING_BASE_LAYER)).toBe(true);
    for (const view of metaFixture.layers.views) {
      if (view.type === "raster") expect(visible(style, viewLayerId(view.id))).toBe(false);
    }
  });

  it("keeps the illumination direction inside the range the specification allows", () => {
    const state = stateFor(metaFixture, { sun: { azimuth: 359.8, altitude: 30 } });
    const style = buildStyle(metaFixture, state, "raking", OPTIONS);
    expect(layer(style, RAKING_LAYER).paint["hillshade-illumination-direction"]).toBe(359);
    expect(validateStyleMin(style)).toEqual([]);
  });

  it("turns terrain on against its own source", () => {
    const state = stateFor(metaFixture, { terrain: { enabled: true, exaggeration: 2.5 } });
    const style = buildStyle(metaFixture, state, "composite", OPTIONS);
    expect(style.terrain).toEqual({ source: DEM_TERRAIN_SOURCE, exaggeration: 2.5 });
    expect(layer(style, RAKING_LAYER).source).not.toBe(DEM_TERRAIN_SOURCE);
  });

  it("styles the OpenMapTiles overlay from its TileJSON and glyphs", () => {
    const style = buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    expect(style.glyphs).toBe("https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf");
    expect(style.sources[overlaySourceId("osm")]).toEqual({
      type: "vector",
      url: "https://tiles.openfreemap.org/planet",
    });
    const osmLayerIds = style.layers.filter((l) => l.id.startsWith("osm-")).map((l) => l.id);
    for (const id of [
      "osm-road-major-casing",
      "osm-road-major",
      "osm-road-path",
      "osm-waterway",
      "osm-boundary",
      "osm-road-label",
      "osm-place-town",
    ]) {
      expect(osmLayerIds).toContain(id);
    }
    // Casings sit under the lines they outline, and labels on top of both.
    expect(osmLayerIds.indexOf("osm-road-major-casing")).toBeLessThan(osmLayerIds.indexOf("osm-road-path"));
    expect(osmLayerIds.indexOf("osm-road-major")).toBeLessThan(osmLayerIds.indexOf("osm-road-label"));
    expect(layer(style, "osm-road-major").paint["line-opacity"]).toBeCloseTo(0.92 * 0.8, 3);
    expect(layer(style, "osm-place-town").paint["text-opacity"]).toBe(0.8);
    expect(layer(style, "osm-place-town").paint["text-halo-width"]).toBeGreaterThan(1);
    const sourceLayers = new Set(
      style.layers.filter((l) => l.id.startsWith("osm-")).map((l) => (l as Record<string, unknown>)["source-layer"]),
    );
    expect([...sourceLayers].sort()).toEqual([
      "boundary",
      "place",
      "transportation",
      "transportation_name",
      "water",
      "water_name",
      "waterway",
    ]);
  });

  it("draws overlays above every base view, with findings on top", () => {
    const style = buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    const ids = style.layers.map((l) => l.id);
    const lastBase = Math.max(
      ids.indexOf(RAKING_LAYER),
      ...ids.filter((id) => id.startsWith("view-")).map((id) => ids.indexOf(id)),
    );
    expect(ids.indexOf("coverage-fill")).toBeGreaterThan(lastBase);
    expect(ids.indexOf("osm-water-area")).toBeGreaterThan(ids.indexOf("coverage-line"));
    expect(ids.indexOf("records-squares")).toBeGreaterThan(ids.indexOf("osm-place-town"));
    expect(ids.indexOf("findings-points")).toBeGreaterThan(ids.indexOf("records-squares"));
    expect(ids.at(-1)).toBe("findings-points");
  });

  it("styles findings by tier and state, with obscured ones as squares", () => {
    const style = buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    const points = layer(style, "findings-points");
    expect(points.type).toBe("circle");
    expect(points["source-layer"]).toBeUndefined();
    const colour = points.paint["circle-color"] as unknown[];
    expect(colour.slice(0, 2)).toEqual(["match", ["get", "tier"]]);
    for (const tier of metaFixture.vocab.tiers) {
      const at = colour.indexOf(tier.id);
      expect(at, tier.id).toBeGreaterThan(0);
      expect(colour[at + 1]).toBe(TIER_COLOURS[tier.id]);
    }
    expect(points.paint["circle-stroke-width"]).toBe(1.5);
    const radius = points.paint["circle-radius"] as unknown[];
    const radii = metaFixture.vocab.tiers.map((tier) => radius[radius.indexOf(tier.id) + 1] as number);
    expect(radii).toEqual([...radii].sort((a, b) => a - b));
    expect(new Set(radii).size).toBe(radii.length);
    // Points are only ever exact positions: obscured findings arrive as polygons. See findingsData.ts.
    expect(JSON.stringify(points.filter)).toContain('["==",["geometry-type"],"Point"]');
    expect(JSON.stringify(points.filter)).toContain('"known"');

    const known = layer(style, "findings-known");
    expect(known.paint["circle-color"]).toBe("rgba(0, 0, 0, 0)");
    expect(known.paint["circle-stroke-width"]).toBeGreaterThan(0);

    const obscured = layer(style, "findings-obscured");
    expect(obscured.type).toBe("line");
    expect(obscured.source).toBe(overlaySourceId("findings"));
    expect(JSON.stringify(obscured.filter)).toContain('["==",["geometry-type"],"Polygon"]');
    expect(obscured.paint["line-dasharray"]).toBeDefined();
  });

  it("hides ruled-out findings until asked", () => {
    const hidden = buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    expect(visible(hidden, "findings-ruled-out")).toBe(false);
    expect(visible(hidden, "findings-ruled-out-casing")).toBe(false);
    expect(visible(hidden, "findings-points")).toBe(true);
    const shown = buildStyle(metaFixture, stateFor(metaFixture, { showRuledOut: true }), "composite", OPTIONS);
    expect(visible(shown, "findings-ruled-out")).toBe(true);
    expect(visible(shown, "findings-obscured-ruled-out")).toBe(true);
  });

  it("draws records as squares coloured by category from the vocabulary", () => {
    const style = buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    const records = layer(style, "records-squares");
    expect(records.type).toBe("symbol");
    expect(records["source-layer"]).toBe("records");
    const colour = records.paint["icon-color"] as unknown[];
    expect(colour.slice(0, 2)).toEqual(["match", ["get", "category"]]);
    for (const category of metaFixture.vocab.record_categories) {
      expect(colour[colour.indexOf(category.id) + 1]).toBe(category.colour);
    }
  });

  it("follows overlay visibility, opacity and availability", () => {
    const base = stateFor(metaFixture);
    const overlays = {
      ...base.overlays,
      osm: { visible: false, opacity: 0.5 },
      findings: { visible: true, opacity: 0.25 },
      coverage: { visible: true, opacity: 1 },
    };
    const style = buildStyle(
      metaFixture,
      stateFor(metaFixture, { overlays, failing: { [overlayTroubleKey("records")]: true } }),
      "composite",
      OPTIONS,
    );
    expect(visible(style, "osm-road-major")).toBe(false);
    expect(visible(style, "findings-points")).toBe(true);
    expect(layer(style, "findings-points").paint["circle-opacity"]).toBe(0.25);
    expect(layer(style, "findings-points").paint["circle-stroke-opacity"]).toBe(0.25);
    expect(visible(style, "coverage-fill")).toBe(true);
    expect(visible(style, "records-squares")).toBe(false);
  });

  it("does not share objects between styles", () => {
    const state = stateFor(metaFixture);
    const first = buildStyle(metaFixture, state, "composite", OPTIONS);
    const second = buildStyle(metaFixture, state, "raking", OPTIONS);
    expect(first.sources).not.toBe(second.sources);
    expect(rawLayer(first, "findings-points")).not.toBe(rawLayer(second, "findings-points"));
    expect(visible(first, viewLayerId("composite"))).toBe(true);
    expect(visible(second, viewLayerId("composite"))).toBe(false);
  });

  it("refuses a view the catalogue does not have", () => {
    expect(() => buildStyle(metaFixture, stateFor(metaFixture), "nope", OPTIONS)).toThrow(MapStyleError);
  });
});

describe("applyMapState", () => {
  function fakeMap(style: StyleSpecification) {
    const ids = new Set(style.layers.map((l) => l.id));
    let terrain: TerrainSpecification | null = style.terrain ?? null;
    const layout = vi.fn();
    const paint = vi.fn();
    const setTerrain = vi.fn((next: TerrainSpecification | null) => {
      terrain = next;
    });
    const map: StyleTarget = {
      getLayer: (id) => (ids.has(id) ? { id } : undefined),
      setLayoutProperty: layout,
      setPaintProperty: paint,
      getTerrain: () => terrain,
      setTerrain,
    };
    return { map, layout, paint, setTerrain };
  }

  it("sends only what changed when it is told what the map was last given", () => {
    const before = stateFor(metaFixture);
    const { map, layout, paint } = fakeMap(buildStyle(metaFixture, before, "raking", OPTIONS));
    const applied = new Map<string, unknown>();
    applyMapState(map, metaFixture, before, "raking", { ...OPTIONS, applied });
    const all = layout.mock.calls.length + paint.mock.calls.length;
    expect(all).toBe(dynamicProperties(metaFixture, before, "raking", OPTIONS).length);

    layout.mockClear();
    paint.mockClear();
    applyMapState(map, metaFixture, before, "raking", { ...OPTIONS, applied });
    expect(layout).not.toHaveBeenCalled();
    expect(paint).not.toHaveBeenCalled();

    const overlays = { ...before.overlays, osm: { visible: true, opacity: 0.4 } };
    applyMapState(map, metaFixture, { ...before, sun: { ...before.sun, azimuth: 90 }, overlays }, "raking", {
      ...OPTIONS,
      applied,
    });
    expect(layout).not.toHaveBeenCalled();
    const names = new Set(paint.mock.calls.map(([, name]) => name as string));
    expect(names.has("hillshade-illumination-direction")).toBe(true);
    expect(names.has("hillshade-illumination-altitude")).toBe(false);
    // Each OpenStreetMap layer's opacity, and nothing of any other overlay.
    expect(paint.mock.calls.every(([id]) => id === "raking" || String(id).startsWith("osm-"))).toBe(true);
  });

  it("sets exactly the properties a fresh style would have", () => {
    const before = stateFor(metaFixture);
    const after = stateFor(metaFixture, { sun: { azimuth: 90, altitude: 12 }, hillshadeExaggeration: 8 });
    const { map, layout, paint } = fakeMap(buildStyle(metaFixture, before, "composite", OPTIONS));
    applyMapState(map, metaFixture, after, "raking", OPTIONS);

    const fresh = buildStyle(metaFixture, after, "raking", OPTIONS);
    for (const [id, name, value] of layout.mock.calls) {
      expect(layer(fresh, id).layout[name], `${id} ${name}`).toEqual(value);
    }
    for (const [id, name, value] of paint.mock.calls) {
      expect(layer(fresh, id).paint[name], `${id} ${name}`).toEqual(value);
    }
    expect(paint).toHaveBeenCalledWith(RAKING_LAYER, "hillshade-illumination-direction", 90);
    expect(paint).toHaveBeenCalledWith(RAKING_LAYER, "hillshade-illumination-altitude", 12);
    expect(paint).toHaveBeenCalledWith(RAKING_LAYER, "hillshade-exaggeration", 0.5);
    expect(paint).toHaveBeenCalledWith(RAKING_BASE_LAYER, "background-color", "rgb(255, 255, 255)");
    expect(layout).toHaveBeenCalledWith(RAKING_LAYER, "visibility", "visible");
    expect(layout).toHaveBeenCalledWith(viewLayerId("composite"), "visibility", "none");
    expect(layout.mock.calls.length + paint.mock.calls.length).toBe(
      dynamicProperties(metaFixture, after, "raking", OPTIONS).length,
    );
  });

  it("switches terrain on, updates its exaggeration and switches it off", () => {
    const { map, setTerrain } = fakeMap(buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS));
    applyMapState(map, metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    expect(setTerrain).not.toHaveBeenCalled();

    const on = stateFor(metaFixture, { terrain: { enabled: true, exaggeration: 1.5 } });
    applyMapState(map, metaFixture, on, "composite", OPTIONS);
    expect(setTerrain).toHaveBeenLastCalledWith({ source: DEM_TERRAIN_SOURCE, exaggeration: 1.5 });
    applyMapState(map, metaFixture, on, "composite", OPTIONS);
    expect(setTerrain).toHaveBeenCalledTimes(1);

    // MapLibre frees a terrain's buffers only when terrain is cleared, so a
    // new exaggeration clears the old terrain before setting the new one.
    const steeper = stateFor(metaFixture, { terrain: { enabled: true, exaggeration: 3 } });
    applyMapState(map, metaFixture, steeper, "composite", OPTIONS);
    expect(setTerrain.mock.calls.slice(1)).toEqual([[null], [{ source: DEM_TERRAIN_SOURCE, exaggeration: 3 }]]);

    applyMapState(map, metaFixture, stateFor(metaFixture), "composite", OPTIONS);
    expect(setTerrain).toHaveBeenLastCalledWith(null);
    expect(setTerrain).toHaveBeenCalledTimes(4);
  });

  it("says what kind of terrain change a state calls for, and can leave terrain to the caller", () => {
    const { map, setTerrain } = fakeMap(buildStyle(metaFixture, stateFor(metaFixture), "composite", OPTIONS));
    const flat = stateFor(metaFixture);
    const on = stateFor(metaFixture, { terrain: { enabled: true, exaggeration: 1.5 } });
    const steeper = stateFor(metaFixture, { terrain: { enabled: true, exaggeration: 3 } });

    expect(terrainChange(map, flat)).toBe("none");
    expect(terrainChange(map, on)).toBe("switch");
    applyMapState(map, metaFixture, on, "composite", { ...OPTIONS, terrain: "leave" });
    expect(setTerrain).not.toHaveBeenCalled();

    applyTerrain(map, on);
    expect(terrainChange(map, on)).toBe("none");
    expect(terrainChange(map, steeper)).toBe("rebuild");
    expect(terrainChange(map, flat)).toBe("switch");
    applyTerrain(map, on);
    expect(setTerrain).toHaveBeenCalledTimes(1);
  });

  it("fails loudly when the map is missing a layer", () => {
    const { map } = fakeMap({ version: 8, sources: {}, layers: [] });
    expect(() => applyMapState(map, metaFixture, stateFor(metaFixture), "composite", OPTIONS)).toThrow(MapStyleError);
  });
});

describe("visibleAttributions", () => {
  it("lists the views, visible overlays and elevation data in use, once each", () => {
    const state = stateFor(metaFixture);
    const osmOverlayAttribution = metaFixture.layers.overlays.find((overlay) => overlay.id === "osm")?.attribution;
    expect(osmOverlayAttribution).toContain("OpenMapTiles");
    const recordsCredit = metaFixture.sources[0]?.attribution;
    expect(recordsCredit).toContain("Historic England");
    const flat = visibleAttributions(metaFixture, state, ["composite", null]);
    expect(flat).toEqual([
      "© Environment Agency copyright and/or database right 2022. All rights reserved.",
      osmOverlayAttribution,
      recordsCredit,
    ]);

    const compared = visibleAttributions(metaFixture, state, ["composite", "osm_standard"]);
    expect(compared).toContain('© <a href="https://www.openstreetmap.org/copyright">OpenStreetMap</a> contributors');

    const raking = visibleAttributions(metaFixture, state, ["raking", "slope"]);
    expect(raking.filter((line) => line.startsWith("Elevation"))).toHaveLength(1);
    expect(raking.filter((line) => line.includes("Environment Agency copyright"))).toHaveLength(1);

    const threeD = visibleAttributions(metaFixture, { ...state, terrain: { enabled: true, exaggeration: 1.5 } }, [
      "composite",
    ]);
    expect(threeD.some((line) => line.startsWith("Elevation"))).toBe(true);

    const noOsm = visibleAttributions(
      metaFixture,
      { ...state, overlays: { ...state.overlays, osm: { visible: false, opacity: 1 } } },
      ["composite"],
    );
    expect(noOsm).toHaveLength(2);
  });

  it("credits every source behind the heritage records while they are showing, and only then", () => {
    const meta: Meta = {
      ...metaFixture,
      sources: [
        ...metaFixture.sources,
        {
          ...(metaFixture.sources[0] as Meta["sources"][number]),
          key: "pas",
          attribution: "© Portable Antiquities Scheme",
        },
        // Two sources from one publisher are credited once.
        { ...(metaFixture.sources[0] as Meta["sources"][number]), key: "nhle-listed" },
      ],
    };
    const state = stateFor(meta);
    const shown = visibleAttributions(meta, state, ["composite"]);
    expect(shown.filter((line) => line.includes("Historic England"))).toHaveLength(1);
    expect(shown).toContain("© Portable Antiquities Scheme");

    const hidden = visibleAttributions(
      meta,
      { ...state, overlays: { ...state.overlays, records: { visible: false, opacity: 1 } } },
      ["composite"],
    );
    expect(hidden.some((line) => line.includes("Historic England"))).toBe(false);
    expect(hidden).not.toContain("© Portable Antiquities Scheme");

    const failing = visibleAttributions(meta, { ...state, failing: { [overlayTroubleKey("records")]: true } }, [
      "composite",
    ]);
    expect(failing.some((line) => line.includes("Historic England"))).toBe(false);
  });
});

describe("raking light shading", () => {
  /**
   * What MapLibre's "basic" hillshade draws for a given shade over a given
   * backdrop: black at strength 1 - 2s below a half, white at 2s - 1 above.
   */
  function drawn(shade: number, backdrop: number): number {
    return shade <= 0.5 ? backdrop * (2 * shade) : backdrop + (1 - backdrop) * (2 * shade - 1);
  }

  it("holds level ground at mid-grey across the useful range of sun heights", () => {
    for (const altitude of [15, 18, 25, 30, 35, 45, 48]) {
      const flat = Math.sin((altitude * Math.PI) / 180);
      expect(drawn(flat, rakingBaseGrey(altitude)), `altitude ${altitude}`).toBeCloseTo(0.5, 6);
    }
  });

  it("is continuous at 30 degrees, where the shade of level ground crosses a half", () => {
    expect(rakingBaseGrey(30)).toBeCloseTo(0.5, 9);
    expect(rakingBaseGrey(29.999)).toBeCloseTo(rakingBaseGrey(30.001), 3);
  });

  it("stays a valid grey at the extremes", () => {
    expect(rakingBaseGrey(5)).toBe(1);
    expect(rakingBaseGrey(0)).toBe(1);
    expect(rakingBaseGrey(70)).toBe(0);
    expect(rakingBaseGrey(90)).toBe(0);
  });

  it("gives more contrast for a lower sun", () => {
    const slopeOfResponse = (altitude: number): number => {
      const flat = Math.sin((altitude * Math.PI) / 180);
      const backdrop = rakingBaseGrey(altitude);
      return (drawn(flat + 0.01, backdrop) - drawn(flat - 0.01, backdrop)) / 0.02;
    };
    expect(slopeOfResponse(18)).toBeGreaterThan(slopeOfResponse(25));
    expect(slopeOfResponse(25)).toBeGreaterThan(1);
  });

  it("turns a vertical exaggeration into MapLibre's setting", () => {
    expect(hillshadeExaggerationParam(1)).toBeCloseTo(1 / (2 * HILLSHADE_DEM_SCALE), 12);
    expect(hillshadeExaggerationParam(LIMITS.hillshadeExaggeration.max)).toBeLessThanOrEqual(1);
    expect(hillshadeExaggerationParam(LIMITS.hillshadeExaggeration.min)).toBeGreaterThan(0);
    expect(hillshadeExaggerationParam(1000)).toBe(1);
    expect(hillshadeExaggerationParam(-1)).toBe(0);
  });
});

describe("absoluteUrl", () => {
  it("prefixes root-relative paths only", () => {
    expect(absoluteUrl("/tiles/dem/{z}/{x}/{y}.png", "http://localhost:5173")).toBe(
      "http://localhost:5173/tiles/dem/{z}/{x}/{y}.png",
    );
    expect(absoluteUrl("/a", "http://localhost:5173/")).toBe("http://localhost:5173/a");
    expect(absoluteUrl("https://example.org/{z}/{x}/{y}.png", ORIGIN)).toBe("https://example.org/{z}/{x}/{y}.png");
    expect(() => absoluteUrl("tiles/{z}.png", ORIGIN)).toThrow(MapStyleError);
  });
});
