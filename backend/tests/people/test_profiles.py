"""People's pages: GET /users/{handle}, its findings, contributions and points."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.auth import accounts
from fieldclub.models import Mention, ReputationEvent, User
from fieldclub.services import findings
from fieldclub.vocab import AgeBand, Visible
from tests.activity.support import API, add_map, comment, items
from tests.findings.support import answer, create
from tests.helpers import ClientAs, MakeUser, error_code

ROUTES = ("", "/findings", "/contributions", "/points")


def mention(db: Session, finding_id: int, user: User, n: int = 1) -> int:
    made = Mention(
        finding_id=finding_id,
        user_id=user.id,
        kind="video",
        url=f"https://video.example/watch?v={n}",
        canonical_url=f"https://video.example/{n}",
        title="Walking the bank",
    )
    db.add(made)
    db.commit()
    return made.id


def test_a_profile(db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs) -> None:
    ann = make_user(
        handle="AnnDigs",
        display_name="Ann Smith",
        avatar_url="https://provider.example/ann.png",
        bio="Parish surveys on the Downs.",
        role="trusted",
    )
    other = make_user()
    mine = create(db, ann)
    theirs = create(db, other)
    add_map(db, theirs, ann)
    comment(db, theirs, ann)
    answer(db, theirs, ann, Visible.YES)
    mention(db, mine.id, ann)
    db.add(ReputationEvent(user_id=ann.id, delta=2, reason="tier_seen", finding_id=mine.id))
    ann.reputation = 2
    db.commit()

    response = client.get(f"{API}/users/anndigs")
    assert response.headers["cache-control"] == "private, no-cache"
    body = response.json()
    assert body == {
        "handle": "AnnDigs",
        "display_name": "Ann Smith",
        "avatar_url": "https://provider.example/ann.png",
        "role": "trusted",
        "bio": "Parish surveys on the Downs.",
        "joined_at": body["joined_at"],
        "reputation": 2,
        "reputation_total": None,
        "counts": {"findings": 1, "second_looks": 1, "evidence": 1, "comments": 1, "mentions": 1},
        "is_me": False,
    }
    assert datetime.fromisoformat(body["joined_at"]) == ann.created_at
    me = client_as(ann).get(f"{API}/users/AnnDigs").json()
    assert (me["is_me"], me["reputation_total"]) == (True, 2)


@pytest.mark.parametrize("band", [AgeBand.AGE_16_17.value, None])
def test_16_to_17_and_unbanded_accounts_show_only_their_handle(
    db: Session, make_user: MakeUser, client: TestClient, band: str | None
) -> None:
    make_user(
        handle="YoungDigger",
        display_name="Real Name",
        avatar_url="https://provider.example/face.png",
        bio="Text me on 07700 900000",
        age_band=band,
        terms_accepted_at=None if band is None else datetime(2026, 1, 1, tzinfo=UTC),
    )
    body = client.get(f"{API}/users/YoungDigger").json()
    assert (body["display_name"], body["avatar_url"], body["bio"]) == ("YoungDigger", None, None)
    assert "Real Name" not in str(body)
    assert "07700" not in str(body)
    assert "age_band" not in body


@pytest.mark.parametrize("route", ROUTES)
def test_deleted_and_banned_accounts_are_not_found(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs, route: str
) -> None:
    banned, leaver, moderator = make_user(handle="Banned"), make_user(handle="Leaver"), make_user("moderator")
    create(db, banned)
    banned.banned_at = datetime.now(UTC)
    accounts.delete_account(db, leaver)
    db.commit()
    for viewer in (client, client_as(moderator)):
        for handle in ("Banned", "Leaver", leaver.handle, "Nobody"):
            assert error_code(viewer.get(f"{API}/users/{handle}{route}")) == "user_not_found"
    too_long = client.get(f"{API}/users/{'a' * 31}{route}")
    assert error_code(too_long) == "validation_error"


def test_their_findings_leave_out_withdrawn_and_hidden_ones(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    ann = make_user(handle="Ann")
    kept = [create(db, ann, title=f"Kept {n}") for n in range(3)]
    hidden = create(db, ann, title="Hidden")
    withdrawn = create(db, ann, title="Withdrawn")
    hidden.hidden_at = datetime.now(UTC)
    db.commit()
    findings.withdraw_finding(db, findings.lock(db, withdrawn), ann)
    db.commit()

    first = client.get(f"{API}/users/Ann/findings", params={"limit": 2}).json()
    rest = client.get(f"{API}/users/Ann/findings", params={"limit": 2, "cursor": first["next_cursor"]}).json()
    titles = [item["title"] for item in first["items"] + rest["items"]]
    assert titles == [f.title for f in reversed(kept)]
    assert rest["next_cursor"] is None
    assert client.get(f"{API}/users/Ann").json()["counts"]["findings"] == 3
    # The finder and moderators may still see a hidden finding; nobody lists a withdrawn one.
    for viewer in (client_as(ann), client_as(make_user("moderator"))):
        listed = {item["title"] for item in items(viewer.get(f"{API}/users/Ann/findings"))}
        assert listed == {"Kept 0", "Kept 1", "Kept 2", "Hidden"}
        assert viewer.get(f"{API}/users/Ann").json()["counts"]["findings"] == 4


def test_contributions_newest_first_across_kinds(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    ann, finder = make_user(handle="Ann"), make_user()
    finding = create(db, finder)
    evidence_id = add_map(db, finding, ann)
    first_comment = comment(db, finding, ann)
    mention_id = mention(db, finding.id, ann)
    second_comment = comment(db, finding, ann)
    deleted = comment(db, finding, ann)
    findings.delete_comment(db, deleted, ann)
    db.commit()

    seen: list[tuple[str, int]] = []
    cursor = None
    while True:
        params: dict[str, Any] = {"limit": 1}
        if cursor:
            params["cursor"] = cursor
        page = client.get(f"{API}/users/Ann/contributions", params=params).json()
        seen += [(item["kind"], item["id"]) for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert seen == [
        ("comment", second_comment),
        ("mention", mention_id),
        ("comment", first_comment),
        ("evidence", evidence_id),
    ]
    listed = items(client.get(f"{API}/users/Ann/contributions"))
    by_kind = {item["kind"]: item for item in listed}
    assert by_kind["evidence"]["subkind"] == "historic_map"
    assert by_kind["mention"]["subkind"] == "video"
    assert by_kind["comment"]["subkind"] is None
    assert all(item["finding"]["public_id"] == finding.public_id for item in listed)
    assert all(item["created_at"] is not None for item in listed)
    only_comments = items(client.get(f"{API}/users/Ann/contributions", params={"kind": "comment"}))
    assert [item["id"] for item in only_comments] == [second_comment, first_comment]
    counts = client.get(f"{API}/users/Ann").json()["counts"]
    assert (counts["evidence"], counts["comments"], counts["mentions"]) == (1, 2, 1)


@pytest.mark.parametrize("cursor", ["nonsense", "WyJ4IiwiY29tbWVudCIsMV0", "WzFd"])
def test_a_bad_contributions_cursor(
    db: Session, make_user: MakeUser, client: TestClient, cursor: str
) -> None:
    make_user(handle="Ann")
    response = client.get(f"{API}/users/Ann/contributions", params={"cursor": cursor})
    assert error_code(response) == "invalid_cursor"


def test_second_looks_are_listed_by_finding_and_paged(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    ann, finder = make_user(handle="Ann"), make_user()
    looked = [create(db, finder) for _ in range(3)]
    for finding in reversed(looked):  # answered in the opposite order to the findings
        answer(db, finding, ann, Visible.UNSURE)
    first = client.get(f"{API}/users/Ann/contributions", params={"kind": "second_look", "limit": 2}).json()
    rest = client.get(
        f"{API}/users/Ann/contributions", params={"kind": "second_look", "cursor": first["next_cursor"]}
    ).json()
    order = [item["finding"]["public_id"] for item in first["items"] + rest["items"]]
    assert order == [f.public_id for f in reversed(looked)]  # newest finding first, whatever the answer order


def test_points_are_for_the_person_alone(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    ann, finder = make_user(handle="Ann"), make_user()
    finding = create(db, finder)
    gone = create(db, finder)
    db.add_all(
        [
            ReputationEvent(
                user_id=ann.id, delta=1, reason="observation_corroborated", finding_id=finding.id
            ),
            ReputationEvent(user_id=ann.id, delta=1, reason="evidence_endorsed_9", finding_id=gone.id),
        ]
    )
    ann.reputation = 2
    gone.hidden_at = datetime.now(UTC)
    db.commit()

    assert error_code(client.get(f"{API}/users/Ann/points")) == "points_are_private"
    assert (
        error_code(client_as(make_user("moderator")).get(f"{API}/users/Ann/points")) == "points_are_private"
    )
    mine = items(client_as(ann).get(f"{API}/users/Ann/points"))
    assert [(item["reason"], item["delta"]) for item in mine] == [
        ("evidence_endorsed_9", 1),
        ("observation_corroborated", 1),
    ]
    assert mine[0]["finding"] is None  # hidden since
    assert mine[1]["finding"]["public_id"] == finding.public_id
    # Others see the points that say nothing about an answer.
    assert client.get(f"{API}/users/Ann").json()["reputation"] == 1
