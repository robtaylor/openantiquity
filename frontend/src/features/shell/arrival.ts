/**
 * What a page does once, on arriving at its address: go to a record, frame
 * a shape, say that a marking was carried on.
 *
 * The Layers panel opens over whatever page is showing and takes its place,
 * and closing it mounts that page again at the same address. A page that
 * did its arriving whenever it mounted then did it twice: someone who had
 * moved the map away from a record was taken back to it for having looked
 * at the layers. So the doing is remembered here, by address, for as long as
 * the address stays the same, and forgotten when the app goes anywhere else.
 */

const visit: { pathname: string | null; done: Set<string> } = { pathname: null, done: new Set() };

function arriveAt(pathname: string): void {
  if (visit.pathname === pathname) return;
  visit.pathname = pathname;
  visit.done.clear();
}

/** Forget every visit. The shell calls it as it starts, since a shell just made has been nowhere yet. */
export function beginVisits(): void {
  visit.pathname = null;
  visit.done.clear();
}

/** Tell this module where the app is. The shell calls it whenever the address's path changes. */
export function leftFor(pathname: string): void {
  arriveAt(pathname);
}

/**
 * Whether `what` has yet to be done on this visit to `pathname`. True the
 * first time it is asked, and false until the app has been somewhere else.
 */
export function firstArrival(pathname: string, what: string): boolean {
  arriveAt(pathname);
  if (visit.done.has(what)) return false;
  visit.done.add(what);
  return true;
}
