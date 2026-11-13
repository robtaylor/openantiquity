import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, ExternalLink, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import { Link } from "react-router";
import type { Meta } from "../../../api/meta.js";
import { safeHref } from "../../../map/attribution.js";
import { Button } from "../../../ui/Button.js";
import { HideButton } from "../../moderation/HideButton.js";
import { photoAddress } from "../../photos/api.js";
import { Photo, PhotoPlaceholder } from "../../photos/Photo.js";
import { CategoryMark } from "../../records/CategoryMark.js";
import { OriginalLink } from "../../records/OriginalLink.js";
import { recordPath } from "../../records/paths.js";
import { SourceCredit } from "../../records/SourceCredit.js";
import { decodeEntities } from "../../records/text.js";
import { fetchRecord } from "../api.js";
import { formatDate, labelOf, needsVerifying, outcomeWords, stanceWords } from "../describe.js";
import { findingPageKeys } from "../keys.js";
import { ReportSlot } from "../Slots.js";
import type { Evidence } from "../types.js";
import { RELATION_WORDS } from "./RecordLinkForm.js";

/**
 * A stored record, for a record link that holds only its id: its name, which
 * opens its page here, what kind of record it is, its source and licence as
 * every list of records gives them, the start of what the source says, and
 * the source's own page in another tab.
 */
function RecordName({ meta, recordId }: { meta: Meta; recordId: number }) {
  const record = useQuery({
    queryKey: findingPageKeys.record(recordId),
    queryFn: ({ signal }) => fetchRecord(recordId, signal),
    staleTime: Number.POSITIVE_INFINITY,
  });
  if (!record.data) return <span className="fc-evidence__title">Record {recordId}</span>;
  const { name, record_type, source, category, summary, url } = record.data;
  return (
    <>
      <Link className="fc-evidence__title fc-evidence__title--link" to={recordPath(recordId)}>
        {decodeEntities(name)}
      </Link>
      <span className="fc-evidence__kind">
        <CategoryMark meta={meta} category={category} />
        {record_type ? <span className="fc-record__type">{record_type}</span> : null}
      </span>
      <span className="fc-evidence__meta">
        From <SourceCredit source={source} compact />
      </span>
      {summary ? <p className="fc-evidence__summary">{summary}</p> : null}
      <OriginalLink url={url} category={category} className="fc-evidence__link" iconSize={14} />
    </>
  );
}

function sourceName(meta: Meta, key: string | null): string | null {
  return key ? (meta.sources.find((source) => source.key === key)?.name ?? key) : null;
}

export interface EvidenceItemProps {
  meta: Meta;
  item: Evidence;
  /** This person may vote on it: they see the exact place and neither added it nor found the finding. */
  mayVote: boolean;
  /** When they may not, why, in a line shown where the votes would be. Without one, the votes are left out. */
  whyNoVote?: string | null;
  mayVerify: boolean;
  mayDelete: boolean;
  /** Being saved, so it can't be acted on yet. */
  pending?: boolean;
  onVote: (value: -1 | 0 | 1) => void;
  onVerify: () => void;
  onDelete: () => void;
  /** A moderator hid it, or the server refused and it is back. Hidden evidence leaves the page for everyone. */
  onHidden?: (hidden: boolean) => void;
  /** The server has hidden it. */
  onHiddenDone?: () => void;
}

function people(count: number): string {
  return count === 1 ? "1 person" : `${count} people`;
}

/**
 * Who has endorsed and disputed it, in words: "Endorsed by 2 people and
 * disputed by 1." The server counts them as it weighs them, leaving out the
 * contributor's and the finder's own votes.
 */
export function votesInWords({ endorsements, disputes }: Pick<Evidence, "endorsements" | "disputes">): string {
  if (endorsements === 0 && disputes === 0) return "Nobody has endorsed or disputed it yet.";
  if (disputes === 0) return `Endorsed by ${people(endorsements)}.`;
  if (endorsements === 0) return `Disputed by ${people(disputes)}.`;
  return `Endorsed by ${people(endorsements)} and disputed by ${disputes}.`;
}

/**
 * One piece of evidence: what it is, whether it supports the finding, who
 * added it, the endorsements and disputes on it, and for an official record
 * whether an expert has verified it.
 */
