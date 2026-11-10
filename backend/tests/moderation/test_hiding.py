"""Hidden things disappear for everyone else on the very next request, on every route that showed them.

Each test reads every route that shows the thing, as other people, before
and after a moderator hides it. The check searches the whole body, so a
field nobody thought of can't carry it back out.
"""

from __future__ import annotations

from collections.abc import Callable

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.models import Finding, User
from fieldclub.services import findings
from fieldclub.vocab import EvidenceKind, Role, Tier
from tests.findings.support import add_desk_evidence, answer, create
from tests.helpers import ClientAs, ClientFor, MakeUser, error_code
from tests.moderation.support import API, REASON, comment, log_entries, mention, photo

SECRET = "Meet me at the barrow at midnight with a detector"


def finding_routes(finding: Finding) -> list[str]:
    """Every read route that can show a finding or something on it."""
    pid = finding.public_id
    return [
        f"/findings/{pid}",
        f"/findings/{pid}/comments",
        f"/findings/{pid}/export?format=geojson",
        f"/findings/{pid}/export?format=csv",
        "/findings",
        "/findings?format=geojson",
        "/findings/export?format=geojson",
        "/findings/export?format=csv",
        f"/findings/{pid}/suggested-records",
        f"/geo/search?q={pid}",
        "/review/next",
        "/review/tasks",
    ]


def bodies(client: TestClient, paths: list[str]) -> dict[str, str]:
    return {path: client.get(API + path).text for path in paths}


@pytest.fixture
def people(make_user: MakeUser) -> dict[str, User]:
    return {
        "finder": make_user(handle="Finder"),
        "author": make_user(handle="Author"),
        "member": make_user(handle="Member"),
        "trusted": make_user(Role.TRUSTED, handle="Trusted"),
        "moderator": make_user(Role.MODERATOR, handle="Mod"),
    }


def viewers(
    people: dict[str, User], client_as: ClientAs, client_for: ClientFor, app
) -> dict[str, TestClient]:
    found = {name: client_as(user) for name, user in people.items()}
    found["signed_out"] = client_for(app)
    return found


def test_a_reported_comment_hidden_by_a_moderator_is_gone_at_once_on_every_route(
    db: Session, people: dict[str, User], client_as: ClientAs, client_for: ClientFor, app
) -> None:
    finding = create(db, people["finder"])
    said = comment(db, finding, people["author"], SECRET)
    comment(db, finding, people["member"], "A reply that stays.")
    clients = viewers(people, client_as, client_for, app)
    paths = finding_routes(finding)
    others = ("finder", "member", "trusted", "signed_out")

    for name in others:
        assert SECRET in bodies(clients[name], paths)[f"/findings/{finding.public_id}/comments"], name
    reported = clients["member"].post(
        f"{API}/reports", json={"target_kind": "comment", "target_id": str(said.id), "reason": "illegal"}
    )
    assert reported.status_code == 201
    hidden = clients["moderator"].post(f"{API}/mod/comments/{said.id}/hide", json=REASON)
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["hidden"] is True

    for name in others:
        for path, text in bodies(clients[name], paths).items():
            assert SECRET not in text, (name, path)
            assert "Author" not in text or path != f"/findings/{finding.public_id}/comments", (name, path)
    listed = clients["member"].get(f"{API}/findings/{finding.public_id}/comments").json()["items"]
    assert [(c["deleted"], c["body"], c["author"], c["hidden"]) for c in listed] == [
        (True, None, None, False),
        (False, "A reply that stays.", listed[1]["author"], False),
    ]
    page = clients["member"].get(f"{API}/findings/{finding.public_id}").json()
    assert page["comment_count"] == 1

    # The author and moderators still see it, marked hidden.
    for name in ("author", "moderator"):
        mine = clients[name].get(f"{API}/findings/{finding.public_id}/comments").json()["items"][0]
        assert (mine["body"], mine["hidden"], mine["deleted"]) == (SECRET, True, False), name

    # Nobody else can report it, or delete it, now: it's gone for them.
    again = clients["trusted"].post(
        f"{API}/reports", json={"target_kind": "comment", "target_id": str(said.id), "reason": "spam"}
    )
    assert (again.status_code, error_code(again)) == (404, "target_not_found")

    shown = clients["moderator"].post(f"{API}/mod/comments/{said.id}/unhide", json=REASON)
    assert shown.status_code == 200
    assert SECRET in clients["signed_out"].get(f"{API}/findings/{finding.public_id}/comments").text
    assert clients["member"].get(f"{API}/findings/{finding.public_id}").json()["comment_count"] == 2
    assert [e.action for e in log_entries(db)] == ["hide", "unhide"]


