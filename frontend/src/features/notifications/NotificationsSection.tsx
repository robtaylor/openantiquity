import { CheckCheck, Unplug } from "lucide-react";
import { type ReactNode, useState } from "react";
import { useMeta } from "../../api/useMeta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { EventRow } from "../activity/EventRow.js";
import { useNow } from "../activity/time.js";
import { useMarkRead, useNotifications } from "./useNotifications.js";
import { useSeen } from "./useSeen.js";
import "./notifications.css";

function NewMark() {
  return (
    <span className="fc-notification-new">
      <span className="fc-notification-new__dot" aria-hidden="true" />
      New
    </span>
  );
}

/**
 * The signed-in person's notifications, on their account page: what happened
 * and to which finding, newest first. Each is marked read once it has been
 * on screen, and keeps its "new" mark for as long as the page stays open, so
 * the person can still tell what had arrived.
 */
export function NotificationsSection() {
  const meta = useMeta().data;
  const query = useNotifications();
  const markRead = useMarkRead();
  const now = useNow();
  /** Read here, while this list has been open. Still shown as new. */
  const [readHere, setReadHere] = useState<ReadonlySet<number>>(new Set());
  const remember = (ids: number[]) => {
    if (ids.length > 0) setReadHere((before) => new Set([...before, ...ids]));
  };
  const track = useSeen((ids) => void markRead({ ids }).then(remember));

  const items = query.data?.pages.flatMap((page) => page.items) ?? [];
  const unread = query.data?.pages[0]?.unread_count ?? 0;
  const newest = items[0]?.id;

  let body: ReactNode;
  if (query.isPending) {
    body = (
      <div role="status">
        <span className="fc-visually-hidden">Loading your notifications</span>
        <Skeleton lines={2} />
      </div>
    );
  } else if (query.isError && items.length === 0) {
    body = (
      <EmptyState
        tone="error"
        icon={<Unplug size={22} />}
        title="Your notifications couldn't be loaded"
        action={
          <Button variant="primary" onClick={() => void query.refetch()}>
            Try again
          </Button>
        }
      >
        <p>{query.error.message}</p>
      </EmptyState>
    );
  } else if (!meta) {
    // The shell shows nothing until /meta has arrived, so this is never on screen.
    body = null;
  } else if (items.length === 0) {
    body = <p className="fc-account-small">Nothing yet. You'll hear here when a finding you follow changes.</p>;
  } else {
    body = (
      <>
        <ul className="fc-activity__list" aria-label="Your notifications">
          {items.map((item) => {
            const fresh = !item.read || readHere.has(item.id);
            return (
              <EventRow
                key={item.id}
                meta={meta}
                facts={{ ...item, investigationTitle: null }}
                createdAt={item.created_at}
                investigation={item.investigation ?? null}
                badge={fresh ? <NewMark /> : undefined}
                rowRef={item.read ? undefined : track(item.id)}
                now={now}
              />
            );
          })}
        </ul>
        {query.hasNextPage ? (
          <div className="fc-activity__more">
            <Button onClick={() => void query.fetchNextPage()} disabled={query.isFetchingNextPage}>
              {query.isFetchingNextPage ? "Loading…" : "Show more"}
            </Button>
          </div>
        ) : null}
      </>
    );
  }

  return (
    <section className="fc-account-section fc-notifications" aria-labelledby="account-notifications">
      <div className="fc-notifications__head">
        <h3 id="account-notifications">Notifications</h3>
        {unread > 0 && newest !== undefined ? (
          <Button
            size="sm"
            variant="ghost"
            icon={<CheckCheck size={16} aria-hidden />}
            onClick={() => void markRead({ upTo: newest }).then(remember)}
          >
            Mark all as read
          </Button>
        ) : null}
      </div>
      <p className="fc-account-small">
        You follow a finding when you mark it, check it or add to it, and you're told here when it changes. A second
        look is never named.
      </p>
      {body}
    </section>
  );
}
