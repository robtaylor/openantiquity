import { useQuery, useQueryClient } from "@tanstack/react-query";
import { Eye, EyeOff, Shield } from "lucide-react";
import { useState } from "react";
import { Button } from "../../ui/Button.js";
import { ChipGroup } from "../../ui/Chip.js";
import { useSession } from "../account/session.js";
import { whoSees } from "../finding/describe.js";
import { toastFailure } from "../finding/feedback.js";
import { LEVEL_NAMES } from "../finding/Tools.js";
import { useApplyFinding, useOptimisticFinding } from "../finding/useFinding.js";
import { type FindingDetail, OFFERED_SENSITIVITIES, type OfferedSensitivity } from "../findings/types.js";
import { isModerator } from "./access.js";
import { fetchActions, setHidden, setLevel } from "./api.js";
import { HIDING } from "./HideButton.js";
import { moderationKeys } from "./keys.js";
import { ReasonDialog } from "./ReasonDialog.js";

/**
 * Whether a finding is hidden. A finding's page doesn't say, so this reads
 * the newest entry about it in the moderation log, which every hide and
 * show writes, and which carries the finding as it is now.
 */
function useFindingHidden(publicId: string, enabled: boolean) {
  const target = { kind: "finding" as const, ref: publicId };
  const query = useQuery({
    queryKey: moderationKeys.actions(target),
    queryFn: ({ signal }) => fetchActions({ target }, signal),
    enabled,
  });
  // A change shows at once, ahead of the log being asked for again.
  const [shown, setShown] = useState<boolean | null>(null);
  const logged = query.data?.items[0]?.target.hidden ?? false;
  return {
    known: query.isSuccess,
    hidden: shown ?? logged,
    setShown,
    refetch: () => void query.refetch(),
  };
}

/**
 * A moderator's controls on someone else's finding: hide it or show it
 * again, and set its level, lower as well as higher, each with a reason for
 * the log. A moderator's own finding gets none of these, since the server
 * refuses them (`own_content`).
 */
export function FindingModeration({ finding }: { finding: FindingDetail }) {
  const session = useSession();
  const applyFinding = useApplyFinding();
  const optimistic = useOptimisticFinding(finding.public_id);
  const client = useQueryClient();
  const allowed = isModerator(session.role) && session.ready && session.me?.handle !== finding.author.handle;
  const state = useFindingHidden(finding.public_id, allowed);
  const [dialog, setDialog] = useState<"hide" | "level" | null>(null);
  const others = OFFERED_SENSITIVITIES.filter((level) => level !== finding.sensitivity);
  const [level, setChosen] = useState<OfferedSensitivity | null>(null);
  if (!allowed) return null;

  async function hide(reason: string): Promise<void> {
    const next = !state.hidden;
    state.setShown(next);
    try {
      await setHidden("finding", finding.public_id, next, reason);
      state.refetch();
      for (const queryKey of [
        ["findings", "bbox"],
        ["findings", "list"],
      ])
        void client.invalidateQueries({ queryKey });
    } catch (error) {
      state.setShown(!next);
      toastFailure(next ? "The finding couldn't be hidden." : "The finding couldn't be shown again.", error);
    }
  }

  async function changeLevel(to: OfferedSensitivity, reason: string): Promise<void> {
    const undo = optimistic((current) => ({ ...current, sensitivity: to }));
    try {
      applyFinding(await setLevel(finding.public_id, to, reason));
    } catch (error) {
      undo();
      toastFailure("Its level couldn't be changed.", error);
    }
  }

  return (
    <section className="fc-finding__section" aria-labelledby="fc-moderation-title">
      <h3 id="fc-moderation-title">Moderation</h3>
      <p className="fc-finding__hint">
        Only moderators see this. Each change goes in the moderation log with your reason.
        {state.hidden ? " This finding is hidden: only its finder and moderators can find it." : ""}
      </p>
      <div className="fc-finding__tools">
        <Button
          size="sm"
          icon={state.hidden ? <Eye size={15} aria-hidden /> : <EyeOff size={15} aria-hidden />}
          disabled={!state.known}
          onClick={() => setDialog("hide")}
        >
          {state.hidden ? "Show it again" : "Hide it"}
        </Button>
        <Button
          size="sm"
          icon={<Shield size={15} aria-hidden />}
          onClick={() => {
            setChosen(null);
            setDialog("level");
          }}
        >
          Change its level
        </Button>
      </div>
      {dialog === "hide" ? (
        <ReasonDialog
          title={state.hidden ? "Show this finding again?" : "Hide this finding?"}
          confirmLabel={state.hidden ? "Show it again" : "Hide it"}
          danger={!state.hidden}
          onConfirm={(reason) => void hide(reason)}
          onClose={() => setDialog(null)}
        >
          <p>{state.hidden ? "Everyone who could find it before will find it again." : HIDING.finding}</p>
        </ReasonDialog>
      ) : null}
      {dialog === "level" ? (
        <ReasonDialog
          title="Change its level"
          confirmLabel="Change it"
          ready={level !== null}
          onConfirm={(reason) => {
            if (level) void changeLevel(level, reason);
          }}
          onClose={() => setDialog(null)}
        >
          <p>
            It's {LEVEL_NAMES[finding.sensitivity].toLowerCase()} now. {whoSees(finding.sensitivity)}
          </p>
          <ChipGroup
            label="New level"
            value={level}
            onChange={(value) => setChosen(value as OfferedSensitivity)}
            options={others.map((id) => ({ id, label: LEVEL_NAMES[id] }))}
          />
          {level ? <p>{whoSees(level)}</p> : null}
        </ReasonDialog>
      ) : null}
    </section>
  );
}
