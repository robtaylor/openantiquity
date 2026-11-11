/**
 * A person's page in words: what each contribution was, where each point
 * came from, and how long they have been a member. Built only from what the
 * server sent, with steps and evidence kinds taken from `/meta`. `/meta` has
 * no words for point reasons, so they are written here.
 */

import type { Meta } from "../../api/meta.js";
import { labelOf, lowerFirst } from "../finding/describe.js";
import type { Contribution } from "./api.js";

/** "You added an aerial photo", "Commented", for the line under a finding. */
export function contributionWords(meta: Meta, item: Contribution, mine: boolean): string {
  switch (item.kind) {
    case "evidence": {
      const kind = item.subkind ? lowerFirst(labelOf(meta.vocab.evidence_kinds, item.subkind)) : "evidence";
      return `${mine ? "You added" : "Added"} ${/^[aeiou]/i.test(kind) ? "an" : "a"} ${kind}`;
    }
    case "comment":
      return mine ? "You commented" : "Commented";
    case "mention": {
      const kind = item.subkind ? lowerFirst(labelOf(meta.vocab.mention_kinds, item.subkind)) : "mention";
      return `${mine ? "You linked" : "Linked"} ${/^[aeiou]/i.test(kind) ? "an" : "a"} ${kind} about it`;
    }
    case "second_look":
      return "You took a second look";
  }
}

const TIER_REASON = /^tier_(.+)$/;
const ENDORSED_REASON = /^evidence_endorsed_\d+$/;

/** Where a point came from, in a sentence, from its `reason` (`services/reputation.py`). */
export function pointWords(meta: Meta, reason: string): string {
  const tier = TIER_REASON.exec(reason)?.[1];
  if (tier !== undefined) return `Your finding reached ${labelOf(meta.vocab.tiers, tier)}`;
  if (ENDORSED_REASON.test(reason)) return "Two people endorsed evidence you added";
  switch (reason) {
    case "known_record":
      return "Your finding matched a known record";
    case "observation_corroborated":
      return "Your second look agreed with how it turned out";
    case "observation_ruled_out":
      return "Your second look agreed that it was explained";
    case "second_looks":
      return "Your second looks agreed with how findings turned out";
    default:
      return reason.replaceAll("_", " ");
  }
}

/** "1 point", "2.5 points". */
export function pointsWords(points: number): string {
  const rounded = Math.round(points * 10) / 10;
  return `${rounded} ${rounded === 1 ? "point" : "points"}`;
}

const JOINED = new Intl.DateTimeFormat("en-GB", { month: "long", year: "numeric", timeZone: "UTC" });

/** "Joined November 2026". */
export function joinedWords(iso: string): string {
  const date = new Date(iso);
  return Number.isNaN(date.getTime()) ? "" : `Joined ${JOINED.format(date)}`;
}
