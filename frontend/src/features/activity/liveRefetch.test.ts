import { InfiniteQueryObserver, QueryClient } from "@tanstack/react-query";
import { afterEach, describe, expect, it, vi } from "vitest";
import { activityKeys, feedRequestOf } from "./keys.js";
import { refreshNewest, withNewestPage } from "./liveRefetch.js";

interface Page {
  items: { id: number; text: string }[];
  next_cursor: string | null;
  unread_count?: number;
}

const page = (ids: number[], next: string | null, text = "old"): Page => ({
  items: ids.map((id) => ({ id, text })),
  next_cursor: next,
});

const ids = (pages: Page[]) => pages.map((each) => each.items.map((item) => item.id));

describe("putting a fresh first page in front", () => {
  it("adds what is new, keeps what the first page held, and keeps its cursor so later pages follow on", () => {
    const data = { pages: [page([10, 9, 8], "c1"), page([7, 6, 5], "c2")], pageParams: [null, "c1"] };
    const merged = withNewestPage(data, { ...page([12, 11, 10], "new", "fresh"), unread_count: 4 });
    expect(ids(merged.pages)).toEqual([
      [12, 11, 10, 9, 8],
      [7, 6, 5],
    ]);
    expect(merged.pages[0]?.next_cursor).toBe("c1");
    expect(merged.pages[0]?.items[2]).toEqual({ id: 10, text: "fresh" });
    expect(merged.pages[0]?.unread_count).toBe(4);
    expect(merged.pageParams).toEqual([null, "c1"]);
  });

  it("lists each item once, even when the fresh page reaches into a later one", () => {
    const data = { pages: [page([10, 9], "c1"), page([8, 7], null)], pageParams: [null, "c1"] };
    expect(ids(withNewestPage(data, page([11, 10, 9, 8], "x")).pages)).toEqual([[11, 10, 9, 8], [7]]);
  });
});

describe("refreshing a paged list", () => {
  const clients: QueryClient[] = [];
  afterEach(() => {
    for (const client of clients) client.clear();
    clients.length = 0;
  });

  function watched(pages: Page[]) {
    const client = new QueryClient({ defaultOptions: { queries: { retry: false, staleTime: Infinity } } });
    clients.push(client);
    const key = activityKeys.feed(null, []);
    const queryFn = vi.fn(async ({ pageParam }: { pageParam: string | null }) => page([pageParam ? 1 : 99], null));
    client.setQueryData(key, { pages, pageParams: pages.map((_, index) => (index === 0 ? null : `c${index}`)) });
    const observer = new InfiniteQueryObserver(client, {
      queryKey: key,
      queryFn,
      initialPageParam: null as string | null,
      getNextPageParam: (last: Page) => last.next_cursor,
    });
    const stop = observer.subscribe(() => {});
    return { client, key, queryFn, stop };
  }

  it("asks only for the first page of a list paged five times, however far the reader went", async () => {
    const pages = [page([60], "c1"), page([50], "c2"), page([40], "c3"), page([30], "c4"), page([20], "c5")];
    const { client, key, queryFn, stop } = watched(pages);
    const fetchFirst = vi.fn(async () => page([61, 60], "new"));
    await refreshNewest(client, activityKeys.all, fetchFirst);
    expect(fetchFirst).toHaveBeenCalledTimes(1);
    expect(fetchFirst).toHaveBeenCalledWith(key);
    expect(queryFn).not.toHaveBeenCalled();
    expect(ids(client.getQueryData<{ pages: Page[] }>(key)?.pages ?? [])).toEqual([[61, 60], [50], [40], [30], [20]]);
    stop();
  });

  it("simply refetches a list of one page", async () => {
    const { client, queryFn, stop } = watched([page([60], "c1")]);
    const fetchFirst = vi.fn(async () => page([61], null));
    await refreshNewest(client, activityKeys.all, fetchFirst);
    expect(fetchFirst).not.toHaveBeenCalled();
    expect(queryFn).toHaveBeenCalledTimes(1);
    stop();
  });

  it("marks the list stale when the first page can't be had", async () => {
    const { client, key, stop } = watched([page([60], "c1"), page([50], null)]);
    await refreshNewest(client, activityKeys.all, () => Promise.reject(new Error("down")));
    expect(client.getQueryState(key)?.isInvalidated).toBe(true);
    stop();
  });
});

describe("reading a feed key back", () => {
  it("gives the box and kinds a feed key was made from", () => {
    expect(feedRequestOf(activityKeys.feed("1,2,3,4", ["comment_added", "tier_changed"]))).toEqual({
      bbox: "1,2,3,4",
      kinds: ["comment_added", "tier_changed"],
    });
    expect(feedRequestOf(activityKeys.feed(null, []))).toEqual({ bbox: null, kinds: [] });
    expect(feedRequestOf(activityKeys.all)).toBeNull();
    expect(feedRequestOf(["activity", "feed", null, "not_a_kind"])).toBeNull();
  });
});
