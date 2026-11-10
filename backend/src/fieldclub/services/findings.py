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
List queries choose the column by viewer in `sensitivity.visible_position_clause`, so a
signed-out visitor's filters touch `location_public` only.

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
from shapely.geometry import Point, Polygon
from shapely.geometry.base import BaseGeometry
from sqlalchemy import (
    ColumnElement,
    Select,
    delete,
    func,
    or_,
    select,
    true,
    tuple_,
    update,
)
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import Session, aliased

from fieldclub import gridref
from fieldclub.errors import (
    ConflictError,
    ForbiddenError,
    InvalidCursorError,
    NotFoundError,
    ValidationFailedError,
)
from fieldclub.models import (
    Comment,
    Evidence,
    EvidenceVote,
    Finding,
    Follow,
    Media,
    Observation,
    Record,
    Source,
    User,
)
from fieldclub.models.common import point_lon_lat, to_db_geometry
from fieldclub.schemas.common import cursor_int, decode_cursor, int_from_cursor, is_bbox, paginate
from fieldclub.services import activity, geo, ids, reputation, sensitivity
from fieldclub.services.confidence import (
    VERIFIER_ROLES,
    Assessment,
    EvidenceInput,
    FindingInputs,
    ObservationInput,
    VoteInput,
    assess,
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
    Stance,
    Tier,
    tier_rank,
)

logger = logging.getLogger(__name__)

# --------------------------------------------------------------------------
# Errors
# --------------------------------------------------------------------------


class FindingNotFoundError(NotFoundError):
    code = "finding_not_found"
    message = "There's no finding with that id."


class OutsideBritishIslesError(ValidationFailedError):
    code = "outside_british_isles"
    message = "Field Club covers Great Britain, Ireland and their islands. That position is outside them."


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
    message = "Only the person who added this evidence, or a moderator, can remove it."


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
    message = "Only the person who wrote this comment, or a moderator, can remove it."


# --------------------------------------------------------------------------
# Where findings may be
# --------------------------------------------------------------------------

# A coarse outline of Great Britain, Ireland, the Isle of Man, Orkney,
# Shetland, the Hebrides and Scilly, in longitude and latitude. It runs down
# the middle of the Channel and the Strait of Dover, so Calais and the Cotentin
# are outside, and well east of the North Sea coast. The Channel Islands are
# outside because they are on neither grid, and a protected finding there
# could not be generalised to a grid square.
BRITISH_ISLES = Polygon(
    [
        (-7.0, 49.8),
        (-5.2, 49.9),
        (-3.6, 50.15),
        (-2.45, 50.45),
        (-1.3, 50.5),
        (0.3, 50.65),
        (1.0, 50.85),
        (1.45, 51.05),
        (2.0, 51.5),
        (2.0, 53.0),
        (0.5, 54.5),
        (-1.0, 57.6),
        (0.0, 61.0),
        (-9.0, 61.0),
        (-14.0, 58.0),
        (-11.0, 54.5),
        (-11.0, 51.2),
    ]
)
assert BRITISH_ISLES.is_valid, "the British Isles outline crosses itself"

# An outline must be near its point and no bigger than a large hillfort's field system.
OUTLINE_MAX_SPAN_DEG = 0.05
OUTLINE_MAX_GAP_DEG = 0.01
OUTLINE_TYPES = ("Polygon", "MultiPolygon", "LineString", "MultiLineString")


def check_in_british_isles(geometry: BaseGeometry) -> None:
    """Refuse a geometry that isn't wholly inside the British Isles and on one of their grids."""
    if not BRITISH_ISLES.contains(geometry):
        raise OutsideBritishIslesError()
    for lon, lat in _corners(geometry):
        try:
            gridref.to_grid(lon, lat)
        except gridref.GridRefError:
            raise OutsideBritishIslesError() from None


def _corners(geometry: BaseGeometry) -> list[tuple[float, float]]:
    min_lon, min_lat, max_lon, max_lat = geometry.bounds
    return [(min_lon, min_lat), (min_lon, max_lat), (max_lon, min_lat), (max_lon, max_lat)]


