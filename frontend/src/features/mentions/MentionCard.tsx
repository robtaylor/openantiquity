import {
  Clapperboard,
  ExternalLink,
  FileText,
  Link2,
  type LucideIcon,
  MessageCircle,
  Mic,
  Newspaper,
  Radar,
  Radio,
  Trash2,
} from "lucide-react";
import { type ReactNode, useState } from "react";
import type { Meta } from "../../api/meta.js";
import { Button } from "../../ui/Button.js";
import { formatDate, labelOf } from "../finding/describe.js";
import { ReportButton } from "../reports/ReportButton.js";
import { ADDRESS_WITHHELD, mentionHref, mentionTitle, safeThumbnail, startWords } from "./describe.js";
import type { Mention } from "./types.js";
import "./mentions.css";

/** A pictogram for each kind, shown where there is no picture. A kind this build doesn't know gets a link. */
const KIND_ICONS: Record<string, LucideIcon> = {
  video: Clapperboard,
  article: Newspaper,
  podcast: Mic,
  paper: FileText,
  broadcast: Radio,
  social: MessageCircle,
};

/**
 * The picture a video's host gives, or a placeholder. It is fetched without a
 * referrer, so the host isn't told which finding was being looked at.
 */
export function MentionThumbnail({ kind, src }: { kind: string; src: string | null }) {
  const safe = safeThumbnail(src);
  const [failed, setFailed] = useState(false);
  const Icon = KIND_ICONS[kind] ?? Link2;
  if (safe === null || failed) {
    return (
      <span className="fc-mention__thumb fc-mention__thumb--none" aria-hidden="true">
        <Icon size={22} />
      </span>
    );
  }
  return (
    <img
      className="fc-mention__thumb"
      src={safe}
      alt=""
      referrerPolicy="no-referrer"
      loading="lazy"
      decoding="async"
      onError={() => setFailed(true)}
    />
  );
}

/** The title, linked to the mention at its start time, opening in a new tab. */
export function MentionLink({ mention }: { mention: Pick<Mention, "title" | "canonical_url" | "start_seconds"> }) {
  const href = mentionHref(mention);
  const title = mentionTitle(mention);
  if (mention.canonical_url === null) {
    return (
      <span className="fc-mention__title">
        {title} <span className="fc-mention__withheld">{ADDRESS_WITHHELD}</span>
      </span>
    );
  }
  if (href === null) return <span className="fc-mention__title">{title}</span>;
  return (
    <a className="fc-mention__title" href={href} target="_blank" rel="noreferrer noopener" referrerPolicy="no-referrer">
      {title}
      <ExternalLink size={13} aria-hidden />
      <span className="fc-visually-hidden"> (opens in a new tab)</span>
    </a>
  );
}

/** "Video · Time Team · 3 March 2024 · from 12:34". */
export function mentionByline(meta: Meta, mention: Mention): string {
  return [
    labelOf(meta.vocab.mention_kinds, mention.kind),
    mention.author_name,
    mention.published_at ? formatDate(mention.published_at) : null,
    mention.start_seconds ? `from ${startWords(mention.start_seconds)}` : null,
  ]
    .filter(Boolean)
    .join(" · ");
}

export interface MentionCardProps {
  meta: Meta;
  mention: Mention;
  /** The viewer added it, so they may remove it. */
  own?: boolean;
  /** Being saved or removed, so it can't be acted on. */
  pending?: boolean;
  onRemove?: () => void;
  /** What the mention is about, such as its finding in the recent feed. */
  children?: ReactNode;
}

/**
 * One mention: its picture, its title linked to it, what it is and who made
 * it, who added it here or that the channel scan found it, and its note.
 * Whoever added it may remove it, and anyone else may report it.
 */
export function MentionCard({ meta, mention, own = false, pending = false, onRemove, children }: MentionCardProps) {
  return (
    <article className="fc-mention" aria-busy={pending || undefined} aria-label={mentionTitle(mention)}>
      <MentionThumbnail kind={mention.kind} src={mention.thumbnail_url} />
      <div className="fc-mention__body">
        <MentionLink mention={mention} />
        <p className="fc-mention__meta">{mentionByline(meta, mention)}</p>
        {mention.note ? <p className="fc-mention__note">{mention.note}</p> : null}
        {mention.auto_detected ? (
          <p className="fc-mention__by fc-mention__auto">
            <Radar size={14} aria-hidden />
            Found automatically: its description links to this finding.
          </p>
        ) : (
          <p className="fc-mention__by">
            {pending
              ? "Saving…"
              : `Added by ${mention.added_by?.display_name ?? "a former member"} on ${formatDate(mention.created_at)}`}
          </p>
        )}
        {mention.hidden ? (
          <p className="fc-mention__hidden">
            {own
              ? "A moderator hid this. Only you and moderators can still see it."
              : "A moderator hid this. Only the person who added it and moderators can see it."}
          </p>
        ) : null}
        {own && onRemove ? (
          <div className="fc-mention__actions">
            <Button
              size="sm"
              variant="ghost"
              icon={<Trash2 size={14} aria-hidden />}
              disabled={pending}
              onClick={onRemove}
            >
              Remove
              {/* Told apart from the other cards' buttons in a list of them. */}
              <span className="fc-visually-hidden"> {mentionTitle(mention)}</span>
            </Button>
          </div>
        ) : !own && !pending ? (
          <div className="fc-mention__actions">
            <ReportButton target={{ kind: "mention", id: mention.id }} ownerHandle={mention.added_by?.handle ?? null} />
          </div>
        ) : null}
      </div>
      {/* Across the whole card, under the picture too, so a long title has room. */}
      {children ? <div className="fc-mention__about">{children}</div> : null}
    </article>
  );
}
