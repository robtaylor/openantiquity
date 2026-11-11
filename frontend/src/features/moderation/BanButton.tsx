import { Ban as BanIcon, Undo2 } from "lucide-react";
import { useState } from "react";
import { Button } from "../../ui/Button.js";
import { toast } from "../../ui/toastStore.js";
import { useSession } from "../account/session.js";
import { toastFailure } from "../finding/feedback.js";
import { mayBan } from "./access.js";
import { setBanned } from "./api.js";
import { ReasonDialog } from "./ReasonDialog.js";

export interface BanButtonProps {
  handle: string;
  /** Their role now, which decides whether this moderator may ban them. */
  targetRole: string;
  banned: boolean;
  /** Told at once, ahead of the server, and again with the old value if the server refuses. */
  onChange?: (banned: boolean) => void;
}

/**
 * "Ban" or "Lift the ban", offered only where the server would allow it:
 * never on yourself, a moderator only by an admin, and never an admin.
 */
export function BanButton({ handle, targetRole, banned, onChange }: BanButtonProps) {
  const session = useSession();
  const [asking, setAsking] = useState(false);
  if (!session.ready || session.me?.handle === handle || !mayBan(session.role, targetRole)) return null;

  async function apply(reason: string): Promise<void> {
    onChange?.(!banned);
    try {
      await setBanned(handle, !banned, reason);
      toast(banned ? `The ban on ${handle} is lifted.` : `${handle} is banned.`, { kind: "success" });
    } catch (error) {
      onChange?.(banned);
      toastFailure(banned ? "The ban couldn't be lifted." : "They couldn't be banned.", error);
    }
  }

  return (
    <>
      <Button
        size="sm"
        variant={banned ? "secondary" : "danger"}
        icon={banned ? <Undo2 size={14} aria-hidden /> : <BanIcon size={14} aria-hidden />}
        aria-label={banned ? `Lift the ban on ${handle}` : `Ban ${handle}`}
        onClick={() => setAsking(true)}
      >
        {banned ? "Lift the ban" : "Ban"}
      </Button>
      {asking ? (
        <ReasonDialog
          title={banned ? `Lift the ban on ${handle}?` : `Ban ${handle}?`}
          confirmLabel={banned ? "Lift the ban" : "Ban them"}
          danger={!banned}
          onConfirm={(reason) => void apply(reason)}
          onClose={() => setAsking(false)}
        >
          <p>
            {banned
              ? "Their second looks, votes and evidence count again at once. They sign in again themselves."
              : "They are signed out everywhere at once. While the ban lasts their second looks, votes and evidence stop counting and their page can't be found. Their findings and comments stay."}
          </p>
        </ReasonDialog>
      ) : null}
    </>
  );
}
