import { useQuery } from "@tanstack/react-query";
import type { Meta } from "../../api/meta.js";
import { Avatar } from "../../ui/Avatar.js";
import { Skeleton } from "../../ui/Skeleton.js";
import { fetchObservations } from "./api.js";
import { creditWords, labelOf } from "./describe.js";
import { findingPageKeys } from "./keys.js";
import { ANSWER_WORDS } from "./secondLook/answer.js";
import type { FindingDetail } from "./types.js";

/**
 * Everyone's second looks, shown only to the finder and to people who have
 * answered (`answers_visible`, Decision 0008). The list is never asked for
 * otherwise, so nothing about other people's answers reaches the page early.
 */
export function Answers({ meta, finding }: { meta: Meta; finding: FindingDetail }) {
  const visible = finding.answers_visible;
  const answers = useQuery({
    queryKey: findingPageKeys.observations(finding.public_id),
    queryFn: ({ signal }) => fetchObservations(finding.public_id, signal),
    enabled: visible,
  });
  if (!visible) return null;
  const items = answers.data?.items ?? [];
  return (
    <section className="fc-finding__section" aria-labelledby="fc-answers-title">
      <h3 id="fc-answers-title">Second looks</h3>
      {answers.isPending ? (
        <Skeleton lines={2} />
      ) : answers.isError ? (
        <p className="fc-muted">The answers couldn't be loaded. {answers.error.message}</p>
      ) : items.length === 0 ? (
        <p className="fc-muted">Nobody has given a second look yet.</p>
      ) : (
        <ul className="fc-people">
          {items.map((answer) => (
            <li
              key={answer.user.handle}
              className={answer.withdrawn ? "fc-people__row fc-people__row--withdrawn" : "fc-people__row"}
            >
              <Avatar
                name={answer.user.display_name}
                handle={answer.user.handle}
                src={answer.user.avatar_url ?? undefined}
                size={24}
              />
              <span>
                <strong>{answer.user.display_name}</strong>{" "}
                <span className="fc-muted">
                  {ANSWER_WORDS[answer.visible].theirs}
                  {answer.feature_class
                    ? `: ${labelOf(meta.vocab.feature_classes, answer.feature_class).toLowerCase()}`
                    : ""}
                  {answer.explanation
                    ? `, maybe a ${labelOf(meta.vocab.explanations, answer.explanation).toLowerCase()}`
                    : ""}
                  {answer.withdrawn ? " (taken back)" : ""}
                </span>
                {answer.note ? <span className="fc-people__note">{answer.note}</span> : null}
              </span>
            </li>
          ))}
        </ul>
      )}
    </section>
  );
}

/** Who did what (DESIGN.md, "Credit is specific"). How someone answered shows only once answers are visible. */
export function Credits({ finding }: { finding: FindingDetail }) {
  if (finding.credits.length === 0) return null;
  // One line per person, with everything they did.
  const byPerson = new Map<string, { name: string; handle: string; avatar: string | null; did: string[] }>();
  for (const credit of finding.credits) {
    const entry = byPerson.get(credit.user.handle) ?? {
      name: credit.user.display_name,
      handle: credit.user.handle,
      avatar: credit.user.avatar_url ?? null,
      did: [],
    };
    const words = creditWords(credit.kind);
    if (!entry.did.includes(words)) entry.did.push(words);
    byPerson.set(credit.user.handle, entry);
  }
  return (
    <section className="fc-finding__section" aria-labelledby="fc-credits-title">
      <h3 id="fc-credits-title">Who helped</h3>
      <ul className="fc-people">
        {[...byPerson.values()].map((person) => (
          <li key={person.handle} className="fc-people__row">
            <Avatar name={person.name} handle={person.handle} src={person.avatar ?? undefined} size={24} />
            <span>
              <strong>{person.name}</strong> <span className="fc-muted">{person.did.join(", ")}</span>
            </span>
          </li>
        ))}
      </ul>
    </section>
  );
}
