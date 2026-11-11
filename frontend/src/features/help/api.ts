/**
 * Help wanted's requests: `GET /review/tasks`, the open next steps across
 * findings grouped by code. Without a code, every group with its first
 * page; with one, that group alone, paged by its cursor. A step that a
 * second look meets comes with no finding and no step, as blind as a review
 * card (Decision 0008), and the panel sends people to the queue for those.
 */

import { apiFetch } from "../../api/client.js";
import type { components } from "../../api/schema.js";

type Schemas = components["schemas"];

export type TaskGroups = Schemas["TaskGroups"];
export type TaskGroup = Schemas["TaskGroupOut"];
export type TaskItem = Schemas["TaskItem"];
export type TaskCode = Schemas["NextStepCode"];

/** How many tasks each group brings at a time. Enough to split the evidence group by strand. */
export const TASKS_PER_PAGE = 50;

export function fetchTaskGroups(signal?: AbortSignal): Promise<TaskGroups> {
  return apiFetch<TaskGroups>("/review/tasks", { query: { limit: TASKS_PER_PAGE }, signal });
}

export function fetchTaskGroup(code: TaskCode, cursor: string | null, signal?: AbortSignal): Promise<TaskGroups> {
  const query: Record<string, string | number> = { code, limit: TASKS_PER_PAGE };
  if (cursor) query.cursor = cursor;
  return apiFetch<TaskGroups>("/review/tasks", { query, signal });
}
