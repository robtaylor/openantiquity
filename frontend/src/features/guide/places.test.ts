import { describe, expect, it } from "vitest";
import type { Meta } from "../../api/meta.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { nationName } from "./nations.js";
import {
  explanationLabel,
  featureClassLabel,
  PAIRS,
  RAKING_PLACE,
  VIEW_NOTES,
  VIEW_PLACE,
  viewNotesFor,
} from "./places.js";

/** Roughly the box the local elevation mirror covers around Avebury and Stonehenge. */
const MIRROR = { west: -2.0, south: 51.1, east: -1.7, north: 51.55 };

function inMirror(place: { lon: number; lat: number }): boolean {
  return place.lon > MIRROR.west && place.lon < MIRROR.east && place.lat > MIRROR.south && place.lat < MIRROR.north;
}

describe("the guide's catalogue", () => {
  it("writes two sentences for each view, each ending in a full stop", () => {
    for (const note of VIEW_NOTES) {
      expect(note.sentences).toHaveLength(2);
      for (const sentence of note.sentences) expect(sentence).toMatch(/^[A-Z].*[.]$/);
    }
  });

  it("lists the lidar views /meta gives, in its order, with a note for each it knows", () => {
    const listed = viewNotesFor(metaFixture);
    expect(listed.map(({ view }) => view.id)).toEqual(
      metaFixture.layers.views.filter((view) => view.group === "lidar").map((view) => view.id),
    );
    expect(listed.every(({ note }) => note !== undefined)).toBe(true);
  });

  it("leaves out a view /meta doesn't list, and shows one it doesn't know with no note", () => {
    const [first, ...rest] = metaFixture.layers.views;
    if (!first) throw new Error("the fixture has no views");
    const meta: Meta = {
      ...metaFixture,
      layers: { ...metaFixture.layers, views: [{ ...first, id: "new_view", title: "New view" }, ...rest] },
    };
    const listed = viewNotesFor(meta);
    expect(listed.map(({ view }) => view.id)).not.toContain("composite");
    expect(listed.find(({ view }) => view.id === "new_view")?.note).toBeUndefined();
  });

  it("names every real example by a class in /meta, and every modern or data look-alike by an explanation", () => {
    for (const pair of PAIRS) {
      expect(featureClassLabel(metaFixture, pair.real.featureClass), pair.id).not.toBeNull();
      const { lookalike } = pair;
      // Something mistaken for an earthwork is either named for what it is instead, or is itself an earthwork.
      // One that is neither would be shown as a look-alike with nothing to say what it is.
      expect(Boolean(lookalike.explanation) !== Boolean(lookalike.featureClass), pair.id).toBe(true);
      if (lookalike.explanation) expect(explanationLabel(metaFixture, lookalike.explanation), pair.id).not.toBeNull();
      if (lookalike.featureClass)
        expect(featureClassLabel(metaFixture, lookalike.featureClass), pair.id).not.toBeNull();
    }
    expect(featureClassLabel(metaFixture, "no_such_class")).toBeNull();
    expect(explanationLabel(metaFixture, undefined)).toBeNull();
  });

  it("says what each example is from a record, or marks it as judgement, never both", () => {
    for (const pair of PAIRS) {
      for (const example of [pair.real, pair.lookalike]) {
        expect(example.judgement, example.title).toBe(example.records.length === 0);
        for (const record of example.records) {
          if (record.url) expect(record.url).toMatch(/^https:\/\//);
        }
      }
      // A real earthwork is always one a record names.
      expect(pair.real.judgement, pair.id).toBe(false);
    }
  });

  it("gives every example a picture or says why it has none, and puts every place where our terrain is", () => {
    const places = [VIEW_PLACE, RAKING_PLACE];
    for (const pair of PAIRS) {
      for (const example of [pair.real, pair.lookalike]) {
        expect(Boolean(example.picture) !== Boolean(example.noPicture), example.title).toBe(true);
        if (example.picture) expect(example.picture.alt.length).toBeGreaterThan(20);
        if (example.place) places.push(example.place);
      }
    }
    for (const place of places) expect(inMirror(place), place.name).toBe(true);
  });
});

describe("nationName", () => {
  it("makes a name from a nation's id", () => {
    expect(nationName("england")).toBe("England");
    expect(nationName("northern_ireland")).toBe("Northern Ireland");
  });
});
