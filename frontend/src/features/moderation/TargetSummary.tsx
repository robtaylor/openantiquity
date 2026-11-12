import { ExternalLink } from "lucide-react";
import { Link } from "react-router";
import { safeHref } from "../../map/attribution.js";
import { formatDate } from "../finding/describe.js";
import { profilePath } from "../people/api.js";
import { roleWords } from "../people/roles.js";
import { Photo } from "../photos/Photo.js";
import type { Target } from "./api.js";
import { KIND_TITLES, targetState } from "./describe.js";

/** Where in the app a target can be seen, or null for one that has gone. */
export function targetPath(target: Target): string | null {
  if (!target.exists || target.ref === null) return null;
  if (target.kind === "user") return profilePath(target.ref);
  if (target.kind === "finding") return `/f/${encodeURIComponent(target.ref)}`;
  if (target.kind === "investigation") return `/i/${encodeURIComponent(target.ref)}`;
  return target.finding ? `/f/${encodeURIComponent(target.finding.public_id)}` : null;
}

/**
 * A reported or acted-on thing as it is now, with enough of it to decide:
 * what it is and where, who posted it, its words, its link and its photo,
 * and whether it is hidden or gone.
 */
export function TargetSummary({ target }: { target: Target }) {
  const path = targetPath(target);
  const state = targetState(target);
  const owner = target.owner;
  return (
    <div className="fc-mod-target">
      <p className="fc-mod-target__kind">
        <strong>{KIND_TITLES[target.kind]}</strong>
        {target.finding && target.kind !== "finding" ? (
          <>
            {" on "}
            <Link to={`/f/${encodeURIComponent(target.finding.public_id)}`}>{target.finding.title}</Link>
          </>
        ) : null}
        {target.created_at ? (
          <span className="fc-muted fc-mod-target__date"> · {formatDate(target.created_at)}</span>
        ) : null}
      </p>
      {owner ? (
        <p className="fc-mod-target__owner">
          {target.kind === "user" ? "" : "Posted by "}
          <Link to={profilePath(owner.handle)}>{owner.display_name}</Link>
          {owner.display_name !== owner.handle ? <span className="fc-muted"> @{owner.handle}</span> : null}
          <span className="fc-muted"> · {roleWords(owner.role).label}</span>
        </p>
      ) : null}
      {target.title && target.kind !== "user" ? <p className="fc-mod-target__title">{target.title}</p> : null}
      {target.body ? <blockquote className="fc-mod-target__body">{target.body}</blockquote> : null}
      {target.url ? (
        safeHref(target.url) ? (
          <a
            className="fc-mod-target__url"
            href={safeHref(target.url)}
            target="_blank"
            rel="noopener noreferrer nofollow ugc"
          >
            <ExternalLink size={14} aria-hidden />
            <span>{target.url}</span>
          </a>
        ) : (
          // Not a web address, so it is shown and never followed.
          <p className="fc-mod-target__url">
            <span className="fc-mono">{target.url}</span>
          </p>
        )
      ) : null}
      {target.photo_url ? (
        <Photo
          src={target.photo_url}
          alt={`The ${KIND_TITLES[target.kind].toLowerCase()}'s photo`}
          unavailable="Its photo can't be shown. Its file may have been refused or removed."
        />
      ) : null}
      {state ? <p className="fc-mod-target__state">{state}</p> : null}
      {path && target.kind !== "user" ? (
        <Link className="fc-mod-target__open" to={path}>
          See it in place
        </Link>
      ) : null}
    </div>
  );
}
