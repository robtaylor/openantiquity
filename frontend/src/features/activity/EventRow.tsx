import {
  CircleDot,
  Eye,
  Footprints,
  type LucideIcon,
  MapPinPlus,
  Megaphone,
  MessageSquare,
  NotebookText,
  Paperclip,
  TrendingUp,
  UserPlus,
} from "lucide-react";
import { Fragment, type ReactNode, type Ref } from "react";
import { useNavigate } from "react-router";
import type { Meta } from "../../api/meta.js";
import { findingPath, useSelectedFinding } from "../findings/selection.js";
import { whereRef } from "../findings/square.js";
import type { ActivityFinding, ActivityKind } from "./api.js";
import { describeEvent, type EventFacts, type Part } from "./describe.js";
import { fullTime, whenWords } from "./time.js";
import "./activity.css";

const KIND_ICONS: Record<ActivityKind, LucideIcon> = {
  finding_created: MapPinPlus,
  tier_changed: TrendingUp,
  state_changed: CircleDot,
  observation_added: Eye,
  evidence_added: Paperclip,
  followup_logged: Footprints,
  comment_added: MessageSquare,
  mention_added: Megaphone,
  investigation_published: NotebookText,
  investigation_invitation: UserPlus,
};

/** The path of an investigation's page. */
export function investigationPath(publicId: string): string {
  return `/i/${encodeURIComponent(publicId)}`;
}

function Sentence({ parts }: { parts: readonly Part[] }) {
  return (
    <span className="fc-event__sentence">
      {parts.map((part, index) => {
        // The parts of one sentence never move, so their place is their key.
        const key = `${index}`;
        // Plain words stay text, so the spaces around a name are kept in what a screen reader is given.
        if (typeof part === "string") return <Fragment key={key}>{part}</Fragment>;
        if ("person" in part) return <strong key={key}>{part.person}</strong>;
        if ("finding" in part)
          return (
            <span key={key} className="fc-event__finding">
              {part.finding}
            </span>
          );
        return (
          <span key={key} className="fc-event__finding">
            {part.investigation}
          </span>
        );
      })}
    </span>
  );
}

export interface EventRowProps {
  meta: Meta;
  facts: EventFacts;
  createdAt: string;
  /** The investigation it opens, for an event about one rather than a finding. */
  investigation: string | null;
  /** Shown first on the second line, such as a "new" mark. */
  badge?: ReactNode;
  rowRef?: Ref<HTMLLIElement>;
  /** Told when the row is followed, before the app moves to it. */
  onOpen?: () => void;
  now?: number;
}

function isPlainClick(event: React.MouseEvent): boolean {
  return !(event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button !== 0);
}

/**
 * One thing that happened: what, in a sentence, and when. It opens its
 * finding, marked on the map as Explore marks it, or its investigation. A
 * finding whose place this viewer may not see is given by its square.
 */
export function EventRow({ meta, facts, createdAt, investigation, badge, rowRef, onOpen, now }: EventRowProps) {
  const navigate = useNavigate();
  const select = useSelectedFinding((state) => state.select);
  const Icon = KIND_ICONS[facts.kind];
  const finding: ActivityFinding | null = facts.finding;
  const href = finding ? findingPath(finding.public_id) : investigation ? investigationPath(investigation) : null;
  const square = finding?.location.obscured ? whereRef(finding.location) : null;

  const body = (
    <>
      <span className="fc-event__icon" aria-hidden="true">
        <Icon size={18} />
      </span>
      <span className="fc-event__text">
        <Sentence parts={describeEvent(meta, facts)} />
        <span className="fc-event__meta">
          {badge}
          <time dateTime={createdAt} title={fullTime(createdAt)}>
            {whenWords(createdAt, now)}
          </time>
          {square ? (
            <span>
              Somewhere in square <span className="fc-mono">{square}</span>
            </span>
          ) : null}
        </span>
      </span>
    </>
  );

  return (
    <li ref={rowRef} className="fc-event">
      {href ? (
        <a
          className="fc-event__row"
          href={href}
          onClick={(event) => {
            if (!isPlainClick(event)) return;
            event.preventDefault();
            onOpen?.();
            if (finding)
              select(finding.public_id, [finding.location.lon, finding.location.lat], finding.location.obscured);
            navigate(href);
          }}
        >
          {body}
        </a>
      ) : (
        <div className="fc-event__row">{body}</div>
      )}
    </li>
  );
}
