"""A finding's page says what the viewer may do, and each flag is what its route then really does.

`services.actions` works each flag out from the check functions the routes
run. These tests hold every flag to the route: for every kind of viewer,
level and state, an allowed action succeeds and a refused one fails with the
reason the flag gave.
"""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.models import Evidence, Finding, User
from fieldclub.services import findings
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, FeatureClass, Sensitivity, Visible
from tests.findings.support import API, add_desk_evidence, answer, create
from tests.helpers import ClientAs, MakeUser, error_code

VIEWERS = ("signed_out", "newcomer", "member", "finder", "trusted", "expert", "moderator")
LEVELS = list(Sensitivity)
NOTHING_TO_DO = {"already_answered", "highest_level", "lowest_level"}


class Case:
    """One fresh finding at a level and state, seen by one kind of viewer."""

    def __init__(
        self, db: Session, make_user: MakeUser, client_as: ClientAs, anonymous: TestClient, viewer: str
    ) -> None:
        self.db = db
        self.make_user = make_user
        self.viewer: User | None = None
        if viewer == "newcomer":
            self.viewer = make_user(age_band=None, terms_accepted_at=None)
        elif viewer == "finder":
            self.viewer = make_user()
        elif viewer != "signed_out":
            self.viewer = make_user(viewer)
        self.client = client_as(self.viewer) if self.viewer is not None else anonymous
        self.is_finder = viewer == "finder"

    def finding(self, level: Sensitivity, withdrawn: bool) -> Finding:
        author = self.viewer if self.is_finder and self.viewer is not None else self.make_user()
        finding = create(
            self.db,
            author,
            feature_class=FeatureClass.ENCLOSURE,
            requested_sensitivity=level,
        )
        assert finding.sensitivity == level.value, "an enclosure starts at the level asked for"
        # Evidence by third people, trusted so that they see a restricted finding exactly.
        self.official, _ = findings.add_evidence(
            self.db,
            findings.lock(self.db, finding),
            self.make_user("trusted"),
            EvidenceFields(kind=EvidenceKind.HER_RECORD, reference="MWI1234"),
        )
        self.desk, _ = add_desk_evidence(self.db, finding, self.make_user("trusted"))
        self.db.commit()
        if withdrawn:
            findings.withdraw_finding(self.db, findings.lock(self.db, finding), self._author(finding))
            self.db.commit()
        return finding

    def _author(self, finding: Finding) -> User:
        author = self.db.get(User, finding.author_id)
        assert author is not None
        return author

    def page(self, finding: Finding) -> dict[str, Any]:
        response = self.client.get(f"{API}/findings/{finding.public_id}")
        assert response.status_code == 200, response.text
        return response.json()


def _holds(flag: dict[str, Any], response: Any, where: str) -> None:
    if flag["allowed"]:
        assert flag["reason"] is None, where
        assert response.status_code < 300, f"{where}: allowed, but {response.status_code} {response.text}"
    else:
        assert response.status_code >= 400, f"{where}: refused as {flag['reason']}, but it worked"
        assert error_code(response) == flag["reason"], where


def _next_level(finding: Finding, step: int) -> str | None:
    order = list(Sensitivity)
    index = order.index(Sensitivity(finding.sensitivity)) + step
    return order[index].value if 0 <= index < len(order) else None


# Each action's route, called as the case's viewer. None when there is nothing to call.
Route = Callable[[Case, Finding], Any]

ROUTES: dict[str, Route] = {
    "answer": lambda c, f: c.client.put(f"{API}/findings/{f.public_id}/observation", json={"visible": "yes"}),
    "add_evidence": lambda c, f: c.client.post(
        f"{API}/findings/{f.public_id}/evidence", json={"kind": "document", "title": "Parish history"}
    ),
    "comment": lambda c, f: c.client.post(f"{API}/findings/{f.public_id}/comments", json={"body": "Hmm."}),
    "edit": lambda c, f: c.client.patch(f"{API}/findings/{f.public_id}", json={"title": "A bank"}),
    "withdraw": lambda c, f: c.client.post(f"{API}/findings/{f.public_id}/withdraw"),
    "raise_level": lambda c, f: c.client.put(
        f"{API}/findings/{f.public_id}/sensitivity", json={"level": _next_level(f, 1)}
    ),
    "lower_level": lambda c, f: c.client.put(
        f"{API}/mod/findings/{f.public_id}/sensitivity",
        json={"level": _next_level(f, -1), "reason": "Checked"},
    ),
    "verify": lambda c, f: c.client.post(f"{API}/evidence/{c.official.id}/verify"),
}


