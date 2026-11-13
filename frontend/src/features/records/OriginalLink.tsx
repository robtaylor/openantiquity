import { ExternalLink } from "lucide-react";
import type { ReactNode } from "react";
import { safeHref } from "../../map/attribution.js";

/** The category of a name read from an old map. No page describes one of those: its original is the map. */
const MAP_LABEL = "map_label";

export interface OriginalLinkProps {
  /** The record's page at its source, as the source gave it. */
  url: string | null;
  /** The record's category, which says what the original is called. */
  category: string;
  className: string;
  iconSize?: number;
  /** Drawn in the link's place when there is nothing to link to. */
  fallback?: ReactNode;
}

/**
 * The record's own page at its source, opened in another tab so the place
 * being looked at stays open. When the source gives no page, or an address
 * that isn't a web page, the fallback is drawn, or nothing.
 */
export function OriginalLink({ url, category, className, iconSize = 16, fallback = null }: OriginalLinkProps) {
  const href = safeHref(url);
  if (!href) return fallback;
  return (
    <a className={className} href={href} target="_blank" rel="noopener noreferrer external">
      <ExternalLink size={iconSize} aria-hidden />
      {category === MAP_LABEL ? "See it on the old map" : "See the original record"}
      <span className="fc-visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}
