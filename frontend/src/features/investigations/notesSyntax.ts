/**
 * The small part of Markdown an investigation's notes are read with:
 * headings, paragraphs, bulleted and numbered lists, strong, emphasis and
 * links. It parses to plain data that `Markdown.tsx` turns into React
 * elements, so the text is only ever text: HTML in a note stays as the
 * characters it is, and a link becomes one only for an http or https
 * address (`safeHref`). Anything else Markdown has is shown as written.
 */

import { safeHref } from "../../map/attribution.js";

export type Inline =
  | { type: "text"; text: string }
  | { type: "strong"; children: Inline[] }
  | { type: "em"; children: Inline[] }
  | { type: "link"; href: string; children: Inline[] };

export type Block =
  | { type: "heading"; level: 1 | 2 | 3 | 4 | 5 | 6; children: Inline[] }
  | { type: "paragraph"; children: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] };

const ESCAPABLE = new Set(["\\", "*", "_", "[", "]", "(", ")", "#", "-", "+", "."]);

/** Adds text to the end of a run, joining it to text already there. */
function pushText(out: Inline[], value: string): void {
  if (value === "") return;
  const last = out[out.length - 1];
  if (last?.type === "text") last.text += value;
  else out.push({ type: "text", text: value });
}

/** Appends a run of inlines, joining text at the seam. */
function pushAll(out: Inline[], inlines: readonly Inline[]): void {
  for (const inline of inlines) {
    if (inline.type === "text") pushText(out, inline.text);
    else out.push(inline);
  }
}

/**
 * Notes come from other people and can be long (50,000 characters), so the
 * parse has to stay quick whatever is in them. Looking ahead for a closing
 * marker is the only costly part. Each run remembers its last search for each
 * marker, so a hundred unclosed openers don't each scan to the end, and every
 * look ahead draws on one budget, a fixed multiple of the note's length. Once
 * it is spent, what is left is shown as written. Emphasis nests at most
 * `MAX_DEPTH` deep, and an address is at most `MAX_ADDRESS` long.
 */
export const MAX_DEPTH = 8;
const MAX_ADDRESS = 2048;
const BUDGET_PER_CHAR = 40;

interface Run {
  /** Characters that may still be looked at ahead of the parse, shared by every nested run. */
  budget: { left: number };
  /** The last search for each closing marker in this run: where it started and what it found. */
  closers: Map<string, { from: number; found: number }>;
  /** The same for the `](` that ends a link's words. */
  labelEnd: { from: number; found: number } | null;
}

function newRun(budget: Run["budget"]): Run {
  return { budget, closers: new Map(), labelEnd: null };
}

/** Where a `**` or a single `*` or `_` that closes emphasis starting at `from` is, or -1. */
function closing(source: string, marker: string, from: number, run: Run): number {
  // The first closer after an earlier start is also the first after any later start before it.
  const last = run.closers.get(marker);
  if (last && from > last.from && (last.found < 0 || from < last.found)) return last.found;
  let found = -1;
  for (let i = from; i < source.length; i++) {
    if (--run.budget.left < 0) return -1;
    if (source[i] === "\\") {
      i++;
      continue;
    }
    if (!source.startsWith(marker, i)) continue;
    // In a run of three, as in `***`, the double marker is the last two: the first closes an emphasis inside.
    if (marker.length === 2 && source[i + 2] === "*") continue;
    // A single marker that is half of a double one belongs to that, unless it closes at the end of the double.
    if (marker.length === 1 && source[i + 1] === marker && source[i + 2] !== marker) {
      i++;
      continue;
    }
    if (i === from || /\s/.test(source[i - 1] ?? "")) continue;
    found = i;
    break;
  }
  run.closers.set(marker, { from, found });
  return found;
}

/** Where the `)` that closes a link's address starting at `from` is, allowing balanced brackets inside, or -1. */
function closingParen(source: string, from: number, run: Run): number {
  let depth = 0;
  const end = Math.min(source.length, from + MAX_ADDRESS);
  for (let i = from; i < end; i++) {
    if (--run.budget.left < 0) return -1;
    const char = source[i];
    if (char === "(") depth++;
    else if (char === ")") {
      if (depth === 0) return i;
      depth--;
    } else if (char === " " || char === "\n") return -1;
  }
  return -1;
}

/** The `](` at or after `from`, or -1, remembering the search as `closing` does. */
function labelEndFrom(source: string, from: number, run: Run): number {
  const last = run.labelEnd;
  if (last && from > last.from && (last.found < 0 || from <= last.found)) return last.found;
  const found = source.indexOf("](", from);
  run.budget.left -= (found < 0 ? source.length : found) - from;
  run.labelEnd = { from, found };
  return found;
}

