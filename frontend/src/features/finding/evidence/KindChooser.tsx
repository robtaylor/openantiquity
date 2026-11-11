import type { EvidenceKind } from "../../../api/meta.js";
import { Button } from "../../../ui/Button.js";

export interface KindChooserProps {
  heading: string;
  kinds: readonly EvidenceKind[];
  /** Keeps each hint's id apart from another chooser's on the same page. */
  idPrefix: string;
  /** Close the chooser before `onChoose` is called. */
  onChoose: (kindId: string) => void;
  onCancel: () => void;
}

/**
 * The kinds of evidence to choose from, each explained beside it, because a
 * tooltip never reaches touch or the keyboard. Used by the evidence section,
 * for every kind, and by the timeline, for the kinds that are follow-ups.
 */
export function KindChooser({ heading, kinds, idPrefix, onChoose, onCancel }: KindChooserProps) {
  return (
    <div className="fc-evidence-add fc-kind-chooser">
      <h4>{heading}</h4>
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
