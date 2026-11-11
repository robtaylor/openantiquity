"""The record of what moderators do can't be skipped.

Every route that changes something is either a moderation route, which logs
what a moderator does with it, or one that acts only for the caller, which
refuses a moderator what only a moderator could do to someone else's work.
"""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.orm import Session

from fieldclub.vocab import Role
from tests.findings.support import add_desk_evidence
from tests.helpers import ClientAs, MakeFinding, MakeUser, error_code
from tests.moderation.support import API, Route, comment, log_entries, mention

WRITE_METHODS = {"post", "put", "patch", "delete"}
LOGGED_PREFIX = f"{API}/mod/"

# Every other write route, and why a moderator using it on someone else's work needs no log entry.
FOR_THE_CALLER = {
    ("POST", f"{API}/auth/dev-login"): "signs in, in development only",
    ("POST", f"{API}/auth/welcome"): "the caller's own welcome step",
    ("PATCH", f"{API}/auth/me"): "the caller's own account",
    ("DELETE", f"{API}/auth/me"): "the caller's own account",
    ("POST", f"{API}/auth/logout"): "the caller's own session",
    ("POST", f"{API}/auth/oauth/{{provider}}/callback"): "signs in",
    ("POST", f"{API}/auth/email/start"): "signs in",
    ("POST", f"{API}/auth/email/verify"): "signs in",
    ("POST", f"{API}/findings"): "marks a finding as the caller",
    ("PATCH", f"{API}/findings/{{public_id}}"): "the finder only: not_finder",
    ("POST", f"{API}/findings/{{public_id}}/withdraw"): "the finder only: not_finder",
    ("PUT", f"{API}/findings/{{public_id}}/sensitivity"): "raises only, as any trusted member may",
    ("POST", f"{API}/findings/{{public_id}}/comments"): "comments as the caller",
    ("DELETE", f"{API}/comments/{{comment_id}}"): "its author only: comment_forbidden",
    ("PUT", f"{API}/findings/{{public_id}}/follow"): "the caller's own follow",
    ("DELETE", f"{API}/findings/{{public_id}}/follow"): "the caller's own follow",
    ("POST", f"{API}/findings/{{public_id}}/evidence"): "adds evidence as the caller",
    ("DELETE", f"{API}/evidence/{{evidence_id}}"): "its contributor only: evidence_forbidden",
    ("PUT", f"{API}/evidence/{{evidence_id}}/vote"): "the caller's own vote",
    ("POST", f"{API}/evidence/{{evidence_id}}/verify"): "the caller's own check, which experts make too",
    ("PUT", f"{API}/findings/{{public_id}}/observation"): "the caller's own answer",
    ("DELETE", f"{API}/findings/{{public_id}}/observation"): "the caller's own answer",
    ("POST", f"{API}/media"): "uploads as the caller",
    ("POST", f"{API}/reports"): "reports as the caller",
    ("POST", f"{API}/terrain/profile"): "reads elevation, changes nothing",
    ("POST", f"{API}/notifications/read"): "the caller's own notifications",
    ("PUT", f"{API}/squares/{{ref}}"): "the caller's own survey of a square",
    ("POST", f"{API}/investigations"): "starts an investigation as the caller",
    ("PATCH", f"{API}/investigations/{{public_id}}"): "its owner and editors only",
    ("DELETE", f"{API}/investigations/{{public_id}}"): "its owner only: investigation_owner_only",
    ("POST", f"{API}/investigations/{{public_id}}/items"): "its owner and editors only",
    ("PATCH", f"{API}/investigations/{{public_id}}/items/{{item_id}}"): "its owner and editors only",
    ("POST", f"{API}/investigations/{{public_id}}/items/{{item_id}}/move"): "its owner and editors only",
    ("DELETE", f"{API}/investigations/{{public_id}}/items/{{item_id}}"): "its owner and editors only",
    ("PUT", f"{API}/investigations/{{public_id}}/members/{{handle}}"): "its owner only",
    ("DELETE", f"{API}/investigations/{{public_id}}/members/{{handle}}"): "its owner, or the member leaving",
    ("POST", f"{API}/investigations/{{public_id}}/invitation"): "the caller's own invitation",
    ("POST", f"{API}/findings/{{public_id}}/mentions"): "adds a mention as the caller",
    ("POST", f"{API}/mentions/preview"): "fetches an address, stores nothing",
    ("DELETE", f"{API}/mentions/{{mention_id}}"): "the person who added it only: mention_forbidden",
}


def test_every_write_route_is_logged_or_acts_only_for_the_caller(app: FastAPI) -> None:
    writes = {
        (method.upper(), path)
        for path, operations in app.openapi()["paths"].items()
        for method in operations
        if method in WRITE_METHODS
    }
    logged = {route for route in writes if route[1].startswith(LOGGED_PREFIX)}
    assert logged, "the moderation routes are mounted"
    # A new write route has to be added to one side or the other, with its reason.
    assert writes - logged == set(FOR_THE_CALLER)


def test_every_moderation_write_on_someone_elses_work_is_logged(
    db: Session, routes: list[Route], make_user: MakeUser, client_as: ClientAs
) -> None:
    moderator = make_user(Role.MODERATOR, handle="Acting")
    client = client_as(moderator)
    for route in routes:
        if route.method == "GET" or not route.path.startswith("/mod/"):
            continue
        before = len(log_entries(db))
        response = client.request(route.method, API + route.path, json=route.body)
        assert response.status_code == 200, (route.method, route.path, response.text)
        entries = log_entries(db)
        assert len(entries) == before + 1, (route.method, route.path)
        assert entries[-1].actor_id == moderator.id


def test_a_moderator_cannot_skip_the_log_through_the_members_routes(
    db: Session, client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding
) -> None:
    owner = make_user(handle="Owner")
    finding = make_finding(owner, sensitivity="restricted")
    said = comment(db, finding, owner)
    evidence, _ = add_desk_evidence(db, finding, owner)
    talked = mention(db, finding, owner)
    scanned = mention(db, finding, None, title="Found by the scan")
    client = client_as(make_user(Role.MODERATOR))
    pid = finding.public_id
    refusals = [
        ("PUT", f"/findings/{pid}/sensitivity", {"level": "open"}, "lower_through_moderation"),
        ("PUT", f"/findings/{pid}/sensitivity", {"level": "protected"}, "lower_through_moderation"),
        ("DELETE", f"/comments/{said.id}", None, "comment_forbidden"),
        ("DELETE", f"/evidence/{evidence.id}", None, "evidence_forbidden"),
        ("DELETE", f"/mentions/{talked.id}", None, "mention_forbidden"),
        ("DELETE", f"/mentions/{scanned.id}", None, "mention_forbidden"),
        ("PATCH", f"/findings/{pid}", {"title": "Renamed by a moderator"}, "not_finder"),
        ("POST", f"/findings/{pid}/withdraw", None, "not_finder"),
    ]
    for method, path, body, code in refusals:
        response = client.request(method, API + path, json=body)
        assert (response.status_code, error_code(response)) == (403, code), (method, path, response.text)
    db.expire_all()
    assert finding.sensitivity == "restricted"
    assert finding.title != "Renamed by a moderator"
    assert finding.state != "withdrawn"
    assert said.deleted_at is None
    assert evidence.deleted_at is None
    assert talked.deleted_at is None
    assert scanned.deleted_at is None
    assert log_entries(db) == []
