/**
 * The facts the notices state that come from `/meta` rather than the page:
 * the minimum age and its bands, the sign-in providers on offer, and where
 * the contribution licence can be read.
 */

import type { Meta } from "../../api/meta.js";

/** Each band the backend knows, by its youngest age and how it is said. */
const BANDS: Record<string, { youngest: number; words: string }> = {
  "16_17": { youngest: 16, words: "16 or 17" },
  "18_plus": { youngest: 18, words: "18 and over" },
};

/** The bands the backend sends that this build knows, youngest first. */
function knownBands(meta: Meta): { youngest: number; words: string }[] {
  // Older documents lack the list. The backend's default minimum is 16, which accepts both bands.
  const ids = meta.auth.age_bands ?? ["16_17", "18_plus"];
  return ids.flatMap((id) => BANDS[id] ?? []).sort((a, b) => a.youngest - b.youngest);
}

/** The youngest age a contributor may be. */
export function minimumAge(meta: Meta): number {
  return knownBands(meta)[0]?.youngest ?? 18;
}

/** Whether members aged 16 or 17 may contribute, and so get the rules that apply to them. */
export function takesUnder18s(meta: Meta): boolean {
  return minimumAge(meta) < 18;
}

/** "16 or 17, or 18 and over", or "18 and over". */
export function ageBandWords(meta: Meta): string {
  // A band can hold "or" itself, so each is set off with a comma.
  return knownBands(meta)
    .map((band) => band.words)
    .join(", or ");
}

/** "A", "A or B", "A, B or C". */
export function orList(items: readonly string[]): string {
  if (items.length <= 1) return items.join("");
  return `${items.slice(0, -1).join(", ")} or ${items.at(-1)}`;
}

/** The labels of the outside sign-in providers on offer, not counting the emailed link. */
export function signInProviders(meta: Meta): string[] {
  return meta.auth.providers
    .filter((provider) => provider.enabled && provider.id !== "email")
    .map((provider) => provider.label);
}

/** Whether an emailed sign-in link is on offer. */
export function offersEmailLink(meta: Meta): boolean {
  return meta.auth.providers.some((provider) => provider.id === "email" && provider.enabled);
}

/** Where licences can be read, by the name `/meta` gives them. */
const LICENCE_ADDRESSES: Record<string, string> = {
  "CC BY 4.0": "https://creativecommons.org/licenses/by/4.0/",
};

/** Where the contribution licence can be read, or null for one this build doesn't know. */
export function licenceAddress(licence: string): string | null {
  return LICENCE_ADDRESSES[licence] ?? null;
}
