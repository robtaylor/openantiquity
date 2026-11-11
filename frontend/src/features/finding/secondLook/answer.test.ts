// @vitest-environment node
import { describe, expect, it } from "vitest";
import { observationFixture } from "../../../test/fixtures/findingPage.js";
import { metaFixture as meta } from "../../../test/fixtures/meta.js";
import { type AnswerDraft, answerBody, explanationFor, newAnswer, sameAnswer, withCheck } from "./answer.js";

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
