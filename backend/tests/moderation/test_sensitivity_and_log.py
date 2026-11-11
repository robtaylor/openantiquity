"""A moderator's location level, and the log of every moderator's actions."""

from __future__ import annotations

from sqlalchemy.orm import Session

from fieldclub.vocab import Role
from tests.findings.support import create
from tests.helpers import ClientAs, MakeUser, error_code
from tests.moderation.support import API, REASON, comment, log_entries, photo


def test_a_moderator_lowers_a_level_as_well_as_raising_it(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    barrow = create(db, make_user(), feature_class="round_barrow")
    assert barrow.sensitivity == "protected"
    client = client_as(make_user(Role.MODERATOR, handle="Mod"))
    path = f"{API}/mod/findings/{barrow.public_id}/sensitivity"
    lowered = client.put(path, json={"level": "open", "reason": "A field boundary, not a barrow."})
    assert lowered.status_code == 200, lowered.text
    assert lowered.json()["sensitivity"] == "open"
    raised = client.put(path, json={"level": "restricted", **REASON})
    assert raised.json()["sensitivity"] == "restricted"
    # Setting the level it has is no change, and isn't logged.
    assert client.put(path, json={"level": "restricted", **REASON}).status_code == 200
    entries = log_entries(db)
    assert [(e.action, e.data) for e in entries] == [
        ("change_sensitivity", {"from": "protected", "to": "open"}),
        ("change_sensitivity", {"from": "open", "to": "restricted"}),
    ]
    assert entries[0].reason == "A field boundary, not a barrow."
    db.refresh(barrow)
    assert barrow.sensitivity == "restricted"


def test_only_moderators_use_the_moderators_route(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    barrow = create(db, finder, feature_class="round_barrow")
    for who in (finder, make_user(Role.TRUSTED), make_user(Role.EXPERT)):
        response = client_as(who).put(
            f"{API}/mod/findings/{barrow.public_id}/sensitivity", json={"level": "restricted", **REASON}
        )
        assert (response.status_code, error_code(response)) == (403, "moderators_only")
    missing = client_as(make_user(Role.MODERATOR)).put(
        f"{API}/mod/findings/ZZZZZZ/sensitivity", json={"level": "open", **REASON}
    )
    assert (missing.status_code, error_code(missing)) == (404, "finding_not_found")


def test_the_log_names_who_did_what_to_which_target_and_why(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    owner = make_user(handle="Owner")
    finding = create(db, owner)
    said = comment(db, finding, owner, "Rude words")
    waiting = photo(db, owner)
    moderator = client_as(make_user(Role.MODERATOR, handle="Mod"))
    trusted = client_as(make_user(Role.TRUSTED, handle="Helper"))
    moderator.post(f"{API}/mod/comments/{said.id}/hide", json={"reason": "Abusive."})
    moderator.post(f"{API}/mod/findings/{finding.public_id}/hide", json={"reason": "Spam finding."})
    trusted.post(f"{API}/mod/media/{waiting.id}/approve")
    moderator.post(f"{API}/mod/users/Owner/ban", json={"reason": "Repeated abuse."})

    response = moderator.get(f"{API}/mod/actions")
    assert response.status_code == 200
    items = response.json()["items"]
    assert [(i["actor"]["handle"], i["action"], i["target"]["kind"], i["reason"]) for i in items] == [
        ("Mod", "ban", "user", "Repeated abuse."),
        ("Helper", "approve_photo", "photo", None),
        ("Mod", "hide", "finding", "Spam finding."),
        ("Mod", "hide", "comment", "Abusive."),
    ]
    assert items[0]["target"]["ref"] == "Owner"
    assert items[2]["target"]["ref"] == finding.public_id
    assert items[3]["target"]["body"] == "Rude words"
    assert all(i["created_at"] for i in items)

    one = moderator.get(f"{API}/mod/actions", params={"target_kind": "comment", "target_id": str(said.id)})
    assert [i["action"] for i in one.json()["items"]] == ["hide"]
    nothing = moderator.get(f"{API}/mod/actions", params={"target_kind": "user", "target_id": "Nobody"})
    assert nothing.json()["items"] == []
    alone = moderator.get(f"{API}/mod/actions", params={"target_id": "Owner"})
    assert (alone.status_code, error_code(alone)) == (400, "target_kind_required")
    first = moderator.get(f"{API}/mod/actions", params={"limit": 3}).json()
    rest = moderator.get(f"{API}/mod/actions", params={"limit": 3, "cursor": first["next_cursor"]}).json()
    assert [i["id"] for i in first["items"] + rest["items"]] == [i["id"] for i in items]


def test_a_moderator_raising_someone_elses_level_through_the_ordinary_route_is_logged(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder, moderator = make_user(handle="Finder"), make_user(Role.MODERATOR, handle="Mod")
    finding = create(db, finder)
    raised = client_as(moderator).put(
        f"{API}/findings/{finding.public_id}/sensitivity", json={"level": "restricted"}
    )
    assert raised.status_code == 200, raised.text
    (entry,) = log_entries(db)
    assert (entry.actor_id, entry.action, entry.target_kind, entry.target_id) == (
        moderator.id,
        "change_sensitivity",
        "finding",
        finding.id,
    )
    assert entry.data == {"from": "open", "to": "restricted"}
    # Asking for the level it already has changes nothing and logs nothing.
    client_as(moderator).put(f"{API}/findings/{finding.public_id}/sensitivity", json={"level": "restricted"})
    assert len(log_entries(db)) == 1


def test_a_finder_or_trusted_member_raising_a_level_is_not_moderation(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user(Role.MODERATOR, handle="ModeratorFinder")
    own = create(db, finder)
    other = create(db, make_user(), lon=-1.85, lat=51.43)
    client_as(finder).put(f"{API}/findings/{own.public_id}/sensitivity", json={"level": "restricted"})
    trusted = make_user(Role.TRUSTED)
    client_as(trusted).put(f"{API}/findings/{other.public_id}/sensitivity", json={"level": "restricted"})
    db.expire_all()
    assert (own.sensitivity, other.sensitivity) == ("restricted", "restricted")
    assert log_entries(db) == []
