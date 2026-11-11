import { useEffect, useRef } from "react";
import { useLocation, useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { MAX_QUERY_CHARS } from "../search/api.js";
import { RECORD_SEARCH_PATH } from "./paths.js";
import { type RecordSearchState, type SearchScope, useRecordSearch } from "./searchStore.js";

/**
 * The record search in the address, so a search can be shared, reloaded and
 * reached again with back and forward:
 *
 *   /records?q=barrow&scope=everywhere&category=monument&category=find&source=nhle-scheduled
 *
 * The parameters have the API's names. The scope is written only when it is
 * not the map's view, which is where a new search looks.
 */

export type SearchTerms = Pick<RecordSearchState, "q" | "sources" | "categories" | "scope">;

const EMPTY: SearchTerms = { q: "", sources: [], categories: [], scope: "view" };

export function searchToParams(terms: SearchTerms): URLSearchParams {
  const params = new URLSearchParams();
  if (terms.q !== "") params.set("q", terms.q);
  if (terms.scope !== "view") params.set("scope", terms.scope);
  for (const category of terms.categories) params.append("category", category);
  for (const source of terms.sources) params.append("source", source);
  return params;
}

/**
 * The search an address describes. Kinds and sources the catalogue doesn't
 * know are dropped, as the server would refuse them, and so is a repeat.
 */
export function searchFromParams(params: URLSearchParams, meta: Meta): SearchTerms {
  const categories = new Set(meta.vocab.record_categories.map((category) => category.id));
  const sources = new Set(meta.sources.map((source) => source.key));
  const known = (values: string[], allowed: Set<string>): string[] =>
    [...new Set(values)].filter((value) => allowed.has(value));
  const scope: SearchScope = params.get("scope") === "everywhere" ? "everywhere" : "view";
  return {
    q: (params.get("q") ?? "").slice(0, MAX_QUERY_CHARS),
    scope,
    categories: known(params.getAll("category"), categories),
    sources: known(params.getAll("source"), sources).slice(0, 1),
  };
}

function queryString(terms: SearchTerms): string {
  const text = searchToParams(terms).toString();
  return text === "" ? "" : `?${text}`;
}

const pickTerms = (state: RecordSearchState): SearchTerms => ({
  q: state.q,
  sources: state.sources,
  categories: state.categories,
  scope: state.scope,
});

/**
 * Keeps the search panel's terms and its address together. An address that
 * carries a search, opened or reached with back and forward, sets the terms.
 * One that carries none is given the search kept from earlier, so a search
 * left to open a record comes back with the panel. A change to the terms
 * rewrites the address: typing replaces the current entry, and any other
 * change, such as a kind chosen, adds one. `commit` adds one for the words as
 * they stand, when Enter is pressed in the words field.
 *
 * The map's hash is left off these addresses on purpose: the router's copy of
 * it trails the map, and the permalink puts the current one straight back.
 */
export function useSearchAddress(meta: Meta): { commit: () => void } {
  const { search } = useLocation();
  const navigate = useNavigate();
  const wanted = useRecordSearch((state) => queryString(pickTerms(state)));
  /** The terms last written to the address, to tell typing from other changes. */
  const written = useRef<SearchTerms | null>(null);

  // The address, when it changes, sets the terms.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the address is the trigger
  useEffect(() => {
    const store = useRecordSearch.getState();
    if (search === "" || search === "?") return;
    const fromAddress = searchFromParams(new URLSearchParams(search), meta);
    written.current = fromAddress;
    if (queryString(fromAddress) !== queryString(pickTerms(store))) store.set(fromAddress);
  }, [search]);

  // The terms, when they change, set the address. They are read afresh, so a
  // search the address has just set is not written back over it.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the terms are the trigger
  useEffect(() => {
    const now = pickTerms(useRecordSearch.getState());
    const next = queryString(now);
    if (next === search) {
      written.current = now;
      return;
    }
    const previous = written.current ?? EMPTY;
    // Only the words changed, or the address had no search to keep.
    const typing = search === "" || queryString({ ...previous, q: "" }) === queryString({ ...now, q: "" });
    written.current = now;
    navigate({ pathname: RECORD_SEARCH_PATH, search: next }, { replace: typing });
  }, [wanted]);

  return {
    commit: () => {
      navigate({ pathname: RECORD_SEARCH_PATH, search: queryString(pickTerms(useRecordSearch.getState())) });
    },
  };
}
