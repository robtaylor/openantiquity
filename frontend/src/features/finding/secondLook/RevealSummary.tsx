import { Sparkles } from "lucide-react";
import type { Meta } from "../../../api/meta.js";
import { FeatureIcon } from "../../../ui/featureIcons.js";
import { changeMessage, labelOf } from "../describe.js";
import type { Reveal } from "../types.js";
import { ANSWER_WORDS } from "./answer.js";

/**
 * What answering a second look shows (Decision 0008): how the answer
 * compares with the finder's and everyone else's, and whether it moved the
 * finding. Shown only from the server's reply to the answer, so nothing here
 * can appear before it is given.
 */
export function RevealSummary({ meta, reveal }: { meta: Meta; reveal: Reveal }) {
  const { comparison, observation } = reveal;
  const { yes, unsure, no } = comparison.others;
  const counted = yes + unsure + no;
  const moved = changeMessage(
    meta,
    { tier: reveal.tier_before, state: reveal.state_before },
    { tier: reveal.tier_after, state: reveal.state_after },
  );
  const yours = observation.feature_class;
  return (
    <div className="fc-reveal" role="status">
      <p className="fc-reveal__answer">
        <strong>{ANSWER_WORDS[observation.visible].given}.</strong>{" "}
        {counted === 0
          ? "Nobody else has answered yet."
          : `${yes} other ${yes === 1 ? "person" : "people"} can see it, ${unsure} ${unsure === 1 ? "isn't" : "aren't"} sure and ${no} can't.`}
      </p>
      <p className="fc-reveal__class">
        <FeatureIcon classId={comparison.finder_class} size={18} />
        <span>
          The finder thinks it's {labelOf(meta.vocab.feature_classes, comparison.finder_class).toLowerCase()}.
          {comparison.matches_finder === true ? " So do you." : null}
          {comparison.matches_finder === false && yours
            ? ` You said ${labelOf(meta.vocab.feature_classes, yours).toLowerCase()}.`
            : null}
          {comparison.community_class && comparison.community_class !== comparison.finder_class
            ? ` Most people say ${labelOf(meta.vocab.feature_classes, comparison.community_class).toLowerCase()}.`
            : null}
        </span>
      </p>
      {moved ? (
        <p className="fc-reveal__moved">
          <Sparkles size={16} aria-hidden />
          {reveal.moved_up ? `Your answer helped. ${moved}` : moved}
        </p>
      ) : null}
    </div>
  );
}
