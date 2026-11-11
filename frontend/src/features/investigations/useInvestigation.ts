/**
 * The queries an investigation's page reads, and the changes it makes.
 * Every change shows at once and is taken back with a toast when the
 * server refuses it (docs/UI.md, "Behaviour"). Moves are sent one at a time
 * and in order, because each says where an item goes relative to another.
 */

import { type QueryClient, type QueryKey, useQuery, useQueryClient } from "@tanstack/react-query";
import { useCallback, useMemo } from "react";
import { ApiError, isTransient } from "../../api/client.js";
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

export function useItems(publicId: string, enabled = true) {
  return useQuery({
    queryKey: investigationKeys.items(publicId),
    queryFn: ({ signal }) => fetchAllItems(publicId, signal),
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
  remove: (item: Item) => Promise<boolean>;
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
    async (item: Item) => {
      setCount(-1);
      const done = await optimistic<Item[], true>(
        client,
        itemsKey,
        (items) => items.filter((current) => current.id !== item.id),
        async () => {
          await removeItem(publicId, item.id);
          return true as const;
        },
        "It couldn't be taken out.",
      );
      if (done) touchLists();
      else setCount(1);
      return done === true;
    },
    [client, itemsKey, publicId, setCount, touchLists],
  );

  const move = useCallback(
    (item: Item, to: number) => {
      const items = client.getQueryData<Item[]>(itemsKey);
      const moved = items ? moveTo(items, item.id, to) : null;
      if (!items || !moved || isPending(item)) return false;
      // The new order shows now. The request waits for the ones before it.
      void client.cancelQueries({ queryKey: itemsKey, exact: true });
      client.setQueryData<Item[]>(
        itemsKey,
        moved.items.map((current, position) => ({ ...current, position })),
      );
      const previous = moveChains.get(publicId) ?? Promise.resolve();
      const next = previous.then(async () => {
        try {
          await moveItem(publicId, item.id, moved.after);
        } catch (error) {
          // Back to the order before this move, then the server's own, which holds any move that did land.
          client.setQueryData<Item[]>(itemsKey, items);
          toastFailure("The new order couldn't be saved.", error);
          void client.invalidateQueries({ queryKey: itemsKey });
        }
      });
      moveChains.set(publicId, next);
      void next.finally(() => {
        if (moveChains.get(publicId) === next) moveChains.delete(publicId);
      });
      return true;
    },
    [client, itemsKey, publicId],
  );

  return useMemo(() => ({ update, add, edit, remove, move }), [update, add, edit, remove, move]);
}
