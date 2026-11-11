/**
 * The queries an investigation's page reads, and the changes it makes.
 * Every change shows at once and is taken back with a toast when the
 * server refuses it (docs/UI.md, "Behaviour"). Moves are sent one at a time
 * and in order, because each says where an item goes relative to another.
 */

import { type QueryClient, type QueryKey, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useEffect, useMemo } from "react";
import { create } from "zustand";
import { ApiError, isTransient } from "../../api/client.js";
import { toast, useToastStore } from "../../ui/toastStore.js";
import { toastFailure } from "../finding/feedback.js";
import {
  addItem,
  fetchAllItems,
  fetchInvestigation,
  fetchMembers,
  type InvestigationDetail,
  type InvestigationUpdate,
  type Item,
  type ItemIn,
  type ItemUpdate,
  moveItem,
  removeItem,
  updateInvestigation,
  updateItem,
} from "./api.js";
import { investigationKeys } from "./keys.js";
import { moveTo } from "./order.js";

const retry = (failures: number, error: Error) => failures < 1 && isTransient(error);

export function isNotFound(error: unknown): boolean {
  return error instanceof ApiError && (error.status === 404 || error.status === 422);
}

export function useInvestigation(publicId: string) {
  return useQuery({
    queryKey: investigationKeys.detail(publicId),
    queryFn: ({ signal }) => fetchInvestigation(publicId, signal),
    retry,
  });
}

/** How long "Undo" is offered after an item is taken out, before it is gone. */
export const UNDO_MS = 6000;

/** Items taken out and waiting out their "Undo", by id: each sends its removal now. */
const takingOut = new Map<number, () => void>();

/** The ids in `takingOut`, for the page to leave out as they change. */
const useTakingOut = create<{ ids: ReadonlySet<number> }>()(() => ({ ids: new Set() }));

function syncTakingOut(): void {
  useTakingOut.setState({ ids: new Set(takingOut.keys()) });
}

/** What the page shows: everything the server has, less what is waiting to be taken out, so a refetch can't bring it back. */
function shown(items: Item[], ids: ReadonlySet<number> = useTakingOut.getState().ids): Item[] {
  return ids.size === 0 ? items : items.filter((item) => !ids.has(item.id));
}

/** Leaving the page sends every removal still waiting, rather than keep what the person took out. */
function sendWaitingRemovals(): void {
  for (const send of [...takingOut.values()]) send();
}
if (typeof window !== "undefined") window.addEventListener("pagehide", sendWaitingRemovals);

export function useItems(publicId: string, enabled = true) {
  const ids = useTakingOut((state) => state.ids);
  // A new function when the ids change, so the query picks again.
  const select = useCallback((items: Item[]) => shown(items, ids), [ids]);
  return useQuery({
    queryKey: investigationKeys.items(publicId),
    queryFn: ({ signal }) => fetchAllItems(publicId, signal),
    select,
    enabled,
    retry,
  });
}

export function useMembers(publicId: string, enabled = true) {
  return useQuery({
    queryKey: investigationKeys.members(publicId),
    queryFn: async ({ signal }) => (await fetchMembers(publicId, signal)).items,
    enabled,
    retry,
  });
}

/**
 * Show `change` in the cache at once, send the request, and on failure put
 * back what was there, say why in a toast and ask the server for the truth.
 * Resolves with the server's answer, or null when it failed.
 */
export async function optimistic<T, R>(
  client: QueryClient,
  key: QueryKey,
  change: (current: T) => T,
  send: () => Promise<R>,
  failure: string,
): Promise<R | null> {
  // Exactly this query: an investigation's own key is the prefix of its items' and members'.
  await client.cancelQueries({ queryKey: key, exact: true });
  const before = client.getQueryData<T>(key);
  if (before !== undefined) client.setQueryData<T>(key, change(before));
  try {
    return await send();
  } catch (error) {
    if (before !== undefined) client.setQueryData<T>(key, before);
    toastFailure(failure, error);
    void client.invalidateQueries({ queryKey: key, exact: true });
    return null;
  }
}

/** Moves waiting to be sent, one chain per investigation, so the server applies them in the order they were made. */
const moveChains = new Map<string, Promise<unknown>>();
/** Investigations with a move refused in the chain still running: asked again once it is idle. */
const refusedMoves = new Set<string>();

/** Ids for items shown before the server has answered. Negative, so they never meet a real one. */
let nextPendingId = -1;

export function isPending(item: Pick<Item, "id">): boolean {
  return item.id < 0;
}

export interface Notebook {
  /** Change the title, summary, notes, area or visibility. */
  update: (changes: InvestigationUpdate, failure: string) => Promise<InvestigationDetail | null>;
  add: (body: ItemIn, preview: Omit<Item, "id" | "position">) => Promise<Item | null>;
  edit: (item: Item, changes: ItemUpdate) => Promise<Item | null>;
  /**
   * Take an item out at once, with "Undo" in a toast. The request goes when
   * the toast does, or sooner if the page closes. `name` is what the toast calls it.
   */
  remove: (item: Item, name: string) => void;
  /** Move an item to place `to`, counted from 0. False when there was nothing to move. */
  move: (item: Item, to: number) => boolean;
}

