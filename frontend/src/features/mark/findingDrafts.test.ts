// @vitest-environment node
import { describe, expect, it } from "vitest";
import { createBody, parseFindingDraft } from "./findingDrafts.js";

/** A finding draft as the outline tool kept it, before paths: a placed point and an outline as GeoJSON. */
const OLD = {
  point: [-1.8542, 51.4286],
  feature_class: "enclosure",
  period: "unknown",
  title: "Enclosure in SU 10 69",
  description: null,
  view_state: { layer: "composite", zoom: 15 },
};

const RING = [
  [-1.855, 51.428],
  [-1.853, 51.428],
  [-1.853, 51.43],
  [-1.855, 51.428],
];

describe("a draft kept before paths", () => {
  it("reads a closed outline as an all-corner closed path", () => {
    const draft = parseFindingDraft({ ...OLD, outline: { type: "Polygon", coordinates: [RING] } });
    expect(draft?.path).toEqual({
      closed: true,
      points: RING.slice(0, -1).map(([lon, lat]) => ({ lon, lat, kind: "corner" })),
    });
    expect(draft).not.toHaveProperty("outline");
    expect(draft?.point).toEqual(OLD.point);
  });

  it("reads a line as an all-corner open path", () => {
    const draft = parseFindingDraft({ ...OLD, outline: { type: "LineString", coordinates: RING.slice(0, 2) } });
    expect(draft?.path).toEqual({
      closed: false,
      points: RING.slice(0, 2).map(([lon, lat]) => ({ lon, lat, kind: "corner" })),
    });
  });

  it("drops an outline that isn't one line or one ring, and keeps the rest of the draft", () => {
    for (const outline of [
      { type: "MultiPolygon", coordinates: [[RING]] },
      { type: "Polygon", coordinates: [RING, RING] },
      { type: "Polygon" },
      { type: "LineString", coordinates: [[-1.855, 51.428]] },
    ]) {
      const draft = parseFindingDraft({ ...OLD, outline });
      expect(draft).toMatchObject({ point: OLD.point, title: OLD.title, path: null });
    }
    expect(parseFindingDraft({ ...OLD, outline: null })?.path).toBeNull();
  });

  it("prefers a path to an outline when a draft somehow has both", () => {
    const path = {
      closed: false,
      points: [
        { lon: -1.85, lat: 51.42, kind: "smooth" },
        { lon: -1.84, lat: 51.42, kind: "corner" },
      ],
    };
    const draft = parseFindingDraft({ ...OLD, path, outline: { type: "Polygon", coordinates: [RING] } });
    expect(draft?.path).toEqual(path);
  });

  it("is sent as its path alone, as the drawing tool sends a shape", () => {
    const draft = parseFindingDraft({ ...OLD, outline: { type: "Polygon", coordinates: [RING] } });
    if (!draft) throw new Error("The old draft wasn't read");
    const body = createBody(draft, "old-1");
    expect(body.path?.closed).toBe(true);
    expect(body).not.toHaveProperty("location");
    expect(body).not.toHaveProperty("outline");
  });
});
