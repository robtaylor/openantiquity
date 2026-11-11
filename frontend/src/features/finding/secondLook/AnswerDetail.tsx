import { useId } from "react";
import type { Meta } from "../../../api/meta.js";
import { ChipGroup } from "../../../ui/Chip.js";
import { Field } from "../../../ui/Field.js";
import { FeatureIcon } from "../../../ui/featureIcons.js";
import { type AnswerDraft, type CheckAnswer, explanationFor, withCheck } from "./answer.js";

const NOT_SAID = "not_said";

export interface AnswerDetailProps {
  meta: Meta;
  answer: AnswerDraft;
  onChange: (answer: AnswerDraft) => void;
}

/**
 * The optional detail of a second look, offered once the answer is chosen
 * and never before (docs/UI.md): what they think it is, whether each
 * ordinary explanation (modern, natural, a fault in the data) could account
 * for it, and a note. Everything here can be left as it is.
 */
export function AnswerDetail({ meta, answer, onChange }: AnswerDetailProps) {
  const headingId = useId();
  const classOptions = [
    { id: NOT_SAID, label: "Not sure" },
    ...meta.vocab.feature_classes
      .filter((featureClass) => featureClass.id !== "unknown")
      .map((featureClass) => ({
        id: featureClass.id,
        label: featureClass.label,
        icon: <FeatureIcon classId={featureClass.id} size={16} />,
      })),
  ];
  return (
    // biome-ignore lint/a11y/useSemanticElements: a fieldset's legend can't take this layout
    <div className="fc-answer-detail" role="group" aria-labelledby={headingId}>
      <p className="fc-answer-detail__title" id={headingId}>
        Anything to add? <span className="fc-muted">All of it is optional.</span>
      </p>
      {answer.visible !== "no" ? (
        <div className="fc-answer-detail__part">
          <p className="fc-answer-detail__label">What do you think it is?</p>
          <ChipGroup
            label="What do you think it is?"
            value={answer.featureClass ?? NOT_SAID}
            onChange={(id) => onChange({ ...answer, featureClass: id === NOT_SAID ? null : id })}
            options={classOptions}
          />
        </div>
      ) : null}
      {meta.vocab.checks.map((check) => {
        const explanation = meta.vocab.explanations.find((entry) => entry.id === explanationFor(meta, check.id));
        if (!explanation) return null;
        return (
          <div className="fc-answer-detail__part" key={check.id}>
            <p className="fc-answer-detail__label">{check.question}</p>
            <p className="fc-answer-detail__hint">{check.hint}</p>
            <ChipGroup
              label={check.question}
              value={answer.checks[check.id] ?? NOT_SAID}
              onChange={(id) => onChange(withCheck(answer, check.id, id === NOT_SAID ? null : (id as CheckAnswer)))}
              options={[
                { id: NOT_SAID, label: "Can't tell" },
                { id: "no", label: "No" },
                { id: "yes", label: `Yes, a ${explanation.label.toLowerCase()}` },
              ]}
            />
          </div>
        );
      })}
      <Field label="Note (optional)" hint="What you saw, or which layer showed it best.">
        {(control) => (
          <textarea
            {...control}
            className="fc-input"
            rows={2}
            maxLength={5000}
            value={answer.note}
            onChange={(event) => onChange({ ...answer, note: event.target.value })}
          />
        )}
      </Field>
    </div>
  );
}
