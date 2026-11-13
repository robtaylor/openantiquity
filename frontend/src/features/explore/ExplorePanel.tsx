import { MapPinPlus, SearchX, SlidersHorizontal, Unplug, ZoomIn } from "lucide-react";
import { type ReactNode, useId, useState } from "react";
import { useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useFindingHighlight } from "../../map/findingHighlight.js";
import { useMapStore } from "../../map/store.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { FeatureIcon } from "../../ui/featureIcons.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { TierBadge } from "../../ui/TierBadge.js";
import { DraftBadge } from "../drafts/DraftBadge.js";
import { useKindDrafts } from "../drafts/savers.js";
import { type FilterKey, filterableStates, hasFilters, useFindingFilters } from "../findings/filters.js";
import { findingPath, useSelectedFinding } from "../findings/selection.js";
import { whereRef } from "../findings/square.js";
import type { FindingSummary } from "../findings/types.js";
import { findingDrafts } from "../mark/findingDrafts.js";
import { MARK_PATH } from "../mark/MarkPanel.js";
import { usePendingFindings } from "../mark/pending.js";
import { draftPath } from "../mark/useSaveMark.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { type FindingsList, useFindingsList } from "./useFindingsList.js";
import "./explore.css";

function labelOf(list: ReadonlyArray<{ id: string; label: string }>, id: string): string {
  return list.find((entry) => entry.id === id)?.label ?? id;
}

/** What a row needs of a finding: a list's summary, or the smaller one a feed or a profile sends. */
export type FindingRowData = Pick<
  FindingSummary,
  "public_id" | "title" | "feature_class" | "tier" | "state" | "location"
>;

/**
 * A finding as a link to its page, with its pictogram, title, step and
 * class, and its square when this viewer may not see it exactly. Choosing
 * it marks it on the map. Other lists of findings show them the same way.
 * `detail` adds a line, such as what someone did on it.
 */
export function FindingLink({ meta, finding, detail }: { meta: Meta; finding: FindingRowData; detail?: ReactNode }) {
  const navigate = useNavigate();
  const select = useSelectedFinding((state) => state.select);
  const { location } = finding;
  const tier = { id: finding.tier, label: labelOf(meta.vocab.tiers, finding.tier) };
  const state = { id: finding.state, label: labelOf(meta.vocab.states, finding.state) };
  return (
    <a
      className="fc-explore__row"
      href={findingPath(finding.public_id)}
      // The row's finding is highlighted on the map while the row has focus or the pointer, so the list is a way
      // to tell overlapping findings apart.
      onFocus={() => useFindingHighlight.getState().set(finding.public_id)}
      onBlur={() => useFindingHighlight.getState().clear(finding.public_id)}
      onMouseEnter={() => useFindingHighlight.getState().set(finding.public_id)}
      onMouseLeave={() => useFindingHighlight.getState().clear(finding.public_id)}
      onClick={(event) => {
        if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
        event.preventDefault();
        select(finding.public_id, [location.lon, location.lat], location.obscured);
        navigate(findingPath(finding.public_id));
      }}
    >
      <span className="fc-explore__icon">
        <FeatureIcon classId={finding.feature_class} size={22} />
      </span>
      <span className="fc-explore__text">
        <span className="fc-explore__title">{finding.title}</span>
        <span className="fc-explore__meta">
          <TierBadge tier={tier} state={state} size="sm" />
          <span className="fc-explore__class">{labelOf(meta.vocab.feature_classes, finding.feature_class)}</span>
        </span>
        {location.obscured ? (
          <span className="fc-explore__where">
            Somewhere in square <span className="fc-mono">{whereRef(location)}</span>
          </span>
        ) : null}
        {detail ? <span className="fc-explore__where">{detail}</span> : null}
      </span>
    </a>
  );
}

