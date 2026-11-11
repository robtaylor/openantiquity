import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { useLocation } from "react-router";
import { terrainKeys } from "../keys.js";
import { fetchProfile } from "./api.js";
import { LINE_PARAM, type LngLat, PROFILE_PATH, parseLine } from "./line.js";

export interface ProfileLine {
  /** True on the profile panel's address. */
  open: boolean;
  points: LngLat[];
}

/** The line in the address, when the profile panel's address is the one showing. */
export function useProfileLine(): ProfileLine {
  const { pathname, search } = useLocation();
  const open = pathname === PROFILE_PATH;
  const raw = open ? new URLSearchParams(search).get(LINE_PARAM) : null;
  // Parsed once per address, so the same line is the same array from render to render.
  const points = useMemo(() => parseLine(raw), [raw]);
  return { open, points };
}

/**
 * The heights along a line, from `POST /terrain/profile`. The panel and the
 * map both ask, and share the one answer. A failed profile is not retried:
 * the panel says what went wrong and offers to try again.
 */
export function useProfileQuery(points: readonly LngLat[]) {
  return useQuery({
    queryKey: terrainKeys.profile(points),
    queryFn: ({ signal }) => fetchProfile(points, signal),
    enabled: points.length >= 2,
    staleTime: Number.POSITIVE_INFINITY,
    retry: false,
  });
}
