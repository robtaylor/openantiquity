import type { LucideIcon } from "lucide-react";
import { Avatar } from "../../ui/Avatar.js";
import { useSession } from "./session.js";
import "./account.css";

/**
 * The Account item's icon in the mode rail and the phone menu: the person's
 * picture or initials when signed in, and the plain icon otherwise. The link
 * around it carries the name, so the picture is hidden from screen readers.
 */
export function AccountModeIcon({ icon: Icon, size }: { icon: LucideIcon; size: number }) {
  const { me } = useSession();
  if (!me) return <Icon size={size} aria-hidden />;
  return (
    <span className="fc-account-rail-avatar" aria-hidden="true" data-testid="account-avatar">
      <Avatar name={me.display_name} handle={me.handle} size={size + 4} />
    </span>
  );
}
