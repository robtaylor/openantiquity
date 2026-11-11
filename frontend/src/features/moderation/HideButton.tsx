import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";
import { Button } from "../../ui/Button.js";
import { useSession } from "../account/session.js";
import { toastFailure } from "../finding/feedback.js";
import { isModerator } from "./access.js";
import { setHidden, type TargetKind } from "./api.js";
import { KIND_WORDS } from "./describe.js";
import { ReasonDialog } from "./ReasonDialog.js";

/** What hiding each kind of thing does, from the next request on (docs/ARCHITECTURE.md, "Moderation"). */
export const HIDING: Record<Exclude<TargetKind, "user">, string> = {
  finding: "Only its finder and moderators will find it. It isn't deleted, and it can be shown again.",
  comment:
    "It will read as removed to everyone but its author and moderators. It isn't deleted, and it can be shown again.",
  evidence:
    "It stops counting at once and leaves the finding's page for everyone. It isn't deleted, and it can be shown again from the moderation log.",
  mention:
    "It leaves the finding's page and the feeds for everyone but whoever added it and moderators. It can be shown again.",
  photo: "Only whoever uploaded it and moderators will see it. It can be shown again.",
  investigation: "Only its members and moderators will find it. It can be shown again.",
};

export interface HideButtonProps {
  kind: Exclude<TargetKind, "user">;
  /** How the API names it: a public id for a finding or an investigation, the id of anything else. */
  targetRef: string;
  /** Who posted it. A moderator never hides their own work, which the server refuses. */
  ownerHandle: string | null;
  hidden: boolean;
  /** Told at once, ahead of the server, and again with the old value if the server refuses. */
  onChange: (hidden: boolean) => void;
  /** Told once the server has done it. */
  onDone?: () => void;
}

/**
 * "Hide" or "Show again", for a moderator, on something someone else
 * posted. A moderator takes down other people's work only by hiding it,
 * with a reason for the log, never by deleting it (Decision 0013).
 */
export function HideButton({ kind, targetRef, ownerHandle, hidden, onChange, onDone }: HideButtonProps) {
  const session = useSession();
  const [asking, setAsking] = useState(false);
  if (!isModerator(session.role) || !session.ready || ownerHandle === session.me?.handle) return null;
  const what = KIND_WORDS[kind].replace(/^an? /, "");

  async function apply(reason: string): Promise<void> {
    onChange(!hidden);
    try {
      await setHidden(kind, targetRef, !hidden, reason);
      onDone?.();
    } catch (error) {
      onChange(hidden);
      toastFailure(hidden ? `The ${what} couldn't be shown again.` : `The ${what} couldn't be hidden.`, error);
    }
  }

  return (
    <>
      <Button
        size="sm"
        variant="ghost"
        icon={hidden ? <Eye size={14} aria-hidden /> : <EyeOff size={14} aria-hidden />}
        aria-label={hidden ? `Show this ${what} again` : `Hide this ${what}`}
        onClick={() => setAsking(true)}
      >
        {hidden ? "Show again" : "Hide"}
      </Button>
      {asking ? (
        <ReasonDialog
          title={hidden ? `Show this ${what} again?` : `Hide this ${what}?`}
          confirmLabel={hidden ? "Show it again" : "Hide it"}
          danger={!hidden}
          onConfirm={(reason) => void apply(reason)}
          onClose={() => setAsking(false)}
        >
          <p>{hidden ? "Everyone who could see it before will see it again on their next visit." : HIDING[kind]}</p>
        </ReasonDialog>
      ) : null}
    </>
  );
}
