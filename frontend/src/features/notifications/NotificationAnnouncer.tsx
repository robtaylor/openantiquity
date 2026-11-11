import { useEffect, useRef, useState } from "react";
import { unreadWords, useUnreadCount } from "./useNotifications.js";

/**
 * One hidden polite live region for the whole app, which says "2 new
 * notifications" when the unread count goes up, because the count on the
 * Account item is drawn for sight and its link's name is read only with
 * focus. It says nothing for the count the page loads with, nor when the
 * count goes down. It has no role, so it is never mistaken for a panel's
 * status.
 */
export function NotificationAnnouncer() {
  const count = useUnreadCount();
  const before = useRef<number | null>(null);
  const [said, setSaid] = useState("");
  useEffect(() => {
    const previous = before.current;
    before.current = count;
    if (count === null || previous === null) {
      setSaid("");
      return;
    }
    if (count > previous) setSaid(unreadWords(count));
    else if (count < previous) setSaid("");
  }, [count]);
  return (
    <div className="fc-visually-hidden" aria-live="polite" aria-atomic="true" data-testid="notification-announcer">
      {said}
    </div>
  );
}
