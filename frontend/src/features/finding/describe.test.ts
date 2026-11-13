// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  evidenceFixture,
  FINDER,
  finderView,
  heldFixture,
  MODERATOR_ACTIONS,
  OTHER,
  observationFixture,
  pageFixture,
  SIGNED_OUT_ACTIONS,
  seenFixture,
  squareFixture,
} from "../../test/fixtures/findingPage.js";
import { MEMBER_ACTIONS } from "../../test/fixtures/findings.js";
import { metaFixture as meta } from "../../test/fixtures/meta.js";
import {
  changeMessage,
  classLabel,
  formatDate,
  groupEvidence,
  isAnswerStep,
  lowerFirst,
  needsVerifying,
  offered,
  positionOf,
  SQUARE_SENTENCE,
  shownClass,
  stateReason,
  stepActions,
  type Viewer,
  whoSees,
} from "./describe.js";

const SIGNED_OUT: Viewer = { ready: false, signedIn: false, handle: null, role: null };
const MEMBER: Viewer = { ready: true, signedIn: true, handle: OTHER.handle, role: "member" };
const THE_FINDER: Viewer = { ready: true, signedIn: true, handle: FINDER.handle, role: "member" };

describe("a class this page's /meta doesn't list", () => {
  // Sent by a later version of the server to a page left open across a deploy.
  const LATER = "added_by_a_later_version";

  it("is shown as Not sure", () => {
    expect(shownClass(meta, LATER)).toBe("unknown");
    expect(classLabel(meta, LATER)).toBe("Not sure");
  });

  it("leaves a class it lists as it is", () => {
    expect(shownClass(meta, "round_barrow")).toBe("round_barrow");
    expect(classLabel(meta, "round_barrow")).toBe("Round barrow or mound");
    expect(classLabel(meta, "unknown")).toBe("Not sure");
  });
});

describe("positionOf", () => {
  it("offers a second look to a member the server lets answer", () => {
    expect(positionOf(pageFixture(), MEMBER)).toMatchObject({ isFinder: false, mayAnswer: true, mayRaise: false });
  });

  it("takes what the finder may do from the server: no second look, but edit, withdraw and raise", () => {
    expect(positionOf(finderView(), THE_FINDER)).toMatchObject({
      isFinder: true,
      mayAnswer: false,
      mayEdit: true,
      mayWithdraw: true,
      mayRaise: true,
      mayLower: false,
    });
  });

  it("follows the server whatever the person's role, which it never reads", () => {
    const trusted = pageFixture({ actions: { ...MEMBER_ACTIONS, raise_level: { allowed: true, reason: null } } });
    expect(positionOf(trusted, MEMBER)).toMatchObject({ mayRaise: true, mayVerify: false });
    expect(positionOf(pageFixture(), { ...MEMBER, role: "admin" })).toMatchObject({ mayRaise: false, mayLower: false });
    expect(positionOf(pageFixture({ actions: MODERATOR_ACTIONS }), MEMBER)).toMatchObject({ mayLower: true });
  });

  it("offers no second look once answered, nor once withdrawn", () => {
    expect(positionOf(pageFixture({ my_observation: observationFixture() }), MEMBER).mayAnswer).toBe(false);
    const withdrawn = pageFixture({
      assessment: { ...pageFixture().assessment, state: "withdrawn" },
      actions: { ...MEMBER_ACTIONS, answer: { allowed: false, reason: "finding_withdrawn" } },
    });
    expect(positionOf(withdrawn, MEMBER)).toMatchObject({ mayAnswer: false, takesWork: false });
  });

  it("offers a signed-out visitor what they could do once signed in, on a finding they see exactly", () => {
    const open = positionOf(pageFixture({ actions: SIGNED_OUT_ACTIONS }), SIGNED_OUT);
    expect(open).toMatchObject({ mayAnswer: true, mayAddEvidence: true, mayComment: true, mayEdit: false });
    const square = positionOf(squareFixture({ actions: SIGNED_OUT_ACTIONS }), SIGNED_OUT);
    expect(square).toMatchObject({ mayAnswer: false, mayAddEvidence: false, mayComment: true });
  });

  it("knows an answer that waits for its detail", () => {
    expect(positionOf(heldFixture(), MEMBER)).toMatchObject({ hasAnswered: true, answerHeld: true, mayAnswer: false });
    expect(positionOf(pageFixture({ my_observation: observationFixture() }), MEMBER).answerHeld).toBe(false);
  });
});

