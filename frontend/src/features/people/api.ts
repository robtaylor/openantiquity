/**
 * A person's public page: `GET /users/{handle}` and its lists. Every shape
 * comes from the generated schema, and each is shown exactly as the server
 * sends it. Someone aged 16 or 17 comes with their handle as their name and
 * no picture or bio (Decision 0009). Second looks and points are listed
 * only to the person themselves (Decisions 0008 and 0010): for anyone else
 * the count is null and the lists aren't asked for.
 */

import { ApiError, apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

export type Profile = Schemas["fieldclub__schemas__people__ProfileOut"];
export type ProfileCounts = Schemas["ProfileCounts"];
export type Contribution = Schemas["ContributionOut"];
export type ContributionKind = Schemas["ContributionKind"];
export type ContributionPage = Schemas["Page_ContributionOut_"];
export type Point = Schemas["PointOut"];
export type PointPage = Schemas["Page_PointOut_"];
export type PersonFindingsPage = Schemas["Page_FindingSummary_"];

/** How many items each list asks for at a time. */
export const PEOPLE_PAGE_SIZE = 20;

/** The address of someone's page in the app. */
export function profilePath(handle: string): string {
  return `/u/${encodeURIComponent(handle)}`;
}

function userUrl(handle: string, rest = ""): string {
  return `/users/${encodeURIComponent(handle)}${rest}`;
}

export function fetchProfile(handle: string, signal?: AbortSignal): Promise<Profile> {
  return apiFetch<Profile>(userUrl(handle), { signal });
}

/** True for the server's "nobody by that handle": a wrong link, a deleted account or a banned one. */
export function isNoSuchPerson(error: unknown): boolean {
  return error instanceof ApiError && (error.code === "user_not_found" || error.status === 404);
}

/** Their findings, newest first, as this viewer may see them. */
export function fetchPersonFindings(
  handle: string,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<PersonFindingsPage> {
  return apiFetch<PersonFindingsPage>(userUrl(handle, "/findings"), {
    query: { limit: PEOPLE_PAGE_SIZE, cursor },
    signal,
  });
}

/**
 * What they helped with: evidence, comments and mentions together when
 * `kind` is null, or the findings they took a second look at, which the
 * server lists only for the person themselves.
 */
export function fetchContributions(
  handle: string,
  kind: "second_look" | null,
  cursor: string | null,
  signal?: AbortSignal,
): Promise<ContributionPage> {
  return apiFetch<ContributionPage>(userUrl(handle, "/contributions"), {
    query: { kind, limit: PEOPLE_PAGE_SIZE, cursor },
    signal,
  });
}

/** Where each of their points came from, newest first. Only for the person themselves. */
export function fetchPoints(handle: string, cursor: string | null, signal?: AbortSignal): Promise<PointPage> {
  return apiFetch<PointPage>(userUrl(handle, "/points"), { query: { limit: PEOPLE_PAGE_SIZE, cursor }, signal });
}
