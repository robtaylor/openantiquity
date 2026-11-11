/**
 * The shapes mentions arrive in, named from the generated `schema.d.ts`.
 * Nothing here is written by hand.
 */

import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

/** A video, article, podcast or paper that discusses a finding. */
export type Mention = Schemas["MentionOut"];
export type MentionPage = Schemas["Page_MentionOut_"];
/** What a mention of an address would show, fetched before anything is saved. */
export type MentionPreview = Schemas["MentionPreview"];
export type MentionIn = Schemas["MentionIn"];
export type MentionKindId = Schemas["MentionKind"];
/** `ok` when the title and the rest were fetched, `refused` or `failed` when they weren't. */
export type FetchStatus = Schemas["FetchStatus"];
/** A mention in the recent feed, with its finding as this viewer may see it. */
export type RecentMention = Schemas["RecentMention"];
export type RecentMentionPage = Schemas["Page_RecentMention_"];
export type MentionedFinding = Schemas["MentionedFinding"];