describe("offered", () => {
  it("offers what is allowed, and what signing in or the welcome step would allow, and nothing else", () => {
    expect(offered({ allowed: true, reason: null })).toBe(true);
    expect(offered({ allowed: false, reason: "unauthorised" })).toBe(true);
    expect(offered({ allowed: false, reason: "onboarding_required" })).toBe(true);
    expect(offered({ allowed: false, reason: "location_hidden" })).toBe(false);
    expect(offered({ allowed: false, reason: null })).toBe(false);
  });
});

describe("words", () => {
  it("keeps the capitals of an acronym and lowers an ordinary word", () => {
    expect(lowerFirst("Old map")).toBe("old map");
    expect(lowerFirst("LIDAR view")).toBe("LIDAR view");
    expect(lowerFirst("HER entry")).toBe("HER entry");
  });

  it("writes dates the British way", () => {
    expect(formatDate("2026-11-01T10:00:00Z")).toBe("1 November 2026");
  });

  it("says who sees the place at each level, and who downloads a protected one exactly", () => {
    expect(whoSees("open")).toMatch(/Everyone/);
    expect(whoSees("protected")).toMatch(/signed in/);
    expect(whoSees("protected")).toMatch(/Downloads give its exact place only to its finder, trusted members/);
  });

  it("tells a signed-out visitor that signing in shows a protected place", () => {
    expect(SQUARE_SENTENCE).toMatch(/Sign in to see it\.$/);
  });
});

