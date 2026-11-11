import { beforeEach, describe, expect, it } from "vitest";
import { resetDraftsForTests } from "../drafts/store.js";
import { answerDrafts, discardAnswerDrafts } from "../finding/secondLook/answerDrafts.js";
import { CARD_STORAGE_KEY, readStoredCard, useReviewStore } from "./reviewStore.js";
import type { ReviewCard } from "./types.js";

const CARD: ReviewCard = {
  public_id: "f-ring",
  place: { lon: -1.8542, lat: 51.4286, grid_ref: "SU 1025 6996" },
  view_state: { layer: "slope", zoom: 16.5, bearing: 0, pitch: 0, sun_azimuth: 200, sun_altitude: 30 },
};

function stored(): string | null {
  return sessionStorage.getItem(CARD_STORAGE_KEY);
}

beforeEach(() => {
  localStorage.clear();
  sessionStorage.clear();
  resetDraftsForTests();
  useReviewStore.getState().reset();
});

describe("the card kept for a provider's sign-in", () => {
  it("is not written while the card has no draft answer", () => {
    useReviewStore.getState().show(CARD);
    expect(stored()).toBeNull();
  });

  it("is written once the answer is a draft, and removed when the draft goes", () => {
    useReviewStore.getState().show(CARD);
    answerDrafts.put({ public_id: CARD.public_id, answer: { visible: "unsure" } });
    expect(JSON.parse(stored() ?? "null")).toMatchObject({ public_id: "f-ring" });
    discardAnswerDrafts(CARD.public_id);
    expect(stored()).toBeNull();
  });

  it("is removed when the person moves off the card", () => {
    useReviewStore.getState().show(CARD);
    answerDrafts.put({ public_id: CARD.public_id, answer: { visible: "yes" } });
    useReviewStore.getState().next();
    expect(stored()).toBeNull();
  });

  it("is read back only while its draft is there, and a stale copy is removed", () => {
    sessionStorage.setItem(CARD_STORAGE_KEY, JSON.stringify(CARD));
    expect(readStoredCard()).toBeNull();
    expect(stored()).toBeNull();

    // As after a reload: the draft is in localStorage, and the copy in sessionStorage.
    answerDrafts.put({ public_id: CARD.public_id, answer: { visible: "yes" } });
    sessionStorage.setItem(CARD_STORAGE_KEY, JSON.stringify(CARD));
    expect(readStoredCard()).toEqual(CARD);
    expect(stored()).not.toBeNull();
  });

  it("removes a copy that can't be read", () => {
    sessionStorage.setItem(CARD_STORAGE_KEY, "{not json");
    expect(readStoredCard()).toBeNull();
    expect(stored()).toBeNull();
  });
});
