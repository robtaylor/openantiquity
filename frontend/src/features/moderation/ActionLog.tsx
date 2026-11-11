import { useInfiniteQuery } from "@tanstack/react-query";
import { ScrollText, Unplug } from "lucide-react";
import { useState } from "react";
import { isTransient } from "../../api/client.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { fullTime, useNow, whenWords } from "../activity/time.js";
import { type Action, fetchActions, isHideable } from "./api.js";
import { actionSentence } from "./describe.js";
import { HideButton } from "./HideButton.js";
import { moderationKeys } from "./keys.js";
import { TargetSummary } from "./TargetSummary.js";

function LogEntry({
  action,
  hidden,
  now,
  onHidden,
}: {
  action: Action;
  hidden: boolean;
  now: number;
  onHidden: (hidden: boolean) => void;
}) {
  const { target } = action;
  // What was hidden and is still hidden can be shown again from here, which is the only way back for hidden evidence.
  const offerShow =
    action.action === "hide" && target.hidden && target.exists && isHideable(target.kind) && target.ref !== null;
  return (
    <li className="fc-mod-card">
      <p className="fc-mod-log__what">{actionSentence(action)}</p>
      {action.reason ? (
        <blockquote className="fc-mod-card__note" aria-label="Their reason">
          {action.reason}
        </blockquote>
      ) : null}
      <p className="fc-muted fc-mod-log__when">
        <time dateTime={action.created_at} title={fullTime(action.created_at)}>
          {whenWords(action.created_at, now)}
        </time>
      </p>
      <details className="fc-mod-log__details">
        <summary>What it was about</summary>
        <TargetSummary target={{ ...target, hidden }} />
      </details>
      {offerShow && isHideable(target.kind) && target.ref !== null ? (
        <div className="fc-mod-card__actions">
          <HideButton
            kind={target.kind}
            targetRef={target.ref}
            ownerHandle={target.owner?.handle ?? null}
            hidden={hidden}
            onChange={onHidden}
          />
        </div>
      ) : null}
    </li>
  );
}

/** What moderators have done, newest first. Nothing in it reaches any member (Decision 0009). */
export function ActionLog() {
  const now = useNow();
  const query = useInfiniteQuery({
    queryKey: moderationKeys.actions(null),
    queryFn: ({ pageParam, signal }) => fetchActions({ cursor: pageParam }, signal),
    initialPageParam: null as string | null,
    getNextPageParam: (page) => page.next_cursor ?? null,
    retry: (failureCount, error) => failureCount < 1 && isTransient(error),
  });
  // A target shown again from one entry is shown as such on every entry about it.
  const [hiddenNow, setHiddenNow] = useState<ReadonlyMap<string, boolean>>(new Map());
  const items = query.data?.pages.flatMap((page) => page.items) ?? [];

  if (query.isPending) {
    return (
      <div role="status" className="fc-mod__loading">
        <span className="fc-visually-hidden">Loading the moderation log</span>
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
        title="The log couldn't be loaded"
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
      <EmptyState icon={<ScrollText size={22} />} title="Nothing has been done yet">
        <p>
          Every report resolved, everything hidden, every role changed and every ban is written here, with its reason.
        </p>
      </EmptyState>
    );
  }
  return (
    <>
      <p className="fc-mod__hint">
        Every moderator's actions, newest first, with their reasons. Only moderators read this log.
      </p>
      <ul className="fc-mod-list" aria-label="Moderation log">
        {items.map((action) => {
          const key = `${action.target.kind}:${action.target.id}`;
          return (
            <LogEntry
              key={action.id}
              action={action}
              hidden={hiddenNow.get(key) ?? action.target.hidden}
              now={now}
              onHidden={(hidden) => setHiddenNow((before) => new Map(before).set(key, hidden))}
            />
          );
        })}
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
