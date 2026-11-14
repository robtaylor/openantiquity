"""Suggestions: a change to a marking's shape that someone else proposes and its keeper accepts or declines.

A suggestion is a whole proposed path, made on the shape as it was at
`base_revision`, kept in `shape_suggestions` and never in
`finding_shape_changes`, whose readers it would change. Any contributor but
the keeper may suggest, on a finding that isn't withdrawn. A suggestion is
held when it is made to the limits and the anchor, as an edit is, and not
to the ground second looks were given on: any member may suggest, and even
a yes or a no would let shapes sent one after another map that ground,
which Decisions 0008 and 0010 keep from members. The keeper, who may see
it, meets that rule on accepting. A suggester is never sent `looked_at`.

Each person has at most one pending suggestion on a finding, and a new one
withdraws the old. A finding holds at most `SUGGESTIONS_MAX_PENDING`.

A banned person's pending suggestions leave every list and every count
(`findings.suggestions_listed_clause`), as their evidence does, and come back
when the ban is lifted. One left out can't be reached: accepting, declining and withdrawing
it answer `suggestion_not_found`.

Accepting goes through `findings.apply_shape_change`, so the change is
credited to the suggester, held to the limits, the anchor and `looked_at` as
they are now, reassessed, told to followers as an edit is, and the
finding's events follow its anchor. A suggestion made on an older shape can
still be accepted: the accept names the revision the keeper saw. One that
breaks the looked-at rule is refused with `looked_at_moved`, with its
figure, and stays pending.

The keeper is told of each suggestion (`shape_suggested`), and the suggester
of the keeper's answer (`suggestion_decided`, with `accepted`). Both are
notifications to one member, who sees the finding exactly, with no free text.
A replaced suggestion doesn't tell the keeper again while the last word of
it is unread, and deciding marks that word read.

Services flush and never commit.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import ColumnElement, func, select
from sqlalchemy.orm import Session, undefer

from fieldclub.errors import ConflictError, ForbiddenError, NotFoundError, ValidationFailedError
from fieldclub.models import Finding, Notification, ShapeSuggestion, User
from fieldclub.models.common import to_db_geometry
from fieldclub.services import activity, findings, shape_edits, shapes
from fieldclub.vocab import ActivityKind, SuggestionState

# How many pending suggestions a finding holds at most. With 5,000 points a
# path, that bounds what one finding's suggestions can store.
SUGGESTIONS_MAX_PENDING = 20


class SuggestionNotFoundError(NotFoundError):
    code = "suggestion_not_found"
    message = "There's no suggestion with that id on this finding."


class NotSuggesterError(ForbiddenError):
    code = "not_suggester"
    message = "Only the person who made this suggestion can take it back."


class SuggestionDecidedError(ConflictError):
    code = "suggestion_decided"
    message = "This suggestion has already been accepted, declined or taken back."


class SuggestionUnchangedError(ValidationFailedError):
    code = "suggestion_unchanged"
    message = "The suggested shape is the shape the finding has now."


class TooManySuggestionsError(ConflictError):
    code = "too_many_suggestions"
    message = (
        f"This finding has {SUGGESTIONS_MAX_PENDING} suggestions waiting for its keeper. "
        "Try again once some are answered."
    )


def _pending(finding: Finding) -> ColumnElement[bool]:
    """The finding's listed pending suggestions (`findings.suggestions_listed_clause`)."""
    return (
        (ShapeSuggestion.finding_id == finding.id)
        & (ShapeSuggestion.state == SuggestionState.PENDING.value)
        & findings.suggestions_listed_clause()
    )


def get(db: Session, finding: Finding, suggestion_id: int, caller: User) -> ShapeSuggestion:
    """A listed suggestion on `finding`, locked, or `SuggestionNotFoundError`. Hold the finding's lock.

    One already decided is found only by its suggester and the keeper, so
    nobody else learns that the id was ever there.
    """
    found = db.scalar(
        select(ShapeSuggestion)
        .options(undefer(ShapeSuggestion.path), undefer(ShapeSuggestion.outline_mid))
        .where(
            ShapeSuggestion.id == suggestion_id,
            ShapeSuggestion.finding_id == finding.id,
            findings.suggestions_listed_clause(),
        )
        .with_for_update()
    )
    if found is None:
        raise SuggestionNotFoundError()
    involved = caller.has_id(found.user_id) or caller.has_id(findings.keeper_of(finding))
    if found.state != SuggestionState.PENDING.value and not involved:
        raise SuggestionNotFoundError()
    return found


def check_may_suggest(finding: Finding, user: User) -> None:
    """Refuse what `suggest` refuses whatever the path: a withdrawn finding, or its keeper suggesting."""
    findings.check_open(finding)
    findings.check_not_keeper(finding, user)
    findings.require_exact(finding, user)


def _check_pending(suggestion: ShapeSuggestion) -> None:
    if suggestion.state != SuggestionState.PENDING.value:
        raise SuggestionDecidedError()


def _notify(
    db: Session, to: User, kind: ActivityKind, actor: User, finding: Finding, data: dict[str, bool] | None
) -> None:
    """A notification to one member, while their account stands, and never of their own act."""
    if not to.is_active or to.has_id(actor.id):
        return
    db.add(Notification(user_id=to.id, kind=kind.value, actor_id=actor.id, finding_id=finding.id, data=data))


