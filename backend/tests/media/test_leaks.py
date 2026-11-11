"""A photo shows where its finding is, so it goes only to those who see the finding exactly (Decision 0005).

`GET /media/{id}` is tried as every kind of viewer against every level, with
the world `tests/findings/test_leaks.py` builds, before and after approval.
Its address is never sent as publicly cacheable, approved or not.
"""

from __future__ import annotations

from datetime import date

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.services import findings, media
from fieldclub.services.findings import EvidenceFields
from fieldclub.vocab import EvidenceKind, Outcome, Sensitivity
from tests.findings import test_leaks as leaks
from tests.moderation.support import API, jpeg, photo

world = leaks.world

# Who sees a photo before it is approved: its uploader (here the finder) and the people who approve photos.
BEFORE_APPROVAL = {"finder", "trusted", "moderator"}


def assert_private(response, where: str) -> None:
    assert response.headers["cache-control"] == "private, no-cache", where
    vary = [token.strip() for line in response.headers.get_list("vary") for token in line.split(",")]
    assert vary.count("Cookie") == 1, where


@pytest.mark.parametrize("level", leaks.LEVELS)
def test_a_photo_goes_only_to_those_who_see_its_finding_exactly(
    world: leaks.World, db: Session, level: Sensitivity
) -> None:
    finding = world.findings[level]
    finder = world.people["finder"]
    waiting = photo(db, finder, data=jpeg(colour=(len(level.value), 40, 80)))
    findings.add_evidence(
        db,
        findings.lock(db, finding),
        finder,
        EvidenceFields(
            kind=EvidenceKind.PHOTO,
            media_id=waiting.id,
            outcome=Outcome.SUPPORTS,
            occurred_on=date(2026, 11, 1),
        ),
    )
    db.commit()
    path = f"{API}/media/{waiting.id}"
    clients: dict[str, TestClient] = {viewer: world.client(viewer) for viewer in leaks.VIEWERS}

    for viewer, client in clients.items():
        response = client.get(path)
        where = f"unapproved photo on the {level} finding, as {viewer}"
        assert response.status_code == (200 if viewer in BEFORE_APPROVAL else 404), where
        assert_private(response, where)

    media.approve_media(db, waiting, world.people["trusted"])
    db.commit()
    for viewer, client in clients.items():
        response = client.get(path)
        where = f"approved photo on the {level} finding, as {viewer}"
        assert response.status_code == (200 if level in leaks.SEES[viewer] else 404), where
        assert_private(response, where)


def test_no_answer_that_carries_an_unapproved_photos_address_is_publicly_cacheable(
    world: leaks.World,
) -> None:
    finder, trusted = world.client("finder"), world.client("trusted")
    uploaded = finder.post(f"{API}/media", content=jpeg(), headers={"Content-Type": "image/jpeg"})
    assert uploaded.status_code == 201
    address = uploaded.json()["url"]
    assert_private(uploaded, "POST /media")
    queue = trusted.get(f"{API}/mod/media")
    assert address in queue.text
    assert_private(queue, "GET /mod/media")
