import { useEffect } from "react";
import { useLocation, useNavigationType } from "react-router";
import { decodePermalink, encodePermalink, PERMALINK_KEYS } from "./permalink.js";
import { changedAny, selectPermalinkState, useMapStore } from "./store.js";

/** Browsers throttle history updates, so the hash trails the map slightly. */
const WRITE_DELAY_MS = 250;

function currentHash(): string {
  return encodePermalink(selectPermalinkState(useMapStore.getState()));
}

function writeHash(): void {
  if (useMapStore.getState().meta === null) return;
  const hash = currentHash();
  if (window.location.hash === hash) return;
  // replaceState keeps the router's own state object and adds no history entry.
  window.history.replaceState(window.history.state, "", `${window.location.pathname}${window.location.search}${hash}`);
}

/**
 * Keep the URL hash and the map state together. The hash is rewritten a
 * moment after the map changes. Editing the hash by hand, pasting a link into
 * the address bar, or following a link inside the app that carries a view,
 * moves the map to match.
 */
export function usePermalink(): void {
  const location = useLocation();
  const navigationType = useNavigationType();

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    function schedule(): void {
      if (timer !== undefined) clearTimeout(timer);
      timer = setTimeout(writeHash, WRITE_DELAY_MS);
    }

    const unsubscribe = useMapStore.subscribe((next, previous) => {
      if (next.meta !== null && (changedAny(next, previous, PERMALINK_KEYS) || previous.meta === null)) schedule();
    });

    function onHashChange(): void {
      const store = useMapStore.getState();
      if (store.meta === null || window.location.hash === currentHash()) return;
      store.applyPermalink(decodePermalink(window.location.hash));
      // Rewrite even if nothing usable was in the hash, so the URL is true again.
      schedule();
    }
    window.addEventListener("hashchange", onHashChange);

    return () => {
      unsubscribe();
      window.removeEventListener("hashchange", onHashChange);
      if (timer !== undefined) clearTimeout(timer);
    };
  }, []);

  // A link inside the app may carry a view of its own, such as a saved view
  // in an investigation. Going there shows that view. Any other route change
  // replaces the URL without a hash, and the hash is put straight back.
  //
  // Back and forward are left out on purpose. The hash on an older history
  // entry is where the map was when that page was left, and pressing Back to
  // close a panel should not also throw the map back there.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the location is the trigger, not an input
  useEffect(() => {
    const store = useMapStore.getState();
    if (store.meta !== null && navigationType !== "POP" && location.hash !== "" && location.hash !== currentHash()) {
      const incoming = decodePermalink(location.hash);
      if (Object.keys(incoming).length > 0) store.applyPermalink(incoming);
    }
    writeHash();
  }, [location.key]);
}
