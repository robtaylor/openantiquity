/**
 * The shapes a finding's page works with, named from the generated
 * `schema.d.ts`. Nothing here is written by hand.
 */

import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

export type { FindingDetail } from "../findings/types.js";
export type Assessment = Schemas["AssessmentOut"];
export type NextStep = Schemas["NextStepOut"];
export type NextStepCode = Schemas["NextStepCode"];
export type Evidence = Schemas["EvidenceOut"];
export type EvidenceIn = Schemas["EvidenceIn"];
export type EvidenceKindId = Schemas["EvidenceKind"];
export type Stance = Schemas["Stance"];
export type Outcome = Schemas["Outcome"];
export type Relation = Schemas["Relation"];
export type Credit = Schemas["CreditOut"];
export type CreditKind = Credit["kind"];
export type PublicUser = Schemas["PublicUser"];
export type Observation = Schemas["ObservationOut"];
export type ObservationIn = Schemas["ObservationIn"];
export type ObservationPage = Schemas["Page_ObservationOut_"];
export type Visible = Schemas["Visible"];
export type ExplanationId = Schemas["Explanation"];
export type Reveal = Schemas["Reveal"];
export type Comparison = Schemas["Comparison"];
export type Tallies = Schemas["Tallies"];
export type Comment = Schemas["CommentOut"];
export type CommentPage = Schemas["Page_CommentOut_"];
export type FindingUpdate = Schemas["FindingUpdate"];
export type Suggestions = Schemas["Suggestions"];
export type SuggestedRecord = Schemas["SuggestedRecord"];
export type RecordSummary = Schemas["RecordSummary"];
export type RecordPage = Schemas["RecordPage"];
export type RecordOut = Schemas["RecordOut"];
export type Source = Schemas["fieldclub__schemas__records__SourceOut"];

/** The three answers to a second look, in the order they are offered. */
export const ANSWERS = ["yes", "unsure", "no"] as const satisfies readonly Visible[];

/** How evidence can relate to the claim, most helpful first. */
export const STANCES = ["supports", "neutral", "contradicts"] as const satisfies readonly Stance[];

/** What a site visit, survey or dig found. */
export const OUTCOMES = ["supports", "inconclusive", "contradicts"] as const satisfies readonly Outcome[];

/** How a heritage record relates to the finding. */
export const RELATIONS = ["same_as", "part_of", "related"] as const satisfies readonly Relation[];
