/**
 * A compile-time check that the two descriptions of `/meta` agree: the one
 * `pnpm gen:api` generates from the backend's OpenAPI document, and the
 * hand-written one in `src/api/meta.ts` that the app is built on.
 *
 * `pnpm gen:api` type-checks this file (with `tsconfig.schema.json`) straight
 * after writing `src/api/schema.d.ts`. If the backend has changed `/meta` in
 * a way the frontend does not expect, that step fails and names this file.
 * It is kept out of the ordinary type-check because the generated file only
 * exists once the backend can be run.
 */
import type { Meta } from "../src/api/meta.js";
import type { components } from "../src/api/schema.js";

type Assert<T extends true> = T;

/** Everything the backend says it serves must be usable as the frontend's `Meta`. */
export type GeneratedMetaFitsMeta = Assert<components["schemas"]["Meta"] extends Meta ? true : false>;
