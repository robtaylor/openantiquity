/**
 * The kinds of help on offer, so people can pick the sort of work they like
 * (docs/DESIGN.md, "Five minutes at a time"): second looks, one kind for
 * each strand of desk evidence (old maps, aerial photos, heritage records
 * and so on), going to look on the ground, and finding it on record.
 *
 * The strands, their evidence kinds and which steps a second look meets
 * come from `/meta` (`vocab.next_steps`, read through `finding/describe.ts`,
 * whose `isAnswerStep` decides which steps are blind). The server sends the
 * steps grouped by code (`GET /review/tasks`), and the evidence step is
 * split here by the strands each finding is missing. `/meta` has no words
 * for the step codes, or for the kinds of people who do each kind of work,
 * so those are written here: a known gap.
 */

import {
  BookOpen,
  Eye,
  Footprints,
  HandHelping,
  Layers,
  Link2,
  type LucideIcon,
  Map as MapIcon,
  Plane,
  ScrollText,
} from "lucide-react";
import type { Meta } from "../../api/meta.js";
import { isAnswerStep, stepRule } from "../finding/describe.js";
import { findingStepPath } from "../finding/stepLink.js";
import type { TaskGroup, TaskItem } from "./api.js";

export interface HelpKind {
  /** Its address under `/help/`. */
  id: string;
  /** What the people who do it are called, such as "Map detectives". */
  name: string;
  /** What the work is, in a sentence. */
  line: string;
  /** The server's step code. Second looks have several, and use the queue instead. */
  code: string;
  /** The evidence strand, for a kind of desk evidence. */
  strand: string | null;
  /** Done blind, through the second-look queue, never from a list that names the finding. */
  blind: boolean;
  icon: LucideIcon;
}

export const SECOND_LOOK_KIND = "second-look";

const EVIDENCE_STEP = "need_strand";

interface Words {
  name: string;
  line: string;
  icon: LucideIcon;
}

const STRAND_WORDS: Record<string, Words> = {
  lidar: {
    name: "Layer lookers",
    line: "Layer lookers check a finding in another LIDAR view, or with the light from another side.",
    icon: Layers,
  },
  aerial: { name: "Sky checkers", line: "Sky checkers look for cropmarks and shadows in aerial photos.", icon: Plane },
  historic_map: {
    name: "Map detectives",
    line: "Map detectives check old maps for a feature drawn or named there.",
    icon: MapIcon,
  },
  records: {
    name: "Record matchers",
    line: "Record matchers link findings to the heritage records that already describe them.",
    icon: Link2,
  },
  literature: { name: "Readers", line: "Readers look for a mention in books, articles and reports.", icon: BookOpen },
};

const CODE_WORDS: Record<string, Words> = {
  need_ground: {
    name: "Field walkers",
    line: "Field walkers go and look, with the landowner's permission, and say what they found on the ground.",
    icon: Footprints,
  },
  need_official: {
    name: "Record keepers",
    line: "Record keepers find it in a Historic Environment Record (the local list of known sites), a designation or a publication.",
    icon: ScrollText,
  },
};

const SECOND_LOOK: HelpKind = {
  id: SECOND_LOOK_KIND,
  name: "Second looks",
  line: "Look at a finding in the view its finder used, and say whether you can see it. You're shown what they thought afterwards, so your eye stays your own.",
  code: "need_observers",
  strand: null,
  blind: true,
  icon: Eye,
};

/** "need_photo" becomes "Need photo". */
function codeName(code: string): string {
  const words = code.replaceAll("_", " ");
  return words.charAt(0).toUpperCase() + words.slice(1);
}

