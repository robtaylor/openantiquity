import type { FindingSummary } from "../../features/findings/types.js";
import type {
  InvestigationDetail,
  InvestigationSummary,
  Item,
  ItemIn,
  Member,
  Role,
  Visibility,
} from "../../features/investigations/api.js";
import type { RecordSummary } from "../../features/records/api.js";
import { FINDINGS_CENTRE, findingFeature, findingSummary } from "./findings.js";
import { AVENUE_RECORD } from "./records.js";

/**
 * Investigations for tests: builders for each shape, and a small in-memory
 * stand-in for the backend's investigation routes that keeps the rules the
 * frontend depends on (services/investigations.py): a private one is found
 * only by its owner and takes no collaborators, only the owner changes
 * visibility and members, an invitation waits until accepted, and moves
 * renumber the items. Vitest and Playwright both answer requests with it.
 */

type PublicUser = InvestigationSummary["owner"];

const NOW = "2026-11-10T10:00:00Z";

export const ADA: PublicUser = {
  handle: "QuietBarrow42",
  display_name: "Ada Lovelace",
  avatar_url: null,
  role: "member",
};
export const MARY: PublicUser = {
  handle: "KeenLynchet7",
  display_name: "Mary Anning",
  avatar_url: null,
  role: "member",
};
export const GUS: PublicUser = { handle: "GreyCairn3", display_name: "Gus Pitt", avatar_url: null, role: "member" };

const AREA = {
  type: "Polygon" as const,
  coordinates: [
    [
      [FINDINGS_CENTRE.lon - 0.01, FINDINGS_CENTRE.lat - 0.006],
      [FINDINGS_CENTRE.lon + 0.01, FINDINGS_CENTRE.lat - 0.006],
      [FINDINGS_CENTRE.lon + 0.01, FINDINGS_CENTRE.lat + 0.006],
      [FINDINGS_CENTRE.lon - 0.01, FINDINGS_CENTRE.lat + 0.006],
      [FINDINGS_CENTRE.lon - 0.01, FINDINGS_CENTRE.lat - 0.006],
    ],
  ],
};

export const AVEBURY_AREA = AREA;

/** A finding as an investigation item carries it. */
export function itemFinding(publicId = "fnd123", overrides: Partial<FindingSummary> = {}): FindingSummary {
  return findingSummary(findingFeature({ public_id: publicId, at: FINDINGS_CENTRE, tier: "seen" }), {
    title: "Round barrow on Overton Hill",
    feature_class: "round_barrow",
    ...overrides,
  });
}

export function itemRecord(): RecordSummary {
  const { id, source_key, name, category, record_type, lon, lat, precision_m, url, source } = AVENUE_RECORD;
  return { id, source_key, name, category, record_type, lon, lat, precision_m, url, source };
}

/** An investigation's page, as `GET /investigations/{id}` sends it: a public one with nothing in it, read by someone who isn't a member. */
export function investigationFixture(overrides: Partial<InvestigationDetail> = {}): InvestigationDetail {
  return {
    public_id: "inv1",
    title: "Barrows of Overton Down",
    summary: null,
    notes: null,
    visibility: "public",
    owner: GUS,
    area: null,
    item_count: 0,
    member_count: 1,
    created_at: NOW,
    updated_at: NOW,
    hidden: false,
    my_role: null,
    invited_as: null,
    ...overrides,
  };
}

interface Stored {
  public_id: string;
  title: string;
  summary: string | null;
  notes: string | null;
  area: InvestigationSummary["area"];
  visibility: Visibility;
  owner: PublicUser;
  hidden: boolean;
  created_at: string;
  updated_at: string;
  members: Array<{ user: PublicUser; role: Role; joined_at: string; accepted: boolean }>;
  items: Item[];
}

export interface FakeResponse {
  status: number;
  body?: unknown;
}

function error(status: number, code: string, message: string): FakeResponse {
  return { status, body: { error: { code, message } } };
}

export interface FakeInvestigationsOptions {
  /** Who is signed in, read on every request. */
  me: () => PublicUser | null;
  /** Everyone an invitation may name. */
  people?: PublicUser[];
  /** The finding an item names, as this viewer sees it. */
  finding?: (publicId: string) => FindingSummary | null;
  record?: (id: number) => RecordSummary | null;
}

/** One request, answered. A failure set with `failNext` comes first. */
export class FakeInvestigations {
  readonly store = new Map<string, Stored>();
  private nextId = 1;
  private nextItem = 100;
  private failures: Array<{ method: string; pattern: RegExp; response: FakeResponse }> = [];

  constructor(private readonly options: FakeInvestigationsOptions) {}

  /** Answer the next request matching this with `response` instead, once. */
  failNext(method: string, pattern: RegExp, response = error(503, "unavailable", "The server is busy.")): void {
    this.failures.push({ method, pattern, response });
  }

