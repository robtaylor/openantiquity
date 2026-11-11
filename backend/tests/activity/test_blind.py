"""Decision 0008 across this track: nobody who hasn't answered learns how anyone answered.

Two members answer a finding, one "yes" and one "no", and the finding climbs
to Corroborated, which pays the "yes" an answer point. A third member who
follows the finding but hasn't answered, and a signed-out visitor, then read
the feed, their notifications, both answerers' profiles and contributions,
and what the event stream would announce. The two answerers must look the
same in everything they read, apart from their names.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Activity, ReputationEvent, User
from fieldclub.services import events, reputation
from fieldclub.services.events import Announcement, EventHub, StreamFilter
from fieldclub.vocab import EvidenceKind, FeatureClass, Visible
from tests.activity.support import API, follow, items, walk
from tests.findings.support import add_desk_evidence, answer, create
from tests.helpers import ClientAs, ClientFor, MakeUser, error_code

# Keys that would say how someone answered.
ANSWER_KEYS = {
    "visible",
    "explanation",
    "not_modern",
    "not_natural",
    "not_artefact",
    "note",
    "answers",
    "tallies",
}


@pytest.fixture
def answered(db: Session, make_user: MakeUser) -> dict[str, Any]:
    finder = make_user(handle="Finder")
    saw, missed, third = make_user(handle="Saw"), make_user(handle="Missed"), make_user(handle="Third")
    researcher = make_user(handle="Researcher")
    onlooker = make_user(handle="Onlooker")
    finding = create(db, finder, title="Ring ditch")
    follow(db, finding, onlooker)
    answer(db, finding, saw, Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    answer(db, finding, missed, Visible.NO)
    answer(db, finding, third, Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    add_desk_evidence(db, finding, researcher, EvidenceKind.AERIAL)
    add_desk_evidence(db, finding, researcher, EvidenceKind.HISTORIC_MAP)
    db.refresh(finding)
    assert finding.tier == "corroborated"
    paid = db.scalars(
        select(ReputationEvent.user_id).where(ReputationEvent.reason == reputation.OBSERVATION_CORROBORATED)
    ).all()
    assert sorted(paid) == sorted([saw.id, third.id]), "the yeses are paid for matching the outcome"
    return {"finding": finding, "saw": saw, "missed": missed, "onlooker": onlooker}


def viewers(answered: dict[str, Any], client: TestClient, client_as: ClientAs) -> dict[str, TestClient]:
    return {"signed_out": client, "onlooker": client_as(answered["onlooker"])}


def assert_nothing_about_answers(body: Any, where: str) -> None:
    for key, value in walk(body):
        assert key not in ANSWER_KEYS, f"{where}: {key} says how someone answered"
        if isinstance(value, str):
            assert value not in reputation.ANSWER_REASONS, f"{where}: {value} says how someone answered"


def test_the_feed_and_notifications_name_no_answerer(
    answered: dict[str, Any], client: TestClient, client_as: ClientAs, db: Session
) -> None:
    for name, viewer in viewers(answered, client, client_as).items():
        listed = items(viewer.get(f"{API}/activity", params={"limit": 200}))
        answer_events = [item for item in listed if item["kind"] in ("observation_added", "tier_changed")]
        assert len([item for item in answer_events if item["kind"] == "observation_added"]) == 3
        for item in answer_events:
            if item["kind"] == "tier_changed" and item["details"]["tier_to"] == "corroborated":
                continue  # the evidence moved it, and the evidence is credited
            assert item["actor"] is None, f"{name} sees who caused {item['kind']}"
        assert_nothing_about_answers(listed, f"{name}'s feed")
        for handle in ("Saw", "Missed"):
            mine = items(viewer.get(f"{API}/activity", params={"person": handle}))
            assert mine == [], f"{name} can find {handle}'s second look in the feed"

    notes = client_as(answered["onlooker"]).get(f"{API}/notifications", params={"limit": 200}).json()
    assert [n["kind"] for n in notes["items"]].count("observation_added") == 3
    assert all(n["actor"] is None for n in notes["items"] if n["kind"] == "observation_added")
    assert_nothing_about_answers(notes, "notifications")
    # The rows themselves name nobody, so no later reader can either.
    for row in db.scalars(select(Activity).where(Activity.kind == "observation_added")):
        assert (row.actor_id, row.data) == (None, None)


def _without_identity(profile: dict[str, Any]) -> dict[str, Any]:
    return {
        key: value for key, value in profile.items() if key not in ("handle", "display_name", "joined_at")
    }


def test_a_yes_and_a_no_look_the_same_on_their_profiles(
    answered: dict[str, Any], client: TestClient, client_as: ClientAs
) -> None:
    for name, viewer in viewers(answered, client, client_as).items():
        saw = viewer.get(f"{API}/users/Saw").json()
        missed = viewer.get(f"{API}/users/Missed").json()
        assert _without_identity(saw) == _without_identity(missed), f"{name} can tell the answers apart"
        assert saw["reputation"] == 0  # the point for matching the outcome isn't shown to others
        assert saw["reputation_total"] is None
        # Second looks are counted and listed only to the person (Decision 0010).
        assert saw["counts"]["second_looks"] is None
        for handle in ("Saw", "Missed"):
            looks = items(viewer.get(f"{API}/users/{handle}/contributions", params={"kind": "second_look"}))
            assert looks == [], f"{name} can list {handle}'s second looks"
        assert items(viewer.get(f"{API}/users/Saw/contributions")) == []

    own = {
        handle: items(
            client_as(answered[handle.lower()]).get(
                f"{API}/users/{handle}/contributions", params={"kind": "second_look"}
            )
        )
        for handle in ("Saw", "Missed")
    }
    assert own["Saw"] == own["Missed"]
    assert own["Saw"][0]["kind"] == "second_look"
    # Never when: a date beside the tier history would show whose answer moved it.
    assert (own["Saw"][0]["id"], own["Saw"][0]["created_at"]) == (None, None)
    assert_nothing_about_answers(own, "a person's own second looks")
    assert client_as(answered["saw"]).get(f"{API}/users/Saw").json()["counts"]["second_looks"] == 1


def test_a_watched_profile_gives_nothing_away_as_answers_arrive(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    """Someone polling a member's profile sees the same page before and after each of their answers.

    One answer takes the finding to Seen and the other leaves it, so if the
    profile moved with them, the tier at that moment would say how each went.
    """
    finder, ann = make_user(handle="Finder"), make_user(handle="Ann")
    watcher = client_as(make_user(handle="Watcher"))
    first, second = create(db, finder, title="Bank"), create(db, finder, title="Ditch")
    answer(db, first, make_user(), Visible.YES, feature_class=FeatureClass.ENCLOSURE)

    def watched() -> list[Any]:
        return [
            viewer.get(f"{API}/users/Ann{path}", params=params).json()
            for viewer in (watcher, client)
            for path, params in (
                ("", {}),
                ("/contributions", {}),
                ("/contributions", {"kind": "second_look"}),
                ("/findings", {}),
            )
        ]

    before = watched()
    answer(db, first, ann, Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    db.refresh(first)
    assert first.tier == "seen", "the yes moved the finding, so a profile that moved with it would tell"
    after_yes = watched()
    answer(db, second, ann, Visible.NO)
    after_no = watched()
    assert before == after_yes == after_no
    assert_nothing_about_answers(after_no, "a watched profile")
    # Ann herself sees both.
    mine = client_as(ann).get(f"{API}/users/Ann").json()
    assert mine["counts"]["second_looks"] == 2


def test_points_are_itemised_only_for_the_person(
    answered: dict[str, Any], app: Any, client_for: ClientFor, client_as: ClientAs
) -> None:
    for viewer in (client_for(app), client_as(answered["onlooker"]), client_as(answered["missed"])):
        assert error_code(viewer.get(f"{API}/users/Saw/points")) == "points_are_private"
    own = client_as(answered["saw"])
    assert [item["reason"] for item in items(own.get(f"{API}/users/Saw/points"))] == [
        reputation.OBSERVATION_CORROBORATED
    ]
    me = own.get(f"{API}/users/Saw").json()
    assert (me["is_me"], me["reputation"], me["reputation_total"]) == (True, 0, 1)


def test_the_stream_announces_second_looks_with_no_actor(answered: dict[str, Any], db: Session) -> None:
    rows = db.scalars(select(Activity).order_by(Activity.id)).all()
    people = {user.id: user.handle for user in db.scalars(select(User))}

    async def announce() -> list[Announcement]:
        hub = EventHub(
            events.conninfo(), events.lookup_public, queue_size=100, max_per_address=1, max_streams=1
        )
        hub.start()
        await asyncio.wait_for(hub.connected.wait(), 10)
        everything = hub.subscribe(StreamFilter(), "a")
        for row in rows:
            # As `activity.event_payload` writes it from the row.
            payload = {
                "id": row.id,
                "kind": row.kind,
                "finding": answered["finding"].public_id,
                "investigation": None,
                "actor": people[row.actor_id] if row.actor_id is not None else None,
            }
            await hub.deliver(json.dumps(payload))
        got = []
        while (item := await everything.next(0.1)) is not None:
            assert isinstance(item, Announcement)
            got.append(item)
        await hub.stop()
        return got

    got = asyncio.run(announce())
    assert len(got) == len(rows)
    for item in got:
        if item.kind == "observation_added":
            assert item.actor is None
        assert item.actor not in ("Saw", "Missed")
