/**
 * The shapes the blind second-look queue works with, named from the
 * generated `schema.d.ts`. Nothing here is written by hand.
 */

import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

/** A blind card: the place and the finder's view, and nothing about what anyone thought (Decision 0008). */
export type ReviewCard = Schemas["ReviewCard"];
export type ReviewPlace = Schemas["ReviewPlace"];
export type ReviewCardPage = Schemas["Page_ReviewCard_"];
