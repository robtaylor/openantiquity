import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Search } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useId, useState } from "react";
import { useNavigate } from "react-router";
import { useMapStore } from "../../map/store.js";
import { useMapCover, visibleCentre } from "../../map/visibleArea.js";
import { IconButton } from "../../ui/IconButton.js";
import { parseRecordId } from "../records/api.js";
import { elsewherePath, RECORD_SEARCH_PATH, recordPath } from "../records/paths.js";
import { SourceCredit } from "../records/SourceCredit.js";
import { useRecordSearch } from "../records/searchStore.js";
import { decodeEntities } from "../records/text.js";
import {
  cameraFor,
  fetchGeoSearch,
  type GeoResult,
  groupResults,
  isSearchRefused,
  isSearchTimeout,
  MAX_QUERY_CHARS,
  resultSources,
  searchKeys,
  takesOnEnter,
} from "./api.js";
import "./search.css";

/** How long typing must pause before the server is asked. */
export const SEARCH_DEBOUNCE_MS = 250;
/** Typing asks nothing until there are this many letters: one letter matches thousands of names. Enter asks anyway. */
export const MIN_SEARCH_CHARS = 2;

function resultDetail(result: GeoResult): string | null {
  const parts = [result.detail ?? null];
  if (result.obscured) parts.push("shown as its one-kilometre square");
  const text = parts.filter((part): part is string => Boolean(part)).join(" · ");
  return text === "" ? null : text;
}

/**
 * The search field. It understands a grid reference, a pair of coordinates,
 * a place name, a record's name and a finding's id, all through
 * `GET /geo/search`. Results are grouped by kind and can be worked by
 * keyboard alone: the arrow keys move through them, Enter takes one, and
 * Escape closes the list, or clears the field once the list is closed.
 * Typing is debounced, and a search still on its way when the text changes
 * is cancelled. Choosing a result moves the map there, and opens it if it is
 * a record or a finding.
 */
