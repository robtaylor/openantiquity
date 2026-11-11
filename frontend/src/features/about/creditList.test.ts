import { describe, expect, it } from "vitest";
import type { Meta, SourceSummary } from "../../api/meta.js";
import { liveSourceFixture as liveSource } from "../../test/fixtures/about.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { categoryTitle, creditCount, creditGroups, LAYERS_GROUP, LIVE_GROUP, searchCredits } from "./creditList.js";

function source(overrides: Partial<SourceSummary>): SourceSummary {
  return {
    key: "nhle-scheduled",
    name: "Scheduled monuments",
    publisher: "Historic England",
    licence: "Open Government Licence v3.0",
    licence_url: "https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    attribution: "© Historic England 2026",
    homepage: "https://historicengland.org.uk/",
    category: "designation",
    access: "bulk",
    record_count: 20006,
    ...overrides,
  };
}

const META: Meta = {
  ...metaFixture,
  sources: [
    source({ key: "nhle-scheduled" }),
    source({ key: "os-open-names", name: "OS Open Names", publisher: "Ordnance Survey", category: "place" }),
    source({ key: "aim", name: "Aerial mapping", category: "monument", licence_url: null }),
    source({ key: "gb1900", name: "Antiquities on old maps", category: "map_label", licence: "CC BY-SA 4.0" }),
  ],
};

describe("creditGroups", () => {
  it("puts the layers first, then sources by category in /meta's order, then the browser's own", () => {
    const groups = creditGroups(META, [liveSource()]);
    expect(groups.map((group) => group.id)).toEqual([
      LAYERS_GROUP,
      "category-designation",
      "category-monument",
      "category-map_label",
      "category-place",
      LIVE_GROUP,
    ]);
    expect(groups.map((group) => group.title)).toEqual([
      "Map layers",
      "Designations",
      "Monument records",
      "Antiquities on old maps",
      "Place",
      "Looked up from your browser",
    ]);
  });

  it("credits layers that share an attribution once, naming them all", () => {
    const layers = creditGroups(META, [])[0];
    const lidar = layers?.credits.find((credit) => credit.attribution?.includes("Environment Agency"));
    expect(lidar?.name).toBe("Composite, Local relief, Sky-view, Multi-direction shade, Slope");
    // Every attribution the map shows is in the list once.
    const attributions = layers?.credits.map((credit) => credit.attribution) ?? [];
    expect(new Set(attributions).size).toBe(attributions.length);
  });

  it("names two layers apart when they share a name but are credited differently", () => {
    const layers = creditGroups(META, [])[0];
    const names = layers?.credits.map((credit) => credit.name) ?? [];
    expect(new Set(names).size).toBe(names.length);
    expect(names).toContain("OpenStreetMap, as a map");
    expect(names).toContain("OpenStreetMap, drawn over the terrain");
  });

  it("gives a layer the licence /meta sends with it, and keeps layers under different licences apart", () => {
    const views = META.layers.views.map((view) =>
      view.id === "slope"
        ? { ...view, licence: "CC BY 4.0", licence_url: "https://creativecommons.org/licenses/by/4.0/" }
        : { ...view, licence: "OGL v3.0", licence_url: "https://www.nationalarchives.gov.uk/doc/ogl/" },
    );
    const layers = creditGroups({ ...META, layers: { ...META.layers, views } }, [])[0];
    const ea = META.layers.views.find((view) => view.id === "composite")?.attribution;
    const credited = layers?.credits.filter((credit) => credit.attribution === ea) ?? [];
    expect(credited.map((credit) => [credit.name, credit.licence, credit.licenceUrl])).toEqual([
      [
        "Composite, Local relief, Sky-view, Multi-direction shade",
        "OGL v3.0",
        "https://www.nationalarchives.gov.uk/doc/ogl/",
      ],
      ["Slope", "CC BY 4.0", "https://creativecommons.org/licenses/by/4.0/"],
    ]);
  });

  it("gives a live source's licence in words and its own credit line", () => {
    const live = creditGroups(META, [liveSource()]).at(-1);
    expect(live?.credits[0]).toMatchObject({
      name: "Wiltshire and Swindon HER",
      licence: "No licence stated",
      attribution: "Wiltshire Council Archaeology Service",
    });
    const fallback = creditGroups(META, [liveSource({ licence_label: null, credit: null })]).at(-1);
    expect(fallback?.credits[0]).toMatchObject({ licence: liveSource().licence, attribution: "Wiltshire Council" });
  });

  it("leaves out the live group while there are none", () => {
    expect(creditGroups(META, []).some((group) => group.id === LIVE_GROUP)).toBe(false);
  });
});

describe("categoryTitle", () => {
  it("uses /meta's name, or makes one from the id", () => {
    expect(categoryTitle(META, "find")).toBe("Finds");
    expect(categoryTitle(META, "elevation_model")).toBe("Elevation model");
  });
});

describe("searchCredits", () => {
  const groups = creditGroups(META, [liveSource()]);

  it("keeps everything for an empty search", () => {
    expect(creditCount(searchCredits(groups, "   "))).toBe(creditCount(groups));
  });

  it("matches every word, in any field, ignoring case, and drops empty groups", () => {
    const found = searchCredits(groups, "ordnance NAMES");
    expect(found.map((group) => group.id)).toEqual(["category-place"]);
    expect(searchCredits(groups, "licence stated wiltshire")[0]?.credits.map((credit) => credit.name)).toEqual([
      "Wiltshire and Swindon HER",
    ]);
  });

  it("reads a credit line's words without its markup", () => {
    expect(searchCredits(groups, "openstreetmap contributors").length).toBeGreaterThan(0);
    expect(searchCredits(groups, "href")).toEqual([]);
  });

  it("keeps a whole group whose title matches", () => {
    const found = searchCredits(groups, "designations");
    expect(found).toHaveLength(1);
    expect(found[0]?.credits).toHaveLength(1);
  });

  it("finds nothing for words nothing holds", () => {
    expect(creditCount(searchCredits(groups, "zzzz"))).toBe(0);
  });
});
