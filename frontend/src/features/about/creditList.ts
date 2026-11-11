/**
 * Every source of data the API lists, as one list of credits the about page
 * can group and search: the map's layers, the record sources in `/meta`, and
 * the sources the browser asks itself (`GET /context/live-sources`). The
 * licences require the credit, so nothing the API lists is left out.
 */

import type { Meta } from "../../api/meta.js";
import type { components } from "../../api/schema.js";
import { attributionText } from "../../map/attribution.js";

export type LiveSource = components["schemas"]["LiveSource"];

export interface Credit {
  key: string;
  name: string;
  publisher: string | null;
  /** The licence in words. */
  licence: string | null;
  licenceUrl: string | null;
  /** The credit the publisher asks for. May hold links, so it is shown with `Attribution`. */
  attribution: string | null;
  homepage: string | null;
}

export interface CreditGroup {
  id: string;
  title: string;
  /** A sentence on how this kind of data reaches the page. */
  about: string;
  credits: Credit[];
}

export const LAYERS_GROUP = "layers";
export const LIVE_GROUP = "live";

/** A record category's name from `/meta`, or the id in words when `/meta` has no name for it. */
export function categoryTitle(meta: Meta, category: string): string {
  const label = meta.vocab.record_categories.find((item) => item.id === category)?.label;
  if (label) return label;
  const words = category.replaceAll("_", " ").trim();
  return words.charAt(0).toUpperCase() + words.slice(1);
}

interface CreditedLayer {
  id: string;
  title: string;
  attribution?: string;
  licence?: string;
  licence_url?: string;
}

/**
 * The map's layers, one credit per attribution and licence: several views
 * drawn from the same data share it. A layer with no attribution needs none.
 * Where two credits would carry the same name, such as a map view and an
 * overlay drawn from the same data by different services, each says what it is.
 */
function layerCredits(meta: Meta): Credit[] {
  const overlays = new Set(meta.layers.overlays.map((overlay) => overlay.id));
  const layers: CreditedLayer[] = [
    ...meta.layers.views,
    { ...meta.layers.dem, id: "dem", title: "Height of the ground" },
    ...meta.layers.overlays,
  ];
  const byTerms = new Map<string, Credit>();
  const overlayCredits = new Set<Credit>();
  for (const layer of layers) {
    const attribution = layer.attribution?.trim();
    if (!attribution) continue;
    const licence = layer.licence?.trim() || null;
    const terms = `${attribution}\n${licence ?? ""}`;
    const credit = byTerms.get(terms);
    if (credit) {
      credit.name = `${credit.name}, ${layer.title}`;
      continue;
    }
    const added: Credit = {
      key: `layer-${layer.id}`,
      name: layer.title,
      publisher: null,
      licence,
      licenceUrl: licence ? (layer.licence_url ?? null) : null,
      attribution,
      homepage: null,
    };
    byTerms.set(terms, added);
    if (overlays.has(layer.id)) overlayCredits.add(added);
  }
  const credits = [...byTerms.values()];
  const names = credits.map((credit) => credit.name);
  for (const credit of credits) {
    if (names.indexOf(credit.name) === names.lastIndexOf(credit.name)) continue;
    credit.name = overlayCredits.has(credit) ? `${credit.name}, drawn over the terrain` : `${credit.name}, as a map`;
  }
  return credits;
}

function liveCredit(source: LiveSource): Credit {
  return {
    key: `live-${source.key}`,
    name: source.name,
    publisher: source.publisher,
    // The label is the licence in words. The `licence` field is the research's note on it.
    licence: source.licence_label ?? source.licence,
    licenceUrl: null,
    attribution: source.credit ?? source.attribution,
    homepage: source.homepage,
  };
}

/** Every credit, grouped: the map's layers, then record sources by category in `/meta`'s order, then live sources. */
export function creditGroups(meta: Meta, live: readonly LiveSource[]): CreditGroup[] {
  const groups: CreditGroup[] = [];
  const layers = layerCredits(meta);
  if (layers.length > 0) {
    groups.push({
      id: LAYERS_GROUP,
      title: "Map layers",
      about: "The terrain views, the height of the ground and the maps drawn over them.",
      credits: layers,
    });
  }

  const byCategory = new Map<string, Credit[]>();
  for (const source of meta.sources) {
    const credits = byCategory.get(source.category) ?? [];
    credits.push({
      key: `source-${source.key}`,
      name: source.name,
      publisher: source.publisher,
      licence: source.licence,
      licenceUrl: source.licence_url ?? null,
      attribution: source.attribution,
      homepage: source.homepage,
    });
    byCategory.set(source.category, credits);
  }
  const order = meta.vocab.record_categories.map((category) => category.id);
  const categories = [...byCategory.keys()].sort((a, b) => {
    const rank = (id: string) => (order.includes(id) ? order.indexOf(id) : order.length);
    return rank(a) - rank(b) || a.localeCompare(b);
  });
  for (const category of categories) {
    groups.push({
      id: `category-${category}`,
      title: categoryTitle(meta, category),
      about: "Copied into Open Antiquity's index under the licence shown.",
      credits: byCategory.get(category) ?? [],
    });
  }

  if (live.length > 0) {
    groups.push({
      id: LIVE_GROUP,
      title: "Looked up from your browser",
      about:
        "Your browser asks these services itself when you look at an area. Open Antiquity doesn't keep a copy of what they send.",
      credits: live.map(liveCredit),
    });
  }
  return groups;
}

function haystack(credit: Credit): string {
  return [
    credit.name,
    credit.publisher,
    credit.licence,
    credit.attribution ? attributionText(credit.attribution) : null,
  ]
    .filter((part): part is string => part !== null)
    .join(" ")
    .toLowerCase();
}

/**
 * The groups with only the credits that hold every word of the search, in
 * their name, publisher, licence or credit line. Groups left empty go.
 */
export function searchCredits(groups: readonly CreditGroup[], search: string): CreditGroup[] {
  const words = search
    .toLowerCase()
    .split(/\s+/)
    .filter((word) => word !== "");
  if (words.length === 0) return [...groups];
  return groups
    .map((group) => {
      const titleMatches = words.every((word) => group.title.toLowerCase().includes(word));
      const credits = titleMatches
        ? group.credits
        : group.credits.filter((credit) => {
            const text = haystack(credit);
            return words.every((word) => text.includes(word));
          });
      return { ...group, credits };
    })
    .filter((group) => group.credits.length > 0);
}

/** How many credits the groups hold. */
export function creditCount(groups: readonly CreditGroup[]): number {
  return groups.reduce((total, group) => total + group.credits.length, 0);
}
