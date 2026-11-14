"""Keeping a marking: who may change it, handing it on, and what happens when its keeper's account goes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.auth.accounts import delete_account
from fieldclub.models import Activity, Finding, Follow, Notification, User
from fieldclub.services import actions, findings, keeping, moderation
from fieldclub.vocab import ActivityKind, Role, Visible
from tests.findings.support import API, answer, create, meridian
from tests.helpers import ClientAs, MakeUser, error_code


def offer(client, finding: Finding, handle: str):
    return client.put(f"{API}/findings/{finding.public_id}/keeping/offer", json={"handle": handle})


def take(client, finding: Finding):
    return client.post(f"{API}/findings/{finding.public_id}/keeping/accept")


def handed_on(db: Session, client_as: ClientAs, finding: Finding, finder: User, to: User) -> None:
    assert offer(client_as(finder), finding, to.handle).status_code == 200
    assert take(client_as(to), finding).status_code == 200
    db.expire_all()


def rename(client, finding: Finding, title: str):
    return client.patch(f"{API}/findings/{finding.public_id}", json={"title": title})


def test_the_finder_edits_until_they_hand_it_on_and_not_after(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, keeper = make_user(), make_user()
    finding = create(db, finder)
    assert rename(client_as(finder), finding, "Before").status_code == 200
    assert rename(client_as(keeper), finding, "Not theirs").json()["error"]["code"] == "not_keeper"

    handed_on(db, client_as, finding, finder, keeper)

    refused = rename(client_as(finder), finding, "After")
    assert (refused.status_code, error_code(refused)) == (403, "not_keeper")
    page = client_as(finder).get(f"{API}/findings/{finding.public_id}").json()
    assert page["author"]["handle"] == finder.handle, "found by never changes"
    assert page["keeper"]["handle"] == keeper.handle
    assert page["actions"]["edit"] == {"allowed": False, "reason": "not_keeper"}
    assert page["actions"]["withdraw"] == {"allowed": True, "reason": None}


def test_the_keeper_edits_and_can_t_withdraw(db: Session, make_user: MakeUser, client_as: ClientAs) -> None:
    finder, keeper = make_user(), make_user()
    finding = create(db, finder)
    handed_on(db, client_as, finding, finder, keeper)

    edited = rename(client_as(keeper), finding, "Kept and renamed")
    assert edited.status_code == 200, edited.text
    assert edited.json()["title"] == "Kept and renamed"
    assert edited.json()["actions"]["edit"]["allowed"] is True
    refused = client_as(keeper).post(f"{API}/findings/{finding.public_id}/withdraw")
    assert (refused.status_code, error_code(refused)) == (403, "not_finder")
    assert edited.json()["actions"]["withdraw"] == {"allowed": False, "reason": "not_finder"}


def test_the_keeper_changes_the_shape_and_the_finder_can_t(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, keeper = make_user(), make_user()
    finding = findings.create_finding(db, finder, path=meridian(0, 0.01), feature_class="linear")
    db.commit()
    handed_on(db, client_as, finding, finder, keeper)
    longer = {
        "points": [{"lon": p.lon, "lat": p.lat, "kind": "corner"} for p in meridian(0, 0.01, 0.02).points]
    }

    refused = client_as(finder).patch(
        f"{API}/findings/{finding.public_id}", json={"path": longer, "path_revision": 0}
    )
    assert error_code(refused) == "not_keeper"
    changed = client_as(keeper).patch(
        f"{API}/findings/{finding.public_id}", json={"path": longer, "path_revision": 0}
    )
    assert changed.status_code == 200, changed.text
    assert changed.json()["location"]["shape"]["revision"] == 1


def test_taking_it_on_follows_the_finding_and_tells_its_followers(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, keeper, follower = make_user(), make_user(), make_user()
    finding = create(db, finder)
    findings.follow(db, follower, finding)
    db.commit()
    handed_on(db, client_as, finding, finder, keeper)

    assert db.scalar(select(Follow).where(Follow.user_id == keeper.id, Follow.finding_id == finding.id))
    (event,) = db.scalars(select(Activity).where(Activity.kind == ActivityKind.KEEPER_CHANGED.value)).all()
    assert (event.actor_id, event.finding_id, event.data) == (keeper.id, finding.id, None)
    told = {n.user_id for n in db.scalars(select(Notification).where(Notification.kind == "keeper_changed"))}
    assert told == {finder.id, follower.id}
    stored = db.get(Finding, finding.id)
    assert stored is not None
    assert (stored.keeper_id, stored.keeping_offered_to, stored.keeping_offered_at) == (keeper.id, None, None)


def test_handing_it_back_to_the_finder_leaves_the_finder_keeping_it(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, keeper = make_user(), make_user()
    finding = create(db, finder)
    handed_on(db, client_as, finding, finder, keeper)
    handed_on(db, client_as, finding, keeper, finder)

    stored = db.get(Finding, finding.id)
    assert stored is not None
    assert stored.keeper_id is None, "null means the finder keeps it"
    assert rename(client_as(finder), finding, "Mine again").status_code == 200


@pytest.mark.parametrize("who", ["banned", "deleted", "unknown"])
def test_an_offer_to_a_banned_a_deleted_or_an_unknown_account_answers_the_same(
    db: Session, make_user: MakeUser, client_as: ClientAs, who: str
) -> None:
    finder = make_user()
    finding = create(db, finder)
    target = make_user()
    handle = target.handle
    if who == "banned":
        target.banned_at = datetime.now(UTC)
    elif who == "deleted":
        # By the handle it has now, which nothing leads to: the old one is free.
        delete_account(db, target)
        handle = target.handle
    else:
        handle = "NobodyByThisName"
    db.commit()

    refused = offer(client_as(finder), finding, handle)
    assert refused.status_code == 404
    assert refused.json()["error"]["code"] == "user_not_found"
    assert refused.json()["error"]["message"] == "There's nobody with that handle."
    assert set(refused.json()["error"]) == {"code", "message", "request_id"}
    db.expire_all()
    assert db.get(Finding, finding.id).keeping_offered_to is None  # type: ignore[union-attr]


def test_an_offer_made_again_to_the_same_person_tells_them_once(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, offered, other = make_user(), make_user(), make_user()
    finding = create(db, finder)
    for handle in (offered.handle, offered.handle, other.handle, other.handle):
        assert offer(client_as(finder), finding, handle).status_code == 200

    sent = db.scalars(select(Notification).where(Notification.kind == "keeping_offered")).all()
    assert sorted(n.user_id for n in sent) == sorted([offered.id, other.id])
    for note in sent:
        assert (note.finding_id, note.actor_id, note.data) == (finding.id, None, None)
    # The newer offer replaced the first, so the first person can't take it.
    refused = take(client_as(offered), finding)
    assert (refused.status_code, error_code(refused)) == (403, "not_offered")


def test_the_offer_goes_only_to_the_keeper_the_person_offered_and_moderators(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, offered, member, moderator = make_user(), make_user(), make_user(), make_user("moderator")
    finding = create(db, finder)
    made = offer(client_as(finder), finding, offered.handle)
    assert made.json()["keeping"]["offered_to"]["handle"] == offered.handle
    for viewer, sees in ((finder, True), (offered, True), (moderator, True), (member, False)):
        page = client_as(viewer).get(f"{API}/findings/{finding.public_id}").json()
        assert (page["keeping"] is not None) is sees, viewer.handle
        assert page["actions"]["take_keeping"]["allowed"] is (viewer is offered)
    assert (
        client_as(member).get(f"{API}/findings/{finding.public_id}").json()["keeper"]["handle"]
        == finder.handle
    )


def test_an_offer_to_the_keeper_and_on_a_hidden_finding_are_refused(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, member = make_user(), make_user()
    finding = create(db, finder)
    assert error_code(offer(client_as(finder), finding, finder.handle)) == "already_keeper"
    finding.hidden_at = datetime.now(UTC)
    db.commit()
    refused = offer(client_as(finder), finding, member.handle)
    assert (refused.status_code, error_code(refused)) == (409, "finding_hidden")


def test_only_the_keeper_and_the_person_offered_take_an_offer_back(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, offered, member = make_user(), make_user(), make_user()
    finding = create(db, finder)
    path = f"{API}/findings/{finding.public_id}/keeping/offer"
    offer(client_as(finder), finding, offered.handle)
    refused = client_as(member).delete(path)
    assert (refused.status_code, error_code(refused)) == (403, "not_offered")
    assert client_as(offered).delete(path).status_code == 204
    offer(client_as(finder), finding, offered.handle)
    assert client_as(finder).delete(path).status_code == 204
    db.expire_all()
    assert db.get(Finding, finding.id).keeping_offered_to is None  # type: ignore[union-attr]


def test_a_keeper_who_isn_t_the_finder_can_t_give_a_second_look_and_an_earlier_one_stands(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, keeper = make_user(), make_user()
    finding = create(db, finder)
    answer(db, finding, keeper, Visible.YES)
    looked_before = db.get(Finding, finding.id).observation_count  # type: ignore[union-attr]
    other = create(db, finder, lon=-1.85, lat=51.43)
    handed_on(db, client_as, finding, finder, keeper)
    handed_on(db, client_as, other, finder, keeper)

    refused = client_as(keeper).put(f"{API}/findings/{other.public_id}/observation", json={"visible": "yes"})
    assert (refused.status_code, error_code(refused)) == (422, "own_marking")
    page = client_as(keeper).get(f"{API}/findings/{other.public_id}").json()
    assert page["actions"]["answer"] == {"allowed": False, "reason": "own_marking"}
    assert db.get(Finding, finding.id).observation_count == looked_before == 1  # type: ignore[union-attr]
    queue = client_as(keeper).get(f"{API}/review/next")
    assert other.public_id not in queue.text


def test_deleting_a_keeper_leaves_what_they_kept_orphaned_and_tells_each_admin_once(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, keeper, offered = make_user(), make_user(), make_user()
    admins = [make_user("admin"), make_user("admin")]
    make_user("admin", banned_at=datetime.now(UTC))
    handed = create(db, finder)
    own = create(db, keeper, lon=-1.85, lat=51.43)
    handed_on(db, client_as, handed, finder, keeper)
    offer(client_as(keeper), own, offered.handle)
    on_offer = create(db, finder, lon=-1.86, lat=51.43)
    offer(client_as(finder), on_offer, keeper.handle)

    gone = db.get(User, keeper.id)
    assert gone is not None
    delete_account(db, gone)
    db.commit()
    db.expire_all()

    for marking in (handed, own):
        stored = db.get(Finding, marking.id)
        assert stored is not None
        assert findings.keeper_of(stored) == keeper.id, "the keeping stays with the deleted account"
        assert keeping.is_orphaned(keeping.keeper(db, stored))
        assert stored.keeping_offered_to is None
    assert db.get(Finding, on_offer.id).keeping_offered_to is None  # type: ignore[union-attr]
    told = db.scalars(select(Notification).where(Notification.kind == "keeper_gone")).all()
    assert sorted(n.user_id for n in told) == sorted(admin.id for admin in admins)
    for note in told:
        assert (note.data, note.finding_id, note.actor_id) == ({"markings": 2}, None, None)
    listed = client_as(admins[0]).get(f"{API}/notifications").json()["items"]
    assert [(n["kind"], n["details"]["markings"]) for n in listed] == [("keeper_gone", 2)]


def test_deleting_an_account_that_kept_nothing_tells_no_admin(db: Session, make_user: MakeUser) -> None:
    make_user("admin")
    quiet = make_user()
    delete_account(db, quiet)
    db.commit()
    assert not db.scalars(select(Notification).where(Notification.kind == "keeper_gone")).all()


def test_an_admin_offers_an_orphaned_marking_and_nobody_else_s(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, volunteer = make_user(), make_user()
    admin, moderator, member = make_user("admin"), make_user("moderator"), make_user()
    kept = create(db, finder)
    orphan = create(db, finder, lon=-1.85, lat=51.43)
    banned = make_user()
    handed_on(db, client_as, orphan, finder, banned)
    banned.banned_at = datetime.now(UTC)
    db.commit()

    refused = offer(client_as(admin), kept, volunteer.handle)
    assert (refused.status_code, error_code(refused)) == (403, "not_keeper")
    for someone in (moderator, member, finder):
        assert error_code(offer(client_as(someone), orphan, volunteer.handle)) == "not_keeper"
    made = offer(client_as(admin), orphan, finder.handle)
    assert made.status_code == 200, made.text
    assert take(client_as(finder), orphan).status_code == 200
    db.expire_all()
    stored = db.get(Finding, orphan.id)
    assert stored is not None
    assert stored.keeper_id is None, "the finder took it back"


def test_hand_on_and_remove_marking_refuse_a_member_alike_whatever_the_keeper_s_standing(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, member = make_user(), make_user()
    kept = create(db, finder)
    orphan = create(db, finder, lon=-1.85, lat=51.43)
    banned = make_user()
    handed_on(db, client_as, orphan, finder, banned)
    banned.banned_at = datetime.now(UTC)
    db.commit()

    pages = [client_as(member).get(f"{API}/findings/{f.public_id}").json()["actions"] for f in (kept, orphan)]
    assert pages[0]["hand_on"] == pages[1]["hand_on"] == {"allowed": False, "reason": "not_keeper"}
    assert (
        pages[0]["remove_marking"]
        == pages[1]["remove_marking"]
        == {"allowed": False, "reason": "admins_only"}
    )
    moderator = make_user("moderator")
    for finding in (kept, orphan):
        mine = client_as(moderator).get(f"{API}/findings/{finding.public_id}").json()["actions"]
        assert mine["remove_marking"] == {"allowed": False, "reason": "admins_only"}
    admin = make_user("admin")
    as_admin = [
        client_as(admin).get(f"{API}/findings/{f.public_id}").json()["actions"] for f in (kept, orphan)
    ]
    assert as_admin[0]["hand_on"] == {"allowed": False, "reason": "not_keeper"}
    assert as_admin[1]["hand_on"] == {"allowed": True, "reason": None}
    assert as_admin[0]["remove_marking"] == {"allowed": False, "reason": "not_orphaned"}
    assert as_admin[1]["remove_marking"] == {"allowed": True, "reason": None}


def test_the_actions_are_answered_by_the_routes_own_checks(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder)
    found = actions.finding_actions(finding, finder, None, [], keeper=finder)
    assert found.hand_on == found.edit == found.decide_suggestions == actions.Action(True)
    assert found.suggest == actions.Action(False, "own_marking")
    assert found.take_keeping == actions.Action(False, "not_offered")
    assert Role(finder.role) is Role.MEMBER


def test_lifting_a_ban_clears_the_offers_made_on_what_the_person_keeps(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, keeper, volunteer = make_user(), make_user(), make_user()
    admin, moderator = make_user("admin"), make_user("moderator")
    finding = create(db, finder)
    handed_on(db, client_as, finding, finder, keeper)
    moderation.ban(db, keeper.handle, moderator, "Trouble.")
    db.commit()
    assert offer(client_as(admin), finding, volunteer.handle).status_code == 200
    moderation.unban(db, keeper.handle, moderator, "Sorted out.")
    db.commit()
    db.expire_all()
    stored = db.get(Finding, finding.id)
    assert stored is not None
    assert (stored.keeping_offered_to, stored.keeping_offered_at) == (None, None)
    refused = take(client_as(volunteer), finding)
    assert (refused.status_code, error_code(refused)) == (403, "not_offered")


def test_taking_on_a_withdrawn_or_hidden_finding_is_refused(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, offered, moderator = make_user(), make_user(), make_user("moderator")
    withdrawn = create(db, finder)
    offer(client_as(finder), withdrawn, offered.handle)
    findings.withdraw_finding(db, findings.lock(db, withdrawn), finder)
    db.commit()
    refused = take(client_as(offered), withdrawn)
    assert (refused.status_code, error_code(refused)) == (409, "finding_withdrawn")

    hidden = create(db, finder, lon=-1.85, lat=51.43)
    offer(client_as(finder), hidden, offered.handle)
    offer(client_as(finder), create(db, finder, lon=-1.86, lat=51.43), moderator.handle)
    hidden.hidden_at = datetime.now(UTC)
    db.commit()
    not_found = take(client_as(offered), hidden)
    assert (not_found.status_code, error_code(not_found)) == (404, "finding_not_found")
    # The finder, who sees it hidden, is refused with the plan's code when it is offered to them.
    hidden.keeping_offered_to = finder.id
    hidden.keeper_id = offered.id
    db.commit()
    seen = take(client_as(finder), hidden)
    assert (seen.status_code, error_code(seen)) == (409, "finding_hidden")


def test_offering_again_after_taking_it_back_doesn_t_tell_them_again_while_unread(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, offered = make_user(), make_user()
    finding = create(db, finder)
    path = f"{API}/findings/{finding.public_id}/keeping/offer"
    for _ in range(3):
        assert offer(client_as(finder), finding, offered.handle).status_code == 200
        assert client_as(finder).delete(path).status_code == 204
    sent = db.scalars(select(Notification).where(Notification.kind == "keeping_offered")).all()
    assert len(sent) == 1
    sent[0].read_at = datetime.now(UTC)
    db.commit()
    offer(client_as(finder), finding, offered.handle)
    assert len(db.scalars(select(Notification).where(Notification.kind == "keeping_offered")).all()) == 2


@pytest.mark.parametrize("gone", ["deleted", "banned"])
def test_an_offer_to_an_account_since_deleted_or_banned_reads_as_no_offer(
    db: Session, make_user: MakeUser, client_as: ClientAs, gone: str
) -> None:
    finder, offered, moderator = make_user(), make_user(), make_user("moderator")
    finding = create(db, finder)
    offer(client_as(finder), finding, offered.handle)
    # As if the account went while the offer crossed it, which deletion and a ban otherwise clear.
    stored = db.get(User, offered.id)
    assert stored is not None
    if gone == "deleted":
        stored.deleted_at = datetime.now(UTC)
    else:
        stored.banned_at = datetime.now(UTC)
    db.commit()
    for viewer in (finder, moderator):
        assert client_as(viewer).get(f"{API}/findings/{finding.public_id}").json()["keeping"] is None


def test_an_offer_to_someone_then_banned_is_gone_and_stays_gone(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    """A ban looks to the keeper like a refusal: an offer that came back with the ban lifted would say it."""
    finder, offered, moderator = make_user(), make_user(), make_user("moderator")
    finding = create(db, finder)
    offer(client_as(finder), finding, offered.handle)
    moderation.ban(db, offered.handle, moderator, "Trouble.")
    db.commit()
    page = f"{API}/findings/{finding.public_id}"
    assert client_as(finder).get(page).json()["keeping"] is None
    moderation.unban(db, offered.handle, moderator, "Sorted out.")
    db.commit()
    assert client_as(finder).get(page).json()["keeping"] is None
    db.expire_all()
    assert db.get(Finding, finding.id).keeping_offered_to is None  # type: ignore[union-attr]


def test_someone_who_said_no_thanks_is_told_of_the_next_offer(
    db: Session, make_user: MakeUser, client_as: ClientAs
) -> None:
    finder, offered, other = make_user(), make_user(), make_user()
    finding = create(db, finder)
    path = f"{API}/findings/{finding.public_id}/keeping/offer"
    offer(client_as(finder), finding, offered.handle)
    assert client_as(offered).delete(path).status_code == 204
    offer(client_as(finder), finding, offered.handle)
    sent = db.scalars(select(Notification).where(Notification.kind == "keeping_offered")).all()
    assert len(sent) == 2, "they answered the first, so the second is news"
    # Taking an offer up marks it read too, so a later offer to them is told.
    assert take(client_as(offered), finding).status_code == 200
    db.expire_all()
    assert all(
        note.read_at is not None
        for note in db.scalars(select(Notification).where(Notification.kind == "keeping_offered"))
    )
    offer(client_as(offered), finding, other.handle)
    client_as(other).delete(path)
    offer(client_as(offered), finding, finder.handle)
    assert take(client_as(finder), finding).status_code == 200
    offer(client_as(finder), finding, offered.handle)
    assert (
        len(
            db.scalars(
                select(Notification).where(
                    Notification.kind == "keeping_offered", Notification.user_id == offered.id
                )
            ).all()
        )
        == 3
    )
