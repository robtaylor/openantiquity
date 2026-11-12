"""The moderation queue and moderators' actions: reports, hiding, location levels, roles, bans and the log.

Every route here is for moderators and admins who have finished the welcome
step, reads included, because that step is where a person accepts the terms
(`tests/test_routes.py` says so of each route). The photo approval queue, which trusted members share, is in
`api.media`. Responses depend on who asks, so none may be cached.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Path, Query, Response

from fieldclub.api.deps import Contributor, CursorQuery, Db, PageQuery, private, rate_limit
from fieldclub.api.findings import detail
from fieldclub.errors import BadRequestError
from fieldclub.models import User
from fieldclub.schemas.common import Page
from fieldclub.schemas.findings import FindingDetail
from fieldclub.schemas.moderation import (
    TARGET_REF_MAX,
    Action,
    Ban,
    Eligible,
    Hidden,
    ModPerson,
    ModSensitivityIn,
    ModUser,
    ReasonIn,
    ReportOut,
    Resolved,
    ResolveIn,
    RoleIn,
)
from fieldclub.services import actions, moderation
from fieldclub.vocab import ReportReason, ReportStatus, ReportTarget, Sensitivity


def require_moderator(user: Contributor) -> User:
    """A moderator or admin who has finished the welcome step, or a 403.

    Every route here needs the welcome step, reads included, since that step
    is where a person accepts the terms they moderate by.
    """
    moderation.check_moderator(user)
    return user


Moderator = Annotated[User, Depends(require_moderator)]

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


@router.post("/reports/{report_id}/resolve", response_model=Resolved, dependencies=_writes)
def resolve_report(
    report_id: Annotated[int, Path(ge=1, le=2**63 - 1)], body: ResolveIn, moderator: Moderator, db: Db
) -> Resolved:
    """Uphold or dismiss a report, and with it every other open report on the same target.

    This doesn't hide anything: hide the target as well when the report is upheld.
    """
    queued, resolved = moderation.resolve_report(
        db, report_id, moderator, ReportStatus(body.outcome), body.note
    )
    db.commit()
    return Resolved(report=ReportOut.build(queued), resolved=resolved)


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
    ReportTarget.INVESTIGATION: "investigations",
}
assert set(_HIDE_PATHS) == moderation.HIDEABLE, "every hideable kind has a route"


def _hide_route(kind: ReportTarget, hidden: bool):
    def route(target_id: TargetRef, body: ReasonIn, moderator: Moderator, db: Db) -> Hidden:
        state = moderation.set_hidden(db, kind, target_id, moderator, hidden=hidden, reason=body.reason)
        db.commit()
        return Hidden.build(state)

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
            response_model=Hidden,
            name=f"{_verb}_{_kind.value}",
            dependencies=_writes,
        )


# --------------------------------------------------------------------------
# Location sensitivity
# --------------------------------------------------------------------------


@router.put("/findings/{public_id}/sensitivity", response_model=FindingDetail, dependencies=_writes)
def set_sensitivity(
    public_id: TargetRef, body: ModSensitivityIn, moderator: Moderator, db: Db, response: Response
) -> FindingDetail:
    """Set a finding's location level, lower as well as higher. The reason goes in the moderation log."""
    finding = moderation.set_sensitivity(db, public_id, moderator, Sensitivity(body.level), body.reason)
    db.commit()
    private(response)
    return detail(db, finding, moderator)


# --------------------------------------------------------------------------
# People
# --------------------------------------------------------------------------


@router.get("/users/eligible", response_model=Page[Eligible])
def eligible_members(
    moderator: Moderator,
    db: Db,
    limit: Annotated[int, Query(ge=1, le=ELIGIBLE_MAX_LIMIT)] = ELIGIBLE_DEFAULT_LIMIT,
    cursor: CursorQuery = None,
) -> Page[Eligible]:
    """Members with fifty points who aren't trusted yet, where the points came from and who else was there."""
    found, next_cursor = moderation.eligible_members(db, moderator, limit=limit, cursor=cursor)
    return Page[Eligible](items=[Eligible.build(item) for item in found], next_cursor=next_cursor)


Handle = Annotated[str, Path(min_length=1, max_length=TARGET_REF_MAX)]


@router.get("/users/{handle}", response_model=ModPerson)
def person(handle: Handle, moderator: Moderator, db: Db) -> ModPerson:
    """One person as a moderator sees them, a banned or deleted account included, and what this
    moderator may do to them: ban, unban, and give each role."""
    user = moderation.get_person(db, handle)
    return ModPerson.build_for(user, actions.person_actions(user, moderator))


@router.put("/users/{handle}/role", response_model=ModUser, dependencies=_writes)
def change_role(handle: Handle, body: RoleIn, moderator: Moderator, db: Db) -> ModUser:
    """Make a member trusted or put them back, or mark an archaeologist as expert.

    Only an admin makes or unmakes a moderator.
    """
    user = moderation.change_role(db, handle, moderator, body.role, body.reason)
    db.commit()
    return ModUser.build(user)


@router.post("/users/{handle}/ban", response_model=Ban, dependencies=_writes)
def ban(handle: Handle, body: ReasonIn, moderator: Moderator, db: Db) -> Ban:
    """Ban someone. Their sessions end now, and their evidence and verifications stop counting.

    Their second looks and votes keep counting as they were given, so that a
    ban can't show how they answered (Decision 0019).
    """
    result = moderation.ban(db, handle, moderator, body.reason)
    db.commit()
    return Ban(user=ModUser.build(result.user), sessions_ended=result.sessions_ended)


@router.post("/users/{handle}/unban", response_model=Ban, dependencies=_writes)
def unban(handle: Handle, body: ReasonIn, moderator: Moderator, db: Db) -> Ban:
    """Lift a ban. Their evidence and verifications count again at once."""
    result = moderation.unban(db, handle, moderator, body.reason)
    db.commit()
    return Ban(user=ModUser.build(result.user), sessions_ended=result.sessions_ended)


# --------------------------------------------------------------------------
# The log
# --------------------------------------------------------------------------


@router.get("/actions", response_model=Page[Action])
def list_actions(
    moderator: Moderator,
    db: Db,
    page: PageQuery,
    target_kind: ReportTarget | None = None,
    target_id: Annotated[str | None, Query(min_length=1, max_length=TARGET_REF_MAX)] = None,
) -> Page[Action]:
    """Every moderator's actions, newest first. Give `target_kind` and `target_id` for one target."""
    if target_id is not None and target_kind is None:
        raise BadRequestError("Give target_kind with target_id.", code="target_kind_required")
    found, next_cursor = moderation.list_actions(
        db, kind=target_kind, ref=target_id, limit=page.limit, cursor=page.cursor
    )
    return Page[Action](items=[Action.build(item) for item in found], next_cursor=next_cursor)
