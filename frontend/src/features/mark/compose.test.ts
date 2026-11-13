// @vitest-environment node
import { afterEach, describe, expect, it, vi } from "vitest";
import { ApiError } from "../../api/client.js";
import { parseMeta } from "../../api/meta.js";
import { defaultsFromMeta } from "../../map/store.js";
import { createdFinding } from "../../test/fixtures/findings.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import { saverFor } from "../drafts/savers.js";
import { composeFinding, OUTSIDE_MESSAGE, saveProblem } from "./compose.js";
import { gridRefOf, suggestTitle, viewStateFrom } from "./describe.js";
import { createBody, findingDrafts, parseFindingDraft } from "./findingDrafts.js";
import { EMPTY_MARK, type MarkFields } from "./markStore.js";
import { FINDS_NOTICE, findsRoute, sensitivityNotice } from "./notices.js";
import { history, type LngLat, type Path } from "./path.js";

const meta = parseMeta(metaFixture);
const AVEBURY: LngLat = [-1.8542, 51.4286];
const map = { ...defaultsFromMeta(meta), meta };

function drawn(points: LngLat[], closed = false): MarkFields["shape"] {
  const path: Path = { closed, points: points.map(([lon, lat]) => ({ lon, lat, kind: "corner" })) };
  return history(path);
}

function fields(overrides: Partial<MarkFields> = {}): MarkFields {
  return { ...EMPTY_MARK, shape: drawn([AVEBURY]), featureClass: "enclosure", ...overrides };
}

describe("viewStateFrom", () => {
  it("records the layer, camera and light the finder was using", () => {
    const view = viewStateFrom({
      ...map,
      mainView: "slope",
      camera: { lng: 0, lat: 0, zoom: 15.123456, bearing: -12.34, pitch: 40 },
      sun: { azimuth: 300, altitude: 18 },
    });
    expect(view).toEqual({
      layer: "slope",
      zoom: 15.12,
      bearing: -12.3,
      pitch: 40,
      sun_azimuth: 300,
      sun_altitude: 18,
    });
  });

  it("records the height exaggeration of 3D, or of the raking light, whichever shaped the picture", () => {
    expect(viewStateFrom({ ...map, terrain: { enabled: true, exaggeration: 2.5 } }).exaggeration).toBe(2.5);
    expect(viewStateFrom({ ...map, mainView: "raking", hillshadeExaggeration: 3 }).exaggeration).toBe(3);
    expect(viewStateFrom({ ...map, mainView: "composite" }).exaggeration).toBeUndefined();
  });

  it("leaves out a layer id the server would refuse", () => {
    expect(viewStateFrom({ ...map, mainView: "Not An Id!" }).layer).toBeUndefined();
  });
});

describe("suggestTitle", () => {
  it("says what it looks like and which kilometre square, so saving needs no typing", () => {
    expect(suggestTitle(meta, "enclosure", AVEBURY)).toBe("Enclosure in SU 10 69");
  });

  it("never names a place finer than the square, whatever the class, because the title is shown to everyone", () => {
    const fine = gridRefOf(AVEBURY);
    expect(fine).toMatch(/^SU \d{3} \d{3}$/);
    for (const featureClass of [...meta.vocab.feature_classes.map((entry) => entry.id), null]) {
      const title = suggestTitle(meta, featureClass, AVEBURY);
      expect(title).not.toContain(fine ?? "");
      expect(title).toMatch(/ in SU \d{2} \d{2}$/);
    }
    expect(suggestTitle(meta, "round_barrow", AVEBURY)).toBe("Round barrow or mound in SU 10 69");
  });

  it("can never hold what the server refuses as a position in the title of a finding that isn't open", () => {
    // The server's rules (backend services/text_positions.py) need, for a grid reference, groups of three
    // figures or more; for coordinates, figures beside a decimal point or comma; for an easting and
    // northing, six figures; and for a three-word address, words joined by dots. A suggestion with no run
    // of three figures, no dot, no slash and no figure beside a comma has none of them, wherever the mark
    // is and whatever the class.
    const unsafe = /\d{3}|\.|\/|\d,|,\d/;
    for (const entry of meta.vocab.feature_classes) expect(entry.label).not.toMatch(/\d|\./);
    for (let lon = -10.5; lon <= 1.8; lon += 0.37) {
      for (let lat = 50; lat <= 60.8; lat += 0.29) {
        for (const featureClass of meta.vocab.feature_classes) {
          expect(suggestTitle(meta, featureClass.id, [lon, lat])).not.toMatch(unsafe);
        }
      }
    }
    // Both grids are covered: Ireland's squares have one letter.
    expect(suggestTitle(meta, "moat", [-6.26, 54.6])).toMatch(/ in [A-Z] \d{2} \d{2}$/);
  });

  it("falls back to the class alone off the grids, and to a plain word with no class", () => {
    expect(suggestTitle(meta, "moat", [20, 50])).toBe("Moat");
    expect(suggestTitle(meta, null, null)).toBe("Finding");
  });
});