describe("stateReason", () => {
  const withState = (state: string, reason: string | null = null) =>
    pageFixture({
      assessment: { ...pageFixture().assessment, state: state as "open", state_reason: reason },
    });

  it("says nothing for an open finding", () => {
    expect(stateReason(meta, withState("open"))).toBeNull();
  });

  it("gives an explanation's label and hint from /meta", () => {
    expect(stateReason(meta, withState("ruled_out", "modern"))).toMatch(
      /most likely a modern feature\. Something recent/,
    );
  });

  it("puts the reasons /meta has no words for into words", () => {
    expect(stateReason(meta, withState("ruled_out", "not_visible"))).toMatch(/couldn't see it/);
    expect(stateReason(meta, withState("ruled_out", "ground_check"))).toMatch(/on the ground/);
  });

  it("uses the state's description for known and disputed findings", () => {
    expect(stateReason(meta, withState("known"))).toMatch(/existing heritage record/);
    expect(stateReason(meta, withState("disputed"))).toMatch(/disagree/);
    expect(stateReason(meta, withState("withdrawn"))).toMatch(/took it back/);
  });
});

describe("stepActions", () => {
  const [answerStep] = pageFixture().assessment.next_steps;
  const [strandStep] = seenFixture().assessment.next_steps;
  if (!answerStep || !strandStep) throw new Error("fixture steps missing");

  it("offers the answer to someone who may give one, and a link to the finder", () => {
    expect(stepActions(answerStep, meta, positionOf(pageFixture(), MEMBER))).toEqual([
      { kind: "answer", label: "Give a second look" },
    ]);
    expect(stepActions(answerStep, meta, positionOf(finderView(), THE_FINDER))).toEqual([
      { kind: "share", label: "Copy a link to ask others" },
    ]);
    expect(stepActions(answerStep, meta, positionOf(squareFixture(), SIGNED_OUT))).toEqual([]);
  });

  it("offers a form for each kind in the missing strands, and only those", () => {
    const actions = stepActions(strandStep, meta, positionOf(seenFixture(), MEMBER));
    expect(actions.map((action) => action.label)).toEqual([
      "Add aerial photo",
      "Add old map",
      "Add heritage record",
      "Add book or report",
    ]);
  });

  it("offers the field kinds for a ground step and the official ones for a record step", () => {
    const position = positionOf(seenFixture(), MEMBER);
    const ground = stepActions({ code: "need_ground", prompt: "" }, meta, position);
    expect(ground.map((action) => action.kind === "evidence" && action.evidenceKind)).toEqual([
      "photo",
      "field_visit",
      "geophysics",
      "excavation",
    ]);
    const official = stepActions({ code: "need_official", prompt: "" }, meta, position);
    expect(official.map((action) => action.kind === "evidence" && action.evidenceKind)).toEqual([
      "her_record",
      "designation",
      "publication",
    ]);
  });

  it("goes to evidence that is waiting for an endorsement", () => {
    const actions = stepActions(
      { code: "need_ground", prompt: "", pending_evidence: [7] },
      meta,
      positionOf(seenFixture(), MEMBER),
    );
    expect(actions[0]).toEqual({ kind: "endorse", evidenceIds: [7], label: "See it" });
  });

  it("takes the kinds that meet a step from /meta, and offers nothing for a step it doesn't name", () => {
    const rules = meta.vocab.next_steps.map((rule) =>
      rule.id === "need_official" ? { ...rule, evidence_kinds: ["designation"] } : rule,
    );
    const changed = { ...meta, vocab: { ...meta.vocab, next_steps: rules } };
    const position = positionOf(seenFixture(), MEMBER);
    expect(stepActions({ code: "need_official", prompt: "" }, changed, position)).toEqual([
      { kind: "evidence", evidenceKind: "designation", label: "Add designation" },
    ]);
    expect(stepActions({ code: "need_photo" as "need_ground", prompt: "Add a photo." }, meta, position)).toEqual([]);
  });

  it("offers the forms only to someone who may add evidence", () => {
    expect(stepActions(strandStep, meta, positionOf(squareFixture(), SIGNED_OUT))).toEqual([]);
  });

  it("offers nothing on a withdrawn finding", () => {
    const withdrawn = pageFixture({ assessment: { ...pageFixture().assessment, state: "withdrawn" } });
    expect(stepActions(strandStep, meta, positionOf(withdrawn, MEMBER))).toEqual([]);
  });
});

describe("changeMessage", () => {
  it("says a finding moved up, with what the new step means", () => {
    expect(changeMessage(meta, { tier: "spotted", state: "open" }, { tier: "seen", state: "open" })).toBe(
      "It has moved up to Seen by others. At least two other people can see it too, and few can't.",
    );
  });

  it("says when it went back, and when its state changed", () => {
    expect(changeMessage(meta, { tier: "seen", state: "open" }, { tier: "spotted", state: "open" })).toMatch(
      /^It has gone back to Spotted/,
    );
    expect(changeMessage(meta, { tier: "seen", state: "open" }, { tier: "seen", state: "disputed" })).toMatch(
      /^It's now marked disputed\./,
    );
  });

  it("never calls anything a discovery", () => {
    for (const tier of meta.vocab.tiers) {
      expect(
        changeMessage(meta, { tier: "spotted", state: "open" }, { tier: tier.id, state: "open" }) ?? "",
      ).not.toMatch(/discover/i);
    }
  });

  it("says nothing when nothing changed", () => {
    expect(changeMessage(meta, { tier: "seen", state: "open" }, { tier: "seen", state: "open" })).toBeNull();
  });
});

describe("groupEvidence", () => {
  it("groups by kind in the vocabulary's order", () => {
    const groups = groupEvidence(meta, [
      evidenceFixture({ id: 1, kind: "historic_map" }),
      evidenceFixture({ id: 2, kind: "aerial" }),
      evidenceFixture({ id: 3, kind: "historic_map" }),
    ]);
    expect(groups.map((group) => [group.kind.id, group.items.map((item) => item.id)])).toEqual([
      ["aerial", [2]],
      ["historic_map", [1, 3]],
    ]);
  });
});

describe("isAnswerStep", () => {
  it("takes the steps a second look meets from /meta", () => {
    const met = meta.vocab.next_steps.map((rule) => rule.id).filter((code) => isAnswerStep(meta, code));
    expect(met.sort()).toEqual(["need_check", "need_class_agreement", "need_observers", "need_trusted_review"]);
  });

  it("is false for a code /meta doesn't name", () => {
    expect(isAnswerStep(meta, "need_ground")).toBe(false);
    expect(isAnswerStep(meta, "need_something_new")).toBe(false);
    expect(isAnswerStep(meta, "toString")).toBe(false);
  });
});

describe("needsVerifying", () => {
  it("is true for the kinds /meta's rules say are verified before they count", () => {
    expect(needsVerifying(meta, "her_record")).toBe(true);
    expect(needsVerifying(meta, "historic_map")).toBe(false);
  });
});
