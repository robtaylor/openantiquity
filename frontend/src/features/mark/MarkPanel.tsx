import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useRef } from "react";
import { useNavigate, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { useAccountUi } from "../account/requireAccount.js";
import { useKindDrafts } from "../drafts/savers.js";
import { useDocumentTitle } from "../placeholders.js";
import { BARE_MAP_PATH } from "../shell/navigation.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { findingDrafts, useSavedDrafts } from "./findingDrafts.js";
import { MarkForm } from "./MarkForm.js";
import { useMarkReturn } from "./markReturn.js";
import { useMarkStore } from "./markStore.js";
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
 * "Mark a finding": the map takes a tap or click for the mark, then this
 * short form fills the panel (the sheet on a phone). At `/mark` it is a new
 * mark, and at `/mark/:draftId` a draft kept in this browser, which is where
 * a sign-in comes back to.
 *
 * Escape, or closing the panel, leaves. While the outline tool is on it
 * stops the outline instead, keeping what was drawn.
 */
export function MarkPanel({ meta }: { meta: Meta }) {
  const { draftId } = useParams();
  const navigate = useNavigate();
  const drafts = useKindDrafts(findingDrafts);
  const draft = draftId === undefined ? null : (drafts.find((candidate) => candidate.id === draftId) ?? null);
  const loaded = useMarkStore((state) => state.draftId);
  const opening = useOpenSavedDraft(draftId);
  const back = useMarkReturn((state) => state.to);
  useDocumentTitle("Mark a finding");

  // A new mark starts afresh. A draft is taken up once, so changes made to it here are kept.
  const begun = useRef(false);
  useEffect(() => {
    const mark = useMarkStore.getState();
    if (draftId === undefined) {
      if (!begun.current || mark.draftId !== null) mark.start();
    } else if (draft && mark.draftId !== draftId) {
      mark.load(draftId, draft.data);
    }
    begun.current = true;
  }, [draftId, draft]);

  function leave(): void {
    const mark = useMarkStore.getState();
    if (mark.drawing) {
      mark.stopDrawing();
      return;
    }
    // Marking opened over a mode, such as a scan, closes back to it.
    navigate(useMarkReturn.getState().to?.path ?? BARE_MAP_PATH);
  }
  const leaveRef = useRef(leave);
  leaveRef.current = leave;

  // Escape leaves from anywhere, the map and the mark included, unless something else on screen took it.
  useEffect(() => {
    function onKeyDown(event: KeyboardEvent): void {
      if (event.key !== "Escape" || event.defaultPrevented) return;
      if (useAccountUi.getState().sheet !== null) return;
      if (event.target instanceof Element && event.target.closest('[role="dialog"], .fc-panel')) return;
      leaveRef.current();
    }
    window.addEventListener("keydown", onKeyDown);
    return () => window.removeEventListener("keydown", onKeyDown);
  }, []);

  const missingDraft = draftId !== undefined && draft === null && !opening;
  const placed = useMarkStore((state) => state.point !== null);
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
        <MarkForm meta={meta} draft={draft} />
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
