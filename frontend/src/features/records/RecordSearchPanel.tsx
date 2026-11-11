import { keepPreviousData, useInfiniteQuery } from "@tanstack/react-query";
import { Download, SearchX, Unplug } from "lucide-react";
import { useEffect, useMemo, useState } from "react";
import { Link, useLocation } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useMeta } from "../../api/useMeta.js";
import { useViewAreaStore } from "../../map/store.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Field } from "../../ui/Field.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { useDebounced } from "../../ui/useDebounced.js";
import { useDocumentTitle } from "../placeholders.js";
import { isSearchRefused, isSearchTimeout, MAX_QUERY_CHARS } from "../search/api.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import {
  type Bbox,
  type RecordQuery,
  type RecordSummary,
  recordKeys,
  recordsDownloadUrl,
  searchRecords,
} from "./api.js";
import { CategoryMark } from "./CategoryMark.js";
import { RECORD_SEARCH_PATH, recordPath } from "./paths.js";
import { SourceCredit } from "./SourceCredit.js";
import { useSearchAddress } from "./searchAddress.js";
import { type SearchScope, useRecordSearch } from "./searchStore.js";
import { decodeEntities } from "./text.js";
import "./records.css";

/** How long the words and the view must hold still before the server is asked. */
export const RECORD_SEARCH_DEBOUNCE_MS = 300;

const SCOPES: Array<{ id: SearchScope; label: string }> = [
  { id: "view", label: "In the map's view" },
  { id: "everywhere", label: "Everywhere" },
];

/** The view to about a hundred metres, as text, so small drags ask the same question again. */
function viewKey(bounds: readonly [number, number, number, number] | null): string | null {
  return bounds === null ? null : bounds.map((value) => value.toFixed(3)).join(",");
}

function ResultItem({ meta, record }: { meta: Meta; record: RecordSummary }) {
  return (
    <li className="fc-record-result">
      <Link className="fc-record-result__name" to={recordPath(record.id)}>
        {decodeEntities(record.name)}
      </Link>
      <p className="fc-record-result__kind">
        <CategoryMark meta={meta} category={record.category} />
        {record.record_type ? <span className="fc-record__type">{record.record_type}</span> : null}
      </p>
      <p className="fc-record-result__source">
        From <SourceCredit source={record.source} compact />
      </p>
    </li>
  );
}

function SearchForm({ meta, onCommit }: { meta: Meta; onCommit: () => void }) {
  const { q, sources, categories, scope, set } = useRecordSearch();
  // Open whenever a search brought back from earlier, or from the address, narrows them.
  const narrowed = categories.length > 0 || sources.length > 0;
  const [moreOpen, setMoreOpen] = useState(narrowed);
  useEffect(() => {
    if (narrowed) setMoreOpen(true);
  }, [narrowed]);
  return (
    <form
      className="fc-record-search__form"
      onSubmit={(event) => {
        event.preventDefault();
        onCommit();
      }}
    >
      <Field label="Words to look for" hint="Part of a name, a type such as “barrow”, or words from a summary.">
        {(control) => (
          <input
            {...control}
            className="fc-input"
            type="search"
            value={q}
            autoComplete="off"
            spellCheck={false}
            maxLength={MAX_QUERY_CHARS}
            enterKeyHint="search"
            onChange={(event) => set({ q: event.currentTarget.value })}
          />
        )}
      </Field>
      <div className="fc-record-search__row">
        <p className="fc-field__label">Where</p>
        <ChipGroup
          label="Where to look"
          value={scope}
          options={SCOPES}
          onChange={(next) => set({ scope: next as SearchScope })}
        />
      </div>
      <details
        className="fc-record-search__more"
        open={moreOpen}
        onToggle={(event) => setMoreOpen(event.currentTarget.open)}
      >
        <summary>
          Kinds and sources
          {categories.length + sources.length > 0 ? ` (${categories.length + sources.length} chosen)` : ""}
        </summary>
        <div className="fc-record-search__row">
          <p className="fc-field__label">Kinds of record</p>
          <ChipGroup
            multiple
            label="Kinds of record to look for"
            value={[...categories]}
            options={meta.vocab.record_categories.map((category) => ({ id: category.id, label: category.label }))}
            onChange={(next) => set({ categories: next })}
          />
          <p className="fc-field__hint">Choose none to look through every kind.</p>
        </div>
        {meta.sources.length > 0 ? (
          <Field label="Source">
            {(control) => (
              <select
                {...control}
                className="fc-input fc-select"
                value={sources[0] ?? ""}
                onChange={(event) => set({ sources: event.currentTarget.value ? [event.currentTarget.value] : [] })}
              >
                <option value="">Every source</option>
                {meta.sources.map((source) => (
                  <option key={source.key} value={source.key}>
                    {source.name}
                  </option>
                ))}
              </select>
            )}
          </Field>
        ) : null}
      </details>
    </form>
  );
}

