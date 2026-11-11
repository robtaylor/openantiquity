import { BookOpen, Eye, MapPinned, Spline, TriangleAlert } from "lucide-react";
import { useState } from "react";
import { Link } from "react-router";
import type { Meta } from "../../api/meta.js";
import { safeHref } from "../../map/attribution.js";
import { formatGridRef, wgs84ToGrid } from "../../map/gridref.js";
import { Button } from "../../ui/Button.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { FindingLink } from "../explore/ExplorePanel.js";
import { distanceText, type LngLat, lineLengthM, profilePath } from "../layers/profile/line.js";
import { ProfileChart } from "../layers/profile/ProfileChart.js";
import { useProfileQuery } from "../layers/profile/useProfile.js";
import { CategoryMark } from "../records/CategoryMark.js";
import { SourceCredit } from "../records/SourceCredit.js";
import { decodeEntities } from "../records/text.js";
import type { Item, ProfileData, SavedView } from "./api.js";
import { UNAVAILABLE } from "./describe.js";
import { Markdown } from "./Markdown.js";
import { showSavedView, viewLayers } from "./savedView.js";
import "../layers/profile/profile.css";

/** The line of a height profile as the chart and the profile panel take it. */
function pointsOf(profile: ProfileData): LngLat[] {
  return profile.line.coordinates.map(([lng, lat]): LngLat => [lng, lat]);
}

function ProfileBody({ profile }: { profile: ProfileData }) {
  const points = pointsOf(profile);
  const query = useProfileQuery(points);
  const [hover, setHover] = useState<number | null>(null);
  return (
    <div className="fc-inv-item__profile">
      {query.data ? (
        <ProfileChart samples={query.data.samples} hover={hover} onHover={setHover} />
      ) : query.isError ? (
        <p className="fc-field__hint">The heights along this line couldn't be loaded. {query.error.message}</p>
      ) : (
        <div role="status">
          <span className="fc-visually-hidden">Reading the heights along the line</span>
          <Skeleton height={120} />
        </div>
      )}
      <p className="fc-inv-item__facts">
        <span className="fc-mono">{distanceText(query.data?.length_m ?? lineLengthM(points))}</span>
        <span>{points.length} points</span>
      </p>
      <Link className="fc-button fc-button--ghost fc-button--sm" to={profilePath(points)}>
        <Spline size={15} aria-hidden />
        Open it on the map
      </Link>
    </div>
  );
}

function ViewBody({ meta, view }: { meta: Meta; view: SavedView }) {
  const grid = wgs84ToGrid(view.centre[0], view.centre[1]);
  const layers = viewLayers(meta, view);
  return (
    <div className="fc-inv-item__view">
      <p className="fc-inv-item__facts">
        {grid ? <span className="fc-mono">{formatGridRef(grid, 6)}</span> : null}
        {layers ? <span>{layers}</span> : null}
        {view.zoom != null ? <span>Zoom {Math.round(view.zoom * 10) / 10}</span> : null}
      </p>
      <Button size="sm" icon={<Eye size={15} aria-hidden />} onClick={() => showSavedView(meta, view)}>
        Show this view
      </Button>
    </div>
  );
}

/** One item's content, drawn for what it is. */
export function ItemBody({ meta, item }: { meta: Meta; item: Item }) {
  if (item.unavailable) {
    return (
      <p className="fc-inv-item__gone">
        <TriangleAlert size={15} aria-hidden /> {UNAVAILABLE[item.unavailable]}
      </p>
    );
  }
  switch (item.kind) {
    case "finding":
      return item.finding ? <FindingLink meta={meta} finding={item.finding} /> : null;
    case "record": {
      const record = item.record;
      if (!record) return null;
      return (
        <div className="fc-inv-item__record">
          <Link className="fc-inv-item__record-link" to={`/r/${record.id}`}>
            <MapPinned size={16} aria-hidden />
            {decodeEntities(record.name)}
          </Link>
          <p className="fc-inv-item__facts">
            <CategoryMark meta={meta} category={record.category} />
            {record.record_type ? <span>{record.record_type}</span> : null}
          </p>
          <SourceCredit source={record.source} compact />
        </div>
      );
    }
    case "view":
      return item.view ? <ViewBody meta={meta} view={item.view} /> : null;
    case "profile":
      return item.profile ? <ProfileBody profile={item.profile} /> : null;
    case "reference": {
      const reference = item.reference;
      const href = safeHref(reference?.url);
      return (
        <div className="fc-inv-item__reference">
          {reference?.citation ? <p>{reference.citation}</p> : null}
          {href ? (
            <a href={href} target="_blank" rel="noopener noreferrer external nofollow">
              <BookOpen size={15} aria-hidden /> {new URL(href).hostname}
              <span className="fc-visually-hidden"> (opens in a new tab)</span>
            </a>
          ) : null}
        </div>
      );
    }
    case "note":
      return null;
  }
}

/** The member's own words on an item: a note's text, or what someone wrote beside a finding or a record. */
export function ItemNote({ item }: { item: Item }) {
  return item.note ? (
    <div className="fc-inv-item__note">
      <Markdown source={item.note} />
    </div>
  ) : null;
}
