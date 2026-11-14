/**
 * "Suggested changes": the pending suggestions to a marking's shape, as the
 * server sends them (`location.shape.suggestions`, only ever to signed-in
 * members who see the finding exactly, Decision 0039). Each says who
 * suggested it and when, what it does, and whether it was made on an
 * earlier shape (`behind`), and "Show on the map" draws it as a dashed band
 * beneath the shape as it is (`dashedShape.ts`).
 *
 * Accept and Decline are offered only where the server allows deciding
 * (`actions.decide_suggestions`), which is the keeper's. Accepting names
 * the revision the keeper sees, and one made on an earlier shape is asked
 * about first, since it replaces the changes since. A refused accept, such
 * as one that would move too much of the ground second looks covered, is
 * said beside the suggestion in the server's words. That refusal reaches
 * only the keeper, who may see that ground. A suggester can withdraw their
 * own.
 */

import { useQueryClient } from "@tanstack/react-query";
import { Check, Map as MapIcon, Undo2, X } from "lucide-react";
import { useEffect, useRef, useState } from "react";
import { useMainMap } from "../../map/mainMap.js";
import { Button } from "../../ui/Button.js";
import { Dialog } from "../../ui/Dialog.js";
import { toast } from "../../ui/toastStore.js";
import { lengthWords } from "../mark/DrawingTool.js";
import { focusAfter } from "../mark/focus.js";
import { usePanelEnvironment } from "../shell/panelContext.js";
import { acceptSuggestion, declineSuggestion, isShapeChanged, withdrawSuggestion } from "./api.js";
import { dashedLayers, useDashedShapeOnMap } from "./dashedShape.js";
import { formatDate } from "./describe.js";
import { reasonOf } from "./feedback.js";
import { PANEL_TITLE } from "./focusWhenGone.js";
import { findingPageKeys } from "./keys.js";
import { frameExtent, whenStageSettled } from "./mapView.js";
import { refreshAfterMarking } from "./refreshLists.js";
import type { FindingDetail, ShapeSuggestion } from "./types.js";

export const SUGGESTION_SOURCE = "finding-suggestion";
export const SUGGESTION_LAYERS = dashedLayers(SUGGESTION_SOURCE);

const MOVED_WHILE_LOOKING =
  "The shape was changed while you were looking. Have another look at the suggestion against it as it is now.";

/** What a suggestion would do to the shape, in a sentence or two. */
export function suggestionWords(suggestion: ShapeSuggestion): string {
  const long = suggestion.path.closed ? "" : ` It would be ${lengthWords(suggestion.length_m)} long.`;
  switch (suggestion.kind) {
    case "extended":
      return `Draws it further.${long}`;
    case "closed":
      return "Closes the line into a shape.";
    case "opened":
      return `Opens the shape out into a line.${long}`;
    case "drawn":
      return `Draws a line or shape for it.${long}`;
    case "removed":
      return "Takes its line or shape away.";
    default:
      return `Changes its line or shape.${long}`;
  }
}

interface CardProps {
  finding: FindingDetail;
  suggestion: ShapeSuggestion;
  mayDecide: boolean;
  own: boolean;
  shown: boolean;
  onShow: () => void;
  onApplied: (finding: FindingDetail) => void;
  /** Said as the person accepts, declines or withdraws it, so focus can follow when the card goes. */
  onActed: () => void;
}