export function SearchBox() {
  const navigate = useNavigate();
  const [text, setText] = useState("");
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(-1);
  const term = text.trim();
  const [settled, setSettled] = useState("");
  /** A search Enter was pressed for before its results had come: its first result is taken when they do. */
  const [pendingPick, setPendingPick] = useState<string | null>(null);
  /** The label of the result just chosen. Nothing is asked for it until the text changes or the field is entered again. */
  const [picked, setPicked] = useState<string | null>(null);
  const id = useId();
  const listId = `${id}-list`;

  useEffect(() => {
    if (term === settled || (term !== "" && term.length < MIN_SEARCH_CHARS)) return;
    const timer = setTimeout(() => {
      setSettled(term);
      setPicked(null);
    }, SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [term, settled]);

  // The signal is passed on, so a search the text has moved past is cancelled.
  const query = useQuery({
    queryKey: searchKeys.geo(settled),
    queryFn: ({ signal }) => fetchGeoSearch(settled, signal),
    enabled: settled !== "" && settled !== picked,
    staleTime: 60_000,
    retry: false,
  });

  const current = term !== "" && settled === term;
  // Long enough to have been asked about, or asked about with Enter.
  const searchable = term !== "" && (term.length >= MIN_SEARCH_CHARS || current);
  const results = current && query.data ? query.data : [];
  const { groups, ordered } = groupResults(results);
  const waiting = searchable && (!current || query.isFetching);

  function choose(result: GeoResult): void {
    useMapStore.getState().requestCamera(cameraFor(result));
    const label = decodeEntities(result.label);
    setText(label);
    setSettled(label.trim());
    setPicked(label.trim());
    setOpen(false);
    setActive(-1);
    setPendingPick(null);
    // The ref is the server's, but it is checked before it becomes an address all the same.
    const recordId = result.type === "record" ? parseRecordId(result.ref ?? undefined) : null;
    if (recordId !== null) navigate(recordPath(recordId));
    else if (result.type === "finding" && result.ref) navigate(`/f/${encodeURIComponent(result.ref)}`);
  }

  /** Enter with nothing picked: the first result, if it is a sure match. Otherwise the list stays open to choose from. */
  function takeFirstIfSure(): void {
    const first = ordered[0];
    if (first && takesOnEnter(first, term)) choose(first);
  }

  // Enter pressed early: once the results for that text are in, go to the first if it is a sure match.
  // biome-ignore lint/correctness/useExhaustiveDependencies: takeFirstIfSure reads the latest render
  useEffect(() => {
    if (pendingPick === null || pendingPick !== term || !current || query.isFetching) return;
    setPendingPick(null);
    takeFirstIfSure();
  }, [pendingPick, current, query.isFetching, ordered[0]]);

  // The option the arrow keys are on is kept in sight in the scrolling list.
  // biome-ignore lint/correctness/useExhaustiveDependencies: the active option is the trigger
  useEffect(() => {
    if (active >= 0) document.getElementById(optionId(active))?.scrollIntoView?.({ block: "nearest" });
  }, [active]);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (term === "") return;
    if (active === moreIndex) {
      searchRecords();
      return;
    }
    if (retryIndex >= 0 && active === retryIndex) {
      retry();
      return;
    }
    const highlighted = ordered[active];
    if (highlighted) {
      choose(highlighted);
      return;
    }
    setOpen(true);
    if (current && !query.isFetching) {
      takeFirstIfSure();
      return;
    }
    setSettled(term);
    setPendingPick(term);
  }

  function onKeyDown(event: KeyboardEvent<HTMLInputElement>): void {
    if (event.key === "ArrowDown" || event.key === "ArrowUp") {
      event.preventDefault();
      if (!open) {
        setOpen(true);
        return;
      }
      const count = moreIndex + 1;
      const step = event.key === "ArrowDown" ? 1 : -1;
      setActive((index) => {
        const next = index + step;
        if (next >= count) return -1;
        if (next < -1) return count - 1;
        return next;
      });
    } else if (event.key === "Escape") {
      if (open && term !== "") {
        event.preventDefault();
        setOpen(false);
        setActive(-1);
      } else if (text !== "") {
        event.preventDefault();
        setText("");
        setActive(-1);
      }
    }
  }

  function searchRecords(): void {
    useRecordSearch.getState().set({ q: term });
    setOpen(false);
    navigate(RECORD_SEARCH_PATH);
  }

  function openElsewhere(): void {
    // The middle of what's showing, not of the window, which is under the panel.
    const middle = visibleCentre(useMapStore.getState().camera, useMapCover.getState().cover);
    navigate(elsewherePath(middle.lng, middle.lat));
  }

  const expanded = open && searchable;
  const optionId = (index: number) => `${id}-option-${index}`;
  const failed = current && query.isError;
  // A search the server refused would be refused again, so it is offered no retry.
  const refused = failed && isSearchRefused(query.error);
  const retryable = failed && !refused;
  // The options are the results, "Try again" when the search failed, and last, searching the records for the text.
  const retryIndex = retryable ? ordered.length : -1;
  const moreIndex = ordered.length + (retryable ? 1 : 0);
  const sources = resultSources(results);

  function retry(): void {
    setActive(-1);
    void query.refetch();
  }

  let message: string | null = null;
  if (expanded) {
    if (refused) {
      message = "That's more than can be searched for at once. Try a few words.";
    } else if (failed) {
      message = isSearchTimeout(query.error)
        ? "That search took too long. Add another word, or search for somewhere smaller."
        : "Search isn't working right now. Please try again in a moment.";
    } else if (waiting) {
      message = "Searching…";
    } else if (current && ordered.length === 0) {
      message = `Nothing matches “${term}”. Try a grid reference such as SU 123 456, a place, or a record's name.`;
    }
  }

  return (
    <search className="fc-search">
      <form onSubmit={onSubmit} role="presentation">
        <label className="fc-visually-hidden" htmlFor={id}>
          Search for a place, grid reference or record
        </label>
        <Search className="fc-search__icon" size={18} aria-hidden />
        <input
          id={id}
          className="fc-search__input"
          type="search"
          name="q"
          role="combobox"
          aria-expanded={expanded}
          aria-controls={listId}
          aria-autocomplete="list"
          aria-activedescendant={expanded && active >= 0 ? optionId(active) : undefined}
          aria-describedby={`${id}-hint`}
          value={text}
          placeholder="Search a place, grid ref or record"
          autoComplete="off"
          spellCheck={false}
          enterKeyHint="search"
          maxLength={MAX_QUERY_CHARS}
          onChange={(event) => {
            setText(event.currentTarget.value);
            setOpen(true);
            setActive(-1);
            setPendingPick(null);
          }}
          onFocus={() => {
            setOpen(true);
            setPicked(null);
          }}
          onBlur={() => setOpen(false)}
          onKeyDown={onKeyDown}
        />
        <span className="fc-visually-hidden" id={`${id}-hint`}>
          Results appear as you type. Use the up and down arrows to pick one and Enter to go there.
        </span>
        <IconButton
          className="fc-search__elsewhere"
          size="sm"
          label="Open the middle of the map in other viewers"
          onClick={openElsewhere}
        >
          <ExternalLink size={16} aria-hidden />
        </IconButton>
      </form>
      <div className="fc-search__popup" hidden={!expanded}>
        <div className="fc-search__message" role="status" aria-live="polite">
          {message}
        </div>
        <div className="fc-search__list" id={listId} role="listbox" aria-label="Search results" aria-busy={waiting}>
          {/* The results scroll. "Try again" and the record search stay at the foot of the list, always in sight. */}
          <div className="fc-search__results" role="presentation">
            {expanded
              ? groups.map((group) => (
                  // biome-ignore lint/a11y/useSemanticElements: a group of options inside a listbox
                  <div
                    key={group.type}
                    role="group"
                    aria-labelledby={`${id}-group-${group.type}`}
                    className="fc-search__group"
                  >
                    <div className="fc-search__group-label" id={`${id}-group-${group.type}`} role="presentation">
                      {group.label}
                    </div>
                    {group.items.map(({ result, index }) => {
                      const detail = resultDetail(result);
                      return (
                        // biome-ignore lint/a11y/useFocusableInteractive: focus stays in the field, as a combobox's does
                        // biome-ignore lint/a11y/useKeyWithClickEvents: the field handles the keys for every option
                        <div
                          key={`${result.type}-${result.ref ?? `${result.lon},${result.lat}`}-${index}`}
                          id={optionId(index)}
                          role="option"
                          aria-selected={index === active}
                          className="fc-search__option"
                          onMouseDown={(event) => event.preventDefault()}
                          onClick={() => choose(result)}
                        >
                          <span className="fc-search__label">{decodeEntities(result.label)}</span>
                          {detail ? <span className="fc-search__detail">{detail}</span> : null}
                        </div>
                      );
                    })}
                  </div>
                ))
              : null}
          </div>
          {expanded && retryable ? (
            // biome-ignore lint/a11y/useFocusableInteractive: focus stays in the field, as a combobox's does
            // biome-ignore lint/a11y/useKeyWithClickEvents: the field handles the keys for every option
            <div
              id={optionId(retryIndex)}
              role="option"
              aria-selected={active === retryIndex}
              className="fc-search__option fc-search__retry"
              onMouseDown={(event) => event.preventDefault()}
              onClick={retry}
            >
              <span className="fc-search__label">Try again</span>
            </div>
          ) : null}
          {expanded ? (
            // biome-ignore lint/a11y/useFocusableInteractive: focus stays in the field, as a combobox's does
            // biome-ignore lint/a11y/useKeyWithClickEvents: the field handles the keys for every option
            <div
              id={optionId(moreIndex)}
              role="option"
              aria-selected={active === moreIndex}
              className="fc-search__option fc-search__more"
              onMouseDown={(event) => event.preventDefault()}
              onClick={searchRecords}
            >
              <span className="fc-search__label">Search the heritage records for “{term}”</span>
            </div>
          ) : null}
        </div>
        {expanded && sources.length > 0 ? (
          // Each source's name and licence, as Decision 0004 asks. A record's page gives its full credit.
          <ul className="fc-search__credits" aria-label="Where these names come from">
            {sources.map((source) => (
              <li key={source.key}>
                <SourceCredit source={source} compact />
              </li>
            ))}
          </ul>
        ) : null}
      </div>
    </search>
  );
}
