"""Findings, their evidence, votes, comments and follows, and keeping each finding assessed.

Every change that could move a finding (an answer, evidence, a vote, a
verification, an edit, a withdrawal) runs under a row lock on the finding:
`lock` takes `SELECT ... FOR UPDATE` before anything is read or written, then
`reassess` gathers every input, calls `confidence.assess`, stores the result,
records `tier_changed` and `state_changed` activity (which notifies followers),
and writes reputation awards. Two people answering at once are serialised by
the lock, so the second assessment always sees the first answer.

Anyone who contributes to a finding follows it, so they hear when it moves.

Who may contribute: answers, evidence and votes come only from someone who
sees the finding's exact position (`require_exact`), because nobody can check
a feature, or judge someone else's evidence for it, from a 1 km square.
Comments stay open to everyone signed in.

Positions: nothing here returns a position. Responses get one from
`schemas.findings.location_out`, which goes through `services.sensitivity`.
List queries choose the column by viewer in `sensitivity.visible_match_clause`, so a
signed-out visitor's filters touch `location_public` only, and the shape of an
open finding.

Services flush and never commit.
"""

from __future__ import annotations

import logging
import math
from collections.abc import Callable, Iterable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
from enum import StrEnum
from typing import Any

from geoalchemy2.shape import to_shape
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry
from sqlalchemy import (
    ColumnElement,
    Select,
    delete,
    func,
    or_,
    select,
    text,
    true,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from fieldclub import gridref
from fieldclub.errors import (
    BadRequestError,
    ConflictError,
    ForbiddenError,
    InvalidCursorError,
    NotFoundError,
    ValidationFailedError,
)
from fieldclub.errors import FindingNotFoundError as FindingNotFoundError
from fieldclub.models import (
    Comment,
    Evidence,
    EvidenceVote,
    Finding,
    FindingShapeChange,
    Follow,
    Media,
    Observation,
    Record,
    Source,
    User,
)
from fieldclub.models.common import point_lon_lat, to_db_geometry
from fieldclub.schemas.common import cursor_int, decode_cursor, int_from_cursor, is_bbox, paginate, web_url
from fieldclub.services import (
    activity,
    geo,
    ids,
    looked_at,
    reputation,
    sensitivity,
    shape_edits,
    shapes,
    text_positions,
)
from fieldclub.services.confidence import (
    NEW_PART_LOOK_M,
    SECOND_LOOK_CODES,
    VERIFIER_ROLES,
    Assessment,
    EvidenceInput,
    FindingInputs,
    ObservationInput,
    VoteInput,
    assess,
    counted_votes,
    load_assessment,
)
from fieldclub.vocab import (
    EVIDENCE_KINDS,
    FEATURE_CLASSES,
    MODERATOR_ROLES,
    ActivityKind,
    EvidenceGroup,
    EvidenceKind,
    FeatureClass,
    FindingState,
    NextStepCode,
    Outcome,
    Period,
    Relation,
    Role,
    Sensitivity,
    ShapeChangeKind,
    ShapeKind,
    Stance,
    Tier,
    tier_rank,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class PositionInTextError(ValidationFailedError):
    code = "position_in_text"
    message = (
        "A protected or restricted finding's title, description and links can't say where it is more "
        "closely than its 1 km square: take out the grid reference, coordinates, map link or three-word "
        "address."
    )


class NotFinderError(ForbiddenError):
    code = "not_finder"
    message = "Only the person who marked this finding can do that."


class LocationHiddenError(ForbiddenError):
    code = "location_hidden"
    message = "You can only answer, add evidence or vote on a finding whose exact position you can see."


class FindingClosedError(ConflictError):
    code = "finding_withdrawn"
    message = "This finding has been withdrawn, so it takes no more answers or evidence."


class EvidenceNotFoundError(NotFoundError):
    code = "evidence_not_found"
    message = "There's no evidence with that id."


class InvalidEvidenceError(ValidationFailedError):
    code = "invalid_evidence"
    message = "That evidence is missing something it needs, or has something it can't have."


class EvidenceForbiddenError(ForbiddenError):
    code = "evidence_forbidden"
    message = "Only the person who added this evidence can remove it. A moderator hides it instead."


class VoteNotAllowedError(ForbiddenError):
    code = "vote_not_allowed"
    message = "You can't vote on evidence you added, or on evidence about your own finding."


class VerifyNotAllowedError(ForbiddenError):
    code = "verify_not_allowed"
    message = (
        "Only an archaeologist or a moderator can verify official evidence, and not on their own finding "
        "or evidence they added."
    )


class CommentNotFoundError(NotFoundError):
    code = "comment_not_found"
    message = "There's no comment with that id."


class CommentForbiddenError(ForbiddenError):
    code = "comment_forbidden"
    message = "Only the person who wrote this comment can remove it. A moderator hides it instead."


class LocationRequiredError(BadRequestError):
    """A finding always has a point: one sent, or one the server places on its shape.

    `POST` and `PATCH` raise this one error, so the code has one status.
    """

    code = "location_required"
    message = "Mark the point, or draw a line or shape for the server to place it on."


# --------------------------------------------------------------------------
# Loading and locking
# --------------------------------------------------------------------------


def is_moderator(viewer: User | None) -> bool:
    active = sensitivity.active_viewer(viewer)
    return active is not None and Role(active.role) in MODERATOR_ROLES


def may_see_hidden(finding: Finding, viewer: User | None) -> bool:
    """A finding hidden by a moderator is seen only by moderators and its finder."""
    active = sensitivity.active_viewer(viewer)
    return active is not None and (active.has_id(finding.author_id) or is_moderator(active))


def may_see_hidden_comment(comment: Comment, viewer: User | None) -> bool:
    """A comment hidden by a moderator is seen only by moderators and its author."""
    active = sensitivity.active_viewer(viewer)
    return active is not None and (active.has_id(comment.user_id) or is_moderator(active))


def standing_evidence_clause() -> ColumnElement[bool]:
    """Evidence that is shown and counted: not deleted, not hidden, and not by a banned account.

    A banned person's evidence stops counting while the ban lasts, and leaves
    finding pages and exports. Lifting the ban restores it. Their answers and
    votes keep counting (Decision 0019). See `services.moderation`.
    """
    banned = select(User.id).where(User.banned_at.is_not(None))
    return Evidence.deleted_at.is_(None) & Evidence.hidden_at.is_(None) & Evidence.user_id.not_in(banned)


def normalise_public_id(public_id: str) -> str:
    """A finding's public id as `services.ids` writes it, or `FindingNotFoundError` for one it can't be."""
    normalised = ids.normalise(public_id)
    if normalised is None:
        raise FindingNotFoundError()
    return normalised


def _by_public_id(public_id: str) -> Select[Finding]:
    return select(Finding).where(Finding.public_id == normalise_public_id(public_id))


def get_finding(db: Session, public_id: str, viewer: User | None) -> Finding:
    """The finding with this public id, or `FindingNotFoundError`. Hidden ones only for those who may."""
    finding = db.scalar(_by_public_id(public_id))
    if finding is None or (finding.hidden_at is not None and not may_see_hidden(finding, viewer)):
        raise FindingNotFoundError()
    return finding


def lock(db: Session, finding: Finding) -> Finding:
    """Take the row lock on a finding and reload it. Every change that could move it starts here."""
    locked = db.scalars(
        select(Finding)
        .where(Finding.id == finding.id)
        .with_for_update()
        .execution_options(populate_existing=True)
    ).one()
    assert locked is finding, "the identity map should hand back the same object"
    return locked


def lock_finding(db: Session, public_id: str, viewer: User | None) -> Finding:
    return lock(db, get_finding(db, public_id, viewer))


def check_open(finding: Finding) -> None:
    if finding.state == FindingState.WITHDRAWN.value:
        raise FindingClosedError()


def check_finder(finding: Finding, actor: User) -> None:
    """Refuse anyone but the finder: editing and withdrawing are theirs alone."""
    if not actor.has_id(finding.author_id):
        raise NotFinderError()


def require_exact(finding: Finding, user: User) -> None:
    """Refuse a contribution from someone who sees the finding only as a 1 km square."""
    if not sensitivity.sees_exact(finding, user):
        raise LocationHiddenError()


def follow(db: Session, user: User, finding: Finding) -> None:
    """Follow a finding. Following it twice is harmless."""
    db.execute(
        insert(Follow)
        .values(user_id=user.id, finding_id=finding.id)
        .on_conflict_do_nothing(index_elements=["user_id", "finding_id"])
    )


def unfollow(db: Session, user: User, finding: Finding) -> None:
    db.execute(delete(Follow).where(Follow.user_id == user.id, Follow.finding_id == finding.id))


def is_following(db: Session, user: User | None, finding: Finding) -> bool:
    if user is None:
        return False
    return (
        db.scalar(select(Follow.user_id).where(Follow.user_id == user.id, Follow.finding_id == finding.id))
        is not None
    )


# --------------------------------------------------------------------------
# Assessing
# --------------------------------------------------------------------------

# Next steps that a second look can meet (`confidence.STEP_RULES`). The queue
# measures how many answers a finding needs only when every open step is one of these.
ANSWER_CODES = SECOND_LOOK_CODES
# The cap on `answers_to_next`, the largest smallint. The queue sorts a
# finding with no count after every stored one by using this.
ANSWERS_TO_NEXT_MAX = 32767


def answers_to_next(assessment: Assessment) -> int | None:
    """How many more members' second looks would move the finding up, or None when answers can't.

    One answer can meet several steps at once (say yes, name the class, clear
    the checks), so it is the largest number any one step needs. A trusted
    review counts as the members it would take instead.
    """
    # A look at a line's new part moves nobody up.
    steps = [step for step in assessment.next_steps if step.code is not NextStepCode.LOOK_AT_NEW_PART]
    if not steps or any(step.code not in ANSWER_CODES for step in steps):
        return None
    needed = []
    for step in steps:
        if step.code is NextStepCode.NEED_TRUSTED_REVIEW:
            assert step.weight_needed is not None, "a trusted-review step says how much weight it needs"
            needed.append(math.ceil(step.weight_needed - 1e-9))
        else:
            assert step.people is not None, f"{step.code} says how many people it needs"
            needed.append(step.people)
    return min(max(needed), ANSWERS_TO_NEXT_MAX)


def _votes(db: Session, evidence_ids: Sequence[int]) -> dict[int, list[VoteInput]]:
    """The votes on each item, each at the weight of the role it was given with, as the engine takes them.

    A vote keeps counting through its voter's ban, as an answer does, because
    an item gives its votes only as counts: a count that moved when a named
    person was banned would say how they voted (Decision 0019).
    """
    votes: dict[int, list[VoteInput]] = {}
    if not evidence_ids:
        return votes
    for evidence_id, user_id, value, role in db.execute(
        select(
            EvidenceVote.evidence_id, EvidenceVote.user_id, EvidenceVote.value, EvidenceVote.role_at_vote
        ).where(EvidenceVote.evidence_id.in_(evidence_ids))
    ).all():
        votes.setdefault(evidence_id, []).append(VoteInput(user_id=user_id, role=Role(role), value=value))
    return votes


def gather_inputs(db: Session, finding: Finding, state: FindingState | None = None) -> FindingInputs:
    """Everything the engine reads about a finding.

    Answers and votes count at the role they were given with, and keep
    counting through a ban: nobody who hasn't answered can name who answered
    what, so a score that moved when a named person's standing changed would
    say how that person answered (Decision 0019). The finder, evidence and
    verifications, which are named on the page, count at each person's
    current role, and a banned person's evidence and verifications stop counting.

    `state` is what to tell the engine, which honours only `withdrawn`. It
    defaults to the stored state. The length of the shape that lies beyond
    what second looks were given on (`looked_at.refresh_added`) asks for a
    look at it.
    """
    author_role = db.scalar(select(User.role).where(User.id == finding.author_id))
    assert author_role is not None, f"finding {finding.public_id} has no author"
    observations = tuple(
        ObservationInput(
            user_id=obs.user_id,
            role=Role(role),
            visible=obs.visible,  # pyright: ignore[reportArgumentType]
            feature_class=obs.feature_class,  # pyright: ignore[reportArgumentType]
            explanation=obs.explanation,  # pyright: ignore[reportArgumentType]
            not_modern=obs.not_modern,
            not_natural=obs.not_natural,
            not_artefact=obs.not_artefact,
        )
        for obs, role in db.execute(
            select(Observation, Observation.role_at_answer).where(
                Observation.finding_id == finding.id, Observation.withdrawn_at.is_(None)
            )
        ).all()
    )
    verifier = aliased(User)
    rows = db.execute(
        select(Evidence, User.role, verifier.role)
        .join(User, User.id == Evidence.user_id)
        .outerjoin(verifier, (verifier.id == Evidence.verified_by) & verifier.banned_at.is_(None))
        .where(Evidence.finding_id == finding.id)
    ).all()
    # Passed to the engine as deleted, so it neither counts nor credits them.
    gone = set(
        db.scalars(select(Evidence.id).where(Evidence.finding_id == finding.id, ~standing_evidence_clause()))
    )
    votes = _votes(db, [item.id for item, _, _ in rows])
    evidence = tuple(
        EvidenceInput(
            id=item.id,
            user_id=item.user_id,
            role=Role(role),
            kind=item.kind,  # pyright: ignore[reportArgumentType]
            stance=item.stance,  # pyright: ignore[reportArgumentType]
            outcome=item.outcome,  # pyright: ignore[reportArgumentType]
            relation=item.relation,  # pyright: ignore[reportArgumentType]
            deleted=item.id in gone,
            # A banned verifier's check stops counting with the rest of their work.
            verified_by=item.verified_by if verifier_role is not None else None,
            verifier_role=Role(verifier_role) if verifier_role is not None else None,
            votes=tuple(votes.get(item.id, ())),
        )
        for item, role, verifier_role in rows
    )
    return FindingInputs(
        author_id=finding.author_id,
        author_role=Role(author_role),
        feature_class=finding.feature_class,  # pyright: ignore[reportArgumentType]
        state=state if state is not None else FindingState(finding.state),
        observations=observations,
        evidence=evidence,
        added_since_looked_m=finding.added_since_looked_m,
    )


@dataclass(frozen=True)
class Reassessment:
    finding: Finding
    tier_before: Tier
    state_before: FindingState
    assessment: Assessment
    awards: tuple[reputation.Award, ...]

    @property
    def tier_after(self) -> Tier:
        return self.assessment.tier

    @property
    def state_after(self) -> FindingState:
        return self.assessment.state

    @property
    def moved_up(self) -> bool:
        return tier_rank(self.tier_after) > tier_rank(self.tier_before)


def reassess(
    db: Session,
    finding: Finding,
    actor: User | None,
    *,
    state: FindingState | None = None,
    quiet_for: User | None = None,
    evidence_id: int | None = None,
) -> Reassessment:
    """Recompute and store a finding's assessment. Call it holding `lock(db, finding)`.

    When the tier or state changes it records activity, which notifies
    followers, with `actor` as its actor. Pass None when the change came from
    a second look: a tier change credited to the person who just answered
    would tell every follower how they answered (Decision 0008). Pass that
    person as `quiet_for` instead, so they aren't notified of their own action.

    `evidence_id` names the evidence item whose adding, removal or
    verification caused the change, and a `tier_changed` event carries it,
    so the timeline can tell which follow-up moved a finding. A change a
    vote caused names no item, since it would say how the actor voted on
    it. A change a second look caused names nothing: no item, and no actor.

    Reputation awards are written every time: `reputation.awards` works out
    what is new and `record_awards` never pays twice.
    """
    assert evidence_id is None or actor is not None, "a change a second look caused names no evidence"
    old = load_assessment(finding.assessment)
    tier_before, state_before = Tier(finding.tier), FindingState(finding.state)
    new = assess(gather_inputs(db, finding, state))

    finding.tier = new.tier.value
    finding.state = new.state.value
    finding.state_reason = new.state_reason.value if new.state_reason is not None else None
    finding.confidence = new.score
    finding.community_class = new.community_class.value if new.community_class is not None else None
    finding.assessment = new.to_json()
    finding.open_steps = [step.code.value for step in new.next_steps]
    finding.answers_to_next = answers_to_next(new)
    # The engine leaves out the finder's own answer and deleted evidence.
    finding.observation_count = len(new.observations)
    finding.evidence_count = len(new.evidence)
    tier_moved = new.tier is not tier_before
    if tier_moved:
        finding.tier_changed_at = datetime.now(UTC)
    db.flush()

    if tier_moved:
        activity.record(
            db,
            ActivityKind.TIER_CHANGED,
            actor,
            finding,
            data={"from": tier_before.value, "to": new.tier.value}
            | ({"evidence_id": evidence_id} if evidence_id is not None else {}),
            quiet_for=quiet_for,
        )
    if new.state is not state_before:
        activity.record(
            db,
            ActivityKind.STATE_CHANGED,
            actor,
            finding,
            data={"from": state_before.value, "to": new.state.value, "reason": finding.state_reason},
            quiet_for=quiet_for,
        )
    recorded = reputation.record_awards(db, finding.id, reputation.awards(old, new))
    return Reassessment(finding, tier_before, state_before, new, recorded.awards)


def current_assessment(finding: Finding) -> Assessment:
    """The stored assessment. Every saved finding has one, written by `create_finding`."""
    stored = load_assessment(finding.assessment)
    assert stored is not None, f"finding {finding.public_id} has no current assessment"
    return stored


# --------------------------------------------------------------------------
# Creating and editing
# --------------------------------------------------------------------------

# The free text of a finding that is checked when it is saved, by request field.
_CHECKED_TEXT = ("title", "description")


def check_text_for_level(level: Sensitivity | str, texts: Mapping[str, str | None]) -> None:
    """Refuse a title or description that writes down a position, unless the finding is open.

    The text would otherwise say more than the 1 km square that everyone
    but members (or trusted people) may see (Decision 0005). `texts` maps
    each request field to its value. Text that slips through, written while
    the finding was open, is hidden on the way out (`sensitivity.visible_text`).
    """
    if Sensitivity(level) is Sensitivity.OPEN:
        return
    found = [name for name, text in texts.items() if text_positions.holds_position(text)]
    if found:
        raise PositionInTextError(
            details=[
                {
                    "field": f"body.{name}",
                    "message": f"The {name} gives a position finer than the 1 km square.",
                }
                for name in found
            ]
        )


_CLASS_LABELS = {info.id: info.label for info in FEATURE_CLASSES}
# As long as a title may be (`schemas.findings.TITLE_MAX`).
SUGGESTED_TITLE_MAX = 120


def suggested_title(feature_class: FeatureClass | str, lon: float, lat: float) -> str:
    """The title a finding takes when none is given: what it is, and its 1 km square.

    Such as "Enclosure in SU 10 69", or "Enclosure in V 26 24" on the Irish
    grid, spaced as the interface writes a square. Everyone may see the
    square, whatever the finding's level, so the title never says more than
    that (Decision 0005), and `services.text_positions` doesn't count a
    square as a position. A point on neither grid gets the class alone.
    """
    label = _CLASS_LABELS[FeatureClass(feature_class)]
    try:
        square = gridref.gridref_at(lon, lat, sensitivity.SQUARE_DIGITS).format()
    except gridref.GridRefError:
        return label
    title = f"{label} in {square}"[:SUGGESTED_TITLE_MAX]
    assert not text_positions.holds_position(title), f"{title!r} says more than the square"
    return title


PUBLIC_ID_CONSTRAINT = "uq_findings_public_id"


def create_finding(
    db: Session,
    author: User,
    *,
    feature_class: FeatureClass | str,
    location: Point | None = None,
    title: str | None = None,
    description: str | None = None,
    period: Period | str = Period.UNKNOWN,
    path: shapes.Path | None = None,
    outline: BaseGeometry | None = None,
    view_state: dict[str, Any] | None = None,
    requested_sensitivity: Sensitivity | str | None = None,
    client_ref: str | None = None,
) -> Finding:
    """Save a new finding, follow it for its finder, assess it, and record `finding_created`.

    It needs a point, a `path`, or both. Without a point the server chooses
    one on the shape (`shapes.derived_anchor`). An `outline`, still accepted
    for a release, is read as an all-corner path. The shape is held to the
    limits in `services.shapes` before anything is checked against the
    British Isles. Drawing it at the start is no change to it: the shape
    starts at revision 0.

    The public id is safe under concurrency (`ids.insert_with_public_id`). The
    starting level is `sensitivity.starting_sensitivity`. A `client_ref` is
    stored for `create_finding_once`, which is the way to pass one.
    """
    feature_class = FeatureClass(feature_class)
    shape = shape_edits.shape_from_request(path, outline)
    derived = location is None
    if location is None:
        if shape is None:
            raise LocationRequiredError()
        location = shapes.derived_anchor(shape)
    elif shape is not None:
        shapes.check_shape(shape.geometry, location)
    geo.check_in_british_isles(location)
    if shape is not None:
        geo.check_in_british_isles(shape.geometry)
    lon, lat = shape_edits.point_parts(location)
    level = sensitivity.starting_sensitivity(feature_class, requested_sensitivity, author)
    check_text_for_level(level, {"title": title, "description": description})
    nation = geo.nation_of(db, Point(lon, lat))

    finding = ids.insert_with_public_id(
        db,
        lambda public_id: Finding(
            public_id=public_id,
            author_id=author.id,
            title=title or suggested_title(feature_class, lon, lat),
            description=description,
            feature_class=feature_class.value,
            period=Period(period).value,
            location=to_db_geometry(location),
            location_derived=derived,
            **shape_edits.shape_columns(shape),
            sensitivity=level.value,
            view_state=view_state or {},
            nation=nation,
            client_ref=client_ref,
        ),
        PUBLIC_ID_CONSTRAINT,
    )

    follow(db, author, finding)
    activity.record(db, ActivityKind.FINDING_CREATED, author, finding)
    reassess(db, lock(db, finding), author)
    return finding


# First key of the two-part advisory lock that serialises one person's
# requests with one client reference. The second is a hash of both.
_CLIENT_REF_LOCK = 5_867_003
CLIENT_REF_MAX = 64


def create_finding_once(db: Session, author: User, client_ref: str, **fields: Any) -> tuple[Finding, bool]:
    """The finding `author` made with `client_ref`, or a new one made with `fields`, and whether it is new.

    A draft can be sent twice, or twice at once from two tabs. Both requests
    take a transaction-level advisory lock on the person and the reference
    before looking, so the second waits until the first commits and then
    finds its finding. The unique index on the two columns backs this up.
    What the second request says is ignored: the reference names the draft,
    and the draft was saved.
    """
    assert 1 <= len(client_ref) <= CLIENT_REF_MAX, "a client reference is 1 to 64 characters"
    db.execute(
        text("SELECT pg_advisory_xact_lock(:namespace, hashtext(:key))"),
        {"namespace": _CLIENT_REF_LOCK, "key": f"{author.id}:{client_ref}"},
    )
    existing = db.scalar(
        select(Finding).where(Finding.author_id == author.id, Finding.client_ref == client_ref)
    )
    if existing is not None:
        return existing, False
    return create_finding(db, author, client_ref=client_ref, **fields), True


_EDITABLE = frozenset(
    {
        "location",
        "feature_class",
        "title",
        "description",
        "period",
        "path",
        "path_revision",
        "outline",
        "view_state",
    }
)


def update_finding(db: Session, finding: Finding, actor: User, changes: dict[str, Any]) -> Finding:
    """Apply the finder's edits. Hold the lock. Keys are `_EDITABLE`; values are already parsed.

    A move keeps `grid_ref`, `nation` and the public position in step. A new
    feature class can raise the level (`sensitivity.level_after_class_change`,
    applied on save) and is reassessed, because the finder's class counts.
    A title that is still the `suggested_title` follows a move or a new class
    when no title is sent, so it never names a square the finding has left.

    A `path` (or an `outline`, read as one) with its `path_revision` goes to
    `shape_edits.change_shape`, with the finder as the one who made the
    change. When that moves the length lying beyond what was looked at, the
    finding is reassessed, which can only change its open steps. An
    extension, or a reshape of an open line that leaves it an open line at
    least `confidence.NEW_PART_LOOK_M` longer, records `shape_extended`,
    which tells the followers. The length before is
    `shape_edits.stored_length`, which measures an old outline the backfill
    hasn't reached.
    """
    check_finder(finding, actor)
    unknown = set(changes) - _EDITABLE
    assert not unknown, f"not editable: {sorted(unknown)}"
    before = point_lon_lat(finding.location)
    suggested = finding.title == suggested_title(finding.feature_class, *before)
    placed = "location" in changes
    location: Point = changes.get("location") or Point(before)
    if placed:
        geo.check_in_british_isles(location)

    changed_shape = False
    if "path" in changes or "outline" in changes:
        added_before = (finding.added_since_looked_m, finding.added_view)
        line_before = (
            shape_edits.stored_length(finding) if shape_edits.stored_kind(finding) is ShapeKind.LINE else None
        )
        kind = shape_edits.change_shape(
            db,
            finding,
            actor,
            path=changes.get("path"),
            outline=changes.get("outline"),
            revision=changes.get("path_revision"),
            placed=location if placed else None,
        )
        changed_shape = kind is not None
        if (finding.added_since_looked_m, finding.added_view) != added_before:
            # Only so that the finding asks, or stops asking, for a look at
            # the new part: nothing the ladder weighs has changed.
            db.flush()
            result = reassess(db, finding, actor)
            if result.tier_after is not result.tier_before:
                # Only an assessment stored before the engine last changed can move here.
                logger.warning(
                    "Finding %s moved from %s on a change of shape", finding.public_id, result.tier_before
                )
        # A point nudged and 20 km added is a reshape to the classifier and an
        # extension to everyone else, so the followers are told of that too.
        # Only a line is carried on: an area's longer edge isn't news of that.
        carried_on = (
            kind is ShapeChangeKind.RESHAPED
            and line_before is not None
            and finding.shape_kind == ShapeKind.LINE
            and finding.shape_length_m is not None
            and finding.shape_length_m - line_before >= NEW_PART_LOOK_M
        )
        if kind is ShapeChangeKind.EXTENDED or carried_on:
            activity.record(db, ActivityKind.SHAPE_EXTENDED, actor, finding)
    if placed and not changed_shape:
        if finding.outline is not None:
            shapes.check_shape(to_shape(finding.outline), location)
        else:
            looked_at.check(db, finding, location)
        shape_edits.move_anchor(db, finding, location)
    if placed:
        finding.location_derived = False
    location = Point(point_lon_lat(finding.location))
    moved = shape_edits.point_parts(location) != before

    for name in ("title", "view_state"):
        if changes.get(name) is not None:
            setattr(finding, name, changes[name])
    if "description" in changes:
        finding.description = changes["description"]
    if changes.get("period") is not None:
        finding.period = Period(changes["period"]).value
    class_changed = False
    if changes.get("feature_class") is not None and changes["feature_class"] != finding.feature_class:
        finding.feature_class = FeatureClass(changes["feature_class"]).value
        class_changed = True
    if suggested and changes.get("title") is None and (moved or class_changed):
        finding.title = suggested_title(finding.feature_class, *shape_edits.point_parts(location))
    level_before = finding.sensitivity
    db.flush()
    # The flush applies a level a new class raises. A raised level checks the
    # text kept as well as the text sent.
    raised = finding.sensitivity != level_before
    checked = [name for name in _CHECKED_TEXT if raised or name in changes]
    check_text_for_level(finding.sensitivity, {name: getattr(finding, name) for name in checked})
    if moved:
        activity.relocate(db, finding)
    if class_changed:
        reassess(db, finding, actor)
    return finding


def check_may_withdraw(finding: Finding, actor: User) -> None:
    check_finder(finding, actor)
    check_open(finding)


def withdraw_finding(db: Session, finding: Finding, actor: User) -> Reassessment:
    """The finder takes the finding back. Hold the lock."""
    check_may_withdraw(finding, actor)
    return reassess(db, finding, actor, state=FindingState.WITHDRAWN)


# --------------------------------------------------------------------------
# Lists
# --------------------------------------------------------------------------


class FindingSort(StrEnum):
    NEWEST = "newest"
    OLDEST = "oldest"
    CONFIDENCE = "confidence"
    UPDATED = "updated"


@dataclass(frozen=True)
class FindingFilters:
    # West, south, east, north in degrees. Matched against the position the viewer may see.
    bbox: tuple[float, float, float, float] | None = None
    tier: tuple[Tier, ...] = ()
    state: tuple[FindingState, ...] = ()
    feature_class: tuple[FeatureClass, ...] = ()
    author: str | None = None
    q: str | None = None
    sort: FindingSort = FindingSort.NEWEST

    def __post_init__(self) -> None:
        assert self.bbox is None or is_bbox(self.bbox), "bbox runs west to east and south to north"


def shown_clause(hidden_at: Any, owner_id: Any, viewer: User | None) -> ColumnElement[bool]:
    """Rows a moderator hasn't hidden, or that this viewer still sees: moderators, and the row's owner.

    The one rule for hidden findings, comments, mentions and investigations in
    a query. `hidden_at` and `owner_id` are the table's columns.
    """
    if is_moderator(viewer):
        return true()
    active = sensitivity.active_viewer(viewer)
    if active is None:
        return hidden_at.is_(None)
    return or_(hidden_at.is_(None), owner_id == active.id)


def not_hidden_clause(viewer: User | None) -> ColumnElement[bool]:
    """Findings that aren't hidden from this viewer: see `may_see_hidden`."""
    return shown_clause(Finding.hidden_at, Finding.author_id, viewer)


def _escape_like(text: str) -> str:
    return text.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


# Each sort's column, whether it runs descending, and how a cursor's value for it is read back.
_SORT_COLUMNS: dict[FindingSort, tuple[Any, bool, Callable[[Any], Any]]] = {
    FindingSort.NEWEST: (Finding.created_at, True, datetime.fromisoformat),
    FindingSort.OLDEST: (Finding.created_at, False, datetime.fromisoformat),
    FindingSort.CONFIDENCE: (Finding.confidence, True, cursor_int),
    FindingSort.UPDATED: (Finding.updated_at, True, datetime.fromisoformat),
}


def findings_query(viewer: User | None, filters: FindingFilters) -> Select[Finding]:
    """The findings this viewer may list, filtered and sorted. No cursor or limit."""
    query = select(Finding).where(not_hidden_clause(viewer))
    if filters.bbox is not None:
        query = query.where(sensitivity.visible_match_clause(viewer, geo.envelope(filters.bbox)))
    if filters.tier:
        query = query.where(Finding.tier.in_([tier.value for tier in filters.tier]))
    if filters.state:
        query = query.where(Finding.state.in_([state.value for state in filters.state]))
    else:
        query = query.where(Finding.state != FindingState.WITHDRAWN.value)
    if filters.feature_class:
        query = query.where(Finding.feature_class.in_([cls.value for cls in filters.feature_class]))
    if filters.author is not None:
        query = query.join(User, User.id == Finding.author_id).where(
            User.handle == filters.author, User.deleted_at.is_(None)
        )
    if filters.q:
        pattern = f"%{_escape_like(filters.q)}%"
        # Someone who doesn't see a finding exactly searches its title with
        # positions hidden, or a search could read one out a figure at a time.
        exact = sensitivity.as_sql(sensitivity.sees_exact_clause(viewer))
        query = query.where(
            or_(
                exact & Finding.title.ilike(pattern, escape="\\"),
                ~exact & Finding.title_public.ilike(pattern, escape="\\"),
                Finding.public_id == filters.q.upper(),
            )
        )
    column, descending, _ = _SORT_COLUMNS[filters.sort]
    order = (column.desc(), Finding.id.desc()) if descending else (column.asc(), Finding.id.asc())
    return query.order_by(*order)


def _cursor_key(finding: Finding, sort: FindingSort) -> list[Any]:
    column, _, _ = _SORT_COLUMNS[sort]
    value = getattr(finding, column.key)
    return [value.isoformat() if isinstance(value, datetime) else value, finding.id]


def _after_cursor(query: Select[Finding], sort: FindingSort, cursor: str) -> Select[Finding]:
    value, last_id = decode_cursor(cursor, 2)
    column, descending, parse = _SORT_COLUMNS[sort]
    last_id = cursor_int(last_id)
    try:
        typed = parse(value)
    except (TypeError, ValueError):
        raise InvalidCursorError() from None
    key = tuple_(column, Finding.id)
    return query.where(key < (typed, last_id) if descending else key > (typed, last_id))


@dataclass(frozen=True)
class FindingPage:
    findings: list[Finding]
    next_cursor: str | None


def users_by_id(db: Session, user_ids: Iterable[int]) -> dict[int, User]:
    wanted = set(user_ids)
    if not wanted:
        return {}
    return {user.id: user for user in db.scalars(select(User).where(User.id.in_(wanted)))}


def list_findings(
    db: Session, viewer: User | None, filters: FindingFilters, *, limit: int, cursor: str | None = None
) -> FindingPage:
    """One page of findings for this viewer. Callers that show authors load them with `users_by_id`."""
    query = findings_query(viewer, filters)
    if cursor is not None:
        query = _after_cursor(query, filters.sort, cursor)
    rows = db.scalars(query.limit(limit + 1)).all()
    items, next_cursor = paginate(rows, limit, lambda finding: _cursor_key(finding, filters.sort))
    return FindingPage(items, next_cursor)


# --------------------------------------------------------------------------
# Evidence
# --------------------------------------------------------------------------

FIELD_KINDS = frozenset(info.id for info in EVIDENCE_KINDS if info.group is EvidenceGroup.FIELD)
DATED_KINDS = frozenset({EvidenceKind.FIELD_VISIT, EvidenceKind.GEOPHYSICS, EvidenceKind.EXCAVATION})
OFFICIAL_KINDS = frozenset(info.id for info in EVIDENCE_KINDS if info.group is EvidenceGroup.OFFICIAL)
RECORD_KINDS = frozenset({EvidenceKind.RECORD_LINK, EvidenceKind.HER_RECORD, EvidenceKind.DESIGNATION})
MEDIA_KINDS = frozenset(
    {EvidenceKind.AERIAL, EvidenceKind.HISTORIC_MAP, EvidenceKind.PHOTO, EvidenceKind.FIELD_VISIT}
)
CITED_KINDS = frozenset({EvidenceKind.HISTORIC_MAP, EvidenceKind.DOCUMENT, EvidenceKind.PUBLICATION})


@dataclass(frozen=True)
class EvidenceFields:
    """What someone sends to add evidence. Which fields each kind needs is `check_evidence_fields`."""

    kind: EvidenceKind
    stance: Stance = Stance.SUPPORTS
    title: str | None = None
    note: str | None = None
    url: str | None = None
    record_id: int | None = None
    source_key: str | None = None
    reference: str | None = None
    relation: Relation | None = None
    media_id: int | None = None
    view: dict[str, Any] | None = None
    occurred_on: date | None = None
    organisation: str | None = None
    outcome: Outcome | None = None


def check_evidence_fields(db: Session, user: User, fields: EvidenceFields, *, today: date) -> None:
    """Refuse evidence that lacks what its kind needs or carries what it can't.

    A record link points at a stored record by `record_id`, or at a live or
    linked one by `reference` (its identifier) and `url` (its address), with
    an optional `source_key`. Decision 0007: for a record we don't store, we
    keep the identifier and address and nothing else, so no title.
    """
    kind = fields.kind
    if (fields.relation is not None) != (kind is EvidenceKind.RECORD_LINK):
        raise InvalidEvidenceError("A heritage record link needs a relation, and only a record link has one.")
    if fields.outcome is not None and kind not in FIELD_KINDS:
        raise InvalidEvidenceError("Only a site visit, ground photo, survey or excavation has an outcome.")
    if kind in DATED_KINDS and (fields.outcome is None or fields.occurred_on is None):
        raise InvalidEvidenceError("Say when it happened and what it found.")
    if fields.occurred_on is not None and fields.occurred_on > today:
        raise InvalidEvidenceError("The date can't be in the future.")
    if (fields.view is not None) != (kind is EvidenceKind.LIDAR_VIEW):
        raise InvalidEvidenceError("A LIDAR view needs the view, and only a LIDAR view has one.")
    if fields.record_id is not None and kind not in RECORD_KINDS:
        raise InvalidEvidenceError("Only a record link, an HER entry or a designation points at a record.")
    if fields.source_key is not None and not (kind is EvidenceKind.RECORD_LINK and fields.record_id is None):
        raise InvalidEvidenceError("A source is given only for a link to a record we don't store.")
    if fields.media_id is not None and kind not in MEDIA_KINDS:
        raise InvalidEvidenceError("Only photos, maps and visit reports carry an uploaded image.")

    if kind is EvidenceKind.RECORD_LINK:
        if fields.title is not None:
            raise InvalidEvidenceError("A record link takes its name from the record, so it has no title.")
        if fields.record_id is None and (fields.reference is None or fields.url is None):
            raise InvalidEvidenceError(
                "Link a stored record, or give the record's identifier and its address."
            )
        if fields.record_id is not None and (fields.reference is not None or fields.url is not None):
            raise InvalidEvidenceError("A stored record already has its identifier and address.")
    if kind in (EvidenceKind.HER_RECORD, EvidenceKind.DESIGNATION) and not (
        fields.record_id or fields.reference
    ):
        raise InvalidEvidenceError("Give the record or its reference number.")
    if kind is EvidenceKind.PHOTO and fields.media_id is None:
        raise InvalidEvidenceError("A ground photo needs the photo.")
    if kind is EvidenceKind.AERIAL and fields.media_id is None and fields.url is None:
        raise InvalidEvidenceError("Link the aerial photo or upload it.")
    if kind in CITED_KINDS and not (fields.title or fields.url or fields.reference):
        raise InvalidEvidenceError("Say which map, book or paper it is: a title, a link or a reference.")

    if fields.record_id is not None and db.get(Record, fields.record_id) is None:
        raise InvalidEvidenceError("There's no stored record with that id.")
    if fields.source_key is not None and db.get(Source, fields.source_key) is None:
        raise InvalidEvidenceError("There's no source with that key.")
    if fields.media_id is not None:
        media = db.get(Media, fields.media_id)
        if media is None or not user.has_id(media.user_id):
            raise InvalidEvidenceError("Attach a photo you uploaded yourself.")


def check_may_add_evidence(finding: Finding, user: User) -> None:
    """Refuse evidence that `add_evidence` refuses whatever it holds."""
    check_open(finding)
    require_exact(finding, user)


def add_evidence(
    db: Session, finding: Finding, user: User, fields: EvidenceFields
) -> tuple[Evidence, Reassessment]:
    """Add evidence to a finding and reassess it. Hold the lock.

    Evidence that points at a stored record also keeps the record's
    identifier, address and source, as a link to a record we don't store
    would (Decision 0007). A full ingest deletes a record its source no
    longer has, which empties `record_id`, and the evidence stays a working
    reference.
    """
    check_may_add_evidence(finding, user)
    check_evidence_fields(db, user, fields, today=datetime.now(UTC).date())
    # A link that says where a protected finding is would say it to everyone who
    # may see the evidence's title. Readers who see only the square never get
    # the address in any case (`sensitivity.visible_url`).
    check_text_for_level(finding.sensitivity, {"url": fields.url})
    data: dict[str, Any] = {}
    if fields.view is not None:
        data["view"] = fields.view
    reference, url, source_key = fields.reference, fields.url, fields.source_key
    if fields.record_id is not None:
        record = db.get(Record, fields.record_id)
        assert record is not None, "check_evidence_fields refuses a record that isn't stored"
        reference, source_key = reference or record.external_id, record.source_key
        # A record stored before ingest checked its address is checked again here.
        url = url or web_url(record.url)
    if source_key is not None:
        data["source_key"] = source_key
    evidence = Evidence(
        finding_id=finding.id,
        user_id=user.id,
        kind=fields.kind.value,
        stance=fields.stance.value,
        title=fields.title,
        note=fields.note,
        url=url,
        record_id=fields.record_id,
        relation=fields.relation.value if fields.relation is not None else None,
        media_id=fields.media_id,
        occurred_on=fields.occurred_on,
        organisation=fields.organisation,
        reference=reference,
        outcome=fields.outcome.value if fields.outcome is not None else None,
        data=data or None,
    )
    db.add(evidence)
    db.flush()
    follow(db, user, finding)
    kind = (
        ActivityKind.FOLLOWUP_LOGGED
        if fields.kind in FIELD_KINDS | OFFICIAL_KINDS
        else ActivityKind.EVIDENCE_ADDED
    )
    activity.record(db, kind, user, finding, data={"evidence_id": evidence.id, "kind": evidence.kind})
    return evidence, reassess(db, finding, user, evidence_id=evidence.id)


def get_evidence(db: Session, evidence_id: int, viewer: User | None) -> tuple[Evidence, Finding]:
    """A standing evidence item and its finding, or `EvidenceNotFoundError`."""
    evidence = db.get(Evidence, evidence_id)
    if evidence is None or evidence.deleted_at is not None:
        raise EvidenceNotFoundError()
    finding = db.get(Finding, evidence.finding_id)
    assert finding is not None, "evidence always belongs to a finding"
    if finding.hidden_at is not None and not may_see_hidden(finding, viewer):
        raise EvidenceNotFoundError()
    if not is_moderator(viewer) and not db.scalar(
        select(standing_evidence_clause()).where(Evidence.id == evidence.id)
    ):
        # Hidden, or by a banned account: gone for everyone but moderators.
        raise EvidenceNotFoundError()
    return evidence, finding


def _locked_evidence(db: Session, evidence_id: int, user: User) -> tuple[Evidence, Finding]:
    evidence, finding = get_evidence(db, evidence_id, user)
    lock(db, finding)
    db.refresh(evidence)
    if evidence.deleted_at is not None:
        raise EvidenceNotFoundError()
    return evidence, finding


def delete_evidence(db: Session, evidence_id: int, user: User) -> Reassessment:
    """Remove evidence, by its contributor. It is kept, marked deleted.

    A moderator removes someone else's evidence by hiding it
    (`services.moderation.set_hidden`), which needs a reason and is logged.
    """
    evidence, finding = _locked_evidence(db, evidence_id, user)
    if not user.has_id(evidence.user_id):
        raise EvidenceForbiddenError()
    evidence.deleted_at = datetime.now(UTC)
    db.flush()
    return reassess(db, finding, user, evidence_id=evidence.id)


def check_may_vote(finding: Finding, evidence: Evidence, user: User) -> None:
    check_open(finding)
    require_exact(finding, user)
    if user.has_id(evidence.user_id) or user.has_id(finding.author_id):
        raise VoteNotAllowedError()


def vote(db: Session, evidence_id: int, user: User, value: int) -> Reassessment:
    """Endorse (+1), object to (-1) or take back (0) a vote on evidence, and reassess."""
    assert value in (-1, 0, 1), "a vote is -1, 0 or 1"
    evidence, finding = _locked_evidence(db, evidence_id, user)
    check_may_vote(finding, evidence, user)
    if value == 0:
        db.execute(
            delete(EvidenceVote).where(
                EvidenceVote.evidence_id == evidence.id, EvidenceVote.user_id == user.id
            )
        )
    else:
        db.execute(
            insert(EvidenceVote)
            .values(evidence_id=evidence.id, user_id=user.id, value=value, role_at_vote=user.role)
            .on_conflict_do_update(
                index_elements=["evidence_id", "user_id"], set_={"value": value, "role_at_vote": user.role}
            )
        )
        follow(db, user, finding)
    # A step names no item here: with the voter as actor it would say who voted on which
    # item and, from the step's direction, how, which the item itself gives only as counts.
    return reassess(db, finding, user)


def check_may_verify(finding: Finding, user: User, evidence: Evidence | None = None) -> None:
    """Refuse a verification `verify` refuses: of `evidence`, or of any item on the finding when None."""
    check_open(finding)
    if (
        Role(user.role) not in VERIFIER_ROLES
        or user.has_id(finding.author_id)
        or (evidence is not None and user.has_id(evidence.user_id))
    ):
        raise VerifyNotAllowedError()
    require_exact(finding, user)
    if evidence is not None and EvidenceKind(evidence.kind) not in OFFICIAL_KINDS:
        raise InvalidEvidenceError(
            "Only an HER entry, a designation or a publication is verified.", code="not_official"
        )


def verify(db: Session, evidence_id: int, user: User) -> Reassessment:
    """An archaeologist or moderator verifies an official item, which can put a finding on record.

    Verifying is a second person's check, so neither the finder nor the
    person who added the item can do it.
    """
    evidence, finding = _locked_evidence(db, evidence_id, user)
    check_may_verify(finding, user, evidence)
    if evidence.verified_by is None:
        evidence.verified_by = user.id
        evidence.verified_at = datetime.now(UTC)
        db.flush()
    follow(db, user, finding)
    return reassess(db, finding, user, evidence_id=evidence.id)


def _standing_verifier(people: Mapping[int, User], user_id: int | None) -> User | None:
    verifier = people.get(user_id) if user_id is not None else None
    return verifier if verifier is not None and not verifier.is_banned else None


@dataclass(frozen=True)
class EvidenceView:
    evidence: Evidence
    contributor: User
    verifier: User | None
    media: Media | None
    my_vote: int | None
    # Counted from the votes as they are now, as the engine counts them, so a
    # stored assessment written before it kept the disputers can't be stale.
    endorsements: int
    disputes: int


def evidence_for(
    db: Session, finding: Finding, viewer: User | None, known: Mapping[int, User] | None = None
) -> list[EvidenceView]:
    """A finding's standing evidence, oldest first, with what a response needs.

    `known` holds users already loaded, such as those named in the credits,
    so only the rest are fetched. A banned verifier isn't named, because
    their check stops counting while the ban lasts (`gather_inputs`).
    """
    items = db.scalars(
        select(Evidence)
        .where(Evidence.finding_id == finding.id, standing_evidence_clause())
        .order_by(Evidence.created_at, Evidence.id)
    ).all()
    people = dict(known or {})
    named = {e.user_id for e in items} | {e.verified_by for e in items if e.verified_by is not None}
    people.update(users_by_id(db, named - people.keys()))
    media_ids = [e.media_id for e in items if e.media_id is not None]
    media = {m.id: m for m in db.scalars(select(Media).where(Media.id.in_(media_ids)))} if media_ids else {}
    votes = _votes(db, [e.id for e in items])
    mine = {
        evidence_id: vote.value
        for evidence_id, cast in votes.items()
        for vote in cast
        if viewer is not None and vote.user_id == viewer.id
    }

    def counted(e: Evidence, sign: int) -> int:
        return sum(v.value == sign for v in counted_votes(votes.get(e.id, ()), e.user_id, finding.author_id))

    return [
        EvidenceView(
            evidence=e,
            contributor=people[e.user_id],
            verifier=_standing_verifier(people, e.verified_by),
            media=media.get(e.media_id) if e.media_id is not None else None,
            my_vote=mine.get(e.id),
            endorsements=counted(e, 1),
            disputes=counted(e, -1),
        )
        for e in items
    ]


# --------------------------------------------------------------------------
# Comments
# --------------------------------------------------------------------------


def add_comment(
    db: Session, finding: Finding, user: User, body: str, parent_id: int | None = None
) -> Comment:
    """Post a comment, follow the finding, and tell its followers."""
    if parent_id is not None:
        parent = db.get(Comment, parent_id)
        if parent is None or parent.finding_id != finding.id:
            raise CommentNotFoundError("The comment you replied to isn't on this finding.")
    comment = Comment(finding_id=finding.id, user_id=user.id, body=body, parent_id=parent_id)
    db.add(comment)
    db.flush()
    db.execute(
        update(Finding).where(Finding.id == finding.id).values(comment_count=Finding.comment_count + 1)
    )
    follow(db, user, finding)
    activity.record(db, ActivityKind.COMMENT_ADDED, user, finding, data={"comment_id": comment.id})
    db.refresh(finding, ["comment_count"])
    return comment


def delete_comment(db: Session, comment_id: int, user: User) -> Comment:
    """Remove a comment, by its author. Replies keep their place.

    A moderator removes someone else's comment by hiding it
    (`services.moderation.set_hidden`), which needs a reason and is logged.
    """
    comment = db.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise CommentNotFoundError()
    finding = db.get(Finding, comment.finding_id)
    assert finding is not None, "a comment always belongs to a finding"
    if finding.hidden_at is not None and not may_see_hidden(finding, user):
        raise CommentNotFoundError()
    if comment.hidden_at is not None and not may_see_hidden_comment(comment, user):
        raise CommentNotFoundError()
    if not user.has_id(comment.user_id):
        raise CommentForbiddenError()
    comment.deleted_at = datetime.now(UTC)
    if comment.hidden_at is None:
        # Hiding already took a hidden comment out of the count.
        db.execute(
            update(Finding)
            .where(Finding.id == finding.id)
            .values(comment_count=func.greatest(Finding.comment_count - 1, 0))
        )
    db.flush()
    return comment


@dataclass(frozen=True)
class CommentPage:
    comments: list[Comment]
    authors: dict[int, User]
    next_cursor: str | None


def list_comments(db: Session, finding: Finding, *, limit: int, cursor: str | None = None) -> CommentPage:
    """A finding's comments, oldest first. Deleted ones stay as placeholders, so threads keep their shape.

    So do hidden ones: `CommentOut.build` shows a hidden comment as removed to
    everyone but moderators and its author.
    """
    query = select(Comment).where(Comment.finding_id == finding.id).order_by(Comment.id)
    if cursor is not None:
        query = query.where(Comment.id > int_from_cursor(cursor))
    rows: Sequence[Comment] = db.scalars(query.limit(limit + 1)).all()
    items, next_cursor = paginate(rows, limit, lambda comment: [comment.id])
    return CommentPage(items, users_by_id(db, (c.user_id for c in items)), next_cursor)


# --------------------------------------------------------------------------
# A finding's page
# --------------------------------------------------------------------------


def my_observation(db: Session, finding: Finding, viewer: User | None) -> Observation | None:
    if viewer is None:
        return None
    return db.scalar(
        select(Observation).where(Observation.finding_id == finding.id, Observation.user_id == viewer.id)
    )


def answers_visible(finding: Finding, viewer: User | None, mine: Observation | None) -> bool:
    """Whether `viewer` may see other people's answers (Decision 0008).

    The finder may, and so may someone whose own answer, `mine`, has been
    revealed, even if they later took it back. An answer waiting for its
    detail hasn't been: until its reveal its author is still someone who
    hasn't seen the answers.
    """
    active = sensitivity.active_viewer(viewer)
    if active is None:
        return False
    assert mine is None or active.has_id(mine.user_id), "`mine` is the viewer's own answer"
    return active.has_id(finding.author_id) or (mine is not None and mine.revealed_at is not None)


@dataclass(frozen=True)
class FindingView:
    """Everything a finding's page shows, loaded for one viewer."""

    finding: Finding
    author: User
    assessment: Assessment
    evidence: list[EvidenceView]
    # Everyone named in the credits.
    people: dict[int, User]
    answers_visible: bool
    my_observation: Observation | None
    following: bool
    # The nation as this viewer may know it (`sensitivity.visible_nation`).
    nation: str | None
    # The newest `SHAPE_CHANGES_SHOWN` changes to the shape, oldest first, for `sensitivity.visible_shape`.
    shape_changes: list[FindingShapeChange]


# How many changes of shape a finding's page holds: the newest, served oldest first.
SHAPE_CHANGES_SHOWN = 50


def finding_view(db: Session, finding: Finding, viewer: User | None) -> FindingView:
    assessment = current_assessment(finding)
    mine = my_observation(db, finding, viewer)
    people = users_by_id(db, {credit.user_id for credit in assessment.credits} | {finding.author_id})
    return FindingView(
        finding=finding,
        author=people[finding.author_id],
        assessment=assessment,
        evidence=evidence_for(db, finding, viewer, known=people),
        people=people,
        answers_visible=answers_visible(finding, viewer, mine),
        my_observation=mine,
        following=is_following(db, viewer, finding),
        nation=sensitivity.visible_nation(db, finding, viewer),
        shape_changes=newest_shape_changes(db, finding),
    )


def newest_shape_changes(db: Session, finding: Finding) -> list[FindingShapeChange]:
    """The newest `SHAPE_CHANGES_SHOWN` changes to the finding's shape, oldest first."""
    newest = db.scalars(
        select(FindingShapeChange)
        .where(FindingShapeChange.finding_id == finding.id)
        .order_by(FindingShapeChange.revision.desc())
        .limit(SHAPE_CHANGES_SHOWN)
    ).all()
    return list(reversed(newest))
