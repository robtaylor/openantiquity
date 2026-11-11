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
import { closeShape, type LngLat } from "./outline.js";

const meta = parseMeta(metaFixture);
const AVEBURY: LngLat = [-1.8542, 51.4286];
const map = { ...defaultsFromMeta(meta), meta };

function fields(overrides: Partial<MarkFields> = {}): MarkFields {
  return { ...EMPTY_MARK, point: AVEBURY, featureClass: "enclosure", ...overrides };
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
  it("needs only the point and the class, and fills in the rest", () => {
    const composed = composeFinding(fields(), meta, map);
    if (!composed.ok) throw new Error(composed.message);
    expect(composed.draft).toEqual({
      point: AVEBURY,
      feature_class: "enclosure",
      period: "unknown",
      title: suggestTitle(meta, "enclosure", AVEBURY),
      description: null,
      outline: null,
      view_state: viewStateFrom(map),
    });
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
    expect(composeFinding(fields({ point: null }), meta, map)).toMatchObject({ ok: false, field: "point" });
    expect(composeFinding(fields({ featureClass: null }), meta, map)).toMatchObject({
      ok: false,
      field: "featureClass",
      message: "Choose what it looks like.",
    });
    expect(composeFinding(fields({ point: [20, 50] }), meta, map)).toMatchObject({
      field: "point",
      message: OUTSIDE_MESSAGE,
    });
    const far = closeShape({
      points: [
        [-1.7, 51.4],
        [-1.69, 51.4],
        [-1.69, 51.41],
      ],
      shape: "drawing",
    });
    expect(composeFinding(fields({ outline: far }), meta, map)).toMatchObject({ ok: false, field: "outline" });
  });

  it("explains a refusal by the field it is about", () => {
    expect(saveProblem(new ApiError(422, "outside_british_isles", "Outside."))).toEqual({
      field: "point",
      message: OUTSIDE_MESSAGE,
    });
    expect(saveProblem(new ApiError(422, "outline_too_far", "Draw it round the point."))).toEqual({
      field: "outline",
      message: "Draw it round the point.",
    });
    expect(saveProblem(new ApiError(500, "internal", "Broken."))).toEqual({ field: null, message: "Broken." });
    expect(saveProblem(new Error("?")).field).toBeNull();
  });
});

describe("finding drafts", () => {
  const composed = composeFinding(
    fields({
      note: "Faint.",
      outline: closeShape({
        points: [
          [-1.855, 51.428],
          [-1.853, 51.428],
          [-1.853, 51.43],
        ],
        shape: "drawing",
      }),
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
    expect(parseFindingDraft({ ...draft, outline: { type: "Polygon" } })).toBeNull();
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

  it("becomes the body of POST /findings, with the point as GeoJSON and the reference that makes a resend harmless", () => {
    expect(createBody(draft, "draft-1")).toEqual({
      client_ref: "draft-1",
      location: { type: "Point", coordinates: AVEBURY },
      feature_class: "enclosure",
      period: "unknown",
      title: draft.title,
      description: "Faint.",
      outline: draft.outline,
      view_state: draft.view_state,
    });
  });
});
