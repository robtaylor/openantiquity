import { describe, expect, it } from "vitest";
import { metaFixture } from "../test/fixtures/meta.js";
import { defaultView, findView, isColour, MetaError, parseMeta } from "./meta.js";

// biome-ignore lint/suspicious/noExplicitAny: these tests break the document in ways its type forbids
type Breakable = any;

function broken(change: (meta: Breakable) => void): unknown {
  const copy = structuredClone(metaFixture);
  change(copy);
  return copy;
}

describe("parseMeta", () => {
  it("accepts the fixture", () => {
    expect(parseMeta(structuredClone(metaFixture))).toEqual(metaFixture);
  });

  it("accepts the example from the architecture document", () => {
    const meta = broken((m) => {
      m.layers.views = [
        {
          id: "composite",
          title: "Composite",
          description: "...",
          group: "lidar",
          type: "raster",
          tiles: ["/tiles/lidar/composite/{z}/{x}/{y}.png"],
          tile_size: 512,
          minzoom: 7,
          maxzoom: 16,
          attribution: "...",
          bounds: null,
          default: true,
        },
        { id: "raking", title: "Raking light", group: "lidar", type: "raking", description: "...", attribution: "..." },
      ];
      m.layers.dem = {
        tiles: ["/tiles/dem/{z}/{x}/{y}.png"],
        tile_size: 512,
        encoding: "terrarium",
        minzoom: 7,
        maxzoom: 16,
        attribution: "...",
      };
    });
    expect(() => parseMeta(meta)).not.toThrow();
  });

  it.each([
    ["not an object", () => null, "not an object"],
    ["no views", (m: Breakable) => (m.layers.views = []), '"layers.views" is empty'],
    ["a duplicate view", (m: Breakable) => m.layers.views.push(m.layers.views[0]), "appears twice"],
    ["a raster view without tiles", (m: Breakable) => (m.layers.views[0].tiles = []), 'needs a non-empty "tiles" list'],
    ["an unknown view type", (m: Breakable) => (m.layers.views[0].type = "wms"), 'unknown type "wms"'],
    ["an unknown group", (m: Breakable) => (m.layers.views[0].group = "weather"), 'unknown group "weather"'],
    [
      "two raking views",
      (m: Breakable) =>
        m.layers.views.push({ ...m.layers.views.find((v: Breakable) => v.type === "raking"), id: "raking2" }),
      "more than one raking view",
    ],
    ["no dem", (m: Breakable) => delete m.layers.dem, '"layers.dem" is missing'],
    ["an unknown dem encoding", (m: Breakable) => (m.layers.dem.encoding = "gsi"), 'unknown dem encoding "gsi"'],
    ["an overlay without tiles", (m: Breakable) => delete m.layers.overlays[1].tiles, 'overlay "records" needs'],
    ["an unknown overlay type", (m: Breakable) => (m.layers.overlays[0].type = "wmts"), 'unknown type "wmts"'],
    ["a bad centre", (m: Breakable) => (m.layers.initial_view.center = [1]), "is not [lon, lat]"],
    ["a missing vocabulary", (m: Breakable) => delete m.vocab.tiers, '"vocab.tiers" is not a list'],
    ["a dem with no zoom range", (m: Breakable) => delete m.layers.dem.minzoom, "needs a numeric minzoom and maxzoom"],
    [
      "a dem whose zoom range is text",
      (m: Breakable) => (m.layers.dem.maxzoom = "15"),
      '"layers.dem" needs a numeric minzoom and maxzoom',
    ],
    [
      "a zoom range that runs backwards",
      (m: Breakable) => (m.layers.views[0].minzoom = 18),
      "zoom range that runs backwards",
    ],
    [
      "bounds that are not numbers",
      (m: Breakable) => (m.layers.views[0].bounds = ["-7.11", "49.85", "2.09", "55.88"]),
      "bounds that are not four numbers",
    ],
    ["bounds with a corner missing", (m: Breakable) => (m.layers.views[0].bounds = [-7, 49, 2]), "not four numbers"],
    [
      "a record category colour the map cannot read",
      (m: Breakable) => (m.vocab.record_categories[0].colour = "tomato-ish"),
      `record category "${metaFixture.vocab.record_categories[0]?.id}" has a colour the map cannot read`,
    ],
    [
      "a record category with no colour",
      (m: Breakable) => delete m.vocab.record_categories[1].colour,
      "has a colour the map cannot read",
    ],
    [
      "two overlays of one kind, which would give two map layers one id",
      (m: Breakable) => m.layers.overlays.push({ ...m.layers.overlays[0], id: "osm2" }),
      'more than one overlay of type "openmaptiles"',
    ],
    [
      "sign-in providers as bare names, as an earlier draft had them",
      (m: Breakable) => (m.auth.providers = ["email", "google"]),
      'each of "auth.providers" needs an id, a label and an enabled flag',
    ],
    [
      "a provider with no enabled flag, which would be offered whether or not it works",
      (m: Breakable) => delete m.auth.providers[0].enabled,
      'each of "auth.providers" needs an id, a label and an enabled flag',
    ],
    ["no step rules", (m: Breakable) => delete m.vocab.next_steps, '"vocab.next_steps" is not a list'],
    [
      "a step rule that doesn't say what meets it",
      (m: Breakable) => delete m.vocab.next_steps[0].met_by,
      'each of "vocab.next_steps" needs an id, what meets it and its evidence kinds',
    ],
    ["no report reasons", (m: Breakable) => delete m.vocab.report_reasons, '"vocab.report_reasons" is not a list'],
    ["age bands that aren't a list", (m: Breakable) => (m.auth.age_bands = "16_17"), '"auth.age_bands" is not a list'],
    [
      "no under-18 field visit notice",
      (m: Breakable) => delete m.notices.field_visit_16_17,
      '"notices.field_visit_16_17" is missing',
    ],
    ["no limits on lines and shapes", (m: Breakable) => delete m.shapes, '"shapes" needs every limit'],
    [
      "a line length limit given as text",
      (m: Breakable) => (m.shapes.line_max_length_m = "600000"),
      '"shapes" needs every limit',
    ],
  ])("rejects %s", (_name, change, message) => {
    const value = _name === "not an object" ? null : broken(change as (meta: Breakable) => void);
    expect(() => parseMeta(value)).toThrow(MetaError);
    expect(() => parseMeta(value)).toThrow(message);
  });
});

describe("isColour", () => {
  it("takes the notations MapLibre reads", () => {
    for (const colour of [
      "#d9544d",
      "#D95",
      "#d9544d80",
      "rgb(217, 84, 77)",
      "rgba(217 84 77 / 0.5)",
      "hsl(3 65% 58%)",
      "tomato",
    ]) {
      expect(isColour(colour), colour).toBe(true);
    }
  });

  it("refuses anything else", () => {
    for (const colour of ["tomato-ish", "#d9544", "#gggggg", "", "rgb(", "url(x)", 12, null, undefined]) {
      expect(isColour(colour), String(colour)).toBe(false);
    }
  });
});

describe("view helpers", () => {
  it("finds views and the default", () => {
    expect(findView(metaFixture, "slope")?.title).toBe("Slope");
    expect(findView(metaFixture, "nope")).toBeUndefined();
    expect(defaultView(metaFixture).id).toBe("composite");
  });
});
