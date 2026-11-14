/**
 * "Suggest a change": the drawing tool opened on someone else's marking, at
 * `/mark/suggest/:publicId`, for whoever the server lets suggest
 * (`actions.suggest`, Decision 0039). The tool is given the saved path under
 * a key of its own (`editingKey(finding, "suggest")`), so a suggestion is
 * never saved as a change, and hands back the changed one; this panel alone
 * knows that it is sent with `POST /findings/{id}/suggestions`, naming the
 * revision it started from. The keeper accepts or declines it.
 *
 * It takes the tool up and asks before taking it over as "Change the shape"
 * does (`useSavedShapeInTool`). What differs is what leaving does. A
 * suggestion is the suggester's own work, as a new marking is, so Close and
 * Escape keep it in hand: it stays on the map, dashed, and is asked about
 * before anything else takes the tool. Only Cancel throws it away.
 *
 * Nothing about the ground second looks covered is drawn or said here. A
 * suggester isn't sent it, and the server doesn't test a suggestion against
 * it until the keeper accepts.
 */

import { useQueryClient } from "@tanstack/react-query";
import { LogIn, MapPinned } from "lucide-react";
import { useMemo } from "react";
import { useNavigate, useParams } from "react-router";
import { useMainMap } from "../../map/mainMap.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { toast } from "../../ui/toastStore.js";
import { useAccountUi } from "../account/requireAccount.js";
import { useSession } from "../account/session.js";
import { isShapeChanged, suggestChange } from "../finding/api.js";
import { findingPageKeys } from "../finding/keys.js";
import type { FindingDetail } from "../finding/types.js";
import { useFinding } from "../finding/useFinding.js";
import { findingPath } from "../findings/selection.js";
import { useDocumentTitle } from "../placeholders.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { ChangedUnderYou } from "./ChangedUnderYou.js";
import { saveProblem } from "./compose.js";
import { baseRevision, changeShapePath, keyFor, suggestPath } from "./editingKey.js";
import { HeldHere } from "./HeldHere.js";
import { DrawingSection, useMarkInView } from "./MarkForm.js";
import { unsentSuggestion, useMarkPath, useMarkStore } from "./markStore.js";
import { apiPath, placesOf } from "./path.js";
import {
  holdsThisFinding,
  inTheWayOf,
  inTheWayWords,
  learnShapeChanged,
  sendableRevision,
  shapeChangedUnseen,
  useSavedShapeInTool,
  wayBackTo,
} from "./savedShape.js";
import { TakeOverNotice } from "./TakeOverNotice.js";
import { useLeaveOnEscape } from "./useLeaveOnEscape.js";
import "./mark.css";

const IN_THE_WAY = inTheWayWords("Suggesting a change");
const CHANGED_UNDER_YOU =
  "The keeper changed the shape while you were drawing. Your suggestion hasn't been sent, and your drawing is still here. The map shows the shape as it is now.";
export const SENT = "Your suggestion is sent. Its keeper accepts or declines it, and you'll be told which.";
const SENT_IN_PLACE =
  "Your suggestion is sent, in place of your earlier one. Its keeper accepts or declines it, and you'll be told which.";
const REPLACES = "You already have a suggestion waiting on this marking. Sending this one replaces it.";
const CHANGE_FIRST = "Change the shape first, or cancel to leave it as it is.";
const A_LINE_OR_SHAPE = "A suggestion is a line or a shape. Put down two points or more.";

/** Cancel: the suggestion is thrown away. What the tool holds for something else is left as it is. */
function discardAndLeave(navigate: ReturnType<typeof useNavigate>, publicId: string): void {
  if (holdsThisFinding(publicId, "suggest")) useMarkStore.getState().start();
  navigate(findingPath(publicId));
}

