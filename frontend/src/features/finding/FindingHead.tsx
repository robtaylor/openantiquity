import { Eye, LogIn } from "lucide-react";
import { Link } from "react-router";
import { type Meta, viewTitle } from "../../api/meta.js";
import { usePointDetail } from "../../map/usePointDetail.js";
import { Avatar } from "../../ui/Avatar.js";
import { Button } from "../../ui/Button.js";
import { FeatureIcon } from "../../ui/featureIcons.js";
import { Meter } from "../../ui/Meter.js";
import { TierBadge } from "../../ui/TierBadge.js";
import { tierVar } from "../../ui/tokens.js";
import { useAccountUi } from "../account/requireAccount.js";
import { whereRef } from "../findings/square.js";
import {
  classLabel,
  distanceWords,
  formatDate,
  labelOf,
  SQUARE_SENTENCE,
  shownClass,
  stateReason,
} from "./describe.js";
import { seeAsFinderDid } from "./mapView.js";
import { ReportSlot } from "./Slots.js";
import type { FindingDetail } from "./types.js";

/** How the finder's view is described on its button's hint, such as "Composite, light from 315°". */
function viewSummary(meta: Meta, finding: FindingDetail): string {
  const view = finding.view_state;
  const parts: string[] = [];
  if (view.layer) parts.push(viewTitle(meta, view.layer));
  if (view.sun_azimuth !== null && view.sun_azimuth !== undefined) {
    parts.push(`light from ${Math.round(view.sun_azimuth)}°`);
  }
  if (view.pitch) parts.push("tilted into 3D");
  return parts.length > 0 ? `${parts.join(", ")}.` : "The layer and light they used.";
}

/**
 * The ladder's steps by name, below the meter, with the finding's own step
 * marked: each tick on the meter is one of these. The steps and their words
 * come from `/meta`.
 */
function Ladder({ meta, tierId, ruledOut }: { meta: Meta; tierId: string; ruledOut: boolean }) {
  const tiers = meta.vocab.tiers;
  return (
    <div className="fc-ladder">
      <p className="fc-finding__hint">
        The meter shows how far it has got up the ladder as others check it. Each mark on it is a step:
      </p>
      <ol className="fc-ladder__steps" aria-label="The ladder">
        {tiers.map((step) => {
          const current = !ruledOut && step.id === tierId;
          return (
            <li
              key={step.id}
              className={current ? "fc-ladder__step fc-ladder__step--current" : "fc-ladder__step"}
              aria-current={current ? "step" : undefined}
            >
              <span className="fc-ladder__dot" style={{ background: tierVar(step.id) }} aria-hidden />
              {step.label}
            </li>
          );
        })}
      </ol>
    </div>
  );
}

export interface FindingHeadProps {
  meta: Meta;
  finding: FindingDetail;
  signedIn: boolean;
  /** What just happened to the finding's step or state, for the live region. */
  change: string | null;
}

/**
 * The top of a finding's page: its step and confidence, its state when it
 * isn't open, who found it and when, what it is and when from, and where.
 * Someone who may not see the exact place sees the square and why.
 */
export function FindingHead({ meta, finding, signedIn, change }: FindingHeadProps) {
  const { assessment, location } = finding;
  const tier = { id: assessment.tier, label: labelOf(meta.vocab.tiers, assessment.tier) };
  const state = { id: assessment.state, label: labelOf(meta.vocab.states, assessment.state) };
  const reason = stateReason(meta, finding);
  const community = finding.answers_visible ? (assessment.tallies?.community_class ?? null) : null;
  const openSignIn = useAccountUi((ui) => ui.openSignIn);
  // Asked of the position this viewer is shown, so a square's finding is named from its square.
  const place = usePointDetail({ lng: location.lon, lat: location.lat }).detail?.place ?? null;

  return (
    <section className="fc-finding__head" aria-label="About this finding">
      <div className="fc-finding__badges">
        <span className="fc-finding__badge" key={`${tier.id}-${state.id}`}>
          <TierBadge tier={tier} state={state} />
        </span>
        <ReportSlot target={{ kind: "finding", id: finding.public_id }} ownerHandle={finding.author.handle} />
      </div>
      <Meter value={assessment.score} tiers={meta.vocab.tiers} tierId={tier.id} ruledOut={state.id === "ruled_out"} />
      <Ladder meta={meta} tierId={tier.id} ruledOut={state.id === "ruled_out"} />
      <p className="fc-finding__change" role="status" aria-live="polite">
        {change}
      </p>

      {reason ? (
        <div className={`fc-finding__state fc-finding__state--${state.id}`}>
          <strong>{state.label}</strong>
          <p>{reason}</p>
        </div>
      ) : null}

      <p className="fc-finding__byline">
        <Avatar name={finding.author.display_name} handle={finding.author.handle} size={24} />
        <span>
          Spotted by <Link to={`/u/${encodeURIComponent(finding.author.handle)}`}>{finding.author.display_name}</Link>{" "}
          on {formatDate(finding.created_at)}
        </span>
      </p>

      <dl className="fc-finding__facts">
        <div>
          <dt>Looks like</dt>
          <dd>
            <FeatureIcon classId={finding.feature_class} size={18} />
            {classLabel(meta, finding.feature_class)}
          </dd>
        </div>
        {community && shownClass(meta, community) !== shownClass(meta, finding.feature_class) ? (
          <div>
            <dt>Others think it's</dt>
            <dd>
              <FeatureIcon classId={community} size={18} />
              {classLabel(meta, community)}
            </dd>
          </div>
        ) : null}
        <div>
          <dt>Period</dt>
          <dd>{labelOf(meta.vocab.periods, finding.period)}</dd>
        </div>
        {place ? (
          <div>
            <dt>Near</dt>
            {/* A distance from the middle of a square would look more exact than the square is. */}
            <dd>{location.obscured ? place.name : `${place.name}, ${distanceWords(place.distance_m)}`}</dd>
          </div>
        ) : null}
        <div>
          <dt>{location.obscured ? "Square" : "Grid reference"}</dt>
          <dd className="fc-mono">{whereRef(location)}</dd>
        </div>
      </dl>

      {location.obscured ? (
        <div className="fc-finding__square">
          <p>You're seeing the one-kilometre square it is in, not the place itself. {SQUARE_SENTENCE}</p>
          {finding.sensitivity === "protected" && !signedIn ? (
            <Button size="sm" icon={<LogIn size={16} aria-hidden />} onClick={() => openSignIn()}>
              Sign in
            </Button>
          ) : null}
        </div>
      ) : (
        <div className="fc-finding__view">
          <Button size="sm" icon={<Eye size={16} aria-hidden />} onClick={() => seeAsFinderDid(meta, finding)}>
            See it as the finder did
          </Button>
          <span className="fc-finding__hint">{viewSummary(meta, finding)}</span>
        </div>
      )}

      {finding.description ? <p className="fc-finding__description">{finding.description}</p> : null}
    </section>
  );
}
