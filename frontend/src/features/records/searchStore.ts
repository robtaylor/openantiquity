import { create } from "zustand";

/**
 * What the record search panel is searching for. Kept while the panel is
 * closed, so that a record opened from the results and closed again brings
 * the same search back.
 */
export type SearchScope = "view" | "everywhere";

export interface RecordSearchState {
  q: string;
  sources: readonly string[];
  categories: readonly string[];
  scope: SearchScope;
  set: (change: Partial<Pick<RecordSearchState, "q" | "sources" | "categories" | "scope">>) => void;
}

export const useRecordSearch = create<RecordSearchState>()((set) => ({
  q: "",
  sources: [],
  categories: [],
  scope: "view",
  set: (change) => set(change),
}));
