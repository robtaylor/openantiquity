import { describe, expect, it } from "vitest";
import { RECORD_LAYERS, recordsLiveSourceId, recordsSelectionSourceId } from "../../map/overlayLayers.js";
import { DEFAULT_SUN, DEFAULT_TERRAIN } from "../../map/store.js";
import { buildStyle, overlaySourceId } from "../../map/style.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { AVENUE_RECORD, CONTEXT_LINKS, FIND_RECORD } from "../../test/fixtures/records.js";
import { parseRecordId, recordsDownloadUrl } from "./api.js";
import { recordLayerFilter } from "./filters.js";
import { groupLinks } from "./OpenElsewherePanel.js";
import { elsewherePath } from "./paths.js";
import { precisionText, recordShape } from "./shape.js";
import { recordTarget, sourcesOf } from "./useRecordsOnMap.js";

describe("parseRecordId", () => {
  it("takes whole numbers from 1 up and nothing else", () => {
    expect(parseRecordId("42")).toBe(42);
    for (const bad of [undefined, "", "0", "-1", "1.5", "42abc", "1e3", " 42", "99999999999999999999"]) {
      expect(parseRecordId(bad), String(bad)).toBeNull();
    }
  });
});

describe("recordsDownloadUrl", () => {
  it("asks for the same search as GeoJSON, the backend's largest page", () => {
    const url = new URL(
      recordsDownloadUrl({
        q: " barrow ",
        sources: ["a", "b"],
        categories: ["find"],
        bbox: [-1.86, 51.42, -1.85, 51.43],
      }),
      "http://localhost",
    );
    expect(url.pathname).toBe("/api/v1/records/search");
    expect(Object.fromEntries(url.searchParams)).toEqual({
      q: "barrow",
      source: "a,b",
      category: "find",
      bbox: "-1.8600,51.4200,-1.8500,51.4300",
      limit: "200",
      format: "geojson",
    });
  });
});

describe("recordLayerFilter", () => {
  const known = ["nhle", "pas", "her"];

  it("leaves a layer without a base filter unfiltered while everything shows", () => {
    expect(recordLayerFilter(RECORD_LAYERS.squares, [], [], known)).toBeNull();
    expect(recordLayerFilter(RECORD_LAYERS.outlines, [], [], known)).toEqual(["!=", ["geometry-type"], "Point"]);
  });

  it("hides a record by its category and its one source", () => {
    expect(recordLayerFilter(RECORD_LAYERS.squares, ["find"], ["pas"], known)).toEqual([
      "all",
      ["!", ["in", ["get", "category"], ["literal", ["find"]]]],
      ["!", ["in", ["get", "source"], ["literal", ["pas"]]]],
    ]);
  });

  it("keeps a count while any source it counts is still on, matching whole keys only", () => {
    const filter = recordLayerFilter(RECORD_LAYERS.counts, [], ["pas"], known);
    expect(filter).toEqual([
      "any",
      ["in", ",nhle,", ["concat", ",", ["coalesce", ["get", "sources"], ""], ","]],
      ["in", ",her,", ["concat", ",", ["coalesce", ["get", "sources"], ""], ","]],
    ]);
  });

  it("hides every count when every source is off", () => {
    expect(recordLayerFilter(RECORD_LAYERS.counts, [], known, known)).toEqual(["==", 1, 0]);
  });
});

describe("recordShape", () => {
  it("draws an exact record as its own geometry, with its centre marked", () => {
    const shape = recordShape(AVENUE_RECORD);
    expect(shape.imprecise).toBe(false);
    expect(shape.collection.features.map((feature) => feature.geometry.type)).toEqual(["LineString", "Point"]);
  });

  it("draws a record published to a kilometre square as that grid square, never as a point", () => {
    const shape = recordShape(FIND_RECORD);
    expect(shape.imprecise).toBe(true);
    expect(shape.square).toMatch(/^SU\d{4}$/);
    expect(shape.collection.features).toHaveLength(1);
    const [only] = shape.collection.features;
    expect(only?.geometry.type).toBe("Polygon");
    expect(only?.properties.imprecise).toBe(true);
    expect(precisionText(FIND_RECORD.precision_m, shape.square)).toBe(
      `Published only to the one-kilometre square ${shape.square}, so the map shows the square, not a spot.`,
    );
  });

  it("draws a coarser record as a square of its own size", () => {
    const shape = recordShape({ ...FIND_RECORD, precision_m: 10_000 });
    expect(shape.square).toBeNull();
    const geometry = shape.collection.features[0]?.geometry;
    if (geometry?.type !== "Polygon") throw new Error("a coarse record is drawn as a polygon");
    const ring = geometry.coordinates[0] ?? [];
    const latSpan = Math.max(...ring.map((p) => p[1] ?? 0)) - Math.min(...ring.map((p) => p[1] ?? 0));
    expect(latSpan * 111_320).toBeCloseTo(10_000, -2);
  });

  it("falls back to the record's point when its geometry can't be drawn", () => {
    const shape = recordShape({ ...AVENUE_RECORD, geometry: { type: "Nonsense" } });
    expect(shape.collection.features).toEqual([
      {
        type: "Feature",
        geometry: { type: "Point", coordinates: [AVENUE_RECORD.lon, AVENUE_RECORD.lat] },
        properties: { imprecise: false },
      },
    ]);
  });

  it("says plainly how exact a position is", () => {
    expect(precisionText(null, null)).toBe("The source doesn't say how exact this position is.");
    expect(precisionText(25, null)).toBe("Exact to within about 25 m.");
    expect(precisionText(1, null)).toBe("Exact to about a metre.");
  });
});

