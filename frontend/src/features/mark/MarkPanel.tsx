import { useQueryClient } from "@tanstack/react-query";
import { ArrowLeft } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useLocation, useNavigate, useParams } from "react-router";
import type { Meta } from "../../api/meta.js";
import { useMainMap } from "../../map/mainMap.js";
import { useMapStore } from "../../map/store.js";
import { Button } from "../../ui/Button.js";
import { EmptyState } from "../../ui/EmptyState.js";
import { toast } from "../../ui/toastStore.js";
import { useKindDrafts } from "../drafts/savers.js";
import { frameExtent } from "../finding/mapView.js";
import { useDocumentTitle } from "../placeholders.js";
import { firstArrival } from "../shell/arrival.js";
import { BARE_MAP_PATH } from "../shell/navigation.js";
import { PanelFrame } from "../shell/PanelFrame.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { findingDrafts, useSavedDrafts } from "./findingDrafts.js";
import { MarkForm, markInSight, uncoveredBox } from "./MarkForm.js";
import { MARK_PATH, wasToldToCarryOn } from "./markPaths.js";
import { useMarkReturn } from "./markReturn.js";
import {
  EMPTY_MARK,
  isUnsavedNewMark,
  type MarkFields,
  type Unsaved,
  unsavedInHand,
  unsavedKey,
  useMarkStore,
} from "./markStore.js";
import { type LngLat, placesOf } from "./path.js";
import { inTheWayWords, wayBackTo } from "./savedShape.js";
import { focusPanelTitle, TakeOverNotice } from "./TakeOverNotice.js";
import { useLeaveOnEscape } from "./useLeaveOnEscape.js";
import { openSavedFinding } from "./useSaveMark.js";
import "./mark.css";

export { MARK_PATH };

/**
 * What a marking page would replace that hasn't been sent: anything unsent
 * in hand, except a new marking at `/mark`, which it carries on with, and
 * at `/mark/:draftId` that draft itself.
 */
export function inTheWayOfMarking(state: MarkFields, draftId: string | undefined): Unsaved | null {
  const held = unsavedInHand(state);
  if (held === null) return null;
  if (draftId === undefined) return held.kind === "marking" ? null : held;
  return held.kind === "draft" && held.draftId === draftId ? null : held;
}

/** A draft that was saved since the page loaded opens the finding it became. */
function useOpenSavedDraft(draftId: string | undefined): boolean {
  const saved = useSavedDrafts((state) => (draftId === undefined ? undefined : state.saved[draftId]));
  const client = useQueryClient();
  const navigate = useNavigate();
  useEffect(() => {
    if (!saved || draftId === undefined) return;
    useSavedDrafts.getState().forget(draftId);
    // The tool lets go of the draft that became the finding, and of nothing else it holds.
    openSavedFinding(client, navigate, saved, useMarkStore.getState().draftId === draftId);
  }, [saved, draftId, client, navigate]);
  return saved !== undefined;
}

/** Move the map to a marking: framed if it has an extent, centred on it if it is one point. */
function bringIntoView(places: readonly LngLat[]): void {
  const [only] = places;
  if (places.length > 1) frameExtent(places);
  else if (only) useMapStore.getState().requestCamera({ lng: only[0], lat: only[1] });
}

/**
 * Let go of the new marking in hand and start afresh, with a way back: a
 * long road is a lot to lose to one press. It comes back only while nothing
 * new has been placed, and set aside if the map is somewhere else
 * (`elsewhere`), so the map isn't moved to it.
 */