/** One finding in a list: `FindingLink` as a list item. */
export function FindingRow({ meta, finding, detail }: { meta: Meta; finding: FindingRowData; detail?: ReactNode }) {
  return (
    <li>
      <FindingLink meta={meta} finding={finding} detail={detail} />
    </li>
  );
}

/** Drafts and findings being saved, at the top of the list, so the list shows what the map shows. */
function YourMarks() {
  const drafts = useKindDrafts(findingDrafts);
  const pending = usePendingFindings((state) => state.pending);
  const navigate = useNavigate();
  if (drafts.length === 0 && pending.length === 0) return null;
  return (
    <ul className="fc-explore__list fc-explore__list--yours" aria-label="Your marks">
      {pending.map((finding) => (
        <li key={`pending-${finding.id}`}>
          <div className="fc-explore__row fc-explore__row--static">
            <span className="fc-explore__icon">
              <FeatureIcon classId={finding.featureClass} size={22} />
            </span>
            <span className="fc-explore__text">
              <span className="fc-explore__title">{finding.title}</span>
              <span className="fc-explore__meta fc-muted" role="status">
                Saving…
              </span>
            </span>
          </div>
        </li>
      ))}
      {drafts.map((draft) => (
        <li key={draft.id}>
          <a
            className="fc-explore__row"
            href={draftPath(draft.id)}
            onClick={(event) => {
              if (event.metaKey || event.ctrlKey || event.shiftKey || event.button !== 0) return;
              event.preventDefault();
              navigate(draftPath(draft.id));
            }}
          >
            <span className="fc-explore__icon">
              <FeatureIcon classId={draft.data.feature_class} size={22} />
            </span>
            <span className="fc-explore__text">
              <span className="fc-explore__title">{draft.data.title}</span>
              <span className="fc-explore__meta">
                <DraftBadge />
              </span>
            </span>
          </a>
        </li>
      ))}
    </ul>
  );
}

