import { ArrowRight, CircleCheck, Eye, Link2, Plus } from "lucide-react";
import type { ReactNode } from "react";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { labelOf, type StepAction, stepActions, type ViewerPosition } from "./describe.js";
import type { FindingDetail } from "./types.js";

const ICONS: Record<StepAction["kind"], typeof Eye> = {
  answer: Eye,
  evidence: Plus,
  endorse: ArrowRight,
  share: Link2,
};

export interface NextStepsProps {
  meta: Meta;
  finding: FindingDetail;
  position: ViewerPosition;
  onAction: (action: StepAction) => void;
}

/**
 * What would move the finding up: each next step the server gives, in its
 * own words, with a button for each thing this person could do about it.
 * The rules stay on the server. This only renders the assessment.
 */
export function NextSteps({ meta, finding, position, onAction }: NextStepsProps) {
  const { assessment } = finding;
  const steps = assessment.next_steps;
  const next = assessment.next_tier ? labelOf(meta.vocab.tiers, assessment.next_tier) : null;

  let body: ReactNode;
  if (!position.takesWork) {
    body = <p className="fc-muted">It's been withdrawn, so nothing more is asked for.</p>;
  } else if (assessment.state === "ruled_out") {
    body = (
      <p className="fc-muted">
        It's been explained, so nothing would move it up unless new evidence counts against that.
      </p>
    );
  } else if (steps.length === 0) {
    body = (
      <p className="fc-finding__done">
        <CircleCheck size={18} aria-hidden />
        {next ? "Nothing is waiting on anyone right now." : "It's on record. Nothing more is needed."}
      </p>
    );
  } else {
    body = (
      <ul className="fc-steps">
        {steps.map((step) => {
          const actions = stepActions(step, meta, position);
          return (
            <li key={`${step.code}-${step.check ?? ""}`} className="fc-steps__step" data-code={step.code}>
              <p className="fc-steps__prompt">{step.prompt}</p>
              {actions.length > 0 ? (
                <div className="fc-steps__actions">
                  {actions.map((action, index) => {
                    const Icon = ICONS[action.kind];
                    return (
                      <Button
                        key={`${action.kind}-${action.label}`}
                        size="sm"
                        variant={index === 0 && action.kind === "answer" ? "primary" : "secondary"}
                        icon={<Icon size={15} aria-hidden />}
                        onClick={() => onAction(action)}
                      >
                        {action.label}
                      </Button>
                    );
                  })}
                </div>
              ) : null}
            </li>
          );
        })}
      </ul>
    );
  }

  return (
    <section className="fc-finding__section" aria-labelledby="fc-steps-title">
      <h3 id="fc-steps-title">What would move it up</h3>
      {next && position.takesWork && assessment.state !== "ruled_out" && steps.length > 0 ? (
        <p className="fc-finding__hint">To reach {next}:</p>
      ) : null}
      {body}
      {!position.seesExact && steps.length > 0 && position.takesWork ? (
        <p className="fc-finding__hint">Only people who can see the exact place can help with these.</p>
      ) : null}
    </section>
  );
}
