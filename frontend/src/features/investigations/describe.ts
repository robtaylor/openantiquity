/**
 * What the interface says about investigations, and what it offers whom.
 *
 * `/meta` has no words for visibility, roles, item kinds or why an item is
 * unavailable, so they are written here, keyed by the schema's own unions:
 * a value the schema gains doesn't build until it has words. The offers
 * follow the server's rules (services/investigations.py), so nothing is
 * offered that the server would refuse: only the owner changes visibility,
 * members and deletes; the owner and editors change everything else; a
 * private investigation has one member (Decision 0009).
 */

import { HANDLE_PATTERN } from "../account/handles.js";
import type { InvestigationDetail, ItemKind, Member, Role, Unavailable, Visibility } from "./api.js";

export const VISIBILITY: Record<Visibility, { label: string; says: string }> = {
  private: {
    label: "Private",
    says: "Only you can find it. Nobody else can be invited until it's public or unlisted.",
  },
  unlisted: {
    label: "Unlisted",
    says: "Anyone with the link can read it, and moderators can find it, but it isn't listed.",
  },
  public: {
    label: "Public",
    says: "Anyone can find it in the list of investigations and read it, signed in or not.",
  },
};

/** The roles someone can be invited as. */
export const INVITABLE = ["editor", "viewer"] as const satisfies readonly Role[];

/** Every visibility, most closed first. */
export const VISIBILITIES = ["private", "unlisted", "public"] as const satisfies readonly Visibility[];

export const ROLE: Record<Role, { label: string; says: string }> = {
  owner: { label: "Owner", says: "The owner started it, and decides who works on it and who can see it." },
  editor: { label: "Editor", says: "Editors can add, change, reorder and remove what's in it." },
  viewer: { label: "Reader", says: "Readers can read it and download it, and change nothing." },
};

export const KIND_LABEL: Record<ItemKind, string> = {
  finding: "Finding",
  record: "Heritage record",
  view: "Map view",
  note: "Note",
  reference: "Reference",
  profile: "Height profile",
};

export const UNAVAILABLE: Record<Unavailable, string> = {
  hidden: "A moderator has hidden this finding.",
  withdrawn: "Its finder has withdrawn this finding.",
  gone: "This record has left the index since it was added.",
  near_protected: "It is near a protected finding, so only people who see that finding's exact place can open it.",
};

/**
 * Said on a notebook that holds a finding the viewer sees only as its square:
 * the server has hidden or blurred what was written and drawn near it.
 */
export const GENERALISED_NOTICE =
  "This notebook holds a finding you see only as its 1 km square. To keep its place private, map views and height profiles near it are held back, its area is shown as the whole 1 km squares it covers, and grid references written in it are hidden. What is hidden from you is kept when you edit: leave each [position hidden] where it is.";

/** What the viewer may do with one investigation. */
export interface Powers {
  /** Change the title, summary, notes, area and items. */
  edit: boolean;
  /** Change visibility, invite and remove people, and delete it. */
  own: boolean;
  /** Leave it: a member who isn't the owner. */
  leave: boolean;
  /** Accept or decline an invitation that waits. */
  answer: boolean;
}

export function powersOf(detail: Pick<InvestigationDetail, "my_role" | "invited_as" | "hidden">): Powers {
  const role = detail.my_role;
  return {
    edit: role === "owner" || role === "editor",
    own: role === "owner",
    leave: role === "editor" || role === "viewer",
    answer: role === null && detail.invited_as !== null,
  };
}

/**
 * The visibilities the owner may choose now. Private only while nobody else
 * is a member or invited, because a private investigation has one member, so
 * never while the members are `undefined`, not known yet or not loaded.
 */
export function visibilityChoices(
  detail: Pick<InvestigationDetail, "visibility">,
  members: readonly Member[] | undefined,
) {
  const alone = members?.every((member) => member.role === "owner") === true;
  return VISIBILITIES.filter((id) => id !== detail.visibility && (id !== "private" || alone));
}

/** True when the owner may invite someone: never to a private investigation. */
export function mayInvite(powers: Powers, detail: Pick<InvestigationDetail, "visibility">): boolean {
  return powers.own && detail.visibility !== "private";
}

/** A handle as typed, without a leading @, or null when it can't be one. */
export function cleanHandle(text: string): string | null {
  const handle = text.trim().replace(/^@/, "");
  return HANDLE_PATTERN.test(handle) ? handle : null;
}

const DATE = new Intl.DateTimeFormat("en-GB", { day: "numeric", month: "long", year: "numeric" });

export function dateText(value: string): string {
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? "" : DATE.format(date);
}

/** "3 items", "1 item", "Nothing in it yet". */
export function itemCountText(count: number): string {
  if (count === 0) return "Nothing in it yet";
  return `${count} ${count === 1 ? "item" : "items"}`;
}

/** Said under every field that takes Markdown. */
export const MARKDOWN_HINT =
  "You can use # for a heading, **bold**, *italic*, - for a list and [words](https://…) for a link.";