/** Every kind of help, in the order offered, including kinds that have nothing waiting just now. */
export function helpKinds(meta: Meta, groups: readonly TaskGroup[]): HelpKind[] {
  const kinds: HelpKind[] = [SECOND_LOOK];
  // The strands of the evidence step, in the vocabulary's order.
  const wanted = stepRule(meta, EVIDENCE_STEP)?.evidence_kinds ?? [];
  const strands: string[] = [];
  for (const kind of meta.vocab.evidence_kinds) {
    if (wanted.includes(kind.id) && !strands.includes(kind.strand)) strands.push(kind.strand);
  }
  for (const strand of strands) {
    const first = meta.vocab.evidence_kinds.find((kind) => kind.strand === strand);
    const words = STRAND_WORDS[strand] ?? {
      name: first?.label ?? codeName(strand),
      line: first?.hint ?? "",
      icon: HandHelping,
    };
    kinds.push({ id: strand, ...words, code: EVIDENCE_STEP, strand, blind: false });
  }
  for (const [code, words] of Object.entries(CODE_WORDS))
    kinds.push({ id: code, ...words, code, strand: null, blind: false });
  // A step this build has no words for still gets listed, under the server's own prompt.
  for (const group of groups) {
    if (isAnswerStep(meta, group.code) || kinds.some((kind) => kind.code === group.code)) continue;
    kinds.push(codeKind(group.code, group.items.find((item) => item.step)?.step?.prompt));
  }
  return kinds;
}

/** Step codes as the server writes them, such as `need_ground`. */
const STEP_CODE = /^need_[a-z_]+$/;

/** A kind for a step code this build has no words for, named from the code. */
export function codeKind(code: string, prompt?: string): HelpKind {
  const line = prompt ?? "Findings that need this next.";
  return { id: code, name: codeName(code), line, code, strand: null, blind: false, icon: HandHelping };
}

/** The kind an address names: one of ours, or a step code this build has no words for. */
export function kindFromAddress(meta: Meta, id: string): HelpKind | null {
  return findKind(helpKinds(meta, []), id) ?? (STEP_CODE.test(id) && !isAnswerStep(meta, id) ? codeKind(id) : null);
}

export function findKind(kinds: readonly HelpKind[], id: string): HelpKind | undefined {
  return kinds.find((kind) => kind.id === id);
}

/** The tasks of this kind among those loaded. Second looks are never listed by their finding. */
export function kindTasks(kind: HelpKind, groups: readonly TaskGroup[]): TaskItem[] {
  if (kind.blind) return [];
  const items = groups.filter((group) => group.code === kind.code).flatMap((group) => group.items);
  // Only a step that names its finding is listed, however the server groups it.
  const named = items.filter((item) => item.finding !== null && item.step !== null);
  return kind.strand === null ? named : named.filter((item) => item.step?.missing_strands?.includes(kind.strand ?? ""));
}

export interface KindCount {
  count: number;
  /** True when more of this kind may be waiting than were loaded. */
  more: boolean;
}

/**
 * How many findings want this kind of help. A whole group's count is the
 * server's. A strand's is what the loaded page of the evidence group holds,
 * and may be more. Second looks count the busiest of their groups, because
 * one finding can want several of them at once.
 */
export function kindCount(meta: Meta, kind: HelpKind, groups: readonly TaskGroup[]): KindCount {
  if (kind.blind) {
    const totals = groups.filter((group) => isAnswerStep(meta, group.code)).map((group) => group.total);
    return { count: Math.max(0, ...totals), more: false };
  }
  const group = groups.find((each) => each.code === kind.code);
  if (!group) return { count: 0, more: false };
  if (kind.strand === null) return { count: group.total, more: false };
  return { count: kindTasks(kind, [group]).length, more: group.next_cursor !== null };
}

export function countWords({ count, more }: KindCount): string {
  if (count === 0) return more ? "Some findings" : "Nothing waiting";
  const noun = count === 1 && !more ? "finding" : "findings";
  return more ? `${count} or more ${noun}` : `${count} ${noun}`;
}

/** A task's finding, opened with the form for this kind of work ready. */
export function taskPath(kind: HelpKind, item: TaskItem): string {
  return findingStepPath(item.public_id, item.code, kind.strand);
}