  /** Put an investigation in, as if made earlier. */
  seed(
    fields: Partial<Omit<Stored, "items" | "members">> & { title: string; owner: PublicUser },
    items: ItemIn[] = [],
  ): string {
    const publicId = fields.public_id ?? `inv${this.nextId++}`;
    const stored: Stored = {
      public_id: publicId,
      summary: null,
      notes: null,
      area: null,
      visibility: "private",
      hidden: false,
      created_at: NOW,
      updated_at: NOW,
      ...fields,
      members: [{ user: fields.owner, role: "owner", joined_at: NOW, accepted: true }],
      items: [],
    };
    this.store.set(publicId, stored);
    for (const item of items) this.addItem(stored, fields.owner, item);
    return publicId;
  }

  /** Invite someone to a seeded investigation, as its owner would. */
  invite(publicId: string, user: PublicUser, role: Exclude<Role, "owner"> = "editor", accepted = false): void {
    this.store.get(publicId)?.members.push({ user, role, joined_at: NOW, accepted });
  }

  private roleOf(stored: Stored, me: PublicUser | null): { role: Role | null; invited: Role | null } {
    const member = me ? stored.members.find((entry) => entry.user.handle === me.handle) : undefined;
    if (!member) return { role: null, invited: null };
    return member.accepted ? { role: member.role, invited: null } : { role: null, invited: member.role };
  }

  private summary(stored: Stored): InvestigationSummary {
    return {
      public_id: stored.public_id,
      title: stored.title,
      summary: stored.summary,
      visibility: stored.visibility,
      owner: stored.owner,
      area: stored.area,
      item_count: stored.items.length,
      created_at: stored.created_at,
      updated_at: stored.updated_at,
      hidden: stored.hidden,
    };
  }

  detail(stored: Stored, me: PublicUser | null): InvestigationDetail {
    const { role, invited } = this.roleOf(stored, me);
    return {
      ...this.summary(stored),
      notes: stored.notes,
      member_count: stored.members.filter((member) => member.accepted).length,
      my_role: role,
      invited_as: invited,
    };
  }

  private member(entry: Stored["members"][number]): Member {
    return { user: entry.user, role: entry.role, joined_at: entry.joined_at, pending: !entry.accepted };
  }

  private addItem(stored: Stored, by: PublicUser, body: ItemIn): Item {
    const item: Item = {
      id: this.nextItem++,
      kind: body.kind,
      position: stored.items.length,
      title: body.title ?? null,
      note: body.note ?? null,
      added_by: by,
      created_at: NOW,
    };
    if (body.kind === "finding") item.finding = (this.options.finding ?? ((id) => itemFinding(id)))(body.finding);
    if (body.kind === "record") item.record = (this.options.record ?? (() => itemRecord()))(body.record_id);
    if (body.kind === "view") item.view = body.view;
    if (body.kind === "reference") item.reference = body.reference;
    if (body.kind === "profile") item.profile = body.profile;
    stored.items.push(item);
    stored.updated_at = new Date().toISOString();
    return item;
  }

  private readable(stored: Stored, me: PublicUser | null): boolean {
    if (stored.visibility !== "private") return true;
    return me?.handle === stored.owner.handle;
  }

