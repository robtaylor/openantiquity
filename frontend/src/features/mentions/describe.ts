/**
 * What a mention says, in words, and the address it opens. Plain functions,
 * so each rule is tested on its own.
 */

import { ApiError } from "../../api/client.js";
import { reasonOf } from "../finding/feedback.js";
import { MAP_LINK_WORDS } from "../finding/positionInText.js";
import type { Mention, MentionPreview } from "./types.js";

/** The longest start time the server takes: a start beyond twelve hours is a typo. */
export const MAX_START_SECONDS = 12 * 3600;
/** The longest note the server keeps. */
export const NOTE_MAX = 1000;
/** The longest address the server takes. */
export const URL_MAX = 2000;

function isWebAddress(url: URL): boolean {
  return url.protocol === "https:" || url.protocol === "http:";
}

/** 754 as "12:34", 3723 as "1:02:03". */
export function startWords(seconds: number): string {
  const whole = Math.max(0, Math.floor(seconds));
  const hours = Math.floor(whole / 3600);
  const minutes = Math.floor((whole % 3600) / 60);
  const rest = String(whole % 60).padStart(2, "0");
  return hours > 0 ? `${hours}:${String(minutes).padStart(2, "0")}:${rest}` : `${minutes}:${rest}`;
}

/**
 * A start time as someone types it: "12:34", "1:02:03" or a number of
 * seconds. Null for an empty field, NaN for anything else.
 */
export function parseStart(text: string): number | null {
  const trimmed = text.trim();
  if (trimmed === "") return null;
  if (!/^\d+(?::\d{1,2}){0,2}$/.test(trimmed)) return Number.NaN;
  const parts = trimmed.split(":").map(Number);
  // Every part after the first is minutes or seconds, so under 60.
  if (parts.slice(1).some((part) => part >= 60)) return Number.NaN;
  const seconds = parts.reduce((total, part) => total * 60 + part, 0);
  return seconds <= MAX_START_SECONDS ? seconds : Number.NaN;
}

/**
 * The address a mention opens: its canonical address, at the start time for
 * a YouTube or Vimeo video. Null when the server withholds the address from
 * this viewer (it could show where a protected finding is), and for anything
 * that isn't a web address, which the server never sends, so a link can
 * never run script.
 */
export function mentionHref(mention: Pick<Mention, "canonical_url" | "start_seconds">): string | null {
  if (mention.canonical_url === null) return null;
  let url: URL;
  try {
    url = new URL(mention.canonical_url);
  } catch {
    return null;
  }
  if (!isWebAddress(url)) return null;
  const start = mention.start_seconds;
  if (start !== null && start > 0) {
    const host = url.hostname.replace(/^www\./, "");
    if (host === "youtube.com" || host === "m.youtube.com") url.searchParams.set("t", `${start}s`);
    else if (host === "vimeo.com") url.hash = `t=${start}s`;
  }
  return url.href;
}

/** A picture we may show: only one served over https. The server keeps no other kind. */
export function safeThumbnail(url: string | null): string | null {
  if (url === null) return null;
  try {
    return new URL(url).protocol === "https:" ? url : null;
  } catch {
    return null;
  }
}

/** The address without its scheme, for a mention with no title. */
export function shortAddress(address: string): string {
  return address.replace(/^https?:\/\//, "").replace(/\/$/, "");
}

/** Said of a mention whose address this viewer isn't sent. */
export const ADDRESS_WITHHELD =
  "Its address is shown only to people who see this finding's exact place, because it could show where it is.";

/** What to call a mention: its title, or its address when its page gave none. */
export function mentionTitle(mention: Pick<Mention, "title" | "canonical_url">): string {
  if (mention.title !== null) return mention.title;
  return mention.canonical_url === null ? "A link" : shortAddress(mention.canonical_url);
}

/** Why the preview found nothing, in a sentence, or null when it found the title. */
export function previewProblem(preview: Pick<MentionPreview, "fetch_status" | "title">): string | null {
  switch (preview.fetch_status) {
    case "ok":
      return preview.title === null ? "Its page doesn't give a title, so it will be listed by its address." : null;
    case "refused":
      return "We don't fetch pages from that site, so it will be listed by its address alone.";
    case "failed":
      return "Its page didn't answer, so we couldn't get its title. You can still save it with its address alone.";
  }
}

/** Where a refusal belongs on the form: beside a field, or above the buttons. */
export type MentionField = "url" | "start" | "note" | null;

export interface MentionFailure {
  field: MentionField;
  message: string;
}

const FIELD_OF: Record<string, MentionField> = {
  "body.url": "url",
  "body.start_seconds": "start",
  "body.note": "note",
};

/** A refused or failed mention request, in plain words, and the field it is about. */
export function mentionFailure(error: unknown): MentionFailure {
  if (!(error instanceof ApiError)) return { field: null, message: reasonOf(error) };
  switch (error.code) {
    case "invalid_address":
      return { field: "url", message: "That isn't a web address or a DOI we can link to." };
    case "mention_exists":
      return { field: "url", message: "That's already listed on this finding." };
    case "mention_hidden":
      return {
        field: "url",
        message: "A moderator has hidden that address on this finding, so it can't be added again.",
      };
    case "position_in_text":
      return { field: "url", message: MAP_LINK_WORDS };
    case "finding_withdrawn":
      return { field: null, message: "This finding has been withdrawn, so it takes no more mentions." };
    case "finding_not_found":
      return { field: null, message: "This finding can't be found any more. A moderator may have hidden it." };
    case "rate_limited":
      return { field: null, message: "You've added a lot in the last hour. Try again a little later." };
    case "mention_not_found":
      return { field: null, message: "That mention has already gone." };
    case "mention_forbidden":
      return { field: null, message: "Only the person who added a mention can remove it." };
    case "validation_error": {
      const [first] = error.fields;
      return { field: (first && FIELD_OF[first.field]) ?? null, message: first?.message ?? error.message };
    }
    default:
      return { field: null, message: reasonOf(error) };
  }
}
