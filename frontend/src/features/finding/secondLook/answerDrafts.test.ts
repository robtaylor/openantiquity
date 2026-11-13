import { beforeEach, describe, expect, it, vi } from "vitest";
import { observationFixture, revealFixture } from "../../../test/fixtures/findingPage.js";
import { saveWaitingDrafts } from "../../drafts/savers.js";
import { listDrafts, resetDraftsForTests, setDraftsViewer } from "../../drafts/store.js";
import { giveAnswer, revealAnswer } from "../api.js";
import { answerDrafts, parseAnswerDraft, useSavedAnswers } from "./answerDrafts.js";

vi.mock("../api.js", () => ({ giveAnswer: vi.fn(), revealAnswer: vi.fn() }));

const ME = "person:42";
const give = vi.mocked(giveAnswer);
const reveal = vi.mocked(revealAnswer);
const HELD = { revealed: false as const, observation: observationFixture({ visible: "unsure", revealed: false }) };

beforeEach(() => {
  localStorage.clear();
  resetDraftsForTests();
  useSavedAnswers.getState().clear();
  give.mockReset();
  reveal.mockReset();
  setDraftsViewer(ME);
});

describe("a second look kept as a draft", () => {
  it("is sent as the API takes it: the answer alone, then its detail with the reveal", async () => {
    const order: string[] = [];
    give.mockImplementation(async () => {
      order.push("answer");
      return HELD;
    });
    const revealed = revealFixture(observationFixture({ visible: "unsure", not_natural: true }));
    reveal.mockImplementation(async () => {
      order.push("detail");
      return revealed;
    });
    answerDrafts.put({
      public_id: "f-ring",
      answer: { visible: "unsure", not_natural: true },
      reveal: true,
      shape_revision: 2,
    });
    await saveWaitingDrafts(ME);
    expect(order).toEqual(["answer", "detail"]);
    // The answer names the shape revision it was given on, as it would have sent at once.
    expect(give).toHaveBeenCalledWith("f-ring", "unsure", 2);
    expect(reveal).toHaveBeenCalledWith("f-ring", { not_natural: true });
    expect(useSavedAnswers.getState().saved["f-ring"]).toMatchObject({ kind: "revealed", reveal: revealed });
    expect(listDrafts()).toEqual([]);
  });

  it("leaves an answer whose comparison wasn't asked for waiting for its detail", async () => {
    give.mockResolvedValue(HELD);
    answerDrafts.put({ public_id: "f-ring", answer: { visible: "unsure" }, reveal: false });
    await saveWaitingDrafts(ME);
    expect(reveal).not.toHaveBeenCalled();
    expect(useSavedAnswers.getState().saved["f-ring"]).toMatchObject({ kind: "held", observation: HELD.observation });
  });

  it("takes the reveal as it is when the answer was finished elsewhere", async () => {
    const revealed = revealFixture(observationFixture());
    give.mockResolvedValue(revealed);
    answerDrafts.put({ public_id: "f-ring", answer: { visible: "yes" }, reveal: true });
    await saveWaitingDrafts(ME);
    expect(reveal).not.toHaveBeenCalled();
    expect(useSavedAnswers.getState().saved["f-ring"]).toMatchObject({ kind: "revealed" });
  });

  it("reads a draft from before the two steps as one that asked for the reveal", () => {
    expect(parseAnswerDraft({ public_id: "f-ring", answer: { visible: "no" } })).toEqual({
      public_id: "f-ring",
      answer: { visible: "no" },
      reveal: true,
      shape_revision: null,
    });
    expect(parseAnswerDraft({ public_id: "f-ring", answer: { visible: "maybe" } })).toBeNull();
  });
});
