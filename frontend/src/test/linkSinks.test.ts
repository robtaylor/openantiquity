import { describe, expect, it } from "vitest";

/**
 * Every link the app draws from data goes through `safeHref` (or, for a
 * mention, `mentionHref`), so an address that isn't a web address is never
 * followed, whatever the server or a publisher sends. This reads the source
 * and refuses an `href` set straight from a field such as `.url`, `.homepage`
 * or `.licenceUrl`, which is how the moderator's view and the credits page
 * once skipped it.
 */

/** The app's own source, by path from `src/`, without the tests. */
const SOURCES = Object.entries(
  import.meta.glob<string>(["../**/*.ts", "../**/*.tsx", "!../**/*.test.ts", "!../**/*.test.tsx", "!../test/**"], {
    query: "?raw",
    import: "default",
    eager: true,
  }),
).map(([path, text]) => ({ path: path.replace(/^\.\.\//, ""), text }));

/** Parsed nodes whose href was put through `safeHref` when they were parsed. */
const PARSED_SAFE = new Set([
  "features/investigations/Markdown.tsx: href={node.href",
  "map/attribution.tsx: href={part.href",
]);

const RAW_HREF = /href=\{\s*[\w.?]*\.(url|homepage|licenceUrl|licence_url|canonical_url|href)\b(?!\()/g;

describe("link sinks", () => {
  it("never sets an href straight from a data field", () => {
    expect(SOURCES.length).toBeGreaterThan(100);
    const raw = SOURCES.flatMap(({ path, text }) =>
      [...text.matchAll(RAW_HREF)].map((match) => `${path}: ${match[0]}`),
    );
    expect(raw.filter((sink) => !PARSED_SAFE.has(sink))).toEqual([]);
  });
});