  handle(method: string, path: string, query: URLSearchParams, body: unknown): FakeResponse | null {
    const failure = this.failures.findIndex((entry) => entry.method === method && entry.pattern.test(path));
    if (failure >= 0) {
      const [entry] = this.failures.splice(failure, 1);
      return entry?.response ?? null;
    }
    const me = this.options.me();
    if (path === "/investigations") return this.list(method, query, body, me);
    const match = /^\/investigations\/([^/]+)(\/.*)?$/.exec(path);
    if (!match) return null;
    const stored = this.store.get(decodeURIComponent(match[1] ?? ""));
    if (!stored || !this.readable(stored, me)) {
      return error(404, "investigation_not_found", "There's no investigation with that id.");
    }
    const rest = match[2] ?? "";
    const { role } = this.roleOf(stored, me);
    const mayEdit = role === "owner" || role === "editor";
    const isOwner = role === "owner";
    const write = method !== "GET";
    if (write && !me) return error(401, "unauthorised", "Sign in first.");
    const page = <T>(items: T[]) => ({ status: 200, body: { items, next_cursor: null } });

    if (rest === "") {
      if (method === "GET") return { status: 200, body: this.detail(stored, me) };
      if (method === "DELETE") {
        if (!isOwner) return error(403, "investigation_owner_only", "Only the investigation's owner can do that.");
        this.store.delete(stored.public_id);
        return { status: 204 };
      }
      if (method === "PATCH") {
        const changes = body as Partial<Stored>;
        if (!mayEdit) return error(403, "investigation_forbidden", "Only the owner or an editor can do that.");
        if (changes.visibility !== undefined) {
          if (!isOwner) return error(403, "investigation_owner_only", "Only the investigation's owner can do that.");
          if (changes.visibility === "private" && stored.members.length > 1) {
            return error(
              409,
              "private_investigation_has_one_member",
              "A private investigation can't have collaborators.",
            );
          }
        }
        Object.assign(stored, changes, { updated_at: new Date().toISOString() });
        return { status: 200, body: this.detail(stored, me) };
      }
    }
    if (rest === "/items") {
      if (method === "GET") return page(stored.items);
      if (!mayEdit) return error(403, "investigation_forbidden", "Only the owner or an editor can do that.");
      return { status: 201, body: this.addItem(stored, me as PublicUser, body as ItemIn) };
    }
    const itemMatch = /^\/items\/(\d+)(\/move)?$/.exec(rest);
    if (itemMatch) {
      if (!mayEdit) return error(403, "investigation_forbidden", "Only the owner or an editor can do that.");
      const id = Number(itemMatch[1]);
      const index = stored.items.findIndex((item) => item.id === id);
      const item = stored.items[index];
      if (!item) return error(404, "item_not_found", "That investigation has no such item.");
      if (itemMatch[2] && method === "POST") {
        const after = (body as { after: number | null }).after;
        const rest = stored.items.filter((other) => other.id !== id);
        const to = after === null ? 0 : rest.findIndex((other) => other.id === after) + 1;
        rest.splice(to, 0, item);
        stored.items = rest.map((other, position) => ({ ...other, position }));
        return { status: 200, body: stored.items[to] };
      }
      if (method === "DELETE") {
        stored.items.splice(index, 1);
        stored.items = stored.items.map((other, position) => ({ ...other, position }));
        return { status: 204 };
      }
      if (method === "PATCH") {
        const updated = { ...item, ...(body as Partial<Item>) };
        stored.items[index] = updated;
        return { status: 200, body: updated };
      }
    }
    if (rest === "/members" && method === "GET") return page(stored.members.map((entry) => this.member(entry)));
    if (rest === "/invitation" && method === "POST") {
      const entry = stored.members.find((member) => member.user.handle === me?.handle && !member.accepted);
      if (!entry) return error(404, "invitation_not_found", "You have no invitation to this investigation waiting.");
      entry.accepted = true;
      return { status: 200, body: this.detail(stored, me) };
    }
    const memberMatch = /^\/members\/([^/]+)$/.exec(rest);
    if (memberMatch) {
      const handle = decodeURIComponent(memberMatch[1] ?? "");
      if (method === "PUT") {
        if (!isOwner) return error(403, "investigation_owner_only", "Only the investigation's owner can do that.");
        if (stored.visibility === "private") {
          return error(
            409,
            "private_investigation_has_one_member",
            "A private investigation can't have collaborators.",
          );
        }
        const user = (this.options.people ?? []).find((person) => person.handle.toLowerCase() === handle.toLowerCase());
        if (!user) return error(404, "user_not_found", "There's nobody with that handle.");
        const roleAsked = (body as { role: Exclude<Role, "owner"> }).role;
        const existing = stored.members.find((member) => member.user.handle === user.handle);
        if (existing) {
          existing.role = roleAsked;
          return { status: 200, body: this.member(existing) };
        }
        const entry = { user, role: roleAsked, joined_at: NOW, accepted: false };
        stored.members.push(entry);
        return { status: 201, body: this.member(entry) };
      }
      if (method === "DELETE") {
        const leaving = handle === me?.handle;
        if (!isOwner && !leaving)
          return error(403, "investigation_owner_only", "Only the investigation's owner can do that.");
        stored.members = stored.members.filter((member) => member.user.handle !== handle);
        return { status: 204 };
      }
    }
    return null;
  }

  private list(method: string, query: URLSearchParams, body: unknown, me: PublicUser | null): FakeResponse {
    if (method === "POST") {
      if (!me) return error(401, "unauthorised", "Sign in first.");
      const { title } = body as { title: string };
      const publicId = this.seed({ title, owner: me, created_at: new Date().toISOString() });
      return { status: 201, body: this.detail(this.store.get(publicId) as Stored, me) };
    }
    const scope = query.get("scope") ?? "public";
    if (scope !== "public" && !me) return error(401, "unauthorised", "Sign in first.");
    const bbox = query.get("bbox")?.split(",").map(Number);
    const all = [...this.store.values()].reverse();
    const chosen = all.filter((stored) => {
      const entry = stored.members.find((member) => member.user.handle === me?.handle);
      if (scope === "mine") return entry?.accepted === true;
      if (scope === "invited") return entry !== undefined && !entry.accepted;
      if (stored.visibility !== "public" || stored.hidden) return false;
      if (!bbox) return true;
      const ring = (stored.area?.coordinates?.[0] ?? []) as Array<[number, number]>;
      const [west, south, east, north] = bbox as [number, number, number, number];
      return ring.some(([lon, lat]) => lon >= west && lon <= east && lat >= south && lat <= north);
    });
    return { status: 200, body: { items: chosen.map((stored) => this.summary(stored)), next_cursor: null } };
  }
}