describe("recordTarget", () => {
  const at = { lng: -1.85, lat: 51.43 };

  it("opens a record, zooms into a count and shows a live record, taking the topmost", () => {
    expect(recordTarget([{ layer: { id: RECORD_LAYERS.squares }, properties: { id: 7 }, id: undefined }], at)).toEqual({
      kind: "record",
      id: 7,
    });
    expect(recordTarget([{ layer: { id: RECORD_LAYERS.outlines }, properties: {}, id: 9 }], at)).toEqual({
      kind: "record",
      id: 9,
    });
    expect(
      recordTarget([{ layer: { id: RECORD_LAYERS.counts }, properties: { count: 5 }, id: undefined }], at),
    ).toEqual({
      kind: "count",
      ...at,
    });
    expect(
      recordTarget(
        [
          { layer: { id: RECORD_LAYERS.live }, properties: { source: "wilts", id: "MWI1" }, id: undefined },
          { layer: { id: RECORD_LAYERS.squares }, properties: { id: 7 }, id: undefined },
        ],
        at,
      ),
    ).toEqual({ kind: "live", source: "wilts", id: "MWI1" });
  });

  it("ignores features it can't open", () => {
    expect(recordTarget([], at)).toBeNull();
    expect(
      recordTarget([{ layer: { id: RECORD_LAYERS.squares }, properties: { id: "x" }, id: undefined }], at),
    ).toBeNull();
    expect(recordTarget([{ layer: { id: RECORD_LAYERS.selectionPoint }, properties: {}, id: 1 }], at)).toBeNull();
  });
});

describe("sourcesOf", () => {
  it("collects a record's source and every source a count names", () => {
    expect(
      sourcesOf([
        { properties: { source: "nhle" } },
        { properties: { sources: "her,pas" } },
        { properties: { sources: "" } },
      ]).sort(),
    ).toEqual(["her", "nhle", "pas"]);
  });
});

describe("groupLinks", () => {
  it("groups by coverage, most local first, and drops links that aren't web addresses", () => {
    const groups = groupLinks(CONTEXT_LINKS.items);
    expect(groups.map((group) => group.label)).toEqual(["England", "Great Britain", "The whole UK"]);
    expect(groups.flatMap((group) => group.links.map((link) => link.key))).not.toContain("hostile-link");
  });

  it("keeps a coverage it has no heading for under its own name, last", () => {
    const [england, gb] = CONTEXT_LINKS.items;
    if (!england || !gb) throw new Error("the fixture has at least two links");
    const groups = groupLinks([{ ...gb, coverage: "isle_of_man" }, england]);
    expect(groups.map((group) => group.label)).toEqual(["England", "isle_of_man"]);
  });
});

describe("elsewherePath", () => {
  it("rounds the spot to about a metre", () => {
    expect(elsewherePath(-1.854213456, 51.428612345)).toBe("/elsewhere?lon=-1.85421&lat=51.42861");
  });
});

describe("the records overlay's style", () => {
  it("draws both layers a records tile can carry, live records and the open record, all in one stack", () => {
    const style = buildStyle(
      metaFixture,
      {
        sun: DEFAULT_SUN,
        hillshadeExaggeration: 2,
        terrain: DEFAULT_TERRAIN,
        overlays: { records: { visible: true, opacity: 1 } },
        showRuledOut: false,
        failing: {},
      },
      "composite",
      { origin: "http://localhost" },
    );
    const tiles = overlaySourceId("records");
    expect(style.sources[recordsLiveSourceId(tiles)]).toMatchObject({ type: "geojson" });
    expect(style.sources[recordsSelectionSourceId(tiles)]).toMatchObject({ type: "geojson" });
    const ids = style.layers.map((layer) => layer.id);
    for (const id of Object.values(RECORD_LAYERS)) expect(ids, id).toContain(id);
    const byId = (id: string) =>
      style.layers.find((layer) => layer.id === id) as { "source-layer"?: string } | undefined;
    expect(byId(RECORD_LAYERS.squares)?.["source-layer"]).toBe("records");
    expect(byId(RECORD_LAYERS.counts)?.["source-layer"]).toBe("record_counts");
    // The open record is drawn above the records, and findings above everything.
    expect(ids.indexOf(RECORD_LAYERS.selectionPoint)).toBeGreaterThan(ids.indexOf(RECORD_LAYERS.squares));
    expect(ids.indexOf("findings-points")).toBeGreaterThan(ids.indexOf(RECORD_LAYERS.selectionPoint));
  });
});