describe("notices", () => {
  it("says who sees the exact place only for a class that starts protected", () => {
    expect(sensitivityNotice(meta, "round_barrow")).toMatch(/only signed-in members will see exactly where/);
    expect(sensitivityNotice(meta, "enclosure")).toBeNull();
    expect(sensitivityNotice(meta, null)).toBeNull();
  });

  it("gives each nation's reporting route for finds, from /meta", () => {
    expect(FINDS_NOTICE).toMatch(/earthworks, not objects/);
    expect(findsRoute(meta, "england")).toMatchObject({
      scheme: "Portable Antiquities Scheme",
      url: "https://finds.org.uk/",
    });
    expect(findsRoute(meta, "scotland")?.text).toMatch(/Treasure Trove/);
    expect(findsRoute(meta, "northern_ireland")?.url).toBeNull();
    expect(findsRoute(meta, "atlantis")).toBeNull();
    expect(findsRoute(meta, null)).toBeNull();
  });
});

describe("composeFinding", () => {
  it("needs only a point and the class, and fills in the rest", () => {
    const composed = composeFinding(fields(), meta, map);
    if (!composed.ok) throw new Error(composed.message);
    expect(composed.draft).toEqual({
      point: AVEBURY,
      path: null,
      feature_class: "enclosure",
      period: "unknown",
      title: suggestTitle(meta, "enclosure", AVEBURY),
      description: null,
      view_state: viewStateFrom(map),
    });
  });

  it("keeps two points or more as a path, and the point near where the server will anchor it", () => {
    const composed = composeFinding(fields({ shape: drawn([AVEBURY, [-1.8522, 51.4286]]) }), meta, map);
    if (!composed.ok) throw new Error(composed.message);
    expect(composed.draft.path).toEqual({
      closed: false,
      points: [
        { lon: AVEBURY[0], lat: AVEBURY[1], kind: "corner" },
        { lon: -1.8522, lat: 51.4286, kind: "corner" },
      ],
    });
    expect(composed.draft.point[0]).toBeCloseTo(-1.8532, 6);
  });

  it("keeps what the finder typed, trimmed", () => {
    const composed = composeFinding(
      fields({ title: "  Ring ditch  ", note: " By the barn. ", period: "iron_age" }),
      meta,
      map,
    );
    expect(composed.ok && composed.draft).toMatchObject({
      title: "Ring ditch",
      description: "By the barn.",
      period: "iron_age",
    });
  });

  it("says what is missing, and where", () => {
    expect(composeFinding(fields({ shape: drawn([]) }), meta, map)).toMatchObject({ ok: false, field: "point" });
    expect(composeFinding(fields({ featureClass: null }), meta, map)).toMatchObject({
      ok: false,
      field: "featureClass",
      message: "Choose what it looks like.",
    });
    expect(composeFinding(fields({ shape: drawn([[20, 50]]) }), meta, map)).toMatchObject({
      field: "point",
      message: OUTSIDE_MESSAGE,
    });
    // Any point off the land covered, not only the anchor.
    expect(composeFinding(fields({ shape: drawn([AVEBURY, [20, 50]]) }), meta, map)).toMatchObject({
      field: "point",
      message: OUTSIDE_MESSAGE,
    });
    // Held to the limits /meta gives: a closed shape more than 25 km across.
    const wide = drawn(
      [
        [-1.9, 51.4],
        [-1.4, 51.4],
        [-1.4, 51.5],
      ],
      true,
    );
    expect(composeFinding(fields({ shape: wide }), meta, map)).toMatchObject({
      ok: false,
      field: "path",
      message: "A closed shape can be at most 25 km across.",
    });
  });

  it("explains a refusal by the field it is about", () => {
    expect(saveProblem(new ApiError(422, "outside_british_isles", "Outside."))).toEqual({
      field: "point",
      message: OUTSIDE_MESSAGE,
    });
    expect(saveProblem(new ApiError(422, "outline_too_far", "Draw it round the point."))).toEqual({
      field: "path",
      message: "Draw it round the point.",
    });
    expect(saveProblem(new ApiError(422, "looked_at_moved", "Only half would be left."))).toEqual({
      field: "path",
      message: "Only half would be left.",
    });
    expect(saveProblem(new ApiError(500, "internal", "Broken."))).toEqual({ field: null, message: "Broken." });
    expect(saveProblem(new Error("?")).field).toBeNull();
  });
});

