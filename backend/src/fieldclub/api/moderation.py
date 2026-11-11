"""The moderation queue and moderators' actions: reports, hiding, location levels, roles, bans and the log.

Every route here is for moderators and admins. Those that change anything
need the welcome step finished, as every write does; reading the queues and
the log doesn't (`tests/test_routes.py`). The photo approval queue, which trusted members share, is in
`api.media`. Responses depend on who asks, so none may be cached.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from fieldclub.api.deps import Contributor, CurrentUser, CursorQuery, Db, PageQuery, private, rate_limit
from fieldclub.api.findings import detail
from fieldclub.errors import BadRequestError, ForbiddenError
from fieldclub.models import User
from fieldclub.schemas.common import Page
from fieldclub.schemas.findings import FindingDetail
from fieldclub.schemas.moderation import (
    TARGET_REF_MAX,
    ActionOut,
    BanOut,
    EligibleOut,
    HiddenOut,
    ModSensitivityIn,
    ModUserOut,
    ReasonIn,
    ReportOut,
    ResolvedOut,
    ResolveIn,
    RoleIn,
)
from fieldclub.services import moderation
from fieldclub.vocab import MODERATOR_ROLES, ReportReason, ReportStatus, ReportTarget, Role


def _moderator(user: User) -> User:
    if Role(user.role) not in MODERATOR_ROLES:
        raise ForbiddenError("Only moderators can do that.", code="moderators_only")
    return user


def require_moderator(user: CurrentUser) -> User:
    """A signed-in moderator or admin, or a 403. Enough to read the queues and the log."""
    return _moderator(user)


def require_acting_moderator(user: Contributor) -> User:
    """A moderator or admin who has finished the welcome step, as every write needs (Decision 0009)."""
    return _moderator(user)


Moderator = Annotated[User, Depends(require_moderator)]
ActingModerator = Annotated[User, Depends(require_acting_moderator)]

router = APIRouter(prefix="/mod", tags=["moderation"], dependencies=[Depends(private)])

_writes = [Depends(rate_limit("moderation", 600, per_seconds=3600))]
TargetRef = Annotated[str, Path(min_length=1, max_length=TARGET_REF_MAX)]
ELIGIBLE_DEFAULT_LIMIT = 20
ELIGIBLE_MAX_LIMIT = 50


# --------------------------------------------------------------------------
# Reports
# --------------------------------------------------------------------------


@router.get("/reports", response_model=Page[ReportOut])
def report_queue(
    moderator: Moderator,
    db: Db,
    page: PageQuery,
    status: ReportStatus = ReportStatus.OPEN,
    reason: ReportReason | None = None,
) -> Page[ReportOut]:
    """Reports, oldest first, each with its target as it is now. Open ones unless `status` says otherwise.

    A report whose reason has a legal deadline carries `due_at`. Filter by
    `reason=intimate_image` to see those first.
    """
    queued, next_cursor = moderation.report_queue(
        db, moderator, status=status, reason=reason, limit=page.limit, cursor=page.cursor
    )
    return Page[ReportOut](items=[ReportOut.build(item) for item in queued], next_cursor=next_cursor)


@router.post("/reports/{report_id}/resolve", response_model=ResolvedOut, dependencies=_writes)
def resolve_report(
    report_id: Annotated[int, Path(ge=1, le=2**63 - 1)], body: ResolveIn, moderator: ActingModerator, db: Db
) -> ResolvedOut:
    """Uphold or dismiss a report, and with it every other open report on the same target.

    This doesn't hide anything: hide the target as well when the report is upheld.
    """
    queued, resolved = moderation.resolve_report(
        db, report_id, moderator, ReportStatus(body.outcome), body.note
    )
    db.commit()
    return ResolvedOut(report=ReportOut.build(queued), resolved=resolved)


# --------------------------------------------------------------------------
# Hiding
# --------------------------------------------------------------------------

# The path under /mod for each kind of thing a moderator can hide.
_HIDE_PATHS: dict[ReportTarget, str] = {
    ReportTarget.FINDING: "findings",
    ReportTarget.COMMENT: "comments",
    ReportTarget.EVIDENCE: "evidence",
    ReportTarget.MENTION: "mentions",
    ReportTarget.PHOTO: "media",
}
assert set(_HIDE_PATHS) == moderation.HIDEABLE, "every hideable kind has a route"


def _hide_route(kind: ReportTarget, hidden: bool):
    def route(target_id: TargetRef, body: ReasonIn, moderator: ActingModerator, db: Db) -> HiddenOut:
        state = moderation.set_hidden(db, kind, target_id, moderator, hidden=hidden, reason=body.reason)
        db.commit()
        return HiddenOut.build(state)

    verb = "Hide" if hidden else "Show again"
    route.__doc__ = (
        f"{verb} a {kind.value}. It takes effect for everyone on their next request."
        if hidden
        else f"{verb} a {kind.value} a moderator hid."
    )
    return route


for _kind, _segment in _HIDE_PATHS.items():
    for _hidden, _verb in ((True, "hide"), (False, "unhide")):
        router.add_api_route(
            f"/{_segment}/{{target_id}}/{_verb}",
            _hide_route(_kind, _hidden),
            methods=["POST"],
            response_model=HiddenOut,
            name=f"{_verb}_{_kind.value}",
            dependencies=_writes,
        )


# --------------------------------------------------------------------------
# Location sensitivity
# --------------------------------------------------------------------------


@router.put("/findings/{public_id}/sensitivity", response_model=FindingDetail, dependencies=_writes)
def set_sensitivity(
    public_id: TargetRef, body: ModSensitivityIn, moderator: ActingModerator, db: Db, response: Response
) -> FindingDetail:
    """Set a finding's location level, lower as well as higher. The reason goes in the moderation log."""
    finding = moderation.set_sensitivity(db, public_id, moderator, body.level, body.reason)
    db.commit()
    private(response)
    return detail(db, finding, moderator)


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


