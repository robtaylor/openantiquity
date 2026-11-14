import { useInfiniteQuery } from "@tanstack/react-query";
import { KeyRound, Unplug } from "lucide-react";
import { Link } from "react-router";
import { isTransient } from "../../api/client.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { findingPath } from "../findings/selection.js";
import { fetchOrphaned, type OrphanedMarking } from "./api.js";
import { moderationKeys } from "./keys.js";
import { removeMarkingPath } from "./paths.js";

const GONE_WORDS: Record<OrphanedMarking["keeper_gone"], string> = {
  deleted: "whose account is deleted",
  banned: "who is banned",
};

/**
 * `/mod/markings`: the markings whose keeper's account is deleted or banned,
 * newest first, for admins alone (Decision 0040). Nobody else is told a
 * marking has no keeper, since that would say its keeper is banned or gone.
 * Each opens its finding, where an admin offers it to someone, or its
 * removal.
 */
export function OrphanedMarkings() {
  const query = useInfiniteQuery({
    queryKey: moderationKeys.orphaned,
    queryFn: ({ pageParam, signal }) => fetchOrphaned(pageParam, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];

  if (query.isPending) {
    return (
      <div role="status" className="fc-mod__loading">
        <span className="fc-visually-hidden">Loading the markings without a keeper</span>
        <Skeleton lines={2} />
        <Skeleton lines={2} />
      </div>
    );
  }
  if (query.isError && items.length === 0) {
    return (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="The markings couldn't be loaded"
        action={
          <Button variant="primary" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{query.error.message}</p>
      </EmptyState>
    );
  }
  if (items.length === 0) {
    return (
      <EmptyState icon={<KeyRound size={22} />} title="Every marking has a keeper">
        <p>When an account that kept markings is deleted or banned, its markings are listed here.</p>
      </EmptyState>
    );
  }
  return (
    <>
      <p className="fc-mod__hint">
        Nobody can change these, because whoever kept each has gone or is banned. Offer one to a member from its page,
        or take back its shape if it causes trouble. Only admins see this list.
      </p>
      <ul className="fc-mod-list" aria-label="Markings without a keeper">
        {items.map((item) => (
          <li key={item.finding.public_id} className="fc-mod-card">
            <p>
              <Link to={findingPath(item.finding.public_id)}>{item.finding.title}</Link>
            </p>
            <p className="fc-muted">
              Kept by {item.keeper.display_name}, {GONE_WORDS[item.keeper_gone]}.
            </p>
            <div className="fc-mod-card__actions">
              <Link
                className="fc-button fc-button--secondary fc-button--sm"
                to={removeMarkingPath(item.finding.public_id)}
              >
                Remove the marking
                <span className="fc-visually-hidden"> of {item.finding.title}</span>
              </Link>
            </div>
          </li>
        ))}
      </ul>
      {query.hasNextPage ? (
        <div className="fc-mod__more">
          <Button disabled={query.isFetchingNextPage} onClick={() => void query.fetchNextPage()}>
            {query.isFetchingNextPage ? "Loading…" : "Show more"}
          </Button>
        </div>
      ) : null}
    </>
  );
}
