"""Roles, the list of members who could be made trusted, and bans (Decisions 0005 and 0008)."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, Finding, ReputationEvent, UserSession
from fieldclub.services import findings, reputation
from fieldclub.vocab import EvidenceKind, Role, Tier
from tests.findings.support import add_desk_evidence, answer, create
from tests.helpers import ClientAs, MakeUser, count, error_code
from tests.moderation.support import API, REASON, log_entries

ROLES = [role.value for role in Role]


def set_role(client, handle: str, role: str):
    return client.put(f"{API}/mod/users/{handle}/role", json={"role": role, **REASON})


def expected(actor: str, current: str, new: str) -> bool:
    """Whether `actor` may move someone from `current` to `new`: admins are never made here,
    and only an admin makes or unmakes a moderator."""
    if Role.ADMIN.value in (current, new):
        return False
    return actor == Role.ADMIN.value or Role.MODERATOR.value not in (current, new)


@pytest.mark.parametrize("actor", ["moderator", "admin"])
@pytest.mark.parametrize("current", ROLES)
@pytest.mark.parametrize("new", ROLES)
def test_every_role_change_in_every_direction(
    actor: str, current: str, new: str, client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    target = make_user(current, handle="Target", reputation=60.0)
    response = set_role(client_as(make_user(actor)), "Target", new)
    db.refresh(target)
    if expected(actor, current, new):
        assert response.status_code == 200, response.text
        assert response.json()["role"] == new
        assert target.role == new
        changed = [e for e in log_entries(db) if e.action == "change_role"]
        assert len(changed) == (0 if current == new else 1)
        if current != new:
            assert changed[0].data == {"from": current, "to": new}
            assert changed[0].reason == REASON["reason"]
    else:
        assert (response.status_code, error_code(response)) == (403, "role_change_forbidden")
        assert target.role == current


@pytest.mark.parametrize("role", ["moderator", "admin"])
def test_nobody_changes_their_own_role(role: str, client_as: ClientAs, make_user: MakeUser) -> None:
    me = make_user(role, handle="Me")
    response = set_role(client_as(me), "Me", "member")
    assert (response.status_code, error_code(response)) == (403, "role_change_forbidden")


def test_a_member_becomes_trusted_only_with_fifty_points(client_as: ClientAs, make_user: MakeUser) -> None:
    client = client_as(make_user(Role.MODERATOR))
    make_user(handle="Short", reputation=49.0)
    make_user(handle="Enough", reputation=50.0)
    short = set_role(client, "Short", "trusted")
    assert (short.status_code, error_code(short)) == (409, "not_eligible")
    assert set_role(client, "Enough", "trusted").status_code == 200
    # An archaeologist needs no points.
    assert set_role(client, "Short", "expert").status_code == 200


def test_banned_deleted_and_unknown_people(client_as: ClientAs, make_user: MakeUser) -> None:
    client = client_as(make_user(Role.ADMIN))
    make_user(handle="Banned", banned_at=datetime(2026, 11, 1, tzinfo=UTC), reputation=80.0)
    make_user(handle="Gone", deleted_at=datetime(2026, 11, 1, tzinfo=UTC))
    banned = set_role(client, "Banned", "trusted")
    assert (banned.status_code, error_code(banned)) == (409, "user_banned")
    for handle in ("Gone", "Nobody"):
        response = set_role(client, handle, "trusted")
        assert (response.status_code, error_code(response)) == (404, "user_not_found")
    bad = client.put(f"{API}/mod/users/Banned/role", json={"role": "emperor", **REASON})
    assert bad.status_code == 422
    no_reason = client.put(f"{API}/mod/users/Banned/role", json={"role": "member"})
    assert no_reason.status_code == 422


def test_a_new_role_weighs_answers_given_from_then_on_and_not_those_given_before(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    """Decision 0019: an answer keeps the weight of the role it was given with."""
    before, after = create(db, make_user()), create(db, make_user())
    archaeologist = make_user(handle="Arch")
    answer(db, before, archaeologist)
    assert set_role(client_as(make_user(Role.MODERATOR)), "Arch", "expert").status_code == 200
    db.refresh(archaeologist)
    answer(db, after, archaeologist)
    db.expire_all()
    assert findings.get_finding(db, before.public_id, None).assessment["seen"] == 1.0
    assert findings.get_finding(db, after.public_id, None).assessment["seen"] == 3.0


def _public_score(client, public_id: str) -> tuple[int, str, str]:
    page = client.get(f"{API}/findings/{public_id}").json()
    return page["confidence"], page["tier"], page["state"]


def test_flipping_a_role_and_back_shows_nobody_how_that_person_answered(
    db: Session, client: TestClient, client_as: ClientAs, make_user: MakeUser
) -> None:
    """A moderator who hasn't answered flips a member to expert and back, watching the score.

    Before Decision 0019 the score went 10, 23, 10 for someone who said yes and
    10, 0, 10 for someone who said no, so the flip said how each had answered.
    """
    finding = create(db, make_user())
    yes, no = make_user(handle="YesSayer"), make_user(handle="NoSayer")
    answer(db, finding, yes, visible="yes")
    answer(db, finding, no, visible="no")
    moderator = client_as(make_user(Role.MODERATOR))
    assert moderator.get(f"{API}/findings/{finding.public_id}/observations").status_code == 403
    start = _public_score(client, finding.public_id)
    events = count(db, Activity)
    for handle in ("YesSayer", "NoSayer"):
        for role in ("expert", "member", "expert", "member"):
            assert set_role(moderator, handle, role).status_code == 200
            assert _public_score(client, finding.public_id) == start, (handle, role)
            assert _public_score(moderator, finding.public_id) == start, (handle, role)
    # Nothing in the feed or the event stream marks the moment either.
    assert count(db, Activity) == events


def test_a_ban_and_its_lifting_show_nobody_how_that_person_answered(
    db: Session, client: TestClient, client_as: ClientAs, make_user: MakeUser
) -> None:
    """A ban is public (the profile goes), so a score that moved with it would say how they answered."""
    finding = create(db, make_user())
    yes, no = make_user(handle="YesSayer"), make_user(handle="NoSayer")
    answer(db, finding, yes, visible="yes")
    answer(db, finding, no, visible="no")
    moderator = client_as(make_user(Role.MODERATOR))
    start = _public_score(client, finding.public_id)
    events = count(db, Activity)
    for handle in ("NoSayer", "YesSayer"):
        banned = moderator.post(f"{API}/mod/users/{handle}/ban", json=REASON)
        assert banned.status_code == 200
        # The answer says nothing of how many findings they answered either.
        assert set(banned.json()) == {"user", "sessions_ended"}
        assert _public_score(client, finding.public_id) == start, handle
        assert moderator.post(f"{API}/mod/users/{handle}/unban", json=REASON).status_code == 200
        assert _public_score(client, finding.public_id) == start, handle
    assert count(db, Activity) == events


# --------------------------------------------------------------------------
# Who could be made trusted
# --------------------------------------------------------------------------


def test_the_eligible_list_shows_where_points_came_from_and_who_else_was_there(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    farmer = make_user(handle="Farmer")
    friend_a, friend_b = make_user(handle="FriendA"), make_user(handle="FriendB")
    helper = make_user(handle="Helper")
    make_user(handle="Poor", reputation=10.0)
    make_user(Role.TRUSTED, handle="AlreadyTrusted", reputation=200.0)
    first = create(db, farmer)
    second = create(db, farmer)
    for finding in (first, second):
        answer(db, finding, friend_a)
        answer(db, finding, friend_b)
        add_desk_evidence(db, finding, helper)
    db.refresh(farmer)
    assert farmer.reputation == 2 * reputation.TIER_POINTS[Tier.SEEN]
    # Top the farmer up to fifty with a hand-written award not tied to a finding.
    db.add(ReputationEvent(user_id=farmer.id, delta=46.0, reason="test_bonus", finding_id=None))
    farmer.reputation = 50.0
    db.commit()

    def listed(moderator):
        response = client_as(moderator).get(f"{API}/mod/users/eligible")
        assert response.status_code == 200
        (item,) = response.json()["items"]
        assert item["user"]["handle"] == "Farmer"
        assert item["user"]["reputation"] == 50.0
        assert item["sources"][0]["finding"] is None
        assert item["sources"][0]["points"] == 46.0
        by_finding = {s["finding"]["public_id"]: s for s in item["sources"] if s["finding"] is not None}
        assert set(by_finding) == {first.public_id, second.public_id}
        for source in by_finding.values():
            assert source["points"] == 2.0
            assert source["reasons"] == ["tier_seen"]
        others = {pid: sorted(p["handle"] for p in s["others"]) for pid, s in by_finding.items()}
        associates = [(a["user"]["handle"], a["shared_findings"]) for a in item["associates"]]
        return others, associates

    # A moderator who hasn't answered either finding isn't told who answered them (Decision 0008).
    others, associates = listed(make_user(Role.MODERATOR))
    assert others == {first.public_id: ["Helper"], second.public_id: ["Helper"]}
    assert associates == [("Helper", 2)]

    # One who answered the first is, for that finding.
    answered = make_user(Role.MODERATOR, handle="Answered")
    answer(db, first, answered)
    others, associates = listed(answered)
    assert others == {
        first.public_id: ["Answered", "FriendA", "FriendB", "Helper"],
        second.public_id: ["Helper"],
    }
    assert associates == [("Helper", 2), ("FriendA", 1), ("FriendB", 1), ("Answered", 1)]


def test_the_eligible_list_does_not_say_how_someone_answered(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finding = create(db, make_user(handle="Finder"))
    looker = make_user(handle="Looker", reputation=50.0)
    db.add_all(
        [
            ReputationEvent(user_id=looker.id, delta=48.0, reason="test_bonus", finding_id=None),
            ReputationEvent(
                user_id=looker.id, delta=1.0, reason=reputation.OBSERVATION_RULED_OUT, finding_id=finding.id
            ),
            ReputationEvent(
                user_id=looker.id,
                delta=1.0,
                reason=reputation.OBSERVATION_CORROBORATED,
                finding_id=create(db, make_user()).id,
            ),
        ]
    )
    db.commit()

    def sources(moderator):
        (item,) = client_as(moderator).get(f"{API}/mod/users/eligible").json()["items"]
        assert item["user"]["handle"] == "Looker"
        return [
            (s["finding"]["public_id"] if s["finding"] else None, s["points"], s["reasons"])
            for s in item["sources"]
        ], item

    # The answer points are added up with no finding, so nothing says which was ruled out by whom.
    blind, item = sources(make_user(Role.MODERATOR))
    assert blind == [(None, 48.0, ["test_bonus"]), (None, 2.0, ["second_looks"])]
    assert finding.public_id not in str(item)
    assert "observation_" not in str(item)
    # The finder may see every answer on their own finding, so a moderator who found it is told.
    finder_moderator = make_user(Role.MODERATOR, handle="ModFinder")
    own = create(db, finder_moderator)
    db.add(
        ReputationEvent(
            user_id=looker.id, delta=1.0, reason=reputation.OBSERVATION_RULED_OUT, finding_id=own.id
        )
    )
    db.commit()
    seen, _ = sources(finder_moderator)
    assert seen == [
        (None, 48.0, ["test_bonus"]),
        (None, 2.0, ["second_looks"]),
        (own.public_id, 1.0, [reputation.OBSERVATION_RULED_OUT]),
    ]


# --------------------------------------------------------------------------
# Bans
# --------------------------------------------------------------------------


def test_a_ban_ends_the_persons_sessions_at_once(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    target = make_user(handle="Target")
    theirs = client_as(target)
    second_device = client_as(target)
    assert theirs.get(f"{API}/auth/me").status_code == 200
    response = client_as(make_user(Role.MODERATOR)).post(f"{API}/mod/users/Target/ban", json=REASON)
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["sessions_ended"] == 2
    assert body["user"]["banned"] is True
    assert count(db, UserSession) == 1  # the moderator's
    for client in (theirs, second_device):
        me = client.get(f"{API}/auth/me")
        assert me.status_code == 401
        write = client.post(f"{API}/findings", json={"location": {"type": "Point"}, "feature_class": "pit"})
        assert write.status_code == 401
    db.refresh(target)
    assert target.banned_at is not None


def test_who_may_ban_whom(client_as: ClientAs, make_user: MakeUser) -> None:
    moderator, admin = make_user(Role.MODERATOR, handle="Mod"), make_user(Role.ADMIN, handle="Admin")
    make_user(Role.MODERATOR, handle="OtherMod")
    make_user(Role.ADMIN, handle="OtherAdmin")
    make_user(Role.EXPERT, handle="Expert")
    by_mod, by_admin = client_as(moderator), client_as(admin)

    def ban(client, handle: str):
        return client.post(f"{API}/mod/users/{handle}/ban", json=REASON)

    for client, handle in [
        (by_mod, "Mod"),
        (by_mod, "OtherMod"),
        (by_mod, "OtherAdmin"),
        (by_admin, "OtherAdmin"),
    ]:
        response = ban(client, handle)
        assert (response.status_code, error_code(response)) == (403, "ban_forbidden"), handle
    assert ban(by_mod, "Expert").status_code == 200
    again = ban(by_mod, "Expert")
    assert (again.status_code, error_code(again)) == (409, "already_banned")
    assert ban(by_admin, "OtherMod").status_code == 200
    unban = by_mod.post(f"{API}/mod/users/OtherMod/unban", json=REASON)
    assert (unban.status_code, error_code(unban)) == (403, "ban_forbidden")
    assert by_admin.post(f"{API}/mod/users/OtherMod/unban", json=REASON).status_code == 200
    not_banned = by_admin.post(f"{API}/mod/users/OtherMod/unban", json=REASON)
    assert (not_banned.status_code, error_code(not_banned)) == (409, "not_banned")


def test_a_banned_persons_evidence_stops_counting_until_the_ban_is_lifted_and_answers_and_votes_keep_counting(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user(handle="Finder")
    banned = make_user(handle="Ringleader")
    finding = create(db, finder)
    answer(db, finding, banned)
    answer(db, finding, make_user())
    evidence, _ = add_desk_evidence(db, finding, banned, EvidenceKind.AERIAL, title="Doctored aerial")
    other, _ = add_desk_evidence(db, finding, make_user(), EvidenceKind.HISTORIC_MAP)
    findings.vote(db, other.id, banned, 1)
    db.commit()
    db.refresh(finding)
    assert finding.tier == Tier.SEEN.value
    before = finding.assessment
    assert before["seen"] == 2.0
    activity_before = count(db, Activity)

    moderator = client_as(make_user(Role.MODERATOR))
    response = moderator.post(f"{API}/mod/users/Ringleader/ban", json=REASON)
    assert response.status_code == 200

    db.expire_all()
    finding = findings.get_finding(db, finding.public_id, None)
    # Their answer and their vote still count (Decision 0019); their evidence doesn't.
    assert finding.tier == Tier.SEEN.value
    assert finding.assessment["seen"] == 2.0
    assert finding.evidence_count == 1
    # The reassessment their evidence caused changed no tier or state, so nothing marks the moment.
    assert count(db, Activity) == activity_before
    viewer = client_as(make_user())
    page = viewer.get(f"{API}/findings/{finding.public_id}").json()
    assert "Doctored aerial" not in str(page)
    (endorsed,) = [item for item in page["evidence"] if item["id"] == other.id]
    assert endorsed["endorsements"] == 1
    export = viewer.get(f"{API}/findings/{finding.public_id}/export?format=csv").text
    assert "Aerial" not in export
    gone = viewer.put(f"{API}/evidence/{evidence.id}/vote", json={"value": 1})
    assert (gone.status_code, error_code(gone)) == (404, "evidence_not_found")

    moderator.post(f"{API}/mod/users/Ringleader/unban", json=REASON)
    db.expire_all()
    restored = db.scalar(select(Finding).where(Finding.id == finding.id))
    assert restored is not None
    assert restored.tier == Tier.SEEN.value
    assert restored.assessment == before
    assert restored.assessment["seen"] == before["seen"]
    assert restored.evidence_count == 2
    actions = [e.action for e in log_entries(db)]
    assert actions == ["ban", "unban"]


def test_a_banned_account_is_not_in_the_eligible_list(client_as: ClientAs, make_user: MakeUser) -> None:
    make_user(handle="Banned", reputation=90.0, banned_at=datetime(2026, 11, 1, tzinfo=UTC))
    make_user(handle="Gone", reputation=90.0, deleted_at=datetime(2026, 11, 1, tzinfo=UTC))
    items = client_as(make_user(Role.MODERATOR)).get(f"{API}/mod/users/eligible").json()["items"]
    assert items == []


def test_a_banned_verifier_is_not_named_while_the_ban_lasts(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finding = create(db, make_user())
    expert = make_user(Role.EXPERT, handle="BadExpert")
    helper = client_as(make_user())
    path = f"{API}/findings/{finding.public_id}"
    added = helper.post(f"{path}/evidence", json={"kind": "her_record", "reference": "MWI1"}).json()
    entry_id = next(e["id"] for e in added["evidence"] if e["kind"] == "her_record")
    assert client_as(expert).post(f"{API}/evidence/{entry_id}/verify").json()["tier"] == "confirmed"
    viewer = client_as(make_user())

    def verified_by() -> tuple[str, object]:
        page = viewer.get(path).json()
        (entry,) = (e for e in page["evidence"] if e["id"] == entry_id)
        return page["tier"], entry["verified_by"] and entry["verified_by"]["handle"]

    assert verified_by() == ("confirmed", "BadExpert")
    moderator = client_as(make_user(Role.MODERATOR))
    assert moderator.post(f"{API}/mod/users/BadExpert/ban", json=REASON).status_code == 200
    assert verified_by() == ("spotted", None)
    assert "BadExpert" not in viewer.get(path).text
    assert moderator.post(f"{API}/mod/users/BadExpert/unban", json=REASON).status_code == 200
    assert verified_by() == ("confirmed", "BadExpert")