def check_outline(outline: BaseGeometry, point: Point) -> None:
    """An outline must be inside the British Isles, near its point, and of a sensible size."""
    check_in_british_isles(outline)
    min_lon, min_lat, max_lon, max_lat = outline.bounds
    if max(max_lon - min_lon, max_lat - min_lat) > OUTLINE_MAX_SPAN_DEG:
        raise ValidationFailedError(
            "An outline can be at most a few kilometres across.", code="outline_too_big"
        )
    if outline.distance(point) > OUTLINE_MAX_GAP_DEG:
        raise ValidationFailedError(
            "The outline must be drawn round the marked point.", code="outline_too_far"
        )


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

    A banned person's answers, evidence and votes stop counting while the ban
    lasts, and their evidence leaves finding pages and exports. Lifting the
    ban restores them. See `services.moderation`.
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

# Next steps that a second look can meet. The queue measures how many answers
# a finding needs only when every open step is one of these.
ANSWER_CODES = frozenset(
    {
        NextStepCode.NEED_OBSERVERS,
        NextStepCode.NEED_CLASS_AGREEMENT,
        NextStepCode.NEED_CHECK,
        NextStepCode.NEED_TRUSTED_REVIEW,
    }
)
# The cap on `answers_to_next`, the largest smallint. The queue sorts a
# finding with no count after every stored one by using this.
ANSWERS_TO_NEXT_MAX = 32767


def answers_to_next(assessment: Assessment) -> int | None:
    """How many more members' second looks would move the finding up, or None when answers can't.

    One answer can meet several steps at once (say yes, name the class, clear
    the checks), so it is the largest number any one step needs. A trusted
    review counts as the members it would take instead.
    """
    steps = assessment.next_steps
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


