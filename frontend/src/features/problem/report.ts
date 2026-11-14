/**
 * The text of a problem report, and the addresses that carry it.
 *
 * A report says which build, what kind of page, which layout and browser,
 * what the map showed and what failed, and nothing that says where anyone
 * was or who they are: no coordinates ever, no id of a finding, record,
 * investigation, draft or person, no handle or name, and nothing a form
 * holds. The repository is public, and a position or an address can say
 * where a protected finding is (Decision 0005). Where the map was is added
 * only when the person asks, and only as the one-kilometre square it was
 * centred on, the size of square a protected finding is shown as, and the
 * zoom. Signed in, a member sees a protected finding exactly, so the option
 * is never offered on a page that shows a finding, a draft or an
 * investigation.
 */

import { matchPath } from "react-router";
import type { KeptFailure } from "../../api/failures.js";
import { formatGridRef, wgs84ToGrid } from "../../map/gridref.js";
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

/** Where the map was looking, as much of it as a report may carry. */
export interface MapPosition {
  /** The one-kilometre grid square the map was centred on, such as "SK 23 88". */
  square: string;
  /** The zoom, as a whole number. */
  zoom: number;
}

/** The square and zoom of a map centred at `lng`, `lat`, or null where the centre is on neither national grid. */
export function positionOf(lng: number, lat: number, zoom: number): MapPosition | null {
  const grid = wgs84ToGrid(lng, lat);
  return grid ? { square: formatGridRef(grid, 4), zoom: Math.round(zoom) } : null;
}

/**
 * The pages, by pattern, on which a report may offer where the map was:
 * those that show no finding, draft or investigation of their own. Any
 * other page, one added later included, doesn't offer it.
 */
const POSITION_PAGES: ReadonlySet<string> = new Set([
  "/",
  "/help",
  "/help/:kind",
  "/activity",
  "/account",
  "/u/:handle",
  "/signin/email",
  "/r/:id",
  "/records",
  "/elsewhere",
  "/profile",
  "/mentions",
  "/investigations",
  "/guide",
  "/about",
  "/about/:notice",
]);

/** Whether a report made on a page with this pattern may offer where the map was. */
export function offersPosition(page: string): boolean {
  return POSITION_PAGES.has(page);
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
  /** Where the map was looking, only when the person chose to add it and the page offers it. */
  position: MapPosition | null;
}

/** The longest title the address is given, from the start of what the person wrote. */
const TITLE_MAX = 70;

/** The issue's title: the start of what the person wrote, or the kind of page. */
export function reportTitle(facts: ReportFacts, choices: ReportChoices): string {
  const firstLine = choices.description.trim().split("\n", 1)[0]?.trim() ?? "";
  if (!firstLine) return `A problem on ${facts.page}`;
  // By characters, so a cut never leaves half of one, which encodeURIComponent refuses.
  const characters = Array.from(firstLine);
  return characters.length > TITLE_MAX
    ? `${characters
        .slice(0, TITLE_MAX - 1)
        .join("")
        .trimEnd()}…`
    : firstLine;
}

function time(at: string): string {
  return at.replace(/\.\d{3}Z$/, "Z");
}

function failureLine(failure: KeptFailure): string {
  // As code, so nothing in an engine's words is read as Markdown.
  if (failure.kind === "error") return `- ${time(failure.at)} An error: \`${failure.message.replaceAll("`", "")}\``;
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
  return `${position.square} at zoom ${position.zoom}`;
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
  "\n\n[The report was cut here to fit the address. Paste the full text, from Copy the details, in place of this.]";

/** An address and whether its body had to be cut to fit. */
export interface ReportAddress {
  url: string;
  cut: boolean;
}

/**
 * The address `build` makes from `body`, under `ADDRESS_MAX` characters. A
 * body too long for that is cut, by characters so no character is split,
 * and ends with `CUT_NOTE`.
 */
function fitted(build: (body: string) => string, body: string): ReportAddress {
  const whole = build(body);
  if (whole.length < ADDRESS_MAX) return { url: whole, cut: false };
  const characters = Array.from(body);
  let low = 0;
  let high = characters.length;
  while (low < high) {
    const middle = Math.ceil((low + high) / 2);
    if (build(characters.slice(0, middle).join("") + CUT_NOTE).length < ADDRESS_MAX) low = middle;
    else high = middle - 1;
  }
  const url = build(characters.slice(0, low).join("") + CUT_NOTE);
  if (url.length >= ADDRESS_MAX) throw new Error("A report's title alone is too long for an address");
  return { url, cut: true };
}

/** A new issue on the repository with `title` and `body` filled in. */
export function githubIssueUrl(title: string, body: string): ReportAddress {
  return fitted((text) => `${NEW_ISSUE_URL}?title=${encodeURIComponent(title)}&body=${encodeURIComponent(text)}`, body);
}

/** A `mailto:` address that writes the report to `address`, cut as the issue's is. */
export function emailUrl(address: string, title: string, body: string): ReportAddress {
  // Encoded whole, but for the "@", so nothing in the setting can add a recipient or a header.
  const to = encodeURIComponent(address).replace("%40", "@");
  return fitted((text) => `mailto:${to}?subject=${encodeURIComponent(title)}&body=${encodeURIComponent(text)}`, body);
}
