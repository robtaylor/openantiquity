import { describe, expect, it } from "vitest";
import { EXPERT, evidenceFixture, OTHER } from "../../../test/fixtures/findingPage.js";
import { metaFixture } from "../../../test/fixtures/meta.js";
import { type ActivityEvent, followUpKinds, ladderMoves, timelineEntries } from "./followUps.js";

function event(overrides: Partial<ActivityEvent>): ActivityEvent {
  return {
    id: 1,
    kind: "followup_logged",
    created_at: "2026-11-05T10:00:00Z",
    actor: OTHER,
    finding: null,
    investigation: null,
    details: {},
    ...overrides,
  };
}

describe("which evidence is a follow-up", () => {
  it("is every kind in the field and official groups of /meta, in its order", () => {
    expect(followUpKinds(metaFixture).map((kind) => kind.id)).toEqual([
      "photo",
      "field_visit",
      "geophysics",
      "excavation",
      "her_record",
      "designation",
      "publication",
    ]);
  });

  it("puts them in date order, by when they happened, and leaves out the desk evidence", () => {
    const evidence = [
      evidenceFixture({ id: 1, kind: "historic_map" }),
      evidenceFixture({ id: 2, kind: "excavation", occurred_on: "2026-09-01", created_at: "2026-11-01T00:00:00Z" }),
      evidenceFixture({ id: 3, kind: "field_visit", occurred_on: "2026-06-12", created_at: "2026-11-03T00:00:00Z" }),
      // No date of its own: the day it was added counts.
      evidenceFixture({ id: 4, kind: "her_record", created_at: "2026-10-20T12:00:00Z" }),
      evidenceFixture({ id: 5, kind: "geophysics", occurred_on: "2026-06-12", created_at: "2026-11-04T00:00:00Z" }),
    ];
    expect(timelineEntries(metaFixture, evidence).map((item) => item.id)).toEqual([3, 5, 2, 4]);
  });
});

describe("what moved the finding up", () => {
  it("is the follow-up logged in the same request as the move, by the same person", () => {
    const events = [
      event({ id: 12, kind: "tier_changed", details: { tier_from: "probable", tier_to: "ground_checked" } }),
      event({ id: 11, details: { evidence_id: 7, evidence_kind: "field_visit" } }),
    ];
    expect(ladderMoves(metaFixture, events)).toEqual(new Map([[7, "ground_checked"]]));
  });

  it("isn't a move down, a move by someone else, or one long after the follow-up", () => {
    const logged = event({ id: 11, details: { evidence_id: 7 } });
    const later = { tier_from: "probable" as const, tier_to: "ground_checked" as const };
    expect(
      ladderMoves(metaFixture, [
        logged,
        event({ id: 12, kind: "tier_changed", details: { tier_from: "ground_checked", tier_to: "probable" } }),
      ]).size,
    ).toBe(0);
    // An expert verifying the record days later moved it: nothing on the timeline says which entry did.
    expect(
      ladderMoves(metaFixture, [
        logged,
        event({ id: 12, kind: "tier_changed", actor: EXPERT, created_at: "2026-11-09T10:00:00Z", details: later }),
      ]).size,
    ).toBe(0);
    expect(
      ladderMoves(metaFixture, [
        logged,
        event({ id: 12, kind: "tier_changed", created_at: "2026-11-05T11:00:00Z", details: later }),
      ]).size,
    ).toBe(0);
  });

  it("puts each move down only to the follow-up just before it", () => {
    const events = [
      event({ id: 1, details: { evidence_id: 7 } }),
      event({ id: 2, details: { evidence_id: 8 } }),
      event({ id: 3, kind: "tier_changed", details: { tier_from: "probable", tier_to: "ground_checked" } }),
      event({ id: 4, kind: "tier_changed", details: { tier_from: "ground_checked", tier_to: "confirmed" } }),
    ];
    expect(ladderMoves(metaFixture, events)).toEqual(new Map([[8, "ground_checked"]]));
  });
});
