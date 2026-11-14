/**
 * The text of a problem report, and the addresses that carry it.
 *
 * A report says which build, what kind of page, which layout and browser,
 * what the map showed and what failed, and nothing that says where anyone
 * was or who they are: no map position unless the person adds it, no id of
 * a finding, record, investigation, draft or person, no handle or name, and
 * nothing a form holds. The repository is public, and a position or an
 * address can say where a protected finding is (Decision 0005).
 */

import { matchPath } from "react-router";
import type { KeptFailure } from "../../api/failures.js";
import { NEW_ISSUE_URL } from "./repository.js";

/**
 * Every page the shell routes to (`features/shell/Shell.tsx`), as its
 * pattern. A report names the pattern, never the address, so no id goes
 * with it. `report.test.ts` checks the list against the shell's routes.
 */
export const PAGE_PATTERNS: readonly string[] = [
  "/",
  "/mark/finding/:publicId",
  "/mark/:draftId?",
  "/f/:id",
  "/review",
  "/help",
  "/help/:kind",
  "/scan",
  "/activity",
  "/account",
  "/u/:handle",
  "/mod/:section?",
  "/signin/email",
  "/r/:id",
  "/records",
  "/elsewhere",
  "/profile",
  "/mentions",
  "/investigations",
  "/i/:id",
  "/guide",
  "/about",
  "/about/:notice",
  "/_ui",
];

/** The kind of page at `pathname`, as its route's pattern, or "another page" for none the shell knows. */
export function pagePattern(pathname: string): string {
  return PAGE_PATTERNS.find((pattern) => matchPath({ path: pattern, end: true }, pathname)) ?? "another page";
}