function Results({ meta }: { meta: Meta }) {
  const { q, sources, categories, scope } = useRecordSearch();
  const bounds = useViewAreaStore((state) => state.bounds);
  const view = useDebounced(scope === "view" ? viewKey(bounds) : null, RECORD_SEARCH_DEBOUNCE_MS);
  const words = useDebounced(q.trim(), RECORD_SEARCH_DEBOUNCE_MS);

  const recordQuery = useMemo<RecordQuery>(
    () => ({
      q: words,
      sources: [...sources],
      categories: [...categories],
      bbox: scope === "view" && view ? (view.split(",").map(Number) as Bbox) : null,
    }),
    [words, sources, categories, scope, view],
  );
  const waitingForView = scope === "view" && recordQuery.bbox === null;

  const search = useInfiniteQuery({
    queryKey: recordKeys.search(recordQuery),
    queryFn: ({ pageParam, signal }) => searchRecords(recordQuery, pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    enabled: !waitingForView,
    staleTime: 60_000,
    placeholderData: keepPreviousData,
    retry: false,
  });

  if (search.isError && !search.data && isSearchRefused(search.error)) {
    // Asking again would be refused again, so there is nothing to retry.
    return (
      <EmptyState tone="error" icon={<SearchX size={22} />} title="That search can't be made">
        <p>Try fewer words, or choose fewer kinds of record.</p>
      </EmptyState>
    );
  }
  if (search.isError && !search.data) {
    const timedOut = isSearchTimeout(search.error);
    return (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title={timedOut ? "That search took too long" : "The records couldn't be searched"}
        action={
          <Button variant="primary" onClick={() => void search.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{timedOut ? "Add another word, or search the map's view instead of everywhere." : search.error.message}</p>
      </EmptyState>
    );
  }
  if (!search.data) {
    return (
      <div role="status" className="fc-record-search__loading">
        <span className="fc-visually-hidden">Searching the records</span>
        <Skeleton lines={3} />
        <Skeleton lines={3} />
      </div>
    );
  }

  const records = search.data.pages.flatMap((page) => page.items);
  if (records.length === 0) {
    return (
      <EmptyState icon={<SearchX size={22} />} title="No records match">
        <p>
          {scope === "view"
            ? "Nothing recorded matches in the map's view. Try looking everywhere, or move the map. An empty map doesn't always mean nothing is recorded: some records are only linked."
            : "Try fewer words, or choose fewer kinds of record."}
        </p>
      </EmptyState>
    );
  }

  return (
    <div className="fc-record-search__results" aria-busy={search.isFetching}>
      <div className="fc-record-search__summary">
        <p role="status">
          {records.length === 1 ? "1 record" : `${records.length} records`}
          {search.hasNextPage ? " so far" : ""}
          {search.isFetching && !search.isFetchingNextPage ? ", updating…" : ""}
        </p>
        <a
          className="fc-button fc-button--ghost fc-button--sm"
          href={recordsDownloadUrl(recordQuery)}
          download="heritage-records.geojson"
        >
          <Download size={16} aria-hidden />
          Download as GeoJSON
        </a>
      </div>
      <p className="fc-field__hint">The download holds up to 200 records, each with its source's licence and credit.</p>
      <ul className="fc-record-search__list">
        {records.map((record) => (
          <ResultItem key={record.id} meta={meta} record={record} />
        ))}
      </ul>
      {search.hasNextPage ? (
        <Button block onClick={() => void search.fetchNextPage()} disabled={search.isFetchingNextPage}>
          {search.isFetchingNextPage ? "Loading more…" : "Show more"}
        </Button>
      ) : null}
      {search.isError ? (
        <p className="fc-record-search__error" role="alert">
          {isSearchTimeout(search.error) ? "That took too long." : "That didn't work."} Try again in a moment.
        </p>
      ) : null}
    </div>
  );
}

/** The form and the results, once the catalogue is in, which the address is read against. */
function SearchBody({ meta }: { meta: Meta }) {
  const { commit } = useSearchAddress(meta);
  return (
    <div className="fc-record-search">
      <SearchForm meta={meta} onCommit={commit} />
      <Results meta={meta} />
    </div>
  );
}

/** `/records`: the record index, searched by words, kind, source and area. The search is kept in the address. */
export function RecordSearchPanel() {
  const { pathname } = useLocation();
  const meta = useMeta().data;
  useDocumentTitle("Search the records");
  return (
    <PanelFrame
      panelKey={pathname || RECORD_SEARCH_PATH}
      title="Search the records"
      subtitle="Heritage records in the index"
    >
      {meta ? <SearchBody meta={meta} /> : null}
    </PanelFrame>
  );
}
