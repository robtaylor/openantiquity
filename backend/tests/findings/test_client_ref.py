"""Saving a draft twice: `POST /findings` with a client reference makes one finding, however often it is sent.

The browser saves drafts after sign-in and retries when an answer is lost, so
the same draft can arrive twice, or twice at once from two tabs. The
reference ties the request to the draft, per person.
"""

from __future__ import annotations

import threading
from typing import Any

import pytest
from shapely.geometry import Point
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub import db as fieldclub_db
from fieldclub.models import Activity, Finding, User
from fieldclub.services import findings
from tests.findings.support import API, LAT, LON
from tests.helpers import ClientAs, MakeUser, count

REF = "draft-6c1f0a52-0d1b-4c7e-9b2a-3f8e5d4c2a10"


def body(**extra: Any) -> dict[str, Any]:
    return {"location": {"type": "Point", "coordinates": [LON, LAT]}, "feature_class": "enclosure", **extra}


def test_the_same_reference_twice_gives_back_the_finding_already_made(
    client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    browser = client_as(make_user())
    first = browser.post(f"{API}/findings", json=body(client_ref=REF, title="Bank and ditch"))
    assert first.status_code == 201, first.text
    again = browser.post(f"{API}/findings", json=body(client_ref=REF, title="Bank and ditch"))
    assert again.status_code == 200, again.text
    assert again.json()["public_id"] == first.json()["public_id"]
    assert again.json() == browser.get(f"{API}/findings/{first.json()['public_id']}").json()
    assert count(db, Finding) == 1
    assert db.scalars(select(Activity.kind)).all() == ["finding_created"]


def test_what_the_second_request_says_changes_nothing(
    client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    browser = client_as(make_user())
    first = browser.post(f"{API}/findings", json=body(client_ref=REF, title="First words"))
    again = browser.post(f"{API}/findings", json=body(client_ref=REF, title="Second words"))
    assert again.status_code == 200
    assert again.json()["title"] == first.json()["title"] == "First words"
    assert count(db, Finding) == 1


def test_a_reference_belongs_to_one_person(client_as: ClientAs, make_user: MakeUser, db: Session) -> None:
    mine = client_as(make_user()).post(f"{API}/findings", json=body(client_ref=REF))
    theirs = client_as(make_user()).post(f"{API}/findings", json=body(client_ref=REF))
    assert (mine.status_code, theirs.status_code) == (201, 201)
    assert mine.json()["public_id"] != theirs.json()["public_id"]
    assert count(db, Finding) == 2


def test_different_references_and_none_at_all_each_make_a_finding(
    client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    browser = client_as(make_user())
    for extra in ({"client_ref": "a"}, {"client_ref": "b"}, {}, {}):
        assert browser.post(f"{API}/findings", json=body(**extra)).status_code == 201
    assert count(db, Finding) == 4


def test_a_withdrawn_finding_is_still_the_one_the_reference_made(
    client_as: ClientAs, make_user: MakeUser, db: Session
) -> None:
    browser = client_as(make_user())
    made = browser.post(f"{API}/findings", json=body(client_ref=REF)).json()["public_id"]
    assert browser.post(f"{API}/findings/{made}/withdraw").status_code == 200
    again = browser.post(f"{API}/findings", json=body(client_ref=REF))
    assert (again.status_code, again.json()["public_id"], again.json()["state"]) == (200, made, "withdrawn")
    assert count(db, Finding) == 1


@pytest.mark.parametrize("ref", ["", "x" * 65, "has space", "tab\there", "café"])
def test_a_reference_is_up_to_64_plain_characters(
    client_as: ClientAs, make_user: MakeUser, db: Session, ref: str
) -> None:
    response = client_as(make_user()).post(f"{API}/findings", json=body(client_ref=ref))
    assert response.status_code == 422
    assert count(db, Finding) == 0


def test_a_reference_of_64_characters_is_kept(client_as: ClientAs, make_user: MakeUser, db: Session) -> None:
    assert client_as(make_user()).post(f"{API}/findings", json=body(client_ref="x" * 64)).status_code == 201


def _create_in_own_session(user_id: int, results: list[str], errors: list[BaseException]) -> None:
    try:
        with fieldclub_db.SessionLocal() as session:
            user = session.get(User, user_id)
            assert user is not None
            finding, _ = findings.create_finding_once(
                session, user, REF, location=Point(LON, LAT), feature_class="enclosure"
            )
            session.commit()
            results.append(finding.public_id)
    except BaseException as exc:
        errors.append(exc)


def test_two_requests_at_once_make_one_finding(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    results: list[str] = []
    errors: list[BaseException] = []
    threads = [
        threading.Thread(target=_create_in_own_session, args=(user.id, results, errors)) for _ in range(4)
    ]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=30)
        assert not thread.is_alive(), "a request never finished"
    assert not errors, errors
    assert len(results) == 4
    assert len(set(results)) == 1
    db.expire_all()
    assert db.scalar(select(func.count()).select_from(Finding)) == 1


def test_the_service_says_whether_it_made_the_finding(db: Session, make_user: MakeUser) -> None:
    user = make_user()
    made, created = findings.create_finding_once(
        db, user, REF, location=Point(LON, LAT), feature_class="enclosure"
    )
    db.commit()
    again, created_again = findings.create_finding_once(
        db, user, REF, location=Point(LON + 0.01, LAT), feature_class="round_barrow"
    )
    assert (created, created_again) == (True, False)
    assert again.id == made.id
    assert again.feature_class == "enclosure"
