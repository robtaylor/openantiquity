import { useQuery } from "@tanstack/react-query";
import { BadgeCheck, ExternalLink, ThumbsDown, ThumbsUp, Trash2 } from "lucide-react";
import type { Meta } from "../../../api/meta.js";
import { Button } from "../../../ui/Button.js";
import { fetchRecord } from "../api.js";
import { formatDate, labelOf, needsVerifying, outcomeWords, stanceWords } from "../describe.js";
import { findingPageKeys } from "../keys.js";
import type { Evidence } from "../types.js";
import { RELATION_WORDS } from "./RecordLinkForm.js";

/** A stored record's name and source, for a record link that holds only its id. */
function RecordName({ meta, recordId }: { meta: Meta; recordId: number }) {
  const record = useQuery({
    queryKey: findingPageKeys.record(recordId),
    queryFn: ({ signal }) => fetchRecord(recordId, signal),
    staleTime: Number.POSITIVE_INFINITY,
  });
  if (!record.data) return <span className="fc-evidence__title">Record {recordId}</span>;
  return (
    <>
      <span className="fc-evidence__title">{record.data.name}</span>
      <span className="fc-evidence__meta">
        {record.data.source.name} · {labelOf(meta.vocab.record_categories, record.data.category)}
      </span>
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
  mayVerify: boolean;
  mayDelete: boolean;
  /** Being saved, so it can't be acted on yet. */
  pending?: boolean;
  onVote: (value: -1 | 0 | 1) => void;
  onVerify: () => void;
  onDelete: () => void;
}

/** The weighted vote total as shown, such as "+2.5", "0" or "−1". */
function supportOf(total: number): string {
  const rounded = Math.round(total * 10) / 10;
  if (rounded > 0) return `+${rounded}`;
  if (rounded < 0) return `−${Math.abs(rounded)}`;
  return "0";
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
  mayVerify,
  mayDelete,
  pending = false,
  onVote,
  onVerify,
  onDelete,
}: EvidenceItemProps) {
  const external = item.kind === "record_link" && item.record_id === null;
  const official = needsVerifying(meta, item.kind);
  const dated = item.occurred_on !== null || item.outcome !== null;

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
        {item.url ? (
          <a className="fc-evidence__link" href={item.url} target="_blank" rel="noreferrer noopener">
            <ExternalLink size={14} aria-hidden />
            Open it
          </a>
        ) : null}
      </div>

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
        {/* biome-ignore lint/a11y/useSemanticElements: a fieldset can't lay out a toolbar row */}
        <div className="fc-vote" role="group" aria-label="Endorse or dispute">
          <Button
            size="sm"
            variant="ghost"
            icon={<ThumbsUp size={15} aria-hidden />}
            aria-pressed={item.my_vote === 1}
            disabled={!mayVote || pending}
            onClick={() => onVote(item.my_vote === 1 ? 0 : 1)}
          >
            Endorse
          </Button>
          <Button
            size="sm"
            variant="ghost"
            icon={<ThumbsDown size={15} aria-hidden />}
            aria-pressed={item.my_vote === -1}
            disabled={!mayVote || pending}
            onClick={() => onVote(item.my_vote === -1 ? 0 : -1)}
          >
            Dispute
          </Button>
          <span className="fc-vote__total">Support {supportOf(item.vote_total)}</span>
        </div>
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
      </div>
    </li>
  );
}