function discardUnfinished(elsewhere: (places: readonly LngLat[]) => boolean): void {
  const before = useMarkStore.getState();
  // The store replaces its values and never changes one in place, so the fields can be kept as they are.
  const kept = Object.fromEntries(Object.keys(EMPTY_MARK).map((key) => [key, before[key as keyof MarkFields]]));
  before.start();
  toast("The unfinished marking was discarded.", {
    action: {
      label: "Undo",
      onClick: () => {
        const now = useMarkStore.getState();
        if (now.editing !== null || now.draftId !== null || now.shape.present.points.length > 0) {
          toast("Finish or discard what you have in hand first.", { kind: "error" });
          return;
        }
        useMarkStore.setState({
          ...(kept as unknown as MarkFields),
          // A point that came from the cross would be taken for one just added.
          crossAdded: false,
          // Away from the tool this means nothing, and the next opening of the tool looks afresh.
          setAside: elsewhere(placesOf(before.shape.present)),
        });
      },
    },
  });
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
  // The form is held back until this panel has looked at what is in hand. The form's own
  // effects run before this one's, and one of them brings the marking into view: that was the
  // jump to a marking left somewhere else.
  const [looked, setLooked] = useState(false);
  const [carriedOn, setCarriedOn] = useState(false);
  const map = useMainMap();
  const { isPhone, sheetHeight } = usePanelEnvironment();
  // Whether a marking is out of the part of the map on show, as things stand when it is asked.
  const elsewhere = (places: readonly LngLat[]): boolean =>
    !markInSight(map, places, uncoveredBox({ isPhone, sheetHeight }, window.innerWidth, window.innerHeight));
  const elsewhereNow = useRef(elsewhere);
  elsewhereNow.current = elsewhere;
  const { state: arrivedWith } = useLocation();
  const stateNow = useRef(arrivedWith);
  stateNow.current = arrivedWith;
  const host = useRef<HTMLDivElement>(null);
  useEffect(() => {
    const mark = useMarkStore.getState();
    // The Layers panel opens over this one and closes back onto it. That isn't opening the tool.
    const arriving = firstArrival(pathname, "open the marking tool");
    if (inTheWayOfMarking(mark, draftId) !== null) {
      // Something unsent that this page would replace is asked about first, as every panel that
      // takes the tool asks. Until it is answered the tool isn't open on it, and a tap adds nothing.
      if (!mark.setAside) useMarkStore.setState({ setAside: true });
    } else if (draftId === undefined) {
      const ownToTool = mark.editing === null && mark.draftId === null;
      if (!begun.current && !arriving && ownToTool) {
        // Back from under the Layers panel: everything is as it was left.
      } else if (!begun.current && isUnsavedNewMark(mark)) {
        // The button was pressed to mark what is on the map now. A marking left somewhere else
        // is asked about, and the map stays where it is until the person says to go to it.
        // Sent here by a panel where the person already said to go back to it: they aren't asked again.
        const chosen = wasToldToCarryOn(stateNow.current);
        const away = !chosen && elsewhereNow.current(placesOf(mark.shape.present));
        if (chosen) bringIntoView(placesOf(mark.shape.present));
        // Said both ways, so an answer left from an earlier opening never stands.
        if (mark.setAside !== away) useMarkStore.setState({ setAside: away });
        if (!away) setCarriedOn(true);
      } else if (!begun.current || mark.draftId !== null) mark.start();
    } else if (draft && mark.draftId !== draftId) {
      mark.load(draftId, draft.data);
    }
    begun.current = true;
    setLooked(true);
  }, [draftId, draft, pathname]);
  useEffect(() => {
    if (draftId === undefined || !draft || loaded !== null) return;
    if (inTheWayOfMarking(useMarkStore.getState(), draftId) === null) useMarkStore.getState().load(draftId, draft.data);
  }, [draftId, draft, loaded]);

  // Marking opened over a mode, such as a scan, closes back to it.
  const leave = useLeaveOnEscape(() => navigate(useMarkReturn.getState().to?.path ?? BARE_MAP_PATH));

  const missingDraft = draftId !== undefined && draft === null && !opening;
  const placed = useMarkStore((state) => state.shape.present.points.length > 0);
  const setAside = useMarkStore((state) => state.setAside) && draftId === undefined;
  // Something unsent in hand that this page would replace, followed as text.
  const heldKey = useMarkStore((state) => (inTheWayOfMarking(state, draftId) === null ? null : unsavedKey(state)));
  const held = heldKey === null ? null : inTheWayOfMarking(useMarkStore.getState(), draftId);
  const asking = held !== null;

  function goToIt(): void {
    bringIntoView(placesOf(useMarkStore.getState().shape.present));
    useMarkStore.setState({ setAside: false });
    setCarriedOn(true);
  }

  function discard(): void {
    setCarriedOn(false);
    discardUnfinished((places) => elsewhereNow.current(places));
  }

  const subtitle = missingDraft
    ? undefined
    : asking
      ? "Something you haven't sent is waiting"
      : setAside
        ? "An unfinished marking is waiting"
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
      ) : !looked ? null : held ? (
        <TakeOverNotice
          words={inTheWayWords(draftId === undefined ? "Marking a finding" : "Opening this draft")[held.kind]}
          back={{
            label: "Go back to it",
            onClick: () => {
              const way = wayBackTo(held);
              useMarkStore.setState({ setAside: false });
              navigate(way.to, { state: way.state });
            },
          }}
          on={
            draftId === undefined
              ? { label: "Discard it and start here", onClick: () => useMarkStore.getState().start() }
              : {
                  label: "Discard it and open the draft",
                  onClick: () => {
                    useMarkStore.getState().start();
                    if (draft) useMarkStore.getState().load(draftId, draft.data);
                  },
                }
          }
        />
      ) : draftId !== undefined && loaded !== draftId ? null : setAside ? (
        // The form isn't shown yet: it would bring the marking into view, and taps would add to it.
        <TakeOverNotice
          words="You have an unfinished marking somewhere else on the map."
          back={{ label: "Go to it", onClick: goToIt }}
          on={{ label: "Discard it and start here", onClick: discard }}
        />
      ) : (
        <>
          {carriedOn && placed && draftId === undefined ? (
            <div className="fc-mark__notice" role="status" ref={host}>
              <p>Carrying on with the marking you hadn't saved.</p>
              <Button
                size="sm"
                onClick={() => {
                  focusPanelTitle(host.current);
                  discard();
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
