import { create } from "zustand";

/** What the coverage layer knows about the view, for the layer panel and the notice on the map. */
export interface CoverageSummary {
  /**
   * "idle": nothing asked. "wide": zoomed out too far to say square by square.
   * "loading", "ready" and "failed" follow the request.
   */
  status: "idle" | "wide" | "loading" | "ready" | "failed";
  /** The capture descriptions of the data in view, such as "2022 composite". */
  captures: string[];
  /** 5 km squares in view with no one-metre elevation, and squares in view in all. */
  gaps: number;
  cells: number;
}

export interface CoverageState {
  /** Whether the outline of where one-metre elevation exists is drawn. Off on every page load. */
  visible: boolean;
  summary: CoverageSummary;
  setVisible: (visible: boolean) => void;
  setSummary: (summary: CoverageSummary) => void;
}

export const IDLE_SUMMARY: CoverageSummary = { status: "idle", captures: [], gaps: 0, cells: 0 };

function sameSummary(a: CoverageSummary, b: CoverageSummary): boolean {
  return (
    a.status === b.status &&
    a.gaps === b.gaps &&
    a.cells === b.cells &&
    a.captures.length === b.captures.length &&
    a.captures.every((capture, i) => capture === b.captures[i])
  );
}

export const useCoverageStore = create<CoverageState>()((set, get) => ({
  visible: false,
  summary: IDLE_SUMMARY,
  setVisible: (visible) => set({ visible }),
  setSummary: (summary) => {
    if (!sameSummary(get().summary, summary)) set({ summary });
  },
}));