@router.get("/users/eligible", response_model=Page[EligibleOut])
def eligible_members(
    moderator: Moderator,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=ELIGIBLE_MAX_LIMIT)] = ELIGIBLE_DEFAULT_LIMIT,
    cursor: CursorQuery = None,
) -> Page[EligibleOut]:
    """Members with fifty points who aren't trusted yet, where the points came from and who else was there."""
    found, next_cursor = moderation.eligible_members(db, moderator, limit=limit, cursor=cursor)
    return Page[EligibleOut](items=[EligibleOut.build(item) for item in found], next_cursor=next_cursor)


Handle = Annotated[str, Path(min_length=1, max_length=TARGET_REF_MAX)]


@router.put("/users/{handle}/role", response_model=ModUserOut, dependencies=_writes)
def change_role(handle: Handle, body: RoleIn, moderator: ActingModerator, db: Db) -> ModUserOut:
    """Make a member trusted or put them back, or mark an archaeologist as expert.

    Only an admin makes or unmakes a moderator.
    """
    user = moderation.change_role(db, handle, moderator, body.role, body.reason)
    db.commit()
    return ModUserOut.build(user)


@router.post("/users/{handle}/ban", response_model=BanOut, dependencies=_writes)
def ban(handle: Handle, body: ReasonIn, moderator: ActingModerator, db: Db) -> BanOut:
    """Ban someone. Their sessions end now, and their answers, evidence and votes stop counting."""
    result = moderation.ban(db, handle, moderator, body.reason)
    db.commit()
    return BanOut(
        user=ModUserOut.build(result.user),
        sessions_ended=result.sessions_ended,
        findings_reassessed=result.findings_reassessed,
    )


@router.post("/users/{handle}/unban", response_model=BanOut, dependencies=_writes)
def unban(handle: Handle, body: ReasonIn, moderator: ActingModerator, db: Db) -> BanOut:
    """Lift a ban. Their work counts again at once."""
    result = moderation.unban(db, handle, moderator, body.reason)
    db.commit()
    return BanOut(
        user=ModUserOut.build(result.user),
        sessions_ended=result.sessions_ended,
        findings_reassessed=result.findings_reassessed,
    )


# --------------------------------------------------------------------------
# The log
# --------------------------------------------------------------------------


@router.get("/actions", response_model=Page[ActionOut])
def list_actions(
    moderator: Moderator,
    db: Db,
    page: PageQuery,
    target_kind: ReportTarget | None = None,
    target_id: Annotated[str | None, Query(min_length=1, max_length=TARGET_REF_MAX)] = None,
) -> Page[ActionOut]:
    """Every moderator's actions, newest first. Give `target_kind` and `target_id` for one target."""
    if target_id is not None and target_kind is None:
        raise BadRequestError("Give target_kind with target_id.", code="target_kind_required")
    found, next_cursor = moderation.list_actions(
        db, kind=target_kind, ref=target_id, limit=page.limit, cursor=page.cursor
    )
    return Page[ActionOut](items=[ActionOut.build(item) for item in found], next_cursor=next_cursor)
