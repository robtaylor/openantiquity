import { useQuery } from "@tanstack/react-query";
import { ExternalLink, Search } from "lucide-react";
import { type FormEvent, type KeyboardEvent, useEffect, useId, useState } from "react";
import { useNavigate } from "react-router";
import { useMapStore } from "../../map/store.js";
import { IconButton } from "../../ui/IconButton.js";
import { elsewherePath, RECORD_SEARCH_PATH, recordPath } from "../records/paths.js";
import { useRecordSearch } from "../records/searchStore.js";
import { cameraFor, fetchGeoSearch, type GeoResult, groupResults, isSearchTimeout, searchKeys } from "./api.js";
import "./search.css";

/** How long typing must pause before the server is asked. */
export const SEARCH_DEBOUNCE_MS = 250;

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
  const id = useId();
  const listId = `${id}-list`;

  useEffect(() => {
    if (term === settled) return;
    const timer = setTimeout(() => setSettled(term), SEARCH_DEBOUNCE_MS);
    return () => clearTimeout(timer);
  }, [term, settled]);

  // The signal is passed on, so a search the text has moved past is cancelled.
  const query = useQuery({
    queryKey: searchKeys.geo(settled),
    queryFn: ({ signal }) => fetchGeoSearch(settled, signal),
    enabled: settled !== "",
    staleTime: 60_000,
    retry: false,
  });

  const current = term !== "" && settled === term;
  const results = current && query.data ? query.data : [];
  const { groups, ordered } = groupResults(results);
  const waiting = term !== "" && (!current || query.isFetching);

  function choose(result: GeoResult): void {
    useMapStore.getState().requestCamera(cameraFor(result));
    setText(result.label);
    setSettled(result.label.trim());
    setOpen(false);
    setActive(-1);
    setPendingPick(null);
    if (result.type === "record" && result.ref) navigate(recordPath(result.ref));
    else if (result.type === "finding" && result.ref) navigate(`/f/${encodeURIComponent(result.ref)}`);
  }

  // Enter pressed early: take the first result for that text as soon as there is one.
  // biome-ignore lint/correctness/useExhaustiveDependencies: choose reads the latest render
  useEffect(() => {
    if (pendingPick === null || pendingPick !== term || !current || query.isFetching) return;
    const first = ordered[0];
    setPendingPick(null);
    if (first) choose(first);
  }, [pendingPick, current, query.isFetching, ordered[0]]);

  function onSubmit(event: FormEvent<HTMLFormElement>): void {
    event.preventDefault();
    if (term === "") return;
    if (active === ordered.length) {
      searchRecords();
      return;
    }
    const picked = ordered[active] ?? (current && !query.isFetching ? ordered[0] : undefined);
    if (picked) {
      choose(picked);
      return;
    }
    setOpen(true);
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
      // The options are the results and, last, searching the records for the text.
      const count = ordered.length + 1;
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
    const { camera } = useMapStore.getState();
    navigate(elsewherePath(camera.lng, camera.lat));
  }

  const expanded = open && term !== "";
  const optionId = (index: number) => `${id}-option-${index}`;
  const moreIndex = ordered.length;

  let message: string | null = null;
  if (expanded) {
    if (current && query.isError) {
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
          onChange={(event) => {
            setText(event.currentTarget.value);
            setOpen(true);
            setActive(-1);
            setPendingPick(null);
          }}
          onFocus={() => setOpen(true)}
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
                        <span className="fc-search__label">{result.label}</span>
                        {detail ? <span className="fc-search__detail">{detail}</span> : null}
                      </div>
                    );
                  })}
                </div>
              ))
            : null}
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
      </div>
    </search>
  );
}