/** Browsers by the mark their user agent string carries, in the order to look for them. */
const BROWSERS: ReadonlyArray<[RegExp, string]> = [
  [/\bEdg(?:e|A|iOS)?\/(\d+)/, "Edge"],
  [/\bOPR\/(\d+)/, "Opera"],
  [/\bSamsungBrowser\/(\d+)/, "Samsung Internet"],
  [/\b(?:Firefox|FxiOS)\/(\d+)/, "Firefox"],
  [/\b(?:Chrome|CriOS)\/(\d+)/, "Chrome"],
  [/\bVersion\/(\d+)[.\d]* (?:Mobile\/\S+ )?Safari\//, "Safari"],
];

/** The browser's name and major version from its user agent string, such as "Firefox 140". */
export function browserName(userAgent: string): string {
  for (const [pattern, name] of BROWSERS) {
    const found = pattern.exec(userAgent);
    if (found) return `${name} ${found[1]}`;
  }
  return "an unknown browser";
}

export interface MapFacts {
  mainView: string;
  compareView: string | null;
  /** The overlays switched on, by id. */
  overlays: readonly string[];
  threeD: boolean;
}

export interface MapPosition {
  lng: number;
  lat: number;
  zoom: number;
}

/** What a report says, gathered when the form opens. */
export interface ReportFacts {
  version: string | null;
  commit: string | null;
  /** The page's route pattern, from `pagePattern`. */
  page: string;
  layout: "phone" | "desktop";
  browser: string;
  window: { width: number; height: number };
  /** Null before the map has started. */
  map: MapFacts | null;
  /** Null when it isn't known yet. */
  signedIn: boolean | null;
  failures: readonly KeptFailure[];
}

export interface ReportChoices {
  /** What the person says they were doing. */
  description: string;
  /** Where the map was looking, only when the person chose to add it and the page allows it. */
  position: MapPosition | null;
}

/** The longest title the address is given, from the start of what the person wrote. */
const TITLE_MAX = 70;

/** The issue's title: the start of what the person wrote, or the kind of page. */
export function reportTitle(facts: ReportFacts, choices: ReportChoices): string {
  const firstLine = choices.description.trim().split("\n", 1)[0]?.trim() ?? "";
  if (!firstLine) return `A problem on ${facts.page}`;
  return firstLine.length > TITLE_MAX ? `${firstLine.slice(0, TITLE_MAX - 1).trimEnd()}…` : firstLine;
}

function time(at: string): string {
  return at.replace(/\.\d{3}Z$/, "Z");
}

function failureLine(failure: KeptFailure): string {
  if (failure.kind === "error") return `- ${time(failure.at)} An error: ${failure.message}`;
  const answer = failure.status === 0 ? "no answer" : String(failure.status);
  const request = failure.requestId ? `, request ${failure.requestId}` : "";
  return `- ${time(failure.at)} ${failure.method} ${failure.path}: ${answer} ${failure.code}${request}`;
}

function mapLine(map: MapFacts | null): string {
  if (!map) return "not started";
  const compare = map.compareView ? `, compared with ${map.compareView}` : "";
  const overlays = map.overlays.length > 0 ? map.overlays.join(", ") : "none";
  return `${map.mainView}${compare}; overlays shown: ${overlays}; 3D ${map.threeD ? "on" : "off"}`;
}

function positionLine(position: MapPosition | null): string {
  if (!position) return "not included";
  return `${position.lat.toFixed(5)}, ${position.lng.toFixed(5)} at zoom ${position.zoom.toFixed(1)}`;
}

function signedInLine(signedIn: boolean | null): string {
  if (signedIn === null) return "not known";
  return signedIn ? "yes" : "no";
}

/** The whole report as it is shown, copied and sent. */
export function reportText(facts: ReportFacts, choices: ReportChoices): string {
  const build = [facts.version ?? "version not known", facts.commit ? `commit ${facts.commit}` : "commit not known"];
  const failures = facts.failures.length > 0 ? facts.failures.map(failureLine) : ["Nothing failed in this page."];
  return [
    "## What happened",
    "",
    choices.description.trim() || "Not filled in.",
    "",
    "## The page",
    "",
    `- Build: ${build.join(", ")}`,
    `- Page: ${facts.page}`,
    `- Layout: ${facts.layout}`,
    `- Browser: ${facts.browser}, window ${facts.window.width} × ${facts.window.height}`,
    `- Map: ${mapLine(facts.map)}`,
    `- Signed in: ${signedInLine(facts.signedIn)}`,
    `- Where the map was: ${positionLine(choices.position)}`,
    "",
    "## What went wrong lately",
    "",
    ...failures,
  ].join("\n");
}

/** GitHub's new-issue form answers an error page for a longer address. Measured on 2026-11-13. */
export const ADDRESS_MAX = 6000;

/** What ends a body cut to fit the address. */
export const CUT_NOTE =
  "\n\n[The report was cut here to fit GitHub's address. Paste the full text, from Copy the details, in place of this.]";

function issueAddress(title: string, body: string): string {
  return `${NEW_ISSUE_URL}?title=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}

/**
 * The address of a new issue with `title` and `body` filled in, under
 * `ADDRESS_MAX` characters. A body too long for that is cut, and says so,
 * and `cut` is true.
 */
export function githubIssueUrl(title: string, body: string): { url: string; cut: boolean } {
  const whole = issueAddress(title, body);
  if (whole.length < ADDRESS_MAX) return { url: whole, cut: false };
  // By characters, not code units, so a cut never splits one and leaves what encodeURIComponent refuses.
  const characters = Array.from(body);
  let low = 0;
  let high = characters.length;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (issueAddress(title, characters.slice(0, middle).join("") + CUT_NOTE).length < ADDRESS_MAX) low = middle;
    else high = middle - 1;
  }
  const url = issueAddress(title, characters.slice(0, low).join("") + CUT_NOTE);
  if (url.length >= ADDRESS_MAX) throw new Error("A report's title alone is too long for GitHub's address");
  return { url, cut: true };
}

/** A `mailto:` address that writes the report to `address`. */
export function emailUrl(address: string, title: string, body: string): string {
  return `mailto:${address}?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(body)}`;
}