def gather_inputs(db: Session, finding: Finding, state: FindingState | None = None) -> FindingInputs:
    """Everything the engine reads about a finding, with each person's current role.

    `state` is what to tell the engine, which honours only `withdrawn`. It
    defaults to the stored state.
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
            select(Observation, User.role)
            .join(User, User.id == Observation.user_id)
            .where(
                Observation.finding_id == finding.id,
                Observation.withdrawn_at.is_(None),
                User.banned_at.is_(None),
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
    votes: dict[int, list[VoteInput]] = {}
    if rows:
        for evidence_id, user_id, value, role in db.execute(
            select(EvidenceVote.evidence_id, EvidenceVote.user_id, EvidenceVote.value, User.role)
            .join(User, User.id == EvidenceVote.user_id)
            .where(
                EvidenceVote.evidence_id.in_([item.id for item, _, _ in rows]),
                User.banned_at.is_(None),
            )
        ).all():
            votes.setdefault(evidence_id, []).append(VoteInput(user_id=user_id, role=Role(role), value=value))
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
) -> Reassessment:
    """Recompute and store a finding's assessment. Call it holding `lock(db, finding)`.

    When the tier or state changes it records activity, which notifies
    followers, with `actor` as its actor. Pass None when the change came from
    a second look: a tier change credited to the person who just answered
    would tell every follower how they answered (Decision 0008). Pass that
    person as `quiet_for` instead, so they aren't notified of their own action.

    Reputation awards are written every time: `reputation.awards` works out
    what is new and `record_awards` never pays twice.
    """
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
            data={"from": tier_before.value, "to": new.tier.value},
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

_CLASS_LABELS = {info.id: info.label for info in FEATURE_CLASSES}
PUBLIC_ID_CONSTRAINT = "uq_findings_public_id"


def _point_parts(point: Point) -> tuple[float, float]:
    assert isinstance(point, Point), "a finding's location is a point"
    return point.x, point.y


def create_finding(
    db: Session,
    author: User,
    *,
    location: Point,
    feature_class: FeatureClass | str,
    title: str | None = None,
    description: str | None = None,
    period: Period | str = Period.UNKNOWN,
    outline: BaseGeometry | None = None,
    view_state: dict[str, Any] | None = None,
    requested_sensitivity: Sensitivity | str | None = None,
) -> Finding:
    """Save a new finding, follow it for its finder, assess it, and record `finding_created`.

    The public id is safe under concurrency (`ids.insert_with_public_id`). The
    starting level is `sensitivity.starting_sensitivity`.
    """
    feature_class = FeatureClass(feature_class)
    check_in_british_isles(location)
    if outline is not None:
        check_outline(outline, location)
    lon, lat = _point_parts(location)
    level = sensitivity.starting_sensitivity(feature_class, requested_sensitivity, author)
    nation = geo.nation_of(db, Point(lon, lat))

    finding = ids.insert_with_public_id(
        db,
        lambda public_id: Finding(
            public_id=public_id,
            author_id=author.id,
            title=title or _CLASS_LABELS[feature_class],
            description=description,
            feature_class=feature_class.value,
            period=Period(period).value,
            location=to_db_geometry(location),
            outline=to_db_geometry(outline) if outline is not None else None,
            sensitivity=level.value,
            view_state=view_state or {},
            nation=nation,
        ),
        PUBLIC_ID_CONSTRAINT,
    )

    follow(db, author, finding)
    activity.record(db, ActivityKind.FINDING_CREATED, author, finding)
    reassess(db, lock(db, finding), author)
    return finding


_EDITABLE = frozenset(
    {"location", "feature_class", "title", "description", "period", "outline", "view_state"}
)


def update_finding(db: Session, finding: Finding, actor: User, changes: dict[str, Any]) -> Finding:
    """Apply the finder's edits. Hold the lock. Keys are `_EDITABLE`; values are already parsed.

    A move keeps `grid_ref`, `nation` and the public position in step. A new
    feature class can raise the level (`sensitivity.level_after_class_change`,
    applied on save) and is reassessed, because the finder's class counts.
    """
    if not actor.has_id(finding.author_id):
        raise NotFinderError()
    unknown = set(changes) - _EDITABLE
    assert not unknown, f"not editable: {sorted(unknown)}"
    location: Point = changes.get("location") or Point(point_lon_lat(finding.location))
    if "location" in changes:
        check_in_british_isles(location)
    outline = changes.get("outline")
    if outline is not None:
        check_outline(outline, location)
    elif "location" in changes and finding.outline is not None:
        check_outline(to_shape(finding.outline), location)

    if "location" in changes:
        finding.location = to_db_geometry(location)
        finding.nation = geo.nation_of(db, Point(*_point_parts(location)))
    if "outline" in changes:
        finding.outline = to_db_geometry(outline) if outline is not None else None
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
    db.flush()
    if "location" in changes:
        activity.relocate(db, finding)
    if class_changed:
        reassess(db, finding, actor)
    return finding


def withdraw_finding(db: Session, finding: Finding, actor: User) -> Reassessment:
    """The finder takes the finding back. Hold the lock."""
    if not actor.has_id(finding.author_id):
        raise NotFinderError()
    check_open(finding)
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


def not_hidden_clause(viewer: User | None) -> ColumnElement[bool]:
    """Findings that aren't hidden from this viewer: see `may_see_hidden`."""
    if is_moderator(viewer):
        return true()
    active = sensitivity.active_viewer(viewer)
    if active is None:
        return Finding.hidden_at.is_(None)
    return or_(Finding.hidden_at.is_(None), Finding.author_id == active.id)


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
        query = query.where(sensitivity.visible_position_clause(viewer, geo.envelope(filters.bbox)))
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
        query = query.where(
            or_(Finding.title.ilike(pattern, escape="\\"), Finding.public_id == filters.q.upper())
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
    check_open(finding)
    require_exact(finding, user)
    check_evidence_fields(db, user, fields, today=datetime.now(UTC).date())
    data: dict[str, Any] = {}
    if fields.view is not None:
        data["view"] = fields.view
    reference, url, source_key = fields.reference, fields.url, fields.source_key
    if fields.record_id is not None:
        record = db.get(Record, fields.record_id)
        assert record is not None, "check_evidence_fields refuses a record that isn't stored"
        reference, source_key = reference or record.external_id, record.source_key
        url = url or record.url
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
    return evidence, reassess(db, finding, user)


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
    """Remove evidence, by its contributor or a moderator. It is kept, marked deleted."""
    evidence, finding = _locked_evidence(db, evidence_id, user)
    if not (user.has_id(evidence.user_id) or is_moderator(user)):
        raise EvidenceForbiddenError()
    evidence.deleted_at = datetime.now(UTC)
    db.flush()
    return reassess(db, finding, user)


def vote(db: Session, evidence_id: int, user: User, value: int) -> Reassessment:
    """Endorse (+1), object to (-1) or take back (0) a vote on evidence, and reassess."""
    assert value in (-1, 0, 1), "a vote is -1, 0 or 1"
    evidence, finding = _locked_evidence(db, evidence_id, user)
    check_open(finding)
    require_exact(finding, user)
    if user.has_id(evidence.user_id) or user.has_id(finding.author_id):
        raise VoteNotAllowedError()
    if value == 0:
        db.execute(
            delete(EvidenceVote).where(
                EvidenceVote.evidence_id == evidence.id, EvidenceVote.user_id == user.id
            )
        )
    else:
        db.execute(
            insert(EvidenceVote)
            .values(evidence_id=evidence.id, user_id=user.id, value=value)
            .on_conflict_do_update(index_elements=["evidence_id", "user_id"], set_={"value": value})
        )
        follow(db, user, finding)
    return reassess(db, finding, user)


def verify(db: Session, evidence_id: int, user: User) -> Reassessment:
    """An archaeologist or moderator verifies an official item, which can put a finding on record.

    Verifying is a second person's check, so neither the finder nor the
    person who added the item can do it.
    """
    evidence, finding = _locked_evidence(db, evidence_id, user)
    check_open(finding)
    if (
        Role(user.role) not in VERIFIER_ROLES
        or user.has_id(finding.author_id)
        or user.has_id(evidence.user_id)
    ):
        raise VerifyNotAllowedError()
    require_exact(finding, user)
    if EvidenceKind(evidence.kind) not in OFFICIAL_KINDS:
        raise InvalidEvidenceError(
            "Only an HER entry, a designation or a publication is verified.", code="not_official"
        )
    if evidence.verified_by is None:
        evidence.verified_by = user.id
        evidence.verified_at = datetime.now(UTC)
        db.flush()
    follow(db, user, finding)
    return reassess(db, finding, user)


@dataclass(frozen=True)
class EvidenceView:
    evidence: Evidence
    contributor: User
    verifier: User | None
    media: Media | None
    my_vote: int | None


def evidence_for(
    db: Session, finding: Finding, viewer: User | None, known: Mapping[int, User] | None = None
) -> list[EvidenceView]:
    """A finding's standing evidence, oldest first, with what a response needs.

    `known` holds users already loaded, such as those named in the credits,
    so only the rest are fetched.
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
    mine: dict[int, int] = {}
    if viewer is not None and items:
        mine = dict(
            db.execute(
                select(EvidenceVote.evidence_id, EvidenceVote.value).where(
                    EvidenceVote.user_id == viewer.id, EvidenceVote.evidence_id.in_([e.id for e in items])
                )
            ).all()
        )
    return [
        EvidenceView(
            evidence=e,
            contributor=people[e.user_id],
            verifier=people.get(e.verified_by) if e.verified_by is not None else None,
            media=media.get(e.media_id) if e.media_id is not None else None,
            my_vote=mine.get(e.id),
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
    """Remove a comment, by its author or a moderator. Replies keep their place."""
    comment = db.get(Comment, comment_id)
    if comment is None or comment.deleted_at is not None:
        raise CommentNotFoundError()
    finding = db.get(Finding, comment.finding_id)
    assert finding is not None, "a comment always belongs to a finding"
    if finding.hidden_at is not None and not may_see_hidden(finding, user):
        raise CommentNotFoundError()
    if comment.hidden_at is not None and not may_see_hidden_comment(comment, user):
        raise CommentNotFoundError()
    if not (user.has_id(comment.user_id) or is_moderator(user)):
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


def answers_visible(finding: Finding, viewer: User | None, answered: bool) -> bool:
    """Whether `viewer` may see other people's answers (Decision 0008): the finder or an answerer."""
    active = sensitivity.active_viewer(viewer)
    return active is not None and (active.has_id(finding.author_id) or answered)


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
        answers_visible=answers_visible(finding, viewer, mine is not None),
        my_observation=mine,
        following=is_following(db, viewer, finding),
        nation=sensitivity.visible_nation(db, finding, viewer),
    )
