import { useQuery } from "@tanstack/react-query";
import { useEffect } from "react";
import { ApiError, isTransient } from "../../api/client.js";
import { useMapStore } from "../../map/store.js";
import { useMapCover, visibleCentre } from "../../map/visibleArea.js";
import { listDrafts } from "../drafts/store.js";
import { nearFrom } from "../review/queue.js";
import { fetchNextSquare, type Square } from "./api.js";
import { scanKeys } from "./keys.js";
import { useScanStore } from "./scanStore.js";
import { squareDrafts } from "./squareDrafts.js";

export type NextSquareStatus =
  | { kind: "loading" }
  | { kind: "square"; square: Square }
  /** No square left to scan within reach of where the map is. */
  | { kind: "none" }
  /** The server is turning people away for now, or isn't answering. */
  | { kind: "busy"; retry: () => void }
  | { kind: "error"; error: Error; retry: () => void };

/** The middle of the part of the map the person can see, rounded, for `GET /squares/next`. */
export function nearHere(): [number, number] | null {
  return nearFrom(visibleCentre(useMapStore.getState().camera, useMapCover.getState().cover));
}

/** Ask for a new square near the middle of the map. */
export function askForSquare(): void {
  useScanStore.getState().ask(nearHere());
}

/**
 * Squares the server shouldn't offer: those done or passed in this visit,
 * and those waiting as drafts in this browser, which the server hasn't heard
 * of. Read when the request goes, so it is as fresh as can be.
 */
export function squaresToLeaveOut(): string[] {
  const drafted = listDrafts().flatMap((draft) => {
    const data = squareDrafts.read(draft);
    return data ? [data.square] : [];
  });
  return [...new Set([...drafted, ...useScanStore.getState().passed])];
}

function isBusy(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 429 || isTransient(error));
}

/**
 * The square to look over, from `GET /squares/next`. The first visit asks
 * near where the map is. After that a square is asked for only when the
 * person asks for the next one, and it lives in the scan store, so leaving
 * for the layer panel or to mark a finding comes back to the same square.
 */
export function useNextSquare(): NextSquareStatus {
  const ticket = useScanStore((state) => state.ticket);
  const near = useScanStore((state) => state.near);
  const current = useScanStore((state) => state.current);

  useEffect(() => {
    if (ticket === 0 && current === null) askForSquare();
  }, [ticket, current]);

  const query = useQuery({
    queryKey: scanKeys.next(ticket),
    queryFn: ({ signal }) => fetchNextSquare({ near, exclude: squaresToLeaveOut() }, signal),
    enabled: ticket > 0 && current === null,
    staleTime: Number.POSITIVE_INFINITY,
    gcTime: 60_000,
    // Only a server error is worth another go at once. A busy server is asked again when the person says.
    retry: (failures, error) => failures < 1 && isTransient(error),
  });

  const square = current === null ? query.data : undefined;
  useEffect(() => {
    if (square) useScanStore.getState().show(square);
  }, [square]);

  if (current) return { kind: "square", square: current };
  if (query.isError && !query.isFetching) {
    const error = query.error;
    const retry = () => void query.refetch();
    if (error instanceof ApiError && error.code === "no_square_available") return { kind: "none" };
    if (isBusy(error)) return { kind: "busy", retry };
    return { kind: "error", error, retry };
  }
  return { kind: "loading" };
}
