import { Sparkles } from "lucide-react";
import type { Meta } from "../../../api/meta.js";
import { FeatureIcon } from "../../../ui/featureIcons.js";
import { changeMessage, classLabel, shownClass } from "../describe.js";
import type { Comparison, Reveal } from "../types.js";
import { ANSWER_WORDS } from "./answer.js";

/**
 * How everyone else answered, in words: "2 other people can see it, 1 isn't
 * sure and 1 can't." A count of nobody is left out rather than said as 0.
 */
export function othersSentence({ yes, unsure, no }: Comparison["others"]): string {
  const parts: string[] = [];
  const who = (count: number) => {
    const first = parts.length === 0;
    if (count === 1) return first ? "1 other person" : "1";
    return first ? `${count} other people` : String(count);
  };
  if (yes > 0) parts.push(`${who(yes)} can see it`);
  if (unsure > 0) parts.push(`${who(unsure)} ${unsure === 1 ? "isn't" : "aren't"} sure`);
  if (no > 0) parts.push(`${who(no)} ${yes > 0 ? "can't" : "can't see it"}`);
  if (parts.length === 0) return "Nobody else has answered yet.";
  const last = parts.pop();
  return `${parts.length > 0 ? `${parts.join(", ")} and ${last}` : last}.`;
}

/**
 * What answering a second look shows (Decision 0008): how the answer
 * compares with the finder's and everyone else's, and whether it moved the
 * finding. Shown only from the server's reply to the answer, so nothing here
 * can appear before it is given.
 *
 * It isn't a live region itself, because one that arrives already filled is
 * often not read out. The page puts it in a region that was there before,
 * or points the control that takes focus at it through `id`.
 */
export function RevealSummary({ meta, reveal, id }: { meta: Meta; reveal: Reveal; id?: string }) {
  const { comparison, observation } = reveal;
  const moved = changeMessage(
    meta,
    { tier: reveal.tier_before, state: reveal.state_before },
    { tier: reveal.tier_after, state: reveal.state_after },
  );
  const yours = observation.feature_class;
  return (
    <div className="fc-reveal" id={id}>
      <p className="fc-reveal__answer">
        <strong>{ANSWER_WORDS[observation.visible].given}.</strong> {othersSentence(comparison.others)}
      </p>
      <p className="fc-reveal__class">
        <FeatureIcon classId={comparison.finder_class} size={18} />
        <span>
          The finder marked it as: {classLabel(meta, comparison.finder_class)}.
          {comparison.matches_finder === true ? " So did you." : null}
          {comparison.matches_finder === false && yours ? ` You said: ${classLabel(meta, yours)}.` : null}
          {comparison.community_class &&
          shownClass(meta, comparison.community_class) !== shownClass(meta, comparison.finder_class)
            ? ` Most people say: ${classLabel(meta, comparison.community_class)}.`
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
