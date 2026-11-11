import { useEffect, useRef } from "react";
import type { EvidenceKind } from "../../../api/meta.js";
import { Button } from "../../../ui/Button.js";
import { scrollBehaviour } from "../../../ui/motion.js";
import { useFocusLater } from "../../../ui/useFocusLater.js";

export interface KindChooserProps {
  heading: string;
  kinds: readonly EvidenceKind[];
  /** Keeps each hint's id apart from another chooser's on the same page. */
  idPrefix: string;
  /** Close the chooser before `onChoose` is called. */
  onChoose: (kindId: string) => void;
  /** Cancel, or Escape. */
  onCancel: () => void;
}

/**
 * The kinds of evidence to choose from, each explained beside it, because a
 * tooltip never reaches touch or the keyboard. Used by the evidence section,
 * for every kind, and by the timeline, for the kinds that are follow-ups.
 * It opens in sight with focus on its heading, so the kinds are read next,
 * and Escape closes it as Cancel does.
 */
export function KindChooser({ heading, kinds, idPrefix, onChoose, onCancel }: KindChooserProps) {
  const title = useRef<HTMLHeadingElement>(null);
  useEffect(() => {
    title.current?.scrollIntoView?.({ block: "start", behavior: scrollBehaviour() });
    title.current?.focus({ preventScroll: true });
  }, []);
  return (
    // biome-ignore lint/a11y/noStaticElementInteractions: Escape is caught for the buttons inside, which have their own roles
    <div
      className="fc-evidence-add fc-kind-chooser"
      onKeyDown={(event) => {
        if (event.key !== "Escape") return;
        event.stopPropagation();
        onCancel();
      }}
    >
      <h4 className="fc-kind-chooser__title" tabIndex={-1} ref={title}>
        {heading}
      </h4>
      <ul className="fc-kind-list">
        {kinds.map((kind) => (
          <li key={kind.id} className="fc-kind-list__item">
            <Button size="sm" aria-describedby={`${idPrefix}-${kind.id}`} onClick={() => onChoose(kind.id)}>
              {kind.label}
            </Button>
            <span className="fc-finding__hint" id={`${idPrefix}-${kind.id}`}>
              {kind.hint}
            </span>
          </li>
        ))}
      </ul>
      <Button size="sm" variant="ghost" onClick={onCancel}>
        Cancel
      </Button>
    </div>
  );
}

/**
 * The button that opens a chooser, by its id, and a way to give it focus
 * back once it is shown again, after Cancel or Escape.
 */
export function useOpener(id: string): { id: string; giveBack: () => void } {
  const focusLater = useFocusLater();
  return { id, giveBack: () => focusLater(() => document.getElementById(id)) };
}
