import type { ReactNode } from "react";
import "./notifications.css";

/**
 * The quiet count of unread notifications on the Account item, over the
 * corner of `children` (an icon), or after a label with `inline`. It is
 * drawn for sight only: the link it sits in says the number in words,
 * through `unreadWords`. Nothing is drawn for none, or for someone who
 * isn't signed in.
 */
export function NotificationCount({
  count,
  inline = false,
  children,
}: {
  count: number | null;
  inline?: boolean;
  children?: ReactNode;
}) {
  const badge = count ? (
    <span
      className={inline ? "fc-notification-count fc-notification-count--inline" : "fc-notification-count"}
      aria-hidden="true"
      data-testid="notification-count"
    >
      {count > 99 ? "99+" : count}
    </span>
  ) : null;
  if (inline) return badge;
  return (
    <span className="fc-notification-anchor">
      {children}
      {badge}
    </span>
  );
}
