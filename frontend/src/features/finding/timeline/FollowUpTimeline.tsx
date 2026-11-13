import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, ExternalLink, Footprints, Plus, TrendingUp } from "lucide-react";
import { type ReactNode, useState } from "react";
import type { Meta } from "../../../api/meta.js";
import { safeHref } from "../../../map/attribution.js";
import { Button } from "../../../ui/Button.js";
import { TierBadge } from "../../../ui/TierBadge.js";
import { formatDate, labelOf, needsVerifying, outcomeWords, stanceWords, type ViewerPosition } from "../describe.js";
import { KindChooser, useOpener } from "../evidence/KindChooser.js";
import { useSignedInFirst } from "../feedback.js";
import { findingPageKeys } from "../keys.js";
import { ShapeChangeEntry } from "../shapeChanges.js";
import type { Evidence, FindingDetail } from "../types.js";
import { fetchLadderEvents } from "./api.js";
import { entryDay, followUpKinds, ladderMoves, timelineEntries } from "./followUps.js";
import "./timeline.css";

/** What a follow-up found, in a few words: its outcome, whether a record is verified, or its stance. */
function foundWords(meta: Meta, item: Evidence): string {
  if (item.outcome) return outcomeWords(item.outcome);
  if (needsVerifying(meta, item.kind)) {
    return item.verified_by ? `Verified by ${item.verified_by.display_name}` : "Not verified yet";
  }
  return stanceWords(item.stance);
}

function Entry({ meta, item, movedTo }: { meta: Meta; item: Evidence; movedTo: string | undefined }) {
  const kind = labelOf(meta.vocab.evidence_kinds, item.kind);
  const named = item.title ?? item.reference;
  const verified = needsVerifying(meta, item.kind) && item.verified_by !== null;
  const link = safeHref(item.url);
  const day = formatDate(item.occurred_on ?? item.created_at);
  return (
    <li className="fc-timeline__entry">
      <span className="fc-timeline__dot" aria-hidden="true" />
      <p className="fc-timeline__when">
        {item.occurred_on ? (
          <time dateTime={item.occurred_on}>{formatDate(item.occurred_on)}</time>
        ) : (
          <>
            Added <time dateTime={item.created_at}>{formatDate(item.created_at)}</time>
          </>
        )}
      </p>
      <p className="fc-timeline__what">
        <strong>{kind}</strong>
        {named ? <span className="fc-timeline__named">{named}</span> : null}
      </p>
      <p className="fc-timeline__who">
        {item.organisation ? `By ${item.organisation}, logged by ` : "Logged by "}
        {item.contributor.display_name}
      </p>
      <p className={`fc-timeline__found fc-stance fc-stance--${item.stance}`}>
        {verified ? <BadgeCheck size={13} aria-hidden /> : null}
        {foundWords(meta, item)}
      </p>
      {item.note ? <p className="fc-timeline__note">{item.note}</p> : null}
      {link ? (
        <a className="fc-evidence__link" href={link} target="_blank" rel="noreferrer noopener">
          <ExternalLink size={14} aria-hidden />
          Open the link
          {/* Each entry's link is told apart in a list of links. */}
          <span className="fc-visually-hidden">
            {" "}
            for {kind}, {day} (opens in a new tab)
          </span>
        </a>
      ) : null}
      {item.redacted ? (
        <p className="fc-finding__hint">Its link and references are hidden, because you can't see the exact place.</p>
      ) : null}
      {movedTo ? (
        <p className="fc-timeline__moved">
          <TrendingUp size={15} aria-hidden />
          It moved the finding up to
          <TierBadge size="sm" tier={{ id: movedTo, label: labelOf(meta.vocab.tiers, movedTo) }} />
        </p>
      ) : null}
    </li>
  );
}

export interface FollowUpTimelineProps {
  meta: Meta;
  finding: FindingDetail;
  position: ViewerPosition;
  /** Open the evidence form for this kind, which is how an entry is added. */
  onAdd: (kindId: string) => void;
}