function SuggestionCard({ finding, suggestion, mayDecide, own, shown, onShow, onApplied, onActed }: CardProps) {
  const client = useQueryClient();
  const [problem, setProblem] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const refresh = () => void client.invalidateQueries({ queryKey: findingPageKeys.detail(finding.public_id) });

  async function run(step: () => Promise<void>): Promise<void> {
    if (busy) return;
    setBusy(true);
    setProblem(null);
    onActed();
    try {
      await step();
    } catch (error) {
      if (isShapeChanged(error)) {
        setProblem(MOVED_WHILE_LOOKING);
        refresh();
      } else setProblem(reasonOf(error));
    } finally {
      setBusy(false);
    }
  }

  const accept = () =>
    run(async () => {
      setConfirming(false);
      const updated = await acceptSuggestion(finding.public_id, suggestion.id, finding.location.shape.revision ?? 0);
      onApplied(updated);
      refreshAfterMarking(client);
      toast(`The suggested change is accepted, and the shape is changed. It names ${suggestion.by.display_name}.`, {
        kind: "success",
      });
    });
  const decline = () =>
    run(async () => {
      await declineSuggestion(finding.public_id, suggestion.id);
      refresh();
      refreshAfterMarking(client);
      toast("The suggestion is declined.");
    });
  const withdraw = () =>
    run(async () => {
      await withdrawSuggestion(finding.public_id, suggestion.id);
      refresh();
      toast("Your suggestion is withdrawn.");
    });

  const day = formatDate(suggestion.created_at);
  return (
    <li className="fc-suggestion" data-suggestion={suggestion.id}>
      <p className="fc-suggestion__who">
        <strong>{suggestion.by.display_name}</strong> suggested on <time dateTime={suggestion.created_at}>{day}</time>
      </p>
      <p>{suggestionWords(suggestion)}</p>
      {suggestion.behind ? (
        <p className="fc-suggestion__behind">
          Made on an earlier shape. Accepting it replaces the changes made to the shape since.
        </p>
      ) : null}
      <div className="fc-finding__tools">
        {mayDecide ? (
          <>
            <Button
              size="sm"
              variant="primary"
              icon={<Check size={15} aria-hidden />}
              aria-disabled={busy || undefined}
              onClick={() => (suggestion.behind ? setConfirming(true) : void accept())}
            >
              Accept
            </Button>
            <Button
              size="sm"
              icon={<X size={15} aria-hidden />}
              aria-disabled={busy || undefined}
              onClick={() => void decline()}
            >
              Decline
            </Button>
          </>
        ) : null}
        {own ? (
          <Button
            size="sm"
            variant="ghost"
            icon={<Undo2 size={15} aria-hidden />}
            aria-disabled={busy || undefined}
            onClick={() => void withdraw()}
          >
            Withdraw it
          </Button>
        ) : null}
        <Button size="sm" icon={<MapIcon size={15} aria-hidden />} aria-pressed={shown} onClick={onShow}>
          Show on the map
        </Button>
      </div>
      {problem ? (
        <p className="fc-field__error" role="alert">
          {problem}
        </p>
      ) : null}
      <Dialog
        open={confirming}
        onClose={() => setConfirming(false)}
        title="Accept a suggestion made on an earlier shape?"
        actions={
          <>
            <Button onClick={() => setConfirming(false)}>Keep the shape as it is</Button>
            <Button variant="primary" onClick={() => void accept()}>
              Accept it
            </Button>
          </>
        }
      >
        <p>
          {suggestion.by.display_name} made it on {day}, before the shape's last change. Accepting it replaces the
          changes made to the shape since with this one.
        </p>
      </Dialog>
    </li>
  );
}

export interface SuggestedChangesProps {
  finding: FindingDetail;
  /** The signed-in viewer's handle, to offer withdrawing on their own suggestion. Null when signed out. */
  viewerHandle: string | null;
  onApplied: (finding: FindingDetail) => void;
}

export function SuggestedChanges({ finding, viewerHandle, onApplied }: SuggestedChangesProps) {
  const map = useMainMap();
  const environment = usePanelEnvironment();
  const suggestions = finding.location.shape.suggestions ?? [];
  const [shownId, setShownId] = useState<number | null>(null);
  const shown = suggestions.find((suggestion) => suggestion.id === shownId) ?? null;
  useDashedShapeOnMap(map, SUGGESTION_SOURCE, SUGGESTION_LAYERS, shown?.outline ?? null);
  // When a card the person acted on goes, focus goes to the next card's first control, or the one
  // before it, or the panel's title once none is left.
  const acted = useRef<{ id: number; order: number[] } | null>(null);
  const ids = suggestions.map((suggestion) => suggestion.id).join(",");
  useEffect(() => {
    const pending = acted.current;
    const now = ids === "" ? [] : ids.split(",").map(Number);
    if (pending === null || now.includes(pending.id)) return;
    acted.current = null;
    const at = pending.order.indexOf(pending.id);
    const after = pending.order.slice(at + 1).find((id) => now.includes(id));
    const before = pending.order
      .slice(0, at)
      .reverse()
      .find((id) => now.includes(id));
    const next = after ?? before;
    focusAfter(null, next === undefined ? PANEL_TITLE : `[data-suggestion="${next}"] button:not(:disabled)`);
  }, [ids]);
  if (suggestions.length === 0) return null;
  const mayDecide = finding.actions.decide_suggestions.allowed;

  function show(suggestion: ShapeSuggestion): void {
    if (shownId === suggestion.id) {
      setShownId(null);
      return;
    }
    setShownId(suggestion.id);
    // On a phone the sheet comes down so the map above it shows the suggestion.
    if (environment.isPhone && environment.stop === "full") environment.setStop("half");
    const points = suggestion.path.points.map(({ lon, lat }) => [lon, lat] as const);
    // Asked for, so it is framed even where some of it is already in sight.
    whenStageSettled(() => frameExtent(points));
  }

  return (
    <section className="fc-finding__section" aria-labelledby="fc-suggested-title">
      <h3 id="fc-suggested-title">Suggested changes</h3>
      <p className="fc-finding__hint">
        {mayDecide
          ? "Others suggest these changes to its shape. Accepting one changes the shape, and the change names who suggested it."
          : "Changes others suggest to its shape. Its keeper accepts or declines them."}
      </p>
      <ul className="fc-suggestions" aria-label="Suggested changes">
        {suggestions.map((suggestion) => (
          <SuggestionCard
            key={suggestion.id}
            finding={finding}
            suggestion={suggestion}
            mayDecide={mayDecide}
            own={viewerHandle !== null && suggestion.by.handle === viewerHandle}
            shown={suggestion.id === shownId}
            onShow={() => show(suggestion)}
            onApplied={onApplied}
            onActed={() => {
              acted.current = { id: suggestion.id, order: suggestions.map((each) => each.id) };
            }}
          />
        ))}
      </ul>
    </section>
  );
}
