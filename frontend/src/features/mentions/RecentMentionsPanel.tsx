import { useInfiniteQuery } from "@tanstack/react-query";
import { Radar, Unplug } from "lucide-react";
import type { ReactNode } from "react";
import { Link } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { FeatureIcon } from "../../ui/featureIcons.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { TierBadge } from "../../ui/TierBadge.js";
import { useSession } from "../account/session.js";
import { labelOf } from "../finding/describe.js";
import { findingPath, useOpenFinding } from "../findings/selection.js";
import { whereRef } from "../findings/square.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { fetchRecentMentions, retryOnceIfTransient } from "./api.js";
import { mentionKeys } from "./keys.js";
import { MentionCard } from "./MentionCard.js";
import { RECENT_MENTIONS_PATH } from "./paths.js";
import type { MentionedFinding } from "./types.js";
import "./mentions.css";

const TITLE = "Recent mentions";

/**
 * The finding a mention is about, as this viewer may see it. One whose place
 * is kept back is given by its one-kilometre square, and is marked on the map
 * as that square, never as a point (Decision 0005).
 */
function FindingLink({ meta, finding }: { meta: Meta; finding: MentionedFinding }) {
  const openFinding = useOpenFinding();
  const { location } = finding;
  const where = whereRef(location);
  return (
    <a className="fc-mention__finding" href={findingPath(finding.public_id)} onClick={openFinding(finding)}>
      <FeatureIcon classId={finding.feature_class} size={22} />
      <span className="fc-mention__finding-text">
        <span className="fc-visually-hidden">About the finding </span>
        <span className="fc-mention__finding-title">{finding.title}</span>
        <span className="fc-mention__finding-meta">
          <TierBadge
            size="sm"
            tier={{ id: finding.tier, label: labelOf(meta.vocab.tiers, finding.tier) }}
            state={{ id: finding.state, label: labelOf(meta.vocab.states, finding.state) }}
          />
          {where ? (
            <span>
              {location.obscured ? "Somewhere in square " : null}
              <span className="fc-mono">{where}</span>
            </span>
          ) : null}
        </span>
      </span>
    </a>
  );
}

/**
 * Recent mentions across the whole map, at `/mentions`, newest first: what
 * was said and where, and the finding it was about. Part of the Activity mode.
 */
export function RecentMentionsPanel({ meta }: { meta: Meta }) {
  useDocumentTitle(TITLE);
  const session = useSession();
  const recent = useInfiniteQuery({
    queryKey: mentionKeys.recent,
    queryFn: ({ pageParam, signal }) => fetchRecentMentions(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? undefined,
    retry: retryOnceIfTransient,
  });
  const all = recent.data?.pages.flatMap((page) => page.items) ?? [];
  const handle = session.me?.handle ?? null;

  let body: ReactNode;
  if (recent.isPending) {
    body = (
      <div role="status">
        <span className="fc-visually-hidden">Loading the recent mentions</span>
        <Skeleton lines={3} />
        <Skeleton lines={3} />
      </div>
    );
  } else if (recent.isError) {
    body = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="The mentions couldn't be loaded"
        action={
          <Button variant="primary" onClick={() => void recent.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{recent.error.message}</p>
      </EmptyState>
    );
  } else if (all.length === 0) {
    body = (
      <EmptyState
        icon={<Radar size={22} />}
        title="No mentions yet"
        action={
          <Link className="fc-button fc-button--secondary fc-button--md" to="/">
            Explore the findings
          </Link>
        }
      >
        <p>
          When someone adds a video, article, podcast or paper to a finding's page, it shows here. Open a finding to add
          one.
        </p>
      </EmptyState>
    );
  } else {
    body = (
      <>
        <ul className="fc-mentions" aria-label={TITLE}>
          {all.map((mention) => (
            <li key={mention.id}>
              <MentionCard meta={meta} mention={mention} own={handle !== null && mention.added_by?.handle === handle}>
                <FindingLink meta={meta} finding={mention.finding} />
              </MentionCard>
            </li>
          ))}
        </ul>
        {recent.hasNextPage ? (
          <Button size="sm" disabled={recent.isFetchingNextPage} onClick={() => void recent.fetchNextPage()}>
            {recent.isFetchingNextPage ? "Loading…" : "Show older mentions"}
          </Button>
        ) : null}
      </>
    );
  }

  return (
    <PanelFrame panelKey={RECENT_MENTIONS_PATH} title={TITLE}>
      <div className="fc-mentions-feed">
        <p className="fc-mentions-feed__hint">
          Videos, articles, podcasts and papers that talk about a finding, from across the map. A finding whose exact
          place is kept back is shown by its one-kilometre square.
        </p>
        {body}
      </div>
    </PanelFrame>
  );
}