describe("finding drafts", () => {
  const composed = composeFinding(
    fields({
      note: "Faint.",
      shape: drawn(
        [
          [-1.855, 51.428],
          [-1.853, 51.428],
          [-1.853, 51.43],
        ],
        true,
      ),
    }),
    meta,
    map,
  );
  if (!composed.ok) throw new Error(composed.message);
  const { draft } = composed;

  it("reads back exactly what was kept, and refuses damaged data", () => {
    expect(parseFindingDraft(JSON.parse(JSON.stringify(draft)))).toEqual(draft);
    expect(parseFindingDraft({ ...draft, point: ["a", 1] })).toBeNull();
    expect(parseFindingDraft({ ...draft, feature_class: "" })).toBeNull();
    // A path that can't be read is dropped, and the rest of the draft kept.
    expect(parseFindingDraft({ ...draft, path: { closed: true, points: [] } })).toEqual({ ...draft, path: null });
    expect(parseFindingDraft(null)).toBeNull();
  });

  afterEach(() => vi.unstubAllGlobals());

  it("is saved after sign-in with the draft's own id as its reference, so a resent draft is stored once", async () => {
    const fetchMock = vi.fn(async (_input: unknown, init?: RequestInit) => {
      const body = JSON.parse(String(init?.body)) as Parameters<typeof createdFinding>[0];
      return new Response(JSON.stringify(createdFinding(body, "made1")), {
        status: 201,
        headers: { "Content-Type": "application/json" },
      });
    });
    vi.stubGlobal("fetch", fetchMock);
    const saver = saverFor(findingDrafts.kind);
    if (!saver) throw new Error("No saver for finding drafts");
    await saver.save(draft, { draftId: "draft-7" });
    const [, init] = fetchMock.mock.calls[0] ?? [];
    expect(JSON.parse(String(init?.body))).toMatchObject({ client_ref: "draft-7", feature_class: "enclosure" });
  });

  it("becomes the body of POST /findings, with a shape as its path alone and the reference that makes a resend harmless", () => {
    expect(createBody(draft, "draft-1")).toEqual({
      client_ref: "draft-1",
      path: draft.path,
      feature_class: "enclosure",
      period: "unknown",
      title: draft.title,
      description: "Faint.",
      view_state: draft.view_state,
    });
  });

  it("sends a spot as its location alone", () => {
    const spot = composeFinding(fields(), meta, map);
    if (!spot.ok) throw new Error(spot.message);
    const body = createBody(spot.draft, "draft-2");
    expect(body.location).toEqual({ type: "Point", coordinates: AVEBURY });
    expect(body).not.toHaveProperty("path");
    expect(body).not.toHaveProperty("outline");
  });
});