export function EvidenceItem({
  meta,
  item,
  mayVote,
  whyNoVote = null,
  mayVerify,
  mayDelete,
  pending = false,
  onVote,
  onVerify,
  onDelete,
  onHidden,
  onHiddenDone,
}: EvidenceItemProps) {
  const stored = item.kind === "record_link" && item.record_id !== null;
  const external = item.kind === "record_link" && !stored;
  const official = needsVerifying(meta, item.kind);
  const dated = item.occurred_on !== null || item.outcome !== null;
  // A stored record gives its own way to its source, from the record as it is now.
  const link = stored ? null : safeHref(item.url);

  return (
    <li className="fc-evidence" id={`evidence-${item.id}`} tabIndex={-1} aria-busy={pending || undefined}>
      <div className="fc-evidence__what">
        {item.kind === "record_link" && item.record_id !== null ? (
          <RecordName meta={meta} recordId={item.record_id} />
        ) : (
          <span className="fc-evidence__title">
            {item.title ??
              item.reference ??
              (external ? "A linked record" : labelOf(meta.vocab.evidence_kinds, item.kind))}
          </span>
        )}
        {external && (item.reference || item.source_key) ? (
          <span className="fc-evidence__meta">
            {[sourceName(meta, item.source_key), item.reference].filter(Boolean).join(" · ")}
          </span>
        ) : null}
        {item.title && item.reference && !external ? <span className="fc-evidence__meta">{item.reference}</span> : null}
        {dated ? (
          <span className="fc-evidence__meta">
            {[
              item.occurred_on ? formatDate(item.occurred_on) : null,
              item.organisation,
              item.outcome ? outcomeWords(item.outcome) : null,
            ]
              .filter(Boolean)
              .join(" · ")}
          </span>
        ) : null}
        {link ? (
          <a className="fc-evidence__link" href={link} target="_blank" rel="noreferrer noopener">
            <ExternalLink size={14} aria-hidden />
            Open it
          </a>
        ) : null}
      </div>

      {/* The server leaves a photo's id out for anyone who may not see it yet. A square's viewer is told why above. */}
      {item.kind === "photo" && item.media_id === null && !pending && !item.redacted ? <PhotoPlaceholder /> : null}
      {item.media_id !== null && !pending ? (
        <Photo
          src={photoAddress(item.media_id)}
          mediaId={item.media_id}
          alt={`${labelOf(meta.vocab.evidence_kinds, item.kind)} added by ${item.contributor.display_name}`}
          actions={
            <ReportSlot
              target={{ kind: "photo", id: item.media_id }}
              ownerHandle={item.contributor.handle}
              label="Report photo"
            />
          }
        />
      ) : null}

      <div className="fc-evidence__tags">
        <span className={`fc-stance fc-stance--${item.stance}`}>{stanceWords(item.stance)}</span>
        {item.relation ? <span className="fc-stance">{RELATION_WORDS[item.relation].label}</span> : null}
      </div>

      {item.note ? <p className="fc-evidence__note">{item.note}</p> : null}
      {item.redacted ? (
        <p className="fc-finding__hint">Its link and references are hidden, because you can't see the exact place.</p>
      ) : null}

      <p className="fc-evidence__by">
        Added by {item.contributor.display_name} on {formatDate(item.created_at)}
        {pending ? " · Saving…" : null}
      </p>
      {pending ? null : <p className="fc-evidence__votes">{votesInWords(item)}</p>}
      {!item.standing ? (
        <p className="fc-evidence__status">More people dispute this than endorse it, so it doesn't count for now.</p>
      ) : !item.independent && !pending ? (
        <p className="fc-evidence__status">It counts once someone other than the finder endorses it.</p>
      ) : null}
      {official ? (
        <p className="fc-evidence__status">
          {item.verified_by ? (
            <>
              <BadgeCheck size={15} aria-hidden /> Verified by {item.verified_by.display_name}
            </>
          ) : (
            "Not verified yet. An archaeologist or moderator checks a record like this before it counts."
          )}
        </p>
      ) : null}

      <div className="fc-evidence__actions">
        {mayVote ? (
          // biome-ignore lint/a11y/useSemanticElements: a fieldset can't lay out a toolbar row
          <div className="fc-vote" role="group" aria-label="Endorse or dispute">
            <Button
              size="sm"
              variant="ghost"
              icon={<ThumbsUp size={15} aria-hidden />}
              aria-pressed={item.my_vote === 1}
              disabled={pending}
              onClick={() => onVote(item.my_vote === 1 ? 0 : 1)}
            >
              Endorse
            </Button>
            <Button
              size="sm"
              variant="ghost"
              icon={<ThumbsDown size={15} aria-hidden />}
              aria-pressed={item.my_vote === -1}
              disabled={pending}
              onClick={() => onVote(item.my_vote === -1 ? 0 : -1)}
            >
              Dispute
            </Button>
          </div>
        ) : whyNoVote ? (
          <p className="fc-finding__hint">{whyNoVote}</p>
        ) : null}
        {official && !item.verified_by && mayVerify ? (
          <Button size="sm" icon={<BadgeCheck size={15} aria-hidden />} disabled={pending} onClick={onVerify}>
            Verify
          </Button>
        ) : null}
        {mayDelete ? (
          <Button
            size="sm"
            variant="ghost"
            icon={<Trash2 size={15} aria-hidden />}
            disabled={pending}
            onClick={onDelete}
          >
            Remove
          </Button>
        ) : null}
        {pending ? null : (
          <span className="fc-flag-actions">
            <ReportSlot target={{ kind: "evidence", id: item.id }} ownerHandle={item.contributor.handle} />
            <HideButton
              kind="evidence"
              targetRef={String(item.id)}
              ownerHandle={item.contributor.handle}
              hidden={false}
              onChange={(hidden) => onHidden?.(hidden)}
              onDone={onHiddenDone}
            />
          </span>
        )}
      </div>
    </li>
  );
}
