/**
 * The requests investigations make. Each is one endpoint from the API table
 * in docs/ARCHITECTURE.md, typed from the generated schema. Query keys live
 * in `keys.ts` and nowhere else.
 */

import { apiFetch, apiUrl } from "../../api/client.js";
import type { components, operations } from "../../api/schema.js";

type Schemas = components["schemas"];
export type InvestigationSummary = Schemas["InvestigationSummary"];
export type InvestigationDetail = Schemas["InvestigationDetail"];
export type InvestigationUpdate = Schemas["InvestigationUpdate"];
export type InvestigationPage = Schemas["Page_InvestigationSummary_"];
export type Item = Schemas["InvestigationItemOut"];
export type ItemKind = Schemas["InvestigationItemKind"];
export type ItemUpdate = Schemas["ItemUpdate"];
export type ItemIn = NonNullable<operations["investigations_add_item"]["requestBody"]>["content"]["application/json"];
export type Member = Schemas["Member"];
export type MemberPage = Schemas["Page_Member_"];
export type Role = Schemas["InvestigationRole"];
export type Visibility = Schemas["Visibility"];
export type Scope = Schemas["Scope"];
export type SavedView = Schemas["SavedView"];
export type ReferenceData = Schemas["ReferenceData"];
export type ProfileData = Schemas["ProfileData"];
export type Unavailable = Schemas["Unavailable"];
export type ExportFormat = "geojson" | "csv" | "html";

/**
 * The longest text the server takes (schemas/investigations.py): an
 * investigation's title, summary and notes, an item's title and note, and a
 * reference's citation. The schema doesn't carry them, so they are repeated.
 */
export const LIMITS = {
  title: 120,
  summary: 1000,
  notes: 50_000,
  itemTitle: 200,
  itemNote: 10_000,
  citation: 1000,
} as const;

/** The backend's largest page, for the lists read whole. */
export const MAX_PAGE = 200;
/** How many investigations one page of a list holds. */
export const LIST_PAGE_SIZE = 30;
/** The most members an investigation has (`MAX_MEMBERS` in services/investigations.py), so one page holds them all. */
export const MEMBERS_PAGE = 50;

/** The path of an investigation's page. */
export function investigationPath(publicId: string): string {
  return `/i/${encodeURIComponent(publicId)}`;
}

export const INVESTIGATIONS_PATH = "/investigations";

function url(publicId: string, rest = ""): string {
  return `/investigations/${encodeURIComponent(publicId)}${rest}`;
}

export function fetchInvestigations(
  scope: Scope,
  bbox: string | null,
  cursor: string | null,
  signal?: AbortSignal,
  limit = LIST_PAGE_SIZE,
): Promise<InvestigationPage> {
  return apiFetch<InvestigationPage>("/investigations", {
    query: { scope, bbox, cursor, limit },
    signal,
  });
}

export function createInvestigation(title: string): Promise<InvestigationDetail> {
  return apiFetch<InvestigationDetail>("/investigations", { method: "POST", body: { title } });
}

export function fetchInvestigation(publicId: string, signal?: AbortSignal): Promise<InvestigationDetail> {
  return apiFetch<InvestigationDetail>(url(publicId), { signal });
}

export function updateInvestigation(publicId: string, body: InvestigationUpdate): Promise<InvestigationDetail> {
  return apiFetch<InvestigationDetail>(url(publicId), { method: "PATCH", body });
}

export function deleteInvestigation(publicId: string): Promise<void> {
  return apiFetch<void>(url(publicId), { method: "DELETE" });
}

/**
 * Every item, in order. An investigation holds at most 500, so this is at
 * most three pages, and the order can only be changed on the whole list.
 */
export async function fetchAllItems(publicId: string, signal?: AbortSignal): Promise<Item[]> {
  const items: Item[] = [];
  let cursor: string | null = null;
  do {
    const page: Schemas["Page_InvestigationItemOut_"] = await apiFetch(url(publicId, "/items"), {
      query: { limit: MAX_PAGE, cursor },
      signal,
    });
    items.push(...page.items);
    cursor = page.next_cursor ?? null;
  } while (cursor !== null);
  return items;
}

export function addItem(publicId: string, body: ItemIn): Promise<Item> {
  return apiFetch<Item>(url(publicId, "/items"), { method: "POST", body });
}

export function updateItem(publicId: string, itemId: number, body: ItemUpdate): Promise<Item> {
  return apiFetch<Item>(url(publicId, `/items/${itemId}`), { method: "PATCH", body });
}

export function removeItem(publicId: string, itemId: number): Promise<void> {
  return apiFetch<void>(url(publicId, `/items/${itemId}`), { method: "DELETE" });
}

/** Put an item straight after `after`, or first when `after` is null. */
export function moveItem(publicId: string, itemId: number, after: number | null): Promise<Item> {
  return apiFetch<Item>(url(publicId, `/items/${itemId}/move`), { method: "POST", body: { after } });
}

export function fetchMembers(publicId: string, signal?: AbortSignal): Promise<MemberPage> {
  return apiFetch<MemberPage>(url(publicId, "/members"), { query: { limit: MEMBERS_PAGE }, signal });
}

/** Invite someone by handle, or change the role they have or were offered. */
export function inviteMember(publicId: string, handle: string, role: Exclude<Role, "owner">): Promise<Member> {
  return apiFetch<Member>(url(publicId, `/members/${encodeURIComponent(handle)}`), {
    method: "PUT",
    body: { role },
  });
}

/** Remove a member or take back an invitation (the owner), or leave or decline (anyone else). */
export function removeMember(publicId: string, handle: string): Promise<void> {
  return apiFetch<void>(url(publicId, `/members/${encodeURIComponent(handle)}`), { method: "DELETE" });
}

export function acceptInvitation(publicId: string): Promise<InvestigationDetail> {
  return apiFetch<InvestigationDetail>(url(publicId, "/invitation"), { method: "POST" });
}

/** The address of an export. The report is a page to open; the others download. */
export function exportUrl(publicId: string, format: ExportFormat): string {
  return apiUrl(url(publicId, "/export"), { format });
}
