// @vitest-environment node
import { describe, expect, it } from "vitest";
import { metaFixture } from "../../test/fixtures/meta.js";
import { composeEvidence, formSpec, isRecordKind, needsVisitReminder, today } from "./evidenceForms.js";

const NOW = new Date(2026, 10, 11, 12, 0, 0);

describe("formSpec", () => {
  it("has a form for every kind in the vocabulary, or a reason it can't be used", () => {
    for (const kind of metaFixture.vocab.evidence_kinds) {
      const spec = formSpec(kind.id);
      expect(isRecordKind(kind.id) || spec.fields.length > 0 || spec.unavailable !== undefined, kind.id).toBe(true);
    }
  });

  it("asks a site visit, a survey and a dig for when, who and what it found", () => {
    for (const kind of ["field_visit", "geophysics", "excavation"]) {
      const ids = formSpec(kind).fields.map((field) => field.id);
      expect(ids).toEqual(expect.arrayContaining(["occurred_on", "organisation", "outcome"]));
      expect(needsVisitReminder(kind)).toBe(true);
    }
    expect(needsVisitReminder("historic_map")).toBe(false);
  });

  it("asks an old map and an aerial photo for their source and address, and nothing about dates", () => {
    for (const kind of ["historic_map", "aerial"]) {
      const ids = formSpec(kind).fields.map((field) => field.id);
      expect(ids).toEqual(expect.arrayContaining(["title", "url"]));
      expect(ids).not.toContain("occurred_on");
      expect(ids).not.toContain("outcome");
    }
  });
});

describe("composeEvidence", () => {
  it("sends an old map with only what was typed", () => {
    expect(
      composeEvidence("historic_map", { title: " OS 6-inch, 1888 ", note: "", stance: "supports" }, null, NOW),
    ).toEqual({
      ok: true,
      body: { kind: "historic_map", title: "OS 6-inch, 1888", stance: "supports" },
    });
  });

  it("wants something that says which map it is", () => {
    expect(composeEvidence("historic_map", { note: "a circle" }, null, NOW)).toMatchObject({
      ok: false,
      field: "title",
    });
  });

  it("wants an aerial photo's address, as a web address", () => {
    expect(composeEvidence("aerial", { title: "Google Earth 2018" }, null, NOW)).toMatchObject({
      ok: false,
      field: "url",
    });
    expect(composeEvidence("aerial", { url: "javascript:alert(1)" }, null, NOW)).toMatchObject({
      ok: false,
      field: "url",
    });
    expect(composeEvidence("aerial", { url: "https://example.org/p/1" }, null, NOW)).toMatchObject({ ok: true });
  });

  it("dates a site visit, says what it found, and takes its stance from that", () => {
    const composed = composeEvidence(
      "field_visit",
      { occurred_on: "2026-11-08", outcome: "contradicts", organisation: "Avebury Field Club" },
      null,
      NOW,
    );
    expect(composed).toEqual({
      ok: true,
      body: {
        kind: "field_visit",
        occurred_on: "2026-11-08",
        outcome: "contradicts",
        stance: "contradicts",
        organisation: "Avebury Field Club",
      },
    });
  });

  it("refuses a visit with no date, no outcome, or a date to come", () => {
    expect(composeEvidence("field_visit", { outcome: "supports" }, null, NOW)).toMatchObject({ field: "occurred_on" });
    expect(composeEvidence("field_visit", { occurred_on: "2026-11-01" }, null, NOW)).toMatchObject({
      field: "outcome",
    });
    expect(composeEvidence("field_visit", { occurred_on: "2026-11-12", outcome: "supports" }, null, NOW)).toMatchObject(
      {
        field: "occurred_on",
        message: "The date can't be in the future.",
      },
    );
    expect(today(NOW)).toBe("2026-11-11");
  });

  it("wants an official record's number", () => {
    expect(composeEvidence("her_record", { title: "Barrow" }, null, NOW)).toMatchObject({ field: "reference" });
    expect(composeEvidence("designation", { reference: "1008391" }, null, NOW)).toEqual({
      ok: true,
      body: { kind: "designation", stance: "supports", reference: "1008391" },
    });
  });

  it("records the map as it is for a LIDAR view", () => {
    const view = { layer: "slope", zoom: 17 };
    expect(composeEvidence("lidar_view", {}, view, NOW)).toEqual({
      ok: true,
      body: { kind: "lidar_view", stance: "supports", view },
    });
  });

  it("says why a ground photo can't be added yet", () => {
    expect(composeEvidence("photo", {}, null, NOW)).toMatchObject({
      ok: false,
      message: expect.stringMatching(/uploading/),
    });
  });
});
