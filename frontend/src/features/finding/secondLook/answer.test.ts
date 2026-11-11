// @vitest-environment node
import { describe, expect, it } from "vitest";
import { observationFixture } from "../../../test/fixtures/findingPage.js";
import { metaFixture as meta } from "../../../test/fixtures/meta.js";
import {
  type AnswerDraft,
  answerBody,
  answerFromBody,
  explanationFor,
  newAnswer,
  sameAnswer,
  withCheck,
} from "./answer.js";
import { othersSentence } from "./RevealSummary.js";

describe("answerBody", () => {
  it("sends only the answer when nothing more was said", () => {
    expect(answerBody(meta, newAnswer("unsure"))).toEqual({ visible: "unsure" });
  });

  it("sends what they think it is, what they ruled out, the one explanation and the note", () => {
    let answer: AnswerDraft = { ...newAnswer("yes"), featureClass: "round_barrow", note: "  clear in slope  " };
    answer = withCheck(answer, "not_modern", "no");
    answer = withCheck(answer, "not_artefact", "yes");
    expect(answerBody(meta, answer)).toEqual({
      visible: "yes",
      feature_class: "round_barrow",
      not_modern: true,
      explanation: "artefact",
      note: "clear in slope",
    });
  });

  it("keeps only one explanation", () => {
    let answer = withCheck(newAnswer("no"), "not_modern", "yes");
    answer = withCheck(answer, "not_natural", "yes");
    expect(answer.checks).toEqual({ not_modern: null, not_natural: "yes" });
    expect(answerBody(meta, answer)).toEqual({ visible: "no", explanation: "natural" });
  });

  it("matches each check in /meta to its explanation", () => {
    expect(meta.vocab.checks.map((check) => explanationFor(meta, check.id))).toEqual(["modern", "natural", "artefact"]);
    expect(explanationFor(meta, "is_old")).toBeNull();
  });
});

describe("answerFromBody", () => {
  it("reads a kept answer back as it was given, so a draft can be changed before it is saved", () => {
    let answer: AnswerDraft = { ...newAnswer("yes"), featureClass: "round_barrow", note: "clear in slope" };
    answer = withCheck(answer, "not_modern", "no");
    answer = withCheck(answer, "not_artefact", "yes");
    expect(answerFromBody(meta, answerBody(meta, answer))).toEqual(answer);
    expect(answerFromBody(meta, { visible: "no" })).toEqual(newAnswer("no"));
  });
});

describe("sameAnswer", () => {
  it("sends the answer exactly as given with a new note, so only the note changes", () => {
    const given = observationFixture({ visible: "yes", feature_class: "round_barrow", not_natural: true, note: "old" });
    expect(sameAnswer(given, "new note")).toEqual({
      visible: "yes",
      feature_class: "round_barrow",
      not_natural: true,
      note: "new note",
    });
    expect(sameAnswer(given, "")).toEqual({ visible: "yes", feature_class: "round_barrow", not_natural: true });
  });
});

describe("othersSentence", () => {
  it("says how the others answered in words, leaving out anyone counted as nobody", () => {
    expect(othersSentence({ yes: 2, unsure: 1, no: 1 })).toBe("2 other people can see it, 1 isn't sure and 1 can't.");
    expect(othersSentence({ yes: 2, unsure: 1, no: 0 })).toBe("2 other people can see it and 1 isn't sure.");
    expect(othersSentence({ yes: 1, unsure: 0, no: 0 })).toBe("1 other person can see it.");
    expect(othersSentence({ yes: 0, unsure: 2, no: 1 })).toBe("2 other people aren't sure and 1 can't see it.");
    expect(othersSentence({ yes: 0, unsure: 0, no: 3 })).toBe("3 other people can't see it.");
    expect(othersSentence({ yes: 0, unsure: 0, no: 0 })).toBe("Nobody else has answered yet.");
  });
});