function Suggest({ finding }: { finding: FindingDetail }) {
  // The server keeps one waiting suggestion for each person on a marking, and a new one replaces it.
  const handle = useSession().me?.handle ?? null;
  const replaces =
    handle !== null && (finding.location.shape.suggestions ?? []).some((suggestion) => suggestion.by.handle === handle);
  const environment = usePanelEnvironment();
  const map = useMainMap();
  const client = useQueryClient();
  const navigate = useNavigate();
  const path = useMarkPath();
  const drawing = useMarkStore((state) => state.drawing);
  const saving = useMarkStore((state) => state.saving);
  const { saved, key, ready, stale, unsaved, resumed, dropResumed, takeUpSaved, heldKey } = useSavedShapeInTool(
    finding,
    "suggest",
  );
  useMarkInView(
    useMemo(() => placesOf(path), [path]),
    drawing,
  );

  async function send(): Promise<void> {
    const mark = useMarkStore.getState();
    const base = sendableRevision(finding.public_id, "suggest", key);
    if (mark.saving || base === null) return;
    if (mark.shape.past.length === 0) {
      mark.setProblem({ field: "path", message: CHANGE_FIRST });
      return;
    }
    if (mark.shape.present.points.length < 2) {
      mark.setProblem({ field: "path", message: A_LINE_OR_SHAPE });
      return;
    }
    mark.setProblem(null);
    mark.setSaving(true);
    try {
      await suggestChange(finding.public_id, { path: apiPath(mark.shape.present), path_revision: base });
      // The page lists the suggestion as the server now has it.
      void client.invalidateQueries({ queryKey: findingPageKeys.detail(finding.public_id) });
      useMarkStore.getState().start();
      navigate(findingPath(finding.public_id), { replace: true });
      toast(replaces ? SENT_IN_PLACE : SENT, { kind: "success" });
    } catch (error) {
      if (isShapeChanged(error)) {
        // The drawing stays in hand with its undo. The panel says so, and the person chooses what next.
        // Without the shape as it now is the panel has nothing to say it against, so a toast does.
        if (!(await learnShapeChanged(client, finding.public_id))) {
          toast(shapeChangedUnseen("suggestion"), { kind: "error" });
        }
        return;
      }
      const problem = saveProblem(error);
      if (problem.field) {
        useMarkStore.getState().setProblem({ field: "path", message: problem.message });
        requestAnimationFrame(() =>
          document.querySelector(".fc-mark .fc-mark__problem")?.scrollIntoView?.({ block: "nearest" }),
        );
      } else toast(`The suggestion couldn't be sent. ${problem.message}`, { kind: "error" });
    } finally {
      useMarkStore.getState().setSaving(false);
    }
  }

  if (!ready) {
    const held = heldKey === null ? null : inTheWayOf(finding.public_id, "suggest", useMarkStore.getState());
    if (held === null) return null;
    const back = wayBackTo(held);
    return (
      <TakeOverNotice
        words={IN_THE_WAY[held.kind]}
        back={{ label: "Go back to it", onClick: () => navigate(back.to, { state: back.state }) }}
        on={{ label: "Discard it and suggest a change", onClick: takeUpSaved }}
      />
    );
  }
  return (
    <div className="fc-mark">
      {stale ? (
        <ChangedUnderYou
          words={CHANGED_UNDER_YOU}
          sendLabel="Send it against the shape as it is now"
          onSend={() => {
            useMarkStore.getState().rename(key);
            void send();
          }}
          onStartAgain={takeUpSaved}
        />
      ) : null}
      {resumed && unsaved && !stale ? (
        <div className="fc-mark__notice" role="status">
          <p>Carrying on with the change you hadn't sent.</p>
          <Button
            size="sm"
            onClick={() => {
              dropResumed();
              takeUpSaved();
            }}
          >
            Discard it
          </Button>
        </div>
      ) : null}
      {saved === null ? (
        <p className="fc-mark__notice">
          Its shape was drawn before the drawing tool and can't be changed point by point. What you draw here is
          suggested in its place.
        </p>
      ) : null}
      {replaces ? <p className="fc-mark__notice">{REPLACES}</p> : null}
      <p className="fc-mark__hint">
        Draw the line or shape as you think it should be. Its keeper sees it drawn over the shape as it is, and accepts
        or declines it. To say why, add a comment on the finding.
      </p>
      <DrawingSection map={map} isPhone={environment.isPhone} />
      <div className="fc-mark__actions">
        <Button variant="primary" disabled={saving || stale} onClick={() => void send()}>
          {saving ? "Sending…" : "Send the suggestion"}
        </Button>
        <Button variant="ghost" onClick={() => discardAndLeave(navigate, finding.public_id)}>
          Cancel
        </Button>
      </div>
    </div>
  );
}

