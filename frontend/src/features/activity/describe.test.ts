import { describe, expect, it } from "vitest";
import { parseMeta } from "../../api/meta.js";
import { metaFixture } from "../../test/fixtures/meta.js";
import type { ActivityFinding, PublicUser } from "./api.js";
import { describeEvent, type EventFacts, sentenceText } from "./describe.js";
import { KIND_GROUPS, kindsFor } from "./kinds.js";
import { whenWords } from "./time.js";

const meta = parseMeta(metaFixture);

const ada: PublicUser = { handle: "QuietBarrow42", display_name: "Ada Lovelace", role: "member" };
const enclosure: ActivityFinding = {
  public_id: "f-1",
  title: "Enclosure in SU 10 69",
  feature_class: "enclosure",
  tier: "seen",
  state: "open",
  location: { lon: -1.85, lat: 51.42, obscured: true, grid_ref: null, square: "SU1069", outline: null },
};

function said(facts: Partial<EventFacts> & Pick<EventFacts, "kind">): string {
  return sentenceText(
    describeEvent(meta, { actor: null, finding: enclosure, investigationTitle: null, details: {}, ...facts }),
  );
}

describe("what happened, in a sentence", () => {
  it("names nobody for a step a second look moved, because the server names nobody", () => {
    expect(said({ kind: "tier_changed", details: { tier_from: "spotted", tier_to: "seen" } })).toBe(
      "Enclosure in SU 10 69 moved up to Seen by others.",
    );
    expect(said({ kind: "observation_added" })).toBe("Enclosure in SU 10 69 had a second look.");
  });

  it("credits the person the server names, and says which way the step went", () => {
    expect(said({ kind: "tier_changed", actor: ada, details: { tier_from: "seen", tier_to: "corroborated" } })).toBe(
      "Enclosure in SU 10 69 moved up to Corroborated, with help from Ada Lovelace.",
    );
    expect(said({ kind: "tier_changed", details: { tier_from: "seen", tier_to: "spotted" } })).toBe(
      "Enclosure in SU 10 69 went back to Spotted.",
    );
  });

  it("takes states, explanations and evidence kinds from /meta", () => {
    expect(said({ kind: "state_changed", details: { state_to: "ruled_out", state_reason: "modern" } })).toBe(
      "Enclosure in SU 10 69 is now marked “Explained” (modern feature).",
    );
    expect(said({ kind: "state_changed", details: { state_to: "open", state_from: "disputed" } })).toBe(
      "Enclosure in SU 10 69 is open again.",
    );
    expect(said({ kind: "evidence_added", actor: ada, details: { evidence_kind: "historic_map" } })).toBe(
      "Ada Lovelace added evidence to Enclosure in SU 10 69: old map.",
    );
    expect(said({ kind: "evidence_added", details: { evidence_kind: "lidar_view" } })).toBe(
      "Evidence was added to Enclosure in SU 10 69: LIDAR view.",
    );
  });

  it("says something plain for every kind, with or without a name", () => {
    expect(said({ kind: "finding_created", actor: ada })).toBe("Ada Lovelace marked Enclosure in SU 10 69.");
    expect(said({ kind: "finding_created" })).toBe("Enclosure in SU 10 69 was marked.");
    expect(said({ kind: "comment_added" })).toBe("Enclosure in SU 10 69 has a new comment.");
    expect(said({ kind: "mention_added" })).toBe("Enclosure in SU 10 69 was mentioned.");
    expect(said({ kind: "followup_logged", actor: ada })).toBe(
      "Ada Lovelace logged a follow-up on Enclosure in SU 10 69.",
    );
    expect(
      said({ kind: "investigation_published", finding: null, investigationTitle: "Barrows of the Ridgeway" }),
    ).toBe("Barrows of the Ridgeway was published.");
    expect(said({ kind: "investigation_invitation", finding: null, actor: ada })).toBe(
      "Ada Lovelace invited you to join an investigation.",
    );
    expect(said({ kind: "comment_added", finding: null })).toBe("A finding has a new comment.");
  });

  it("says who carried a line or shape further, and nothing of how far", () => {
    expect(said({ kind: "shape_extended", actor: ada })).toBe("Ada Lovelace drew more of Enclosure in SU 10 69.");
    expect(said({ kind: "shape_extended" })).toBe("More of Enclosure in SU 10 69 was drawn.");
    expect(said({ kind: "shape_extended", finding: null })).toBe("More of a finding was drawn.");
  });
});

describe("the feed's kinds", () => {
  it("offers every kind the feed lists in exactly one group, and never the invitation", () => {
    const kinds = KIND_GROUPS.flatMap((group) => group.kinds);
    expect(new Set(kinds).size).toBe(kinds.length);
    expect(kinds).toContain("observation_added");
    expect(kinds).not.toContain("investigation_invitation");
    expect(kindsFor(["steps"])).toEqual(["tier_changed", "state_changed"]);
    // A line drawn further is listed and filtered with the findings marked, which the filter says.
    expect(kindsFor(["findings"])).toEqual(["finding_created", "shape_extended"]);
    expect(KIND_GROUPS.find((group) => group.id === "findings")?.label).toBe("Findings marked or drawn further");
    expect(kindsFor([])).toEqual([]);
  });
});

describe("when, in words", () => {
  const now = Date.parse("2026-11-11T12:00:00Z");
  it("is relative for the last week and a date after that", () => {
    expect(whenWords("2026-11-11T11:59:30Z", now)).toBe("just now");
    expect(whenWords("2026-11-11T11:55:00Z", now)).toBe("5 minutes ago");
    expect(whenWords("2026-11-11T09:00:00Z", now)).toBe("3 hours ago");
    expect(whenWords("2026-11-10T09:00:00Z", now)).toBe("yesterday");
    expect(whenWords("2026-10-01T09:00:00Z", now)).toMatch(/1 October 2026/);
  });
});
