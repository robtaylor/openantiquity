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

/** Where a `**` or a single `*` or `_` that closes emphasis starting at `from` is, or -1. */
function closing(source: string, marker: string, from: number): number {
  for (let i = from; i < source.length; i++) {
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
    return i;
  }
  return -1;
}

/** Where the `)` that closes a link's address starting at `from` is, allowing balanced brackets inside, or -1. */
function closingParen(source: string, from: number): number {
  let depth = 0;
  for (let i = from; i < source.length; i++) {
    const char = source[i];
    if (char === "(") depth++;
    else if (char === ")") {
      if (depth === 0) return i;
      depth--;
    } else if (char === " " || char === "\n") return -1;
  }
  return -1;
}

/** `[words](address)` starting at `start`, or null when there isn't one. */
function link(source: string, start: number): { label: string; href: string; end: number } | null {
  const labelEnd = source.indexOf("](", start + 1);
  if (labelEnd < 0 || source.slice(start + 1, labelEnd).includes("[")) return null;
  const hrefEnd = closingParen(source, labelEnd + 2);
  if (hrefEnd < 0) return null;
  return { label: source.slice(start + 1, labelEnd), href: source.slice(labelEnd + 2, hrefEnd), end: hrefEnd + 1 };
}

/** One line's, or one paragraph's, emphasis and links. */
export function parseInline(source: string): Inline[] {
  const out: Inline[] = [];
  let i = 0;
  while (i < source.length) {
    const char = source[i] as string;
    if (char === "\\" && ESCAPABLE.has(source[i + 1] ?? "")) {
      pushText(out, source[i + 1] as string);
      i += 2;
      continue;
    }
    if (char === "*" || char === "_") {
      const double = source.startsWith(`${char}${char}`, i) && char === "*";
      const marker = double ? "**" : char;
      const from = i + marker.length;
      const opensWord = !/\s/.test(source[from] ?? " ");
      // `_` inside a word, as in snake_case, is a letter, not emphasis.
      const midWord = char === "_" && /\w/.test(source[i - 1] ?? "");
      const end = opensWord && !midWord ? closing(source, marker, from) : -1;
      const closesWord = end >= 0 && !(char === "_" && /\w/.test(source[end + 1] ?? ""));
      if (end > from && closesWord) {
        out.push({ type: double ? "strong" : "em", children: parseInline(source.slice(from, end)) });
        i = end + marker.length;
        continue;
      }
      pushText(out, marker);
      i = from;
      continue;
    }
    if (char === "[") {
      const found = link(source, i);
      if (found) {
        const children = parseInline(found.label);
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
    const line = raw.replace(/\s+$/, "");
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
