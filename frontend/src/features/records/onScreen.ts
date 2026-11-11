import { create } from "zustand";

/**
 * What the records part of the map has on screen, for the credits. Written
 * by `useRecordsOnMap` whenever the map comes to rest, and by the live
 * sources as they answer.
 */
export interface RecordsOnScreen {
  /**
   * Keys of the stored sources whose records, or counts of records, are drawn
   * on screen. Null until the map has said, and the credits then name every
   * source, so nothing is ever shown uncredited.
   */
  sources: readonly string[] | null;
  /** The attribution of each live source that has records on the map. */
  liveAttributions: readonly string[];
  setSources: (sources: readonly string[] | null) => void;
  setLiveAttributions: (lines: readonly string[]) => void;
}

function sameList(a: readonly string[] | null, b: readonly string[] | null): boolean {
  if (a === null || b === null) return a === b;
  return a.length === b.length && a.every((value, index) => value === b[index]);
}

export const useRecordsOnScreen = create<RecordsOnScreen>()((set, get) => ({
  sources: null,
  liveAttributions: [],
  setSources: (sources) => {
    const sorted = sources === null ? null : [...new Set(sources)].sort();
    if (!sameList(get().sources, sorted)) set({ sources: sorted });
  },
  setLiveAttributions: (lines) => {
    if (!sameList(get().liveAttributions, lines)) set({ liveAttributions: [...lines] });
  },
}));