def suggest(
    db: Session, finding: Finding, user: User, *, path: shapes.Path, revision: int | None
) -> ShapeSuggestion:
    """Propose `path` for `finding`. Hold the lock.

    Refused, in this order: a withdrawn finding, the keeper, a revision
    missing or not the shape's now, a path that is the shape already, a
    finding with `SUGGESTIONS_MAX_PENDING` waiting, then the limits and the
    anchor. Never `looked_at_moved`: that is for the keeper to meet. A
    pending suggestion of the same person's is
    withdrawn first, so a new one replaces it. The suggester follows the
    finding, and the keeper is told.
    """
    check_may_suggest(finding, user)
    shape_edits.check_revision(finding, revision)
    shape = shapes.shape_of(path)
    kind = shapes.classify_change(shape_edits.stored_path(finding), shape.path)
    if kind is None:
        raise SuggestionUnchangedError()
    now = datetime.now(UTC)
    for mine in db.scalars(
        select(ShapeSuggestion).where(_pending(finding), ShapeSuggestion.user_id == user.id).with_for_update()
    ):
        mine.state = SuggestionState.WITHDRAWN.value
        mine.decided_at = now
    db.flush()
    waiting = db.scalar(select(func.count()).select_from(ShapeSuggestion).where(_pending(finding))) or 0
    if waiting >= SUGGESTIONS_MAX_PENDING:
        raise TooManySuggestionsError()
    current = shape_edits.current_anchor(finding)
    shape_edits.place_anchor(shape, placed=None, current=current, derived=finding.location_derived)
    suggestion = ShapeSuggestion(
        finding_id=finding.id,
        user_id=user.id,
        base_revision=finding.shape_revision,
        path=shape.path.to_json(),
        outline_mid=to_db_geometry(shape.mid),
        kind=kind.value,
        length_m=shape.length_m,
        state=SuggestionState.PENDING.value,
    )
    db.add(suggestion)
    db.flush()
    findings.follow(db, user, finding)
    kept_by = db.get(User, findings.keeper_of(finding))
    assert kept_by is not None, "a finding has a keeper"
    # A replaced suggestion doesn't tell the keeper again while the last word of it waits unread.
    if not activity.has_unread(db, kept_by, ActivityKind.SHAPE_SUGGESTED, finding, user):
        _notify(db, kept_by, ActivityKind.SHAPE_SUGGESTED, user, finding, None)
    db.flush()
    return suggestion


def withdraw(db: Session, finding: Finding, user: User, suggestion_id: int) -> None:
    """The suggester takes a pending suggestion back. Hold the finding's lock."""
    suggestion = get(db, finding, suggestion_id, user)
    if not user.has_id(suggestion.user_id):
        raise NotSuggesterError()
    _check_pending(suggestion)
    suggestion.state = SuggestionState.WITHDRAWN.value
    suggestion.decided_at = datetime.now(UTC)
    db.flush()


def accept(
    db: Session, finding: Finding, keeper: User, suggestion_id: int, *, shape_revision: int | None
) -> ShapeSuggestion:
    """The keeper accepts a suggestion, which changes the shape as an edit would, credited to the suggester.

    Refused, in this order: a suggestion not found, anyone but the keeper, a
    withdrawn finding, a suggestion already decided, a `shape_revision` that
    isn't the shape's now, then whatever the change refuses. A refused
    suggestion stays pending.
    """
    suggestion = get(db, finding, suggestion_id, keeper)
    findings.check_keeper(finding, keeper)
    findings.check_open(finding)
    _check_pending(suggestion)
    if keeper.has_id(suggestion.user_id):
        # Only a crossed request leaves a keeper a pending suggestion of their own: taking the
        # marking on withdraws it. They change the shape themselves.
        raise findings.OwnMarkingError()
    shape_edits.check_revision(finding, shape_revision)
    by = db.get(User, suggestion.user_id)
    assert by is not None, "a suggestion has a suggester"
    assert suggestion.path is not None, "a suggestion has a path"
    kind = findings.apply_shape_change(
        db, finding, by, path=shapes.read_path(suggestion.path), revision=finding.shape_revision
    )
    _decide(db, finding, suggestion, keeper, by, SuggestionState.ACCEPTED)
    if kind is not None:
        suggestion.applied_revision = finding.shape_revision
    _notify(db, by, ActivityKind.SUGGESTION_DECIDED, keeper, finding, {"accepted": True})
    db.flush()
    return suggestion


def decline(db: Session, finding: Finding, keeper: User, suggestion_id: int) -> ShapeSuggestion:
    """The keeper declines a suggestion. No reason is kept: talk goes in the comments (Decision 0009)."""
    suggestion = get(db, finding, suggestion_id, keeper)
    findings.check_keeper(finding, keeper)
    _check_pending(suggestion)
    by = db.get(User, suggestion.user_id)
    assert by is not None, "a suggestion has a suggester"
    _decide(db, finding, suggestion, keeper, by, SuggestionState.DECLINED)
    _notify(db, by, ActivityKind.SUGGESTION_DECIDED, keeper, finding, {"accepted": False})
    db.flush()
    return suggestion


def _decide(
    db: Session, finding: Finding, suggestion: ShapeSuggestion, keeper: User, by: User, state: SuggestionState
) -> None:
    """Record the keeper's answer, and mark their word of the suggestion read: they have acted on it.

    So the suggester's next suggestion is news, and tells them.
    """
    activity.mark_read_about(db, keeper, ActivityKind.SHAPE_SUGGESTED, finding, by)
    suggestion.state = state.value
    suggestion.decided_by = keeper.id
    suggestion.decided_at = datetime.now(UTC)