/** `[words](address)` starting at `start`, or null when there isn't one. */
function link(source: string, start: number, run: Run): { label: string; href: string; end: number } | null {
  if (run.budget.left < 0) return null;
  const labelEnd = labelEndFrom(source, start + 1, run);
  if (labelEnd < 0) return null;
  // Words with a `[` of their own aren't a link's. The nearest `[` is never further than the next one parsed.
  const bracket = source.indexOf("[", start + 1);
  if (bracket >= 0 && bracket < labelEnd) return null;
  const hrefEnd = closingParen(source, labelEnd + 2, run);
  if (hrefEnd < 0) return null;
  return { label: source.slice(start + 1, labelEnd), href: source.slice(labelEnd + 2, hrefEnd), end: hrefEnd + 1 };
}

/** One line's, or one paragraph's, emphasis and links. */
export function parseInline(source: string): Inline[] {
  return inline(source, { left: BUDGET_PER_CHAR * source.length + 1000 }, 0);
}

function inline(source: string, budget: Run["budget"], depth: number): Inline[] {
  const run = newRun(budget);
  // Deeper than this, markers are shown as written.
  const nests = depth < MAX_DEPTH;
  const out: Inline[] = [];
  let i = 0;
  while (i < source.length) {
    const char = source[i] as string;
    if (char === "\\" && ESCAPABLE.has(source[i + 1] ?? "")) {
      pushText(out, source[i + 1] as string);
      i += 2;
      continue;
    }
    if (nests && (char === "*" || char === "_")) {
      const double = source.startsWith(`${char}${char}`, i) && char === "*";
      const marker = double ? "**" : char;
      const from = i + marker.length;
      const opensWord = !/\s/.test(source[from] ?? " ");
      // `_` inside a word, as in snake_case, is a letter, not emphasis.
      const midWord = char === "_" && /\w/.test(source[i - 1] ?? "");
      const end = opensWord && !midWord ? closing(source, marker, from, run) : -1;
      const closesWord = end >= 0 && !(char === "_" && /\w/.test(source[end + 1] ?? ""));
      if (end > from && closesWord) {
        out.push({ type: double ? "strong" : "em", children: inline(source.slice(from, end), budget, depth + 1) });
        i = end + marker.length;
        continue;
      }
      pushText(out, marker);
      i = from;
      continue;
    }
    if (nests && char === "[") {
      const found = link(source, i, run);
      if (found) {
        const children = inline(found.label, budget, depth + 1);
        const href = safeHref(found.href.trim());
        if (href) out.push({ type: "link", href, children });
        else pushAll(out, children);
        i = found.end;
        continue;
      }
    }
    pushText(out, char);
    i++;
  }
  return out;
}

const HEADING = /^(#{1,6})\s+(.*?)\s*#*\s*$/;
const BULLET = /^\s{0,3}[-*+]\s+(.*)$/;
const NUMBERED = /^\s{0,3}\d{1,9}[.)]\s+(.*)$/;

/** The blocks of a note, in order. */
export function parseMarkdown(source: string): Block[] {
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  let list: { ordered: boolean; items: string[] } | null = null;

  function flush(): void {
    if (paragraph.length > 0) {
      blocks.push({ type: "paragraph", children: parseInline(paragraph.join(" ")) });
      paragraph = [];
    }
    if (list) {
      blocks.push({ type: "list", ordered: list.ordered, items: list.items.map((item) => parseInline(item)) });
      list = null;
    }
  }

  for (const raw of source.replace(/\r\n?/g, "\n").split("\n")) {
    // trimEnd, not a regular expression: `\s+$` backtracks over every run of spaces inside a long line.
    const line = raw.trimEnd();
    if (line.trim() === "") {
      flush();
      continue;
    }
    const heading = HEADING.exec(line);
    if (heading && paragraph.length === 0) {
      flush();
      const level = (heading[1] as string).length as 1 | 2 | 3 | 4 | 5 | 6;
      blocks.push({ type: "heading", level, children: parseInline(heading[2] as string) });
      continue;
    }
    const bullet = BULLET.exec(line);
    const numbered = bullet ? null : NUMBERED.exec(line);
    const item = bullet ?? numbered;
    if (item) {
      const ordered = numbered !== null;
      if (paragraph.length > 0 || (list && list.ordered !== ordered)) flush();
      list ??= { ordered, items: [] };
      list.items.push((item[1] as string).trim());
      continue;
    }
    if (list && /^\s/.test(raw)) {
      const last = list.items.length - 1;
      list.items[last] = `${list.items[last]} ${line.trim()}`;
      continue;
    }
    if (list) flush();
    paragraph.push(line.trim());
  }
  flush();
  return blocks;
}
