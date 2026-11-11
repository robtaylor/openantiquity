// @vitest-environment node
import { describe, expect, it } from "vitest";
import {
  evidenceFixture,
  FINDER,
  OTHER,
  observationFixture,
  pageFixture,
  seenFixture,
  squareFixture,
} from "../../test/fixtures/findingPage.js";
import { metaFixture as meta } from "../../test/fixtures/meta.js";
import {
  changeMessage,
  formatDate,
  groupEvidence,
  isAnswerStep,
  lowerFirst,
  MET_BY_SECOND_LOOK,
  positionOf,
  squareSentence,
  stateReason,
  stepActions,
  type Viewer,
  whoSees,
} from "./describe.js";

const SIGNED_OUT: Viewer = { ready: false, signedIn: false, handle: null, role: null };
const MEMBER: Viewer = { ready: true, signedIn: true, handle: OTHER.handle, role: "member" };
const THE_FINDER: Viewer = { ready: true, signedIn: true, handle: FINDER.handle, role: "member" };

describe("positionOf", () => {
  it("offers a second look to a member who hasn't answered and sees the place", () => {
    expect(positionOf(pageFixture(), MEMBER)).toMatchObject({ isFinder: false, mayAnswer: true, mayRaise: false });
  });

  it("never offers the finder a second look of their own finding, and lets them raise its level", () => {
    expect(positionOf(pageFixture(), THE_FINDER)).toMatchObject({ isFinder: true, mayAnswer: false, mayRaise: true });
  });

  it("offers no second look once answered, nor on a square, nor once withdrawn", () => {
    expect(positionOf(pageFixture({ my_observation: observationFixture() }), MEMBER).mayAnswer).toBe(false);
    expect(positionOf(squareFixture(), MEMBER).mayAnswer).toBe(false);
    const withdrawn = pageFixture({ assessment: { ...pageFixture().assessment, state: "withdrawn" } });
    expect(positionOf(withdrawn, MEMBER)).toMatchObject({ mayAnswer: false, takesWork: false });
  });

  it("offers a signed-out visitor a second look on a finding they see exactly", () => {
    expect(positionOf(pageFixture(), SIGNED_OUT).mayAnswer).toBe(true);
  });

  it("lets trusted members raise a level, and experts verify", () => {
    expect(positionOf(pageFixture(), { ...MEMBER, role: "trusted" })).toMatchObject({
      mayRaise: true,
      mayVerify: false,
    });
    expect(positionOf(pageFixture(), { ...MEMBER, role: "expert" }).mayVerify).toBe(true);
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

  it("says who sees the place at each level", () => {
    expect(whoSees("open")).toMatch(/Everyone/);
    expect(whoSees("protected")).toMatch(/signed in/);
    expect(whoSees("restricted")).toMatch(/trusted members/);
  });

  it("tells a signed-out visitor that signing in shows a protected place, and nobody that for a restricted one", () => {
    expect(squareSentence(squareFixture(), false)).toMatch(/Sign in to see it\.$/);
    expect(squareSentence(squareFixture(), true)).not.toMatch(/Sign in/);
    expect(squareSentence(squareFixture({ sensitivity: "restricted" }), false)).not.toMatch(/Sign in/);
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
    expect(stepActions(answerStep, meta, positionOf(pageFixture(), THE_FINDER))).toEqual([
      { kind: "share", label: "Copy a link to ask others" },
    ]);
    expect(stepActions(answerStep, meta, positionOf(squareFixture(), MEMBER))).toEqual([]);
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
  it("matches the steps the backend's ANSWER_CODES says a second look meets", () => {
    // services/findings.py, ANSWER_CODES. Change both together.
    const met = Object.entries(MET_BY_SECOND_LOOK)
      .filter(([, value]) => value)
      .map(([code]) => code);
    expect(met.sort()).toEqual(["need_check", "need_class_agreement", "need_observers", "need_trusted_review"]);
  });

  it("is false for a code this build doesn't know, and for names on the object's prototype", () => {
    expect(isAnswerStep("need_observers")).toBe(true);
    expect(isAnswerStep("need_ground")).toBe(false);
    expect(isAnswerStep("need_something_new")).toBe(false);
    expect(isAnswerStep("toString")).toBe(false);
  });
});
