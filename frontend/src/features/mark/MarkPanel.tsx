import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { useKindDrafts } from "../drafts/savers.js";
import { useDocumentTitle } from "../placeholders.js";
import { firstArrival } from "../shell/arrival.js";
import { BARE_MAP_PATH } from "../shell/navigation.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { findingDrafts, useSavedDrafts } from "./findingDrafts.js";
import { MarkForm } from "./MarkForm.js";
import { useMarkReturn } from "./markReturn.js";
import { isUnsavedNewMark, useMarkStore } from "./markStore.js";
import { useLeaveOnEscape } from "./useLeaveOnEscape.js";
import { openSavedFinding } from "./useSaveMark.js";
import "./mark.css";

export const MARK_PATH = "/mark";

/** A draft that was saved since the page loaded opens the finding it became. */
function useOpenSavedDraft(draftId: string | undefined): boolean {
  const saved = useSavedDrafts((state) => (draftId === undefined ? undefined : state.saved[draftId]));
  const client = useQueryClient();
  const navigate = useNavigate();
  useEffect(() => {
    if (!saved || draftId === undefined) return;
    useSavedDrafts.getState().forget(draftId);
    openSavedFinding(client, navigate, saved);
  }, [saved, draftId, client, navigate]);
  return saved !== undefined;
}

/**
 * "Mark a finding": the map takes taps at once, the first placing a point
 * and each further one adding to it, and this short form fills the panel
 * (the sheet on a phone) beside the guidance and the drawing bar. At
 * `/mark` it is a new mark, and at `/mark/:draftId` a draft kept in this
 * browser, which is where a sign-in comes back to.
 *
 * Escape, or closing the panel, leaves. While points are being added it
 * stops adding them instead, keeping what was drawn.
 */
export function MarkPanel({ meta }: { meta: Meta }) {
  const { pathname } = useLocation();
  const { draftId } = useParams();
  const navigate = useNavigate();
  const drafts = useKindDrafts(findingDrafts);
  const draft = draftId === undefined ? null : (drafts.find((candidate) => candidate.id === draftId) ?? null);
  const loaded = useMarkStore((state) => state.draftId);
  const opening = useOpenSavedDraft(draftId);
  const back = useMarkReturn((state) => state.to);
  useDocumentTitle("Mark a finding");

  // A new mark starts afresh, unless a marking that was never saved or kept is still in hand:
  // another panel opened over this one, or the tool was closed, and what was drawn mustn't be
  // lost for that. A draft is taken up once, so changes made to it here are kept. The store
  // forgets everything when the person changes, and a draft open here is then taken up again.
  const begun = useRef(false);
  const [carriedOn, setCarriedOn] = useState(false);
  useEffect(() => {
    const mark = useMarkStore.getState();
    // The Layers panel opens over this one and closes back onto it. That isn't opening the tool.
    const arriving = firstArrival(pathname, "open the marking tool");
    if (draftId === undefined) {
      const ownToTool = mark.editing === null && mark.draftId === null;
      if (!begun.current && !arriving && ownToTool) {
        // Back from under the Layers panel: everything is as it was left.
      } else if (!begun.current && isUnsavedNewMark(mark)) setCarriedOn(true);
      else if (!begun.current || mark.draftId !== null) mark.start();
    } else if (draft && mark.draftId !== draftId) {
      mark.load(draftId, draft.data);
    }
    begun.current = true;
  }, [draftId, draft, pathname]);
  useEffect(() => {
    if (draftId !== undefined && draft && loaded === null) useMarkStore.getState().load(draftId, draft.data);
  }, [draftId, draft, loaded]);

  // Marking opened over a mode, such as a scan, closes back to it.
  const leave = useLeaveOnEscape(() => navigate(useMarkReturn.getState().to?.path ?? BARE_MAP_PATH));

  const missingDraft = draftId !== undefined && draft === null && !opening;
  const placed = useMarkStore((state) => state.shape.present.points.length > 0);
  const subtitle = missingDraft
    ? undefined
    : !placed
      ? "Put the mark where you see it"
      : draftId !== undefined
        ? "Not saved yet"
        : "Say what it looks like, then save";

  return (
    <PanelFrame panelKey={MARK_PATH} title="Mark a finding" subtitle={subtitle} onClose={leave}>
      {missingDraft ? (
        <EmptyState
          title="This draft isn't here any more"
          action={
            <Button variant="primary" onClick={() => navigate(MARK_PATH)}>
              Mark a finding
            </Button>
          }
        >
          <p>It may have been saved or discarded in another tab.</p>
        </EmptyState>
      ) : draftId !== undefined && loaded !== draftId ? null : (
        <>
          {carriedOn && placed && draftId === undefined ? (
            <div className="fc-mark__notice" role="status">
              <p>Carrying on with the marking you hadn't saved.</p>
              <Button
                size="sm"
                onClick={() => {
                  setCarriedOn(false);
                  useMarkStore.getState().start();
                }}
              >
                Discard it
              </Button>
            </div>
          ) : null}
          <MarkForm meta={meta} draft={draft} />
        </>
      )}
      {back ? (
        <div className="fc-mark-back">
          <Button
            variant="ghost"
            size="sm"
            icon={<ArrowLeft size={15} aria-hidden />}
            onClick={() => navigate(back.path)}
          >
            {back.label}
          </Button>
        </div>
      ) : null}
    </PanelFrame>
  );
}
