import { useCallback, useEffect, useRef } from "react";

/** How much of a row must be in sight for it to count as seen. */
export const SEEN_RATIO = 0.6;
/** Rows seen within this long of each other are marked read in one request. */
export const SEEN_BATCH_MS = 800;

/**
 * Hear when rows come into sight. `track(id)` gives a ref for a row; once
 * most of it has been on screen, its id is passed to `onSeen`, together
 * with any others seen at about the same time, and it is not watched again.
 * Where the browser can't tell what is in sight, a row counts as seen as
 * soon as it is shown.
 */
export function useSeen(onSeen: (ids: number[]) => void): (id: number) => (element: HTMLElement | null) => void {
  const latest = useRef(onSeen);
  latest.current = onSeen;
  const pending = useRef(new Set<number>());
  const done = useRef(new Set<number>());
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const observer = useRef<IntersectionObserver | null>(null);
  const ids = useRef(new WeakMap<Element, number>());

  const seen = useCallback((id: number) => {
    if (done.current.has(id)) return;
    done.current.add(id);
    pending.current.add(id);
    if (timer.current !== null) return;
    timer.current = setTimeout(() => {
      timer.current = null;
      const batch = [...pending.current];
      pending.current.clear();
      if (batch.length > 0) latest.current(batch);
    }, SEEN_BATCH_MS);
  }, []);

  useEffect(
    () => () => {
      observer.current?.disconnect();
      observer.current = null;
      if (timer.current !== null) clearTimeout(timer.current);
      timer.current = null;
      // Seen just before the list went: still seen.
      const batch = [...pending.current];
      pending.current.clear();
      if (batch.length > 0) latest.current(batch);
    },
    [],
  );

  return useCallback(
    (id: number) => (element: HTMLElement | null) => {
      if (element === null || done.current.has(id)) return;
      if (typeof IntersectionObserver !== "function") {
        seen(id);
        return;
      }
      observer.current ??= new IntersectionObserver(
        (entries) => {
          for (const entry of entries) {
            const seenId = ids.current.get(entry.target);
            if (seenId === undefined || entry.intersectionRatio < SEEN_RATIO) continue;
            observer.current?.unobserve(entry.target);
            seen(seenId);
          }
        },
        { threshold: SEEN_RATIO },
      );
      ids.current.set(element, id);
      observer.current.observe(element);
    },
    [seen],
  );
}