def test_a_hidden_comment_deleted_afterwards_is_counted_once(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = create(db, people["finder"])
    said = comment(db, finding, people["author"])
    moderator = client_as(people["moderator"])
    moderator.post(f"{API}/mod/comments/{said.id}/hide", json=REASON)
    # The author can still remove their own hidden comment.
    assert client_as(people["author"]).delete(f"{API}/comments/{said.id}").status_code == 204
    db.expire_all()
    assert db.get(Finding, finding.id).comment_count == 0  # pyright: ignore[reportOptionalMemberAccess]
    # Once deleted it is gone, so there is nothing left to show again.
    shown = moderator.post(f"{API}/mod/comments/{said.id}/unhide", json=REASON)
    assert (shown.status_code, error_code(shown)) == (404, "target_not_found")
    db.expire_all()
    assert db.get(Finding, finding.id).comment_count == 0  # pyright: ignore[reportOptionalMemberAccess]


def test_a_hidden_finding_is_gone_from_every_route_but_its_finders_and_moderators(
    db: Session, people: dict[str, User], client_as: ClientAs, client_for: ClientFor, app
) -> None:
    finding = create(db, people["finder"], title="Hide this title please")
    clients = viewers(people, client_as, client_for, app)
    paths = finding_routes(finding)
    for name in ("member", "trusted", "signed_out"):
        seen = bodies(clients[name], paths)
        for path in (
            f"/findings/{finding.public_id}",
            "/findings",
            "/findings?format=geojson",
            "/review/next",
        ):
            assert finding.public_id in seen[path], (name, path)

    response = clients["moderator"].post(f"{API}/mod/findings/{finding.public_id}/hide", json=REASON)
    assert response.status_code == 200

    for name in ("member", "trusted", "signed_out", "author"):
        for path, text in bodies(clients[name], paths).items():
            assert finding.public_id not in text, (name, path)
            assert "Hide this title please" not in text, (name, path)
    detail = clients["member"].get(f"{API}/findings/{finding.public_id}")
    assert (detail.status_code, error_code(detail)) == (404, "finding_not_found")
    for name in ("finder", "moderator"):
        assert clients[name].get(f"{API}/findings/{finding.public_id}").status_code == 200, name
    # Nor can anyone else act on it.
    answered = clients["member"].put(
        f"{API}/findings/{finding.public_id}/observation", json={"visible": "yes"}
    )
    assert answered.status_code == 404


def test_hiding_evidence_reassesses_the_finding_and_removes_it_everywhere(
    db: Session, people: dict[str, User], client_as: ClientAs, client_for: ClientFor, app, make_user: MakeUser
) -> None:
    finding = create(db, people["finder"])
    answer(db, finding, make_user())
    answer(db, finding, make_user())
    add_desk_evidence(db, finding, people["author"], EvidenceKind.AERIAL, title="Cropmark photo 1976")
    evidence, _ = add_desk_evidence(
        db, finding, people["member"], EvidenceKind.HISTORIC_MAP, title="OS 6-inch 1888"
    )
    finding = findings.get_finding(db, finding.public_id, None)
    db.refresh(finding)
    assert finding.tier == Tier.SEEN.value
    clients = viewers(people, client_as, client_for, app)
    paths = finding_routes(finding)
    assert "OS 6-inch 1888" in clients["signed_out"].get(f"{API}/findings/{finding.public_id}").text

    response = clients["moderator"].post(f"{API}/mod/evidence/{evidence.id}/hide", json=REASON)
    assert response.status_code == 200, response.text

    for name in ("finder", "author", "member", "trusted", "signed_out", "moderator"):
        for path, text in bodies(clients[name], paths).items():
            assert "OS 6-inch 1888" not in text, (name, path)
    page = clients["finder"].get(f"{API}/findings/{finding.public_id}").json()
    assert page["evidence_count"] == 1
    assert all(credit["evidence_id"] != evidence.id for credit in page["credits"])
    assert all(item["id"] != evidence.id for item in page["evidence"])
    vote = clients["trusted"].put(f"{API}/evidence/{evidence.id}/vote", json={"value": 1})
    assert (vote.status_code, error_code(vote)) == (404, "evidence_not_found")
    # A moderator can still find it, to show it again.
    shown = clients["moderator"].post(f"{API}/mod/evidence/{evidence.id}/unhide", json=REASON)
    assert shown.status_code == 200
    assert "OS 6-inch 1888" in clients["signed_out"].get(f"{API}/findings/{finding.public_id}").text


def test_hiding_evidence_can_move_the_finding_down_with_no_actor(
    db: Session, people: dict[str, User], client_as: ClientAs, make_user: MakeUser
) -> None:
    from fieldclub.models import Activity

    finding = create(db, people["finder"], feature_class="enclosure")
    for _ in range(2):
        answer(db, finding, make_user(), feature_class="enclosure")
    first, _ = add_desk_evidence(db, finding, make_user(), EvidenceKind.AERIAL)
    add_desk_evidence(db, finding, make_user(), EvidenceKind.HISTORIC_MAP)
    db.refresh(finding)
    assert finding.tier == Tier.CORROBORATED.value
    client_as(people["moderator"]).post(f"{API}/mod/evidence/{first.id}/hide", json=REASON)
    db.expire_all()
    finding = findings.get_finding(db, finding.public_id, None)
    assert finding.tier == Tier.SEEN.value
    last = db.query(Activity).order_by(Activity.id.desc()).first()
    assert last is not None
    assert (last.kind, last.actor_id) == ("tier_changed", None)


def test_hiding_a_mention_takes_it_out_of_the_count(
    db: Session, people: dict[str, User], client_as: ClientAs
) -> None:
    finding = create(db, people["finder"])
    talked = mention(db, finding, people["author"])
    mention(db, finding, None, title="Another")
    moderator = client_as(people["moderator"])
    assert moderator.post(f"{API}/mod/mentions/{talked.id}/hide", json=REASON).status_code == 200
    assert client_as(people["member"]).get(f"{API}/findings/{finding.public_id}").json()["mention_count"] == 1
    again = moderator.post(f"{API}/mod/mentions/{talked.id}/hide", json=REASON)
    assert (again.status_code, error_code(again)) == (409, "already_hidden")
    assert moderator.post(f"{API}/mod/mentions/{talked.id}/unhide", json=REASON).status_code == 200
    assert client_as(people["member"]).get(f"{API}/findings/{finding.public_id}").json()["mention_count"] == 2


def test_a_hidden_photo_is_served_only_to_moderators_and_its_uploader(
    db: Session, people: dict[str, User], client_as: ClientAs, client_for: ClientFor, app
) -> None:
    shown = photo(db, people["author"], approved_by=people["trusted"])
    clients = viewers(people, client_as, client_for, app)
    assert clients["signed_out"].get(f"{API}/media/{shown.id}").status_code == 200
    assert clients["moderator"].post(f"{API}/mod/media/{shown.id}/hide", json=REASON).status_code == 200
    for name, status in {
        "signed_out": 404,
        "member": 404,
        "trusted": 404,
        "finder": 404,
        "author": 200,
        "moderator": 200,
    }.items():
        assert clients[name].get(f"{API}/media/{shown.id}").status_code == status, name


# Each kind of hideable target, by its route segment, and how to make one on a finding by a person.
TARGET_MAKERS: list[tuple[str, Callable[[Session, Finding, User], object]]] = [
    ("findings", lambda db, f, u: f.public_id),
    ("comments", lambda db, f, u: comment(db, f, u).id),
    ("evidence", lambda db, f, u: add_desk_evidence(db, f, u)[0].id),
    ("mentions", lambda db, f, u: mention(db, f, u).id),
    ("media", lambda db, f, u: photo(db, u).id),
]


@pytest.mark.parametrize(("segment", "make"), TARGET_MAKERS)
def test_hide_twice_unhide_twice_and_unknown_targets(
    segment: str,
    make: Callable[[Session, Finding, User], object],
    db: Session,
    people: dict[str, User],
    client_as: ClientAs,
) -> None:
    finding = create(db, people["finder"])
    ref = make(db, finding, people["author"])
    client = client_as(people["moderator"])
    assert client.post(f"{API}/mod/{segment}/{ref}/hide", json=REASON).status_code == 200
    twice = client.post(f"{API}/mod/{segment}/{ref}/hide", json=REASON)
    assert (twice.status_code, error_code(twice)) == (409, "already_hidden")
    assert client.post(f"{API}/mod/{segment}/{ref}/unhide", json=REASON).status_code == 200
    twice = client.post(f"{API}/mod/{segment}/{ref}/unhide", json=REASON)
    assert (twice.status_code, error_code(twice)) == (409, "not_hidden")
    missing = client.post(f"{API}/mod/{segment}/987654/hide", json=REASON)
    assert (missing.status_code, error_code(missing)) == (404, "target_not_found")
    no_reason = client.post(f"{API}/mod/{segment}/{ref}/hide", json={"reason": ""})
    assert no_reason.status_code == 422


@pytest.mark.parametrize(("segment", "make"), TARGET_MAKERS)
def test_a_moderator_does_not_hide_or_show_their_own_work(
    segment: str,
    make: Callable[[Session, Finding, User], object],
    db: Session,
    client_as: ClientAs,
    make_user: MakeUser,
) -> None:
    mine = make_user(Role.MODERATOR, handle="Mine")
    finding = create(db, mine)
    ref = make(db, finding, mine)
    someone_else = make_user(Role.MODERATOR, handle="Other")
    me, other = client_as(mine), client_as(someone_else)
    hidden = me.post(f"{API}/mod/{segment}/{ref}/hide", json=REASON)
    assert (hidden.status_code, error_code(hidden)) == (403, "own_content")
    # Another moderator hides it, and its author can't undo that.
    assert other.post(f"{API}/mod/{segment}/{ref}/hide", json=REASON).status_code == 200
    shown = me.post(f"{API}/mod/{segment}/{ref}/unhide", json=REASON)
    assert (shown.status_code, error_code(shown)) == (403, "own_content")
    assert [(e.action, e.actor_id) for e in log_entries(db)] == [("hide", someone_else.id)]


def test_a_moderator_does_not_set_the_level_of_their_own_finding(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    mine = make_user(Role.MODERATOR)
    barrow = create(db, mine, feature_class="round_barrow")
    response = client_as(mine).put(
        f"{API}/mod/findings/{barrow.public_id}/sensitivity", json={"level": "open", **REASON}
    )
    assert (response.status_code, error_code(response)) == (403, "own_content")
    db.refresh(barrow)
    assert barrow.sensitivity == "protected"
    assert log_entries(db) == []
