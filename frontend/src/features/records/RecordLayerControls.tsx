import { ExternalLink, Search } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router";
import type { Meta } from "../../api/meta.js";
import { safeHref } from "../../map/attribution.js";
import { useViewAreaStore } from "../../map/store.js";
import { ChipGroup } from "../../ui/Chip.js";
import { Switch } from "../../ui/Switch.js";
import { CategorySwatch } from "./CategoryMark.js";
import { useRecordFilters } from "./filters.js";
import type { LiveSource } from "./live/catalogue.js";
import { type LiveStatus, liveStatus, pickedKey, useLiveStore } from "./live/store.js";
import { LIVE_MIN_ZOOM, useLiveCatalogue } from "./live/useLiveRecords.js";
import { RECORD_SEARCH_PATH } from "./paths.js";
import "./records.css";

/** How many of a live source's records are listed in the panel before the rest are left to the map. */
const LISTED_LIVE_RECORDS = 30;

/** The categories and sources of the heritage records layer, each turned on and off by a chip. */
export function RecordFilterControls({ meta }: { meta: Meta }) {
  const hiddenCategories = useRecordFilters((state) => state.hiddenCategories);
  const hiddenSources = useRecordFilters((state) => state.hiddenSources);
  const setHiddenCategories = useRecordFilters((state) => state.setHiddenCategories);
  const setHiddenSources = useRecordFilters((state) => state.setHiddenSources);

  const categories = meta.vocab.record_categories.map((category) => category.id);
  const sources = meta.sources.map((source) => source.key);
  // The chips show what is on. The store keeps what is off, so anything the catalogue gains later shows.
  const shown = (all: string[], hidden: readonly string[]) => all.filter((id) => !hidden.includes(id));
  const hiddenOf = (all: string[], on: string[]) => all.filter((id) => !on.includes(id));

  return (
    <div className="fc-record-controls">
      <div className="fc-record-controls__group">
        <p className="fc-record-controls__label">Kinds of record</p>
        <ChipGroup
          multiple
          label="Kinds of record to show"
          value={shown(categories, hiddenCategories)}
          options={meta.vocab.record_categories.map((category) => ({
            id: category.id,
            label: category.label,
            icon: <CategorySwatch colour={category.colour} />,
          }))}
          onChange={(next) => setHiddenCategories(hiddenOf(categories, next))}
        />
      </div>
      {meta.sources.length > 0 ? (
        <div className="fc-record-controls__group">
          <p className="fc-record-controls__label">Sources</p>
          <ChipGroup
            multiple
            label="Sources of records to show"
            value={shown(sources, hiddenSources)}
            options={meta.sources.map((source) => ({ id: source.key, label: source.name }))}
            onChange={(next) => setHiddenSources(hiddenOf(sources, next))}
          />
        </div>
      ) : null}
      <Link className="fc-button fc-button--ghost fc-button--sm fc-record-controls__search" to={RECORD_SEARCH_PATH}>
        <Search size={16} aria-hidden />
        Search the records
      </Link>
    </div>
  );
}

function statusLine(source: LiveSource, state: LiveStatus, on: boolean, zoom: number): string {
  if (state.state === "refused") {
    return `${state.message} Some services don't let other websites ask them, so it's off for now.`;
  }
  if (state.state === "failed") return `${state.message} It's off for now.`;
  if (!on) return `From ${source.publisher}.`;
  if (zoom < LIVE_MIN_ZOOM) return "Zoom in closer to see its records.";
  if (state.state === "loading") return "Asking…";
  if (state.state === "ready") {
    const count = state.records.length;
    if (count === 0) return "Nothing from this source in view.";
    const base = count === 1 ? "1 record in view" : `${count} records in view`;
    return state.truncated ? `${base}, the first ${count} it sent.` : `${base}.`;
  }
  return `From ${source.publisher}.`;
}

function LiveSourceRow({ source }: { source: LiveSource }) {
  const on = useLiveStore((state) => Boolean(state.on[source.key]));
  const status = useLiveStore((state) => liveStatus(state.status, source.key));
  const picked = useLiveStore((state) => state.picked);
  const setOn = useLiveStore((state) => state.setOn);
  const zoom = useViewAreaStore((state) => state.zoom);
  const list = useRef<HTMLUListElement>(null);

  useEffect(() => {
    if (!picked?.startsWith(`${source.key}/`)) return;
    const item = list.current?.querySelector<HTMLElement>('[data-picked="true"]');
    item?.scrollIntoView({ block: "nearest" });
    item?.focus({ preventScroll: true });
  }, [picked, source.key]);

  const records = on && status.state === "ready" ? status.records.slice(0, LISTED_LIVE_RECORDS) : [];
  return (
    <li className="fc-live-source" data-live-source={source.key}>
      <Switch
        label={source.name}
        hint={statusLine(source, status, on, zoom)}
        checked={on}
        onChange={(next) => setOn(source.key, next)}
      />
      {on ? (
        <div className="fc-live-source__credit">
          <p>{source.attribution}</p>
          <p>Licence: {source.licence}</p>
        </div>
      ) : null}
      {records.length > 0 ? (
        <ul className="fc-live-source__records" ref={list} aria-label={`Records from ${source.name}`}>
          {records.map((record) => {
            const href = safeHref(record.url);
            const isPicked = picked === pickedKey(source.key, record.id);
            return (
              <li key={record.id} data-picked={isPicked} tabIndex={isPicked ? -1 : undefined}>
                <span className="fc-record-swatch fc-record-swatch--live" aria-hidden="true" />
                <span className="fc-live-source__name">{record.name}</span>
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer external" className="fc-live-source__link">
                    <ExternalLink size={14} aria-hidden />
                    <span className="fc-visually-hidden">
                      Open {record.name} at {source.publisher} (new tab)
                    </span>
                  </a>
                ) : null}
              </li>
            );
          })}
        </ul>
      ) : null}
    </li>
  );
}

/**
 * Indexes we may not keep a copy of, which this browser asks directly when
 * someone turns one on and zooms in (Decision 0007). The catalogue is only
 * asked for once the section is opened.
 */
export function LiveSourceControls() {
  const picked = useLiveStore((state) => state.picked);
  const anyOn = useLiveStore((state) => Object.values(state.on).some(Boolean));
  const [open, setOpen] = useState(anyOn || picked !== null);
  const { sources, loading, failed } = useLiveCatalogue(open || anyOn);

  useEffect(() => {
    if (picked !== null) setOpen(true);
  }, [picked]);

  return (
    <details className="fc-live" open={open} onToggle={(event) => setOpen(event.currentTarget.open)}>
      <summary className="fc-live__summary">Live sources{anyOn ? " (on)" : ""}</summary>
      <p className="fc-live__hint">
        Some records can't be kept on our servers. Turn a source on and your browser asks its publisher directly, only
        for the area you're looking at. Live records are hollow squares.
      </p>
      {loading ? <p className="fc-muted">Loading the list…</p> : null}
      {failed ? <p className="fc-muted">The list of live sources couldn't be loaded.</p> : null}
      {!loading && !failed && sources.length === 0 ? <p className="fc-muted">No live sources are set up.</p> : null}
      {sources.length > 0 ? (
        <ul className="fc-live__list">
          {sources.map((source) => (
            <LiveSourceRow key={source.key} source={source} />
          ))}
        </ul>
      ) : null}
    </details>
  );
}