function Filters({ meta }: { meta: Meta }) {
  const filters = useFindingFilters((state) => state.filters);
  const setFilter = useFindingFilters((state) => state.setFilter);
  const clear = useFindingFilters((state) => state.clear);
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  const count = filters.tier.length + filters.state.length + filters.feature_class.length;
  const group = (key: FilterKey, label: string, options: Array<{ id: string; label: string; icon?: ReactNode }>) => (
    <div className="fc-explore__filter">
      <h3 className="fc-explore__filter-title">{label}</h3>
      <ChipGroup
        multiple
        label={label}
        value={[...filters[key]]}
        onChange={(values) => setFilter(key, values)}
        options={options}
      />
    </div>
  );
  return (
    <div className="fc-explore__filters">
      <div className="fc-explore__filter-bar">
        <Button
          size="sm"
          icon={<SlidersHorizontal size={14} aria-hidden />}
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen(!open)}
        >
          {count > 0 ? `Filters (${count})` : "Filters"}
        </Button>
        {hasFilters(filters) ? (
          <Button size="sm" variant="ghost" onClick={clear}>
            Clear filters
          </Button>
        ) : null}
      </div>
      {open ? (
        <div className="fc-explore__filter-body" id={bodyId}>
          {group(
            "tier",
            "Step",
            meta.vocab.tiers.map((tier) => ({ id: tier.id, label: tier.label })),
          )}
          {group(
            "state",
            "State",
            filterableStates(meta.vocab.states).map((state) => ({ id: state.id, label: state.label })),
          )}
          {group(
            "feature_class",
            "What it looks like",
            meta.vocab.feature_classes.map((featureClass) => ({
              id: featureClass.id,
              label: featureClass.label,
              icon: <FeatureIcon classId={featureClass.id} size={16} />,
            })),
          )}
          <p className="fc-explore__hint">
            A step is how far a finding has got on the ladder from spotted to on record. The map shows only what the
            list shows.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function ListBody({ meta, list }: { meta: Meta; list: FindingsList }) {
  const navigate = useNavigate();
  const setShowRuledOut = useMapStore((state) => state.setShowRuledOut);
  const clear = useFindingFilters((state) => state.clear);
  const filtered = useFindingFilters((state) => hasFilters(state.filters));

  switch (list.status) {
    case "zoomed-out":
      return (
        <EmptyState icon={<ZoomIn size={22} />} title="Zoom in to see findings">
          <p>Findings are listed once the map shows a few miles across or less.</p>
        </EmptyState>
      );
    case "filtered-out": {
      const explained = labelOf(meta.vocab.states, "ruled_out");
      return (
        <EmptyState
          icon={<SearchX size={22} />}
          title={`${explained} findings are hidden`}
          action={<Button onClick={() => setShowRuledOut(true)}>Show them</Button>}
        >
          <p>The filters ask only for {explained.toLowerCase()} findings, and the map is hiding those.</p>
        </EmptyState>
      );
    }
    case "missing":
      return (
        <EmptyState icon={<Unplug size={22} />} title="Findings can't be listed yet">
          <p>This server doesn't list findings yet.</p>
        </EmptyState>
      );
    case "loading":
      return (
        <div className="fc-explore__loading" role="status">
          <span className="fc-visually-hidden">Loading the findings in view</span>
          <Skeleton lines={3} />
          <Skeleton lines={3} />
        </div>
      );
    case "error":
      return (
        <EmptyState
          tone="error"
          icon={<Unplug size={22} />}
          title="The findings couldn't be loaded"
          action={
            <Button variant="primary" onClick={list.retry}>
              Try again
            </Button>
          }
        >
          <p>{list.error?.message ?? "Something went wrong."}</p>
        </EmptyState>
      );
    case "ready":
      break;
  }

  if (list.items.length === 0) {
    return filtered ? (
      <EmptyState
        icon={<SearchX size={22} />}
        title="Nothing here matches the filters"
        action={<Button onClick={clear}>Clear filters</Button>}
      >
        <p>Move the map, or ask for less.</p>
      </EmptyState>
    ) : (
      <EmptyState
        icon={<MapPinPlus size={22} />}
        title="No findings here yet"
        action={
          <Button variant="primary" onClick={() => navigate(MARK_PATH)}>
            Mark a finding
          </Button>
        }
      >
        <p>If you can see a bank, a ditch or a mound that nobody has marked, mark it.</p>
      </EmptyState>
    );
  }

  return (
    <>
      <ul className="fc-explore__list" aria-label="Findings in view" aria-busy={list.stale}>
        {list.items.map((finding) => (
          <FindingRow key={finding.public_id} meta={meta} finding={finding} />
        ))}
      </ul>
      {list.hasMore ? (
        <div className="fc-explore__more">
          <Button onClick={list.loadMore} disabled={list.loadingMore}>
            {list.loadingMore ? "Loading…" : "Show more"}
          </Button>
        </div>
      ) : null}
    </>
  );
}

function countLine(list: FindingsList): string | undefined {
  if (list.status !== "ready") return undefined;
  const count = list.items.length;
  if (list.hasMore) return `${count} or more findings in view`;
  return count === 1 ? "1 finding in view" : `${count} findings in view`;
}

/**
 * Explore, at `/`: the findings in view as a list, kept in step with the map
 * as it moves and with the same filters, so nothing depends on pointing at
 * the canvas (docs/UI.md). Choosing one opens its page and marks it on the
 * map. A finding whose position this viewer may not see is listed by its
 * one-kilometre square. Closing the panel leaves the bare map.
 */
export function ExplorePanel({ meta }: { meta: Meta }) {
  const list = useFindingsList();
  useDocumentTitle("Explore");
  return (
    <PanelFrame panelKey="/" title="Explore" subtitle={countLine(list)}>
      <div className="fc-explore">
        <Filters meta={meta} />
        <YourMarks />
        <ListBody meta={meta} list={list} />
      </div>
    </PanelFrame>
  );
}
