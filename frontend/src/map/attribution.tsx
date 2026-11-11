import { Fragment, type ReactNode, useMemo } from "react";
import type { Meta } from "../api/meta.js";
import { useRecordsOnScreen } from "../features/records/onScreen.js";
import { useMapStore } from "./store.js";
import { visibleAttributions } from "./style.js";

/**
 * Attribution strings follow the map convention of allowing HTML, mostly for
 * a link to a licence page. They come from /meta, and in turn from other
 * people's services, so they are never put into the page as markup. They are
 * parsed, and only text and web links are kept.
 */

export interface AttributionPart {
  text: string;
  /** Set for a link to an http or https address. */
  href?: string;
}

/**
 * The address if it is an absolute http or https link, normalised, and
 * otherwise undefined. Anything from another service that becomes an `href`
 * goes through this, so a `javascript:` or `data:` address never does.
 */
export function safeHref(value: string | null | undefined): string | undefined {
  if (!value) return undefined;
  try {
    const url = new URL(value, "https://invalid.example/");
    // A relative address would resolve against the placeholder host above.
    if (url.hostname === "invalid.example") return undefined;
    return url.protocol === "https:" || url.protocol === "http:" ? url.href : undefined;
  } catch {
    return undefined;
  }
}

function collect(node: Node, href: string | undefined, parts: AttributionPart[]): void {
  if (node.nodeType === Node.TEXT_NODE) {
    const text = node.textContent ?? "";
    if (text === "") return;
    const last = parts[parts.length - 1];
    // Neighbouring pieces with the same target are one run of text.
    if (last && last.href === href) last.text += text;
    else parts.push(href === undefined ? { text } : { text, href });
    return;
  }
  if (node.nodeType !== Node.ELEMENT_NODE) return;
  const element = node as Element;
  const tag = element.tagName.toLowerCase();
  if (tag === "script" || tag === "style") return;
  const ownHref = tag === "a" ? safeHref(element.getAttribute("href")) : undefined;
  for (const child of element.childNodes) collect(child, ownHref ?? href, parts);
}

function parse(html: string): AttributionPart[] {
  if (!html.includes("<") && !html.includes("&")) return html.trim() === "" ? [] : [{ text: html.trim() }];
  const document = new DOMParser().parseFromString(html, "text/html");
  const parts: AttributionPart[] = [];
  collect(document.body, undefined, parts);
  const first = parts[0];
  const last = parts[parts.length - 1];
  if (first) first.text = first.text.trimStart();
  if (last) last.text = last.text.trimEnd();
  return parts.filter((part) => part.text !== "");
}

/**
 * Parsed attributions by source string. The strings come from /meta, so there
 * are only a few, and the status bar asks for them on every pointer move.
 */
const parsed = new Map<string, readonly Readonly<AttributionPart>[]>();
/** A guard against unbounded growth should the strings ever stop being a small fixed set. */
const MAX_CACHED = 256;

/** Split an attribution string into text and links, dropping all other markup. */
export function parseAttribution(html: string): readonly Readonly<AttributionPart>[] {
  let parts = parsed.get(html);
  if (!parts) {
    if (parsed.size >= MAX_CACHED) parsed.clear();
    parts = Object.freeze(parse(html).map((part) => Object.freeze(part)));
    parsed.set(html, parts);
  }
  return parts;
}

/** The attribution as plain text, for places with no room for links. */
export function attributionText(html: string): string {
  return parseAttribution(html)
    .map((part) => part.text)
    .join("")
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Attribution lines for everything the map currently shows: the layers, the
 * sources of the heritage records drawn on screen, and every live source
 * whose records are on the map.
 */
export function useAttributions(meta: Meta): string[] {
  const mainView = useMapStore((state) => state.mainView);
  const compareView = useMapStore((state) => state.compareView);
  const overlays = useMapStore((state) => state.overlays);
  const terrain = useMapStore((state) => state.terrain);
  const failing = useMapStore((state) => state.failing);
  const recordSources = useRecordsOnScreen((state) => state.sources);
  const live = useRecordsOnScreen((state) => state.liveAttributions);
  return useMemo(() => {
    const lines = visibleAttributions(meta, { overlays, terrain, failing }, [mainView, compareView], recordSources);
    for (const line of live) if (!lines.includes(line)) lines.push(line);
    return lines;
  }, [meta, overlays, terrain, failing, mainView, compareView, recordSources, live]);
}

/** The attribution with its links, safe to render. */
export function Attribution({ html }: { html: string }): ReactNode {
  return parseAttribution(html).map((part, index) =>
    part.href ? (
      // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one string never reorder
      <a key={index} href={part.href} target="_blank" rel="noopener noreferrer">
        {part.text}
      </a>
    ) : (
      // biome-ignore lint/suspicious/noArrayIndexKey: the parts of one string never reorder
      <Fragment key={index}>{part.text}</Fragment>
    ),
  );
}
