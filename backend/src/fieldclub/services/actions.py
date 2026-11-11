"""What one viewer may do on a finding's page, worked out from the rules the routes enforce.

Each action is answered by running the same check functions its route runs,
in the same order, and catching the error a refusal raises. So an action is
allowed exactly when the route would accept it, and when it isn't, `reason`
is the code the route would answer with:

- `answer`: `PUT /findings/{id}/observation`. `review.check_may_answer`, then
  no answer given yet. A viewer who took their answer back gets
  `answer_withdrawn`: `PUT` with the same `visible` as `my_observation`
  restores it, and any other answer is `answer_final`.
- `add_evidence`: `POST /findings/{id}/evidence`. `findings.check_may_add_evidence`.
- `comment`: `POST /findings/{id}/comments`. Any contributor.
- `edit`: `PATCH /findings/{id}`. `findings.check_finder`.
- `withdraw`: `POST /findings/{id}/withdraw`. `findings.check_may_withdraw`.
- `raise_level`: `PUT /findings/{id}/sensitivity` to the next level up.
  `sensitivity.may_change_sensitivity`.
- `lower_level`: `PUT /mod/findings/{id}/sensitivity` to the next level down.
  `moderation.check_moderator`, then `moderation.check_may_set_sensitivity`.
- `verify`: `POST /evidence/{id}/verify` on an official item someone else
  added. `findings.check_may_verify`, then some item on the page that its
  own `verify` allows (`nothing_to_verify` when none is).

Every route first takes `Contributor`: signed in, not banned, and through the
welcome step. A signed-out viewer gets `unauthorised` for everything, and
someone who hasn't finished the welcome step `onboarding_required`, so the
client can offer sign-in or the welcome sheet where an action would follow.

Each evidence item carries its own `vote` and `verify`, which add the checks
about that item. A few reasons aren't errors a route raises, because there is
nothing to send: `already_answered` (the viewer's answer is given, and its
page says whether it waits for its detail), `answer_withdrawn`,
`highest_level`, `lowest_level` and `nothing_to_verify`.

Nothing here says anything about other people's answers: whether someone may
answer turns on their own answer only.
"""

from __future__ import annotations

from collections.abc import Callable, Sequence
from dataclasses import dataclass, fields

from fieldclub.auth import onboarding
from fieldclub.config import get_settings
from fieldclub.errors import AppError, UnauthorisedError
from fieldclub.models import Evidence, Finding, Observation, User
from fieldclub.services import findings, moderation, review, sensitivity
from fieldclub.vocab import SENSITIVITY_ORDER, Sensitivity, sensitivity_rank

ALREADY_ANSWERED = "already_answered"
ANSWER_WITHDRAWN = "answer_withdrawn"
HIGHEST_LEVEL = "highest_level"
LOWEST_LEVEL = "lowest_level"
NOTHING_TO_VERIFY = "nothing_to_verify"


@dataclass(frozen=True)
class Action:
    allowed: bool
    # The code the route would refuse with, or why there is nothing to do. None when allowed.
    reason: str | None = None


@dataclass(frozen=True)
class FindingActions:
    answer: Action
    add_evidence: Action
    comment: Action
    edit: Action
    withdraw: Action
    raise_level: Action
    lower_level: Action
    verify: Action


@dataclass(frozen=True)
class EvidenceActions:
    vote: Action
    verify: Action


class _NothingToDoError(AppError):
    """A reason there is nothing to do, which no route raises."""

    def __init__(self, code: str) -> None:
        super().__init__(code=code)


def _action(*checks: Callable[[], None]) -> Action:
    """Run the checks in order. The first that raises gives the reason."""
    try:
        for check in checks:
            check()
    except AppError as refused:
        return Action(False, refused.code)
    return Action(True)


def _contributor(viewer: User | None) -> tuple[User | None, Action]:
    """The viewer as the `Contributor` dependency lets them through, or why it doesn't."""
    active = sensitivity.active_viewer(viewer)
    if active is None:
        # A banned account's session is refused as signed out, and banning ends its sessions.
        return None, Action(False, UnauthorisedError.code)
    found = _action(lambda: onboarding.check_contributor(active, get_settings()))
    return (active if found.allowed else None), found


def _level_beside(finding: Finding, step: int) -> Sensitivity | None:
    """The level one above (`step` 1) or below (-1) the finding's, or None at the end."""
    index = sensitivity_rank(finding.sensitivity) + step
    return SENSITIVITY_ORDER[index] if 0 <= index < len(SENSITIVITY_ORDER) else None


def _nothing(code: str) -> Callable[[], None]:
    def check() -> None:
        raise _NothingToDoError(code)

    return check


def finding_actions(
    finding: Finding, viewer: User | None, mine: Observation | None, evidence: Sequence[Evidence]
) -> FindingActions:
    """What `viewer` may do on `finding`.

    `mine` is the viewer's own answer, if any, and `evidence` the standing
    items the page shows, which `verify` looks through.
    """
    user, refused = _contributor(viewer)
    if user is None:
        return FindingActions(*(refused for _ in fields(FindingActions)))
    assert mine is None or user.has_id(mine.user_id), "`mine` is the viewer's own answer"
    higher, lower = _level_beside(finding, 1), _level_beside(finding, -1)

    def raise_to(level: Sensitivity) -> None:
        if not sensitivity.may_change_sensitivity(finding, user, level):
            raise sensitivity.SensitivityChangeForbiddenError()

    def something_to_verify() -> None:
        for item in evidence:
            if _action(lambda item=item: findings.check_may_verify(finding, user, item)).allowed:
                return
        raise _NothingToDoError(NOTHING_TO_VERIFY)

    def unanswered() -> None:
        if mine is not None:
            raise _NothingToDoError(ALREADY_ANSWERED if mine.withdrawn_at is None else ANSWER_WITHDRAWN)

    return FindingActions(
        answer=_action(lambda: review.check_may_answer(finding, user), unanswered),
        add_evidence=_action(lambda: findings.check_may_add_evidence(finding, user)),
        comment=Action(True),
        edit=_action(lambda: findings.check_finder(finding, user)),
        withdraw=_action(lambda: findings.check_may_withdraw(finding, user)),
        raise_level=_action(
            _nothing(HIGHEST_LEVEL) if higher is None else lambda: raise_to(higher),
        ),
        lower_level=_action(
            lambda: moderation.check_moderator(user),
            _nothing(LOWEST_LEVEL)
            if lower is None
            else lambda: moderation.check_may_set_sensitivity(finding, user, lower),
        ),
        verify=_action(lambda: findings.check_may_verify(finding, user), something_to_verify),
    )


def evidence_actions(finding: Finding, evidence: Evidence, viewer: User | None) -> EvidenceActions:
    """What `viewer` may do with one standing evidence item on `finding`."""
    user, refused = _contributor(viewer)
    if user is None:
        return EvidenceActions(vote=refused, verify=refused)
    return EvidenceActions(
        vote=_action(lambda: findings.check_may_vote(finding, evidence, user)),
        verify=_action(lambda: findings.check_may_verify(finding, user, evidence)),
    )