@pytest.mark.parametrize("withdrawn", [False, True], ids=["open", "withdrawn"])
@pytest.mark.parametrize("level", LEVELS, ids=[level.value for level in LEVELS])
@pytest.mark.parametrize("action", list(ROUTES))
def test_each_flag_is_what_its_route_does(
    db: Session,
    make_user: MakeUser,
    client_as: ClientAs,
    client: TestClient,
    action: str,
    level: Sensitivity,
    withdrawn: bool,
) -> None:
    seen: set[tuple[bool, str | None]] = set()
    for viewer in VIEWERS:
        case = Case(db, make_user, client_as, client, viewer)
        finding = case.finding(level, withdrawn)
        flag = case.page(finding)["actions"][action]
        where = f"{action} by {viewer} on a {level.value} finding, {'withdrawn' if withdrawn else 'open'}"
        seen.add((flag["allowed"], flag["reason"]))
        if flag["reason"] in NOTHING_TO_DO:
            assert action in {"raise_level", "lower_level"}, where
            assert _next_level(finding, 1 if action == "raise_level" else -1) is None, where
            continue
        _holds(flag, ROUTES[action](case, finding), where)
    assert len(seen) > 1 or action == "comment", f"{action} never varies, so the test proves little"


def test_someone_who_has_answered_has_nothing_to_answer(
    db: Session, make_user: MakeUser, client_as: ClientAs, client: TestClient
) -> None:
    case = Case(db, make_user, client_as, client, "member")
    finding = case.finding(Sensitivity.OPEN, withdrawn=False)
    assert case.page(finding)["actions"]["answer"] == {"allowed": True, "reason": None}
    assert case.viewer is not None
    answer(db, finding, case.viewer, Visible.YES, detail_follows=True)
    assert case.page(finding)["actions"]["answer"] == {"allowed": False, "reason": "already_answered"}
    # A different answer is refused, which is what "nothing to answer" spares the client from finding out.
    response = case.client.put(f"{API}/findings/{finding.public_id}/observation", json={"visible": "no"})
    assert error_code(response) == "answer_final"


EVIDENCE_ROUTES: dict[str, Callable[[Case, Evidence], Any]] = {
    "vote": lambda c, e: c.client.put(f"{API}/evidence/{e.id}/vote", json={"value": 1}),
    "verify": lambda c, e: c.client.post(f"{API}/evidence/{e.id}/verify"),
}


@pytest.mark.parametrize("withdrawn", [False, True], ids=["open", "withdrawn"])
@pytest.mark.parametrize("level", LEVELS, ids=[level.value for level in LEVELS])
@pytest.mark.parametrize("action", list(EVIDENCE_ROUTES))
def test_each_evidence_flag_is_what_its_route_does(
    db: Session,
    make_user: MakeUser,
    client_as: ClientAs,
    client: TestClient,
    action: str,
    level: Sensitivity,
    withdrawn: bool,
) -> None:
    for viewer in VIEWERS:
        for which in ("official", "desk", "own"):
            case = Case(db, make_user, client_as, client, viewer)
            finding = case.finding(level, withdrawn)
            item = {"official": case.official, "desk": case.desk}.get(which)
            if which == "own":
                if case.viewer is None or withdrawn:
                    continue
                item = Evidence(
                    finding_id=finding.id, user_id=case.viewer.id, kind="her_record", stance="supports"
                )
                db.add(item)
                db.commit()
            assert item is not None
            page = case.page(finding)
            flags = next(e["actions"] for e in page["evidence"] if e["id"] == item.id)
            where = f"{action} on {which} evidence by {viewer}, {level.value}, withdrawn={withdrawn}"
            _holds(flags[action], EVIDENCE_ROUTES[action](case, item), where)
