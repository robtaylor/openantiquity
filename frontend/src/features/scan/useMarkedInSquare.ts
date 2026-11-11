import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useSession } from "../account/session.js";
import { useKindDrafts } from "../drafts/savers.js";
import { findingDrafts, useSavedDrafts } from "../mark/findingDrafts.js";
import { fetchOwnFindingsIn, type Square } from "./api.js";
import { scanKeys } from "./keys.js";
import { inSquare } from "./square.js";

/**
 * How far before the square came up a finding saved to the server may be
 * dated and still count. The server's clock and the browser's can disagree.
 */
export const CLOCK_SLACK_MS = 5 * 60_000;

export interface MarkedInSquare {
  /** Findings marked in the square since it came up. */
  count: number;
  /** How many of them are drafts in this browser, not saved yet. */
  drafts: number;
}

/**
 * The findings marked in the square since it came up, with the marking
 * flow that every other mode uses: the person's own findings there that the
 * server has, dated from then on, and the finding drafts in this browser
 * placed in it since then. A draft saved after sign-in moves from one to the
 * other, and is asked for again when it does.
 */
export function useMarkedInSquare(square: Square, startedAt: number | null): MarkedInSquare {
  const { ready, me } = useSession();
  const handle = ready ? (me?.handle ?? null) : null;
  const since = startedAt ?? Date.now();
  const savedDrafts = useSavedDrafts((state) => state.count);
  const drafts = useKindDrafts(findingDrafts);

  const own = useQuery({
    queryKey: scanKeys.ownFindings(square.square, handle ?? "", savedDrafts),
    queryFn: ({ signal }) => {
      if (handle === null) throw new Error("Own findings were asked for with nobody signed in");
      return fetchOwnFindingsIn(square.bbox, handle, signal);
    },
    enabled: handle !== null,
    staleTime: 30_000,
  });

  return useMemo(() => {
    const drafted = drafts.filter(
      (draft) => Date.parse(draft.createdAt) >= since && inSquare(square.square, draft.data.point),
    ).length;
    const saved = (own.data?.items ?? []).filter(
      (finding) =>
        Date.parse(finding.created_at) >= since - CLOCK_SLACK_MS &&
        inSquare(square.square, [finding.location.lon, finding.location.lat]),
    ).length;
    return { count: drafted + saved, drafts: drafted };
  }, [drafts, own.data, since, square.square]);
}
