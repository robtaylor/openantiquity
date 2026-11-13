/**
 * The kinds of activity, grouped the way the feed's filter offers them. The
 * kinds are the API's `ActivityKind`. `/meta` has no words for them, so the
 * names are written here, typed over every kind the feed lists: a new kind
 * in the schema doesn't build until it is given a group.
 */

import type { ActivityKind } from "./api.js";

/** A notification only, never in the feed (docs/ARCHITECTURE.md, "Events"). */
export type FeedKind = Exclude<ActivityKind, "investigation_invitation">;

export type KindGroupId = "findings" | "steps" | "looks" | "evidence" | "comments" | "mentions" | "investigations";

export interface KindGroup {
  id: KindGroupId;
  label: string;
  kinds: FeedKind[];
}

const GROUP_OF = {
  finding_created: "findings",
  tier_changed: "steps",
  state_changed: "steps",
  observation_added: "looks",
  evidence_added: "evidence",
  followup_logged: "evidence",
  comment_added: "comments",
  mention_added: "mentions",
  investigation_published: "investigations",
  shape_extended: "findings",
} as const satisfies Record<FeedKind, KindGroupId>;

const GROUP_LABELS: Record<KindGroupId, string> = {
  findings: "Findings marked or drawn further",
  steps: "Steps and states",
  looks: "Second looks",
  evidence: "Evidence and visits",
  comments: "Comments",
  mentions: "Mentions",
  investigations: "Investigations",
};

/** The groups, in the order the filter shows them. */
export const KIND_GROUPS: KindGroup[] = (Object.keys(GROUP_LABELS) as KindGroupId[]).map((id) => ({
  id,
  label: GROUP_LABELS[id],
  kinds: (Object.keys(GROUP_OF) as FeedKind[]).filter((kind) => GROUP_OF[kind] === id),
}));

/** The kinds to ask for, for the groups chosen. None chosen asks for every kind. */
export function kindsFor(groups: readonly KindGroupId[]): FeedKind[] {
  return KIND_GROUPS.filter((group) => groups.includes(group.id)).flatMap((group) => group.kinds);
}

export function isKindGroupId(value: string): value is KindGroupId {
  return Object.hasOwn(GROUP_LABELS, value);
}

/** Whether this build knows a kind the server sent. */
export function isActivityKind(value: unknown): value is ActivityKind {
  return typeof value === "string" && (Object.hasOwn(GROUP_OF, value) || value === "investigation_invitation");
}