/**
 * What happened on the ground and on record, in date order: site visits,
 * surveys, digs, a new Historic Environment Record entry or a scheduling,
 * each with its date, who did it, what it found and a link, and the step it
 * moved the finding up to when it did. The entries are the finding's own
 * evidence, so adding one opens that kind's evidence form, which reminds the
 * person of the rules before a visit is logged. Changes to the finding's
 * shape are listed among them by their day, after a follow-up of the same day.
 */
export function FollowUpTimeline({ meta, finding, position, onAdd }: FollowUpTimelineProps) {
  const signedInFirst = useSignedInFirst();
  const [choosing, setChoosing] = useState(false);
  const opener = useOpener("fc-timeline-add");
  const entries = timelineEntries(meta, finding.evidence);
  // Asked again whenever the step or the entries change, so a move shows on the entry that made it.
  const as = [finding.assessment.tier, ...entries.map((item) => item.id)].join(",");
  const events = useQuery({
    queryKey: findingPageKeys.ladderEvents(finding.public_id, as),
    queryFn: ({ signal }) => fetchLadderEvents(finding.public_id, signal),
    enabled: entries.length > 0,
  });
  const moves = events.data ? ladderMoves(meta, events.data.items) : new Map<number, string>();
  const kinds = followUpKinds(meta);
  const changes = finding.location.shape.changes.map((change, index) => ({ change, index }));
  // Both lists are oldest first. Merged by day, a follow-up goes before a change of the same day.
  const items: Array<{ key: string; day: string; node: ReactNode }> = [
    ...entries.map((item) => ({
      key: `evidence-${item.id}`,
      day: entryDay(item),
      node: <Entry key={`evidence-${item.id}`} meta={meta} item={item} movedTo={moves.get(item.id)} />,
    })),
    ...changes.map(({ change, index }) => ({
      key: `shape-${index}`,
      day: change.on,
      node: <ShapeChangeEntry key={`shape-${index}`} change={change} />,
    })),
  ];
  const ordered = items
    .map((item, order) => ({ ...item, order }))
    .sort((a, b) => a.day.localeCompare(b.day) || a.order - b.order);

  return (
    <section className="fc-finding__section" aria-labelledby="fc-timeline-title" id="fc-timeline">
      <h3 id="fc-timeline-title">Timeline</h3>
      <p className="fc-finding__hint">
        What has happened at the site and on record since it was spotted, in date order. Each entry is also evidence.
      </p>
      {ordered.length === 0 ? (
        <p className="fc-muted fc-timeline__empty">
          <Footprints size={15} aria-hidden /> Nothing yet. A site visit, a survey, a dig or a new heritage record goes
          here, with its date.
        </p>
      ) : (
        <ol className="fc-timeline" aria-label="What happened, oldest first">
          {ordered.map((item) => item.node)}
        </ol>
      )}
      {events.isError ? (
        <div className="fc-finding__inline-error" role="alert">
          <p>Which of these moved it up the ladder couldn't be loaded. {events.error.message}</p>
          <Button size="sm" onClick={() => void events.refetch()}>
            Try again
          </Button>
        </div>
      ) : null}
      {position.mayAddEvidence ? (
        choosing ? (
          <KindChooser
            heading="What happened?"
            kinds={kinds}
            idPrefix="fc-timeline-kind"
            onChoose={(kindId) => {
              setChoosing(false);
              void signedInFirst().then((ready) => {
                if (ready) onAdd(kindId);
              });
            }}
            onCancel={() => {
              setChoosing(false);
              opener.giveBack();
            }}
          />
        ) : (
          <Button id={opener.id} icon={<Plus size={16} aria-hidden />} onClick={() => setChoosing(true)}>
            Add to the timeline
          </Button>
        )
      ) : null}
    </section>
  );
}
