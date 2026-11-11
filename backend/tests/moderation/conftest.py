"""Fixtures shared by the moderation tests."""

from __future__ import annotations

import pytest
from sqlalchemy.orm import Session

from fieldclub.models import Report
from fieldclub.vocab import Role
from tests.findings.support import add_desk_evidence
from tests.helpers import MakeFinding, MakeUser
from tests.investigations.support import make
from tests.moderation.support import (
    APPROVERS,
    CONTRIBUTORS,
    MODERATORS,
    REASON,
    Route,
    comment,
    jpeg,
    mention,
    photo,
)


@pytest.fixture
def routes(db: Session, make_user: MakeUser, make_finding: MakeFinding) -> list[Route]:
    """Each moderation route, aimed at something that exists and belongs to someone other than the caller.

    In this order each route acts on something still there: unhide follows hide.
    """
    owner = make_user(handle="Owner")
    target = make_user(handle="Target")
    approver = make_user(Role.MODERATOR, handle="EarlierModerator")
    finding = make_finding(owner)
    said = comment(db, finding, owner)
    evidence, _ = add_desk_evidence(db, finding, make_user())
    talked = mention(db, finding, owner)
    waiting = photo(db, owner)
    refused = photo(db, owner, data=jpeg(colour=(10, 200, 30)))
    shown = photo(db, owner, approved_by=approver)
    report = Report(reporter_id=owner.id, target_kind="comment", target_id=said.id, reason="spam")
    db.add(report)
    db.commit()
    notebook = make(db, owner, title="A notebook to hide")
    pid = finding.public_id
    hide_targets = {
        "findings": pid,
        "comments": said.id,
        "evidence": evidence.id,
        "mentions": talked.id,
        "media": shown.id,
        "investigations": notebook.public_id,
    }
    found = [
        Route("GET", "/mod/reports", None, MODERATORS),
        Route(
            "POST", f"/mod/reports/{report.id}/resolve", {"outcome": "upheld", "note": "Spam."}, MODERATORS
        ),
        Route("PUT", f"/mod/findings/{pid}/sensitivity", {"level": "restricted", **REASON}, MODERATORS),
        Route("GET", "/mod/users/eligible", None, MODERATORS),
        Route("GET", "/mod/users/Target", None, MODERATORS),
        Route("PUT", "/mod/users/Target/role", {"role": "expert", **REASON}, MODERATORS),
        Route("POST", "/mod/users/Target/ban", REASON, MODERATORS),
        Route("POST", "/mod/users/Target/unban", REASON, MODERATORS),
        Route("GET", "/mod/actions", None, MODERATORS),
        Route("GET", "/mod/media", None, APPROVERS),
        Route("POST", f"/mod/media/{waiting.id}/approve", None, APPROVERS),
        Route("POST", f"/mod/media/{refused.id}/reject", REASON, APPROVERS),
        Route(
            "POST",
            "/reports",
            {"target_kind": "user", "target_id": target.handle, "reason": "abuse"},
            CONTRIBUTORS,
        ),
    ]
    found.extend(
        Route("POST", f"/mod/{segment}/{ref}/{verb}", REASON, MODERATORS)
        for segment, ref in hide_targets.items()
        for verb in ("hide", "unhide")
    )
    return found
