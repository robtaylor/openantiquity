import { ArrowRight, ExternalLink } from "lucide-react";
import { useEffect, useRef } from "react";
import { Link } from "react-router";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { FeatureIcon } from "../../ui/featureIcons.js";
import { Meter } from "../../ui/Meter.js";
import { TierBadge } from "../../ui/TierBadge.js";
import { labelOf } from "../finding/describe.js";
import { RevealSummary } from "../finding/secondLook/RevealSummary.js";
import type { Reveal } from "../finding/types.js";
import { findingPath } from "../findings/selection.js";

/** The summary, which "Next finding" is described by, so it is read out with the button that takes focus. */
const SUMMARY_ID = "fc-review-reveal-summary";

export interface RevealCardProps {
  meta: Meta;
  reveal: Reveal;
  onNext: () => void;
}

/**
 * What answering a card shows (Decision 0008): how the answer compares and
 * whether it moved the finding up, then the finding in full, as the finder
 * marked it. One press goes on to the next card, and focus waits on that
 * button so Enter does it.
 */
export function RevealCard({ meta, reveal, onNext }: RevealCardProps) {
  const { finding } = reveal;
  const { assessment } = finding;
  const tier = { id: assessment.tier, label: labelOf(meta.vocab.tiers, assessment.tier) };
  const state = { id: assessment.state, label: labelOf(meta.vocab.states, assessment.state) };
  const [nextStep] = assessment.next_steps;
  const section = useRef<HTMLElement>(null);
  const actions = useRef<HTMLDivElement>(null);

  // The reveal starts at its top, whatever the detail before it was scrolled to.
  useEffect(() => {
    section.current?.scrollIntoView?.({ block: "start" });
    actions.current?.querySelector<HTMLButtonElement>("button")?.focus({ preventScroll: true });
  }, []);

  return (
    <section className="fc-review__reveal" aria-labelledby="fc-review-revealed" ref={section}>
      <RevealSummary meta={meta} reveal={reveal} id={SUMMARY_ID} />

      <div className="fc-review__finding">
        <p className="fc-review__eyebrow">What the finder marked</p>
        <h3 className="fc-review__title" id="fc-review-revealed">
          {finding.title}
        </h3>
        <TierBadge tier={tier} state={state} />
        <Meter value={assessment.score} tiers={meta.vocab.tiers} tierId={tier.id} ruledOut={state.id === "ruled_out"} />
        <dl className="fc-finding__facts">
          <div>
            <dt>Looks like</dt>
            <dd>
              <FeatureIcon classId={finding.feature_class} size={18} />
              {labelOf(meta.vocab.feature_classes, finding.feature_class)}
            </dd>
          </div>
          <div>
            <dt>Period</dt>
            <dd>{labelOf(meta.vocab.periods, finding.period)}</dd>
          </div>
          <div>
            <dt>Spotted by</dt>
            <dd>{finding.author.display_name}</dd>
          </div>
        </dl>
        {finding.description ? <p className="fc-finding__description">{finding.description}</p> : null}
        {nextStep ? (
          <p className="fc-finding__hint">
            <strong>What would move it up:</strong> {nextStep.prompt}
          </p>
        ) : null}
        <p className="fc-finding__hint">
          You can't change your answer now. On the finding's page you can add a note to it, or take it back so it stops
          counting.
        </p>
      </div>

      <div className="fc-second-look__send fc-review__actions" ref={actions}>
        <Button
          variant="primary"
          icon={<ArrowRight size={16} aria-hidden />}
          onClick={onNext}
          aria-describedby={SUMMARY_ID}
        >
          Next finding
        </Button>
        <Link className="fc-button fc-button--ghost fc-button--md" to={findingPath(finding.public_id)}>
          <ExternalLink size={16} aria-hidden />
          Open its page
        </Link>
      </div>
    </section>
  );
}