/** For anyone the server doesn't let suggest a change: the keeper changes it themselves, and others are told. */
function CantSuggest({ finding }: { finding: FindingDetail }) {
  const navigate = useNavigate();
  const held = useMarkStore((state) => unsentSuggestion(state) === finding.public_id);
  if (!held) return <CantSuggestBody finding={finding} />;
  const choices = [{ label: "Discard your suggestion", onClick: () => useMarkStore.getState().start() }];
  if (finding.actions.edit.allowed) {
    // They keep it now: what they drew carries over as a change, begun on the shape it was drawn on.
    choices.unshift({
      label: "Change the shape with your drawing",
      onClick: () => {
        const mark = useMarkStore.getState();
        const base = baseRevision(mark.editing, finding.public_id, "suggest");
        if (base === null) return;
        mark.rename(keyFor(finding.public_id, base));
        navigate(changeShapePath(finding.public_id));
      },
    });
  }
  return (
    <>
      <HeldHere
        words="Your suggested change to this shape wasn't sent, and it can't be sent now. It is still drawn on the map."
        choices={choices}
      />
      <CantSuggestBody finding={finding} />
    </>
  );
}

function CantSuggestBody({ finding }: { finding: FindingDetail }) {
  const navigate = useNavigate();
  const back = <Button onClick={() => navigate(findingPath(finding.public_id))}>Back to the finding</Button>;
  if (finding.actions.edit.allowed) {
    return (
      <EmptyState
        icon={<MapPinned size={22} />}
        title="You keep this marking"
        action={
          <>
            <Button variant="primary" onClick={() => navigate(changeShapePath(finding.public_id))}>
              Change the shape
            </Button>
            {back}
          </>
        }
      >
        <p>You keep this marking, so you change its shape yourself.</p>
      </EmptyState>
    );
  }
  if (finding.actions.suggest.reason === "unauthorised") {
    return (
      <EmptyState
        icon={<LogIn size={22} />}
        title="Sign in to suggest a change"
        action={
          <>
            <Button variant="primary" onClick={() => useAccountUi.getState().openSignIn()}>
              Sign in
            </Button>
            {back}
          </>
        }
      >
        <p>A suggestion goes to the marking's keeper, who accepts or declines it.</p>
      </EmptyState>
    );
  }
  return (
    <EmptyState icon={<MapPinned size={22} />} title="You can't suggest a change to this shape" action={back}>
      <p>This finding takes no suggestions now.</p>
    </EmptyState>
  );
}

/**
 * The panel at `/mark/suggest/:publicId`. Escape, or closing it, stops adding
 * points first, then goes back to the finding with the suggestion still in
 * hand. Cancel throws it away.
 */
export function SuggestPanel() {
  const { publicId = "" } = useParams();
  const navigate = useNavigate();
  const query = useFinding(publicId);
  const finding = query.data;
  useDocumentTitle("Suggest a change");

  const leave = useLeaveOnEscape(
    () => navigate(findingPath(publicId)),
    () => holdsThisFinding(publicId, "suggest"),
  );

  return (
    <PanelFrame panelKey={suggestPath(publicId)} title="Suggest a change" subtitle={finding?.title} onClose={leave}>
      {finding ? (
        finding.actions.suggest.allowed ? (
          <Suggest finding={finding} />
        ) : (
          <CantSuggest finding={finding} />
        )
      ) : query.isError ? (
        <EmptyState
          tone="error"
          title="This finding couldn't be loaded"
          action={
            <Button variant="primary" onClick={() => void query.refetch()}>
              Try again
            </Button>
          }
        >
          <p>{query.error.message}</p>
        </EmptyState>
      ) : null}
    </PanelFrame>
  );
}
