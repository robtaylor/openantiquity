import { History, SearchX, SlidersHorizontal, Unplug } from "lucide-react";
import { useId, useState } from "react";
import { useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { MARK_PATH } from "../mark/MarkPanel.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { EventRow } from "./EventRow.js";
import { isKindGroupId, KIND_GROUPS } from "./kinds.js";
import { useLiveStatus } from "./LiveEvents.js";
import type { LiveStatus } from "./liveStream.js";
import { useNow } from "./time.js";
import { type ActivityFeed, type FeedWhere, useActivityFeed, useFeedFilters } from "./useActivityFeed.js";
import "./activity.css";

export const ACTIVITY_PATH = "/activity";

const WHERE_OPTIONS: Array<{ id: FeedWhere; label: string }> = [
  { id: "everywhere", label: "Everywhere" },
  { id: "view", label: "In the map's view" },
];

/** What the live stream means for the feed, in a sentence, or null while it is starting. */
export function liveWords(status: LiveStatus | null): string | null {
  switch (status) {
    case "live":
      return "New activity shows here as it happens.";
    case "waiting":
    case "unsupported":
      return "New activity is checked for every minute or so.";
    case "offline":
      return "You're offline. New activity will show when you're back.";
    case "connecting":
    case "paused":
    case null:
      return null;
  }
}

function Filters() {
  const where = useFeedFilters((state) => state.where);
  const groups = useFeedFilters((state) => state.groups);
  const setWhere = useFeedFilters((state) => state.setWhere);
  const setGroups = useFeedFilters((state) => state.setGroups);
  const clear = useFeedFilters((state) => state.clear);
  const [open, setOpen] = useState(false);
  const bodyId = useId();
  const count = (where === "view" ? 1 : 0) + groups.length;
  return (
    <div className="fc-activity__filters">
      <div className="fc-activity__filter-bar">
        <Button
          size="sm"
          icon={<SlidersHorizontal size={14} aria-hidden />}
          aria-expanded={open}
          aria-controls={bodyId}
          onClick={() => setOpen(!open)}
        >
          {count > 0 ? `Filters (${count})` : "Filters"}
        </Button>
        {count > 0 ? (
          <Button size="sm" variant="ghost" onClick={clear}>
            Clear filters
          </Button>
        ) : null}
      </div>
      {open ? (
        <div className="fc-activity__filter-body" id={bodyId}>
          <div className="fc-activity__filter">
            <h3 className="fc-activity__filter-title">Where</h3>
            <ChipGroup
              label="Where"
              value={where}
              options={WHERE_OPTIONS}
              onChange={(value) => setWhere(value === "view" ? "view" : "everywhere")}
            />
          </div>
          <div className="fc-activity__filter">
            <h3 className="fc-activity__filter-title">What</h3>
            <ChipGroup
              multiple
              label="What"
              value={groups}
              options={KIND_GROUPS.map((group) => ({ id: group.id, label: group.label }))}
              onChange={(values) => setGroups(values.filter(isKindGroupId))}
            />
          </div>
          <p className="fc-activity__hint">
            A step is how far a finding has got on the ladder from spotted to on record. A second look is someone
            checking a finding without being told what it is, and nobody is named for one.
          </p>
        </div>
      ) : null}
    </div>
  );
}

function FeedBody({ meta, feed }: { meta: Meta; feed: ActivityFeed }) {
  const where = useFeedFilters((state) => state.where);
  const filtered = useFeedFilters((state) => state.groups.length > 0);
  const setWhere = useFeedFilters((state) => state.setWhere);
  const clear = useFeedFilters((state) => state.clear);
  const navigate = useNavigate();
  const now = useNow();

  if (feed.status === "loading") {
    return (
      <div className="fc-activity__loading" role="status">
        <span className="fc-visually-hidden">Loading what has happened</span>
        <Skeleton lines={2} />
        <Skeleton lines={2} />
        <Skeleton lines={2} />
      </div>
    );
  }
  if (feed.status === "error") {
    return (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="The activity couldn't be loaded"
        action={
          <Button variant="primary" onClick={feed.retry}>
            Try again
          </Button>
        }
      >
        <p>{feed.error?.message ?? "Something went wrong."}</p>
      </EmptyState>
    );
  }
  if (feed.items.length === 0) {
    if (filtered) {
      return (
        <EmptyState
          icon={<SearchX size={22} />}
          title="Nothing like that has happened here yet"
          action={<Button onClick={clear}>Clear filters</Button>}
        >
          <p>Ask for more kinds of activity, or look everywhere.</p>
        </EmptyState>
      );
    }
    if (where === "view") {
      return (
        <EmptyState
          icon={<SearchX size={22} />}
          title="Nothing has happened in view yet"
          action={<Button onClick={() => setWhere("everywhere")}>Look everywhere</Button>}
        >
          <p>Move the map somewhere else, or see what has happened everywhere.</p>
        </EmptyState>
      );
    }
    return (
      <EmptyState
        icon={<History size={22} />}
        title="Nothing has happened yet"
        action={
          <Button variant="primary" onClick={() => navigate(MARK_PATH)}>
            Mark a finding
          </Button>
        }
      >
        <p>When someone marks a finding, checks one or adds evidence, it will show here.</p>
      </EmptyState>
    );
  }

  return (
    <>
      <ul className="fc-activity__list" aria-label="What has happened" aria-busy={feed.stale}>
        {feed.items.map((item) => (
          <EventRow
            key={item.id}
            meta={meta}
            facts={{ ...item, investigationTitle: item.investigation?.title ?? null }}
            createdAt={item.created_at}
            investigation={item.investigation?.public_id ?? null}
            now={now}
          />
        ))}
      </ul>
      {feed.hasMore ? (
        <div className="fc-activity__more">
          <Button onClick={feed.loadMore} disabled={feed.loadingMore}>
            {feed.loadingMore ? "Loading…" : "Show more"}
          </Button>
        </div>
      ) : null}
    </>
  );
}

/**
 * `/activity`: what has happened, newest first, in plain sentences. It can
 * be narrowed to the map's view and to kinds of activity, and each item
 * opens its finding or investigation. It keeps up by itself while the live
 * stream is open, and says so.
 */
export function ActivityPanel({ meta }: { meta: Meta }) {
  const feed = useActivityFeed();
  const live = liveWords(useLiveStatus((state) => state.status));
  useDocumentTitle("Activity");
  return (
    <PanelFrame panelKey={ACTIVITY_PATH} title="Activity" subtitle="What people have been doing">
      <div className="fc-activity">
        <Filters />
        <p className="fc-activity__live" role="status">
          {live}
        </p>
        <FeedBody meta={meta} feed={feed} />
      </div>
    </PanelFrame>
  );
}
