import { create } from "zustand";
import { onPersonChanged } from "../account/session.js";

/**
 * The photos this person has uploaded in this page that were waiting for
 * approval when the server answered. Evidence carries only a photo's id, not
 * whether it is approved, so this is how the uploader's own evidence can say
 * that its photo is still waiting. It is held in memory only, and forgotten
 * when the person changes.
 */
interface WaitingState {
  ids: ReadonlySet<number>;
  add: (mediaId: number) => void;
  clear: () => void;
}

export const useWaitingPhotos = create<WaitingState>()((set) => ({
  ids: new Set(),
  add: (mediaId) => set((state) => ({ ids: new Set([...state.ids, mediaId]) })),
  clear: () => set({ ids: new Set() }),
}));

onPersonChanged(() => useWaitingPhotos.getState().clear());

/** Who sees a photo before and after approval, in one sentence each (Decision 0009). */
export const WHO_SEES_WAITING =
  "Until a moderator or trusted member approves it, only you, moderators and trusted members can see it.";
export const WHO_SEES_APPROVED = "Once approved, everyone who can see this finding's exact place can see it.";