/** The changes a notebook's editors make, each shown at once. */
export function useNotebook(publicId: string): Notebook {
  const client = useQueryClient();
  const itemsKey = investigationKeys.items(publicId);
  const detailKey = investigationKeys.detail(publicId);

  const touchLists = useCallback(() => void client.invalidateQueries({ queryKey: investigationKeys.lists }), [client]);

  const update = useCallback(
    async (changes: InvestigationUpdate, failure: string) => {
      const saved = await optimistic<InvestigationDetail, InvestigationDetail>(
        client,
        detailKey,
        (current) => ({ ...current, ...(changes as Partial<InvestigationDetail>) }),
        () => updateInvestigation(publicId, changes),
        failure,
      );
      if (saved) {
        client.setQueryData(detailKey, saved);
        touchLists();
      }
      return saved;
    },
    [client, detailKey, publicId, touchLists],
  );

  const setCount = useCallback(
    (delta: number) =>
      client.setQueryData<InvestigationDetail>(detailKey, (current) =>
        current ? { ...current, item_count: Math.max(0, current.item_count + delta) } : current,
      ),
    [client, detailKey],
  );

  const add = useCallback(
    async (body: ItemIn, preview: Omit<Item, "id" | "position">) => {
      const pendingId = nextPendingId--;
      setCount(1);
      const saved = await optimistic<Item[], Item>(
        client,
        itemsKey,
        (items) => [...items, { ...preview, id: pendingId, position: items.length }],
        () => addItem(publicId, body),
        "It couldn't be added.",
      );
      if (saved) {
        client.setQueryData<Item[]>(itemsKey, (items) => items?.map((item) => (item.id === pendingId ? saved : item)));
        touchLists();
      } else setCount(-1);
      return saved;
    },
    [client, itemsKey, publicId, setCount, touchLists],
  );

  const edit = useCallback(
    async (item: Item, changes: ItemUpdate) => {
      const saved = await optimistic<Item[], Item>(
        client,
        itemsKey,
        (items) => items.map((current) => (current.id === item.id ? ({ ...current, ...changes } as Item) : current)),
        () => updateItem(publicId, item.id, changes),
        "Your change couldn't be saved.",
      );
      if (saved) {
        client.setQueryData<Item[]>(itemsKey, (items) =>
          items?.map((current) => (current.id === saved.id ? saved : current)),
        );
      }
      return saved;
    },
    [client, itemsKey, publicId],
  );

  const remove = useCallback(
    (item: Item, name: string) => {
      if (takingOut.has(item.id)) return;
      let toastId = 0;
      let timer: ReturnType<typeof setTimeout> | undefined;
      const finish = (): boolean => {
        if (!takingOut.has(item.id)) return false;
        takingOut.delete(item.id);
        syncTakingOut();
        clearTimeout(timer);
        useToastStore.getState().dismiss(toastId);
        return true;
      };
      const send = (): void => {
        if (!finish()) return;
        // A refetch already on its way would bring it back.
        void client.cancelQueries({ queryKey: itemsKey, exact: true });
        client.setQueryData<Item[]>(itemsKey, (items) => items?.filter((current) => current.id !== item.id));
        removeItem(publicId, item.id).then(touchLists, (error: unknown) => {
          setCount(1);
          toastFailure("It couldn't be taken out.", error);
          void client.invalidateQueries({ queryKey: itemsKey, exact: true });
        });
      };
      const undo = (): void => {
        if (!finish()) return;
        setCount(1);
        toast(`“${name}” is back.`);
        // Moves made in the meantime may have put it somewhere else on the server.
        void client.invalidateQueries({ queryKey: itemsKey, exact: true });
      };
      takingOut.set(item.id, send);
      syncTakingOut();
      timer = setTimeout(send, UNDO_MS);
      setCount(-1);
      toastId = toast(`Took “${name}” out.`, { action: { label: "Undo", onClick: undo }, duration: UNDO_MS });
    },
    [client, itemsKey, publicId, setCount, touchLists],
  );

  // Closing the notebook sends what is waiting to be taken out of it.
  useEffect(() => sendWaitingRemovals, []);

  const move = useCallback(
    (item: Item, to: number) => {
      const all = client.getQueryData<Item[]>(itemsKey);
      // Places count in the list as shown. An item being added isn't on the server yet, so it can't be followed.
      const moved = all ? moveTo(shown(all), item.id, to, isPending) : null;
      if (!all || !moved || isPending(item)) return false;
      // The new order shows now. The request waits for the ones before it.
      void client.cancelQueries({ queryKey: itemsKey, exact: true });
      const hidden = all.filter((current) => takingOut.has(current.id));
      client.setQueryData<Item[]>(
        itemsKey,
        [...moved.items, ...hidden].map((current, position) => ({ ...current, position })),
      );
      const previous = moveChains.get(publicId) ?? Promise.resolve();
      const next = previous.then(async () => {
        try {
          await moveItem(publicId, item.id, moved.after);
        } catch (error) {
          toastFailure("The new order couldn't be saved.", error);
          refusedMoves.add(publicId);
        }
      });
      moveChains.set(publicId, next);
      void next.finally(() => {
        if (moveChains.get(publicId) !== next) return;
        moveChains.delete(publicId);
        // Once nothing is waiting, the server's order, which holds every move that did land, replaces what is shown.
        // Asked any sooner, its answer could arrive before the moves still queued and undo them on screen.
        if (refusedMoves.delete(publicId)) void client.invalidateQueries({ queryKey: itemsKey, exact: true });
      });
      return true;
    },
    [client, itemsKey, publicId],
  );

  return useMemo(() => ({ update, add, edit, remove, move }), [update, add, edit, remove, move]);
}
