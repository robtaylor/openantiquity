"""What a mention fetch may cost: database connections, the shared fetch budget, and stored text."""

from __future__ import annotations

import pytest
import respx
from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import db as fieldclub_db
from fieldclub.models import Finding, Mention
from fieldclub.services import unfurl
from tests.helpers import ClientAs, MakeFinding, MakeUser, error_code
from tests.mentions.support import API, YOUTUBE_URL, serve_youtube_oembed


def post(client: TestClient, finding: Finding, url: str, **body: object):
    return client.post(f"{API}/findings/{finding.public_id}/mentions", json={"url": url, **body})


@pytest.fixture
def checked_out_during_fetch(monkeypatch: pytest.MonkeyPatch) -> list[int]:
    """How many database connections were checked out at each fetch."""
    seen: list[int] = []
    real_fetch = unfurl._fetch

    def watched(address: unfurl.Address, resolver: object) -> unfurl.Metadata:
        seen.append(fieldclub_db.get_engine().pool.checkedout())  # type: ignore[attr-defined]
        return real_fetch(address, resolver)  # type: ignore[arg-type]

    monkeypatch.setattr(unfurl, "_fetch", watched)
    return seen


# --------------------------------------------------------------------------
# No database connection is held while a stranger's server answers
# --------------------------------------------------------------------------


def test_a_preview_holds_no_database_connection_while_it_fetches(
    client_as: ClientAs,
    make_user: MakeUser,
    db: Session,
    offline: respx.MockRouter,
    checked_out_during_fetch: list[int],
) -> None:
    serve_youtube_oembed()
    client = client_as(make_user())
    db.close()
    assert client.post(f"{API}/mentions/preview", json={"url": YOUTUBE_URL}).status_code == 200
    assert checked_out_during_fetch == [0]


def test_adding_holds_no_database_connection_while_it_fetches(
    client_as: ClientAs,
    make_user: MakeUser,
    make_finding: MakeFinding,
    db: Session,
    offline: respx.MockRouter,
    checked_out_during_fetch: list[int],
) -> None:
    serve_youtube_oembed()
    finding = make_finding()
    client = client_as(make_user())
    db.close()
    response = post(client, finding, YOUTUBE_URL, note="Near the end.")
    assert response.status_code == 201
    assert checked_out_during_fetch == [0]
    stored = db.get(Mention, response.json()["id"])
    assert stored is not None
    assert stored.note == "Near the end."


def test_a_finding_withdrawn_while_the_address_was_fetched_gets_nothing(
    client_as: ClientAs,
    make_user: MakeUser,
    make_finding: MakeFinding,
    db: Session,
    offline: respx.MockRouter,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    serve_youtube_oembed()
    finding = make_finding()
    real_unfurl = unfurl.unfurl

    def withdraw_meanwhile(address: unfurl.Address, **kwargs: object) -> unfurl.Unfurled:
        with fieldclub_db.SessionLocal() as other:
            other.get_one(Finding, finding.id).state = "withdrawn"
            other.commit()
        return real_unfurl(address)

    monkeypatch.setattr(unfurl, "unfurl", withdraw_meanwhile)
    response = post(client_as(make_user()), finding, YOUTUBE_URL)
    assert error_code(response) == "finding_withdrawn"
    assert db.scalars(select(Mention)).all() == []


# --------------------------------------------------------------------------
# The fetch budget for the whole process
# --------------------------------------------------------------------------


def budget_left() -> float:
    return unfurl._all_fetches.remaining("all")


@pytest.mark.usefixtures("limits_on")
def test_callers_who_arent_contributors_spend_nothing(
    client: TestClient, make_finding: MakeFinding, offline: respx.MockRouter
) -> None:
    finding = make_finding()
    full = budget_left()
    for n in range(40):
        headers = {"X-Forwarded-For": f"203.0.113.{n}"}
        preview = client.post(f"{API}/mentions/preview", json={"url": YOUTUBE_URL}, headers=headers)
        added = client.post(
            f"{API}/findings/{finding.public_id}/mentions", json={"url": YOUTUBE_URL}, headers=headers
        )
        assert (preview.status_code, added.status_code) == (401, 401)
    assert budget_left() == full
    assert offline.calls.call_count == 0


@pytest.mark.usefixtures("limits_on")
def test_only_a_real_fetch_spends_the_budget(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, offline: respx.MockRouter
) -> None:
    serve_youtube_oembed()
    finding = make_finding()
    client = client_as(make_user())
    full = budget_left()
    assert client.post(f"{API}/mentions/preview", json={"url": YOUTUBE_URL}).status_code == 200
    assert budget_left() == pytest.approx(full - 1, abs=0.5)
    # The add finds the preview's answer in the cache.
    assert post(client, finding, YOUTUBE_URL).status_code == 201
    # A duplicate, a missing finding and a withdrawn one are refused before any fetch.
    assert error_code(post(client, finding, YOUTUBE_URL)) == "mention_exists"
    missing = client.post(f"{API}/findings/ZZZZZZ/mentions", json={"url": "https://example.org/a"})
    assert missing.status_code == 404
    assert budget_left() == pytest.approx(full - 1, abs=0.5)
    assert offline.calls.call_count == 1


@pytest.mark.usefixtures("limits_on")
def test_a_used_up_budget_leaves_the_address_unfetched_and_uncached(
    client_as: ClientAs, make_user: MakeUser, offline: respx.MockRouter
) -> None:
    route = serve_youtube_oembed()
    client = client_as(make_user())
    unfurl._all_fetches.hit("all", cost=budget_left())

    def preview() -> dict[str, object]:
        response = client.post(f"{API}/mentions/preview", json={"url": YOUTUBE_URL})
        assert response.status_code == 200
        return response.json()

    assert preview()["fetch_status"] == "failed"
    assert route.call_count == 0
    unfurl._all_fetches.reset()
    assert preview()["fetch_status"] == "ok"


# --------------------------------------------------------------------------
# Invisible characters
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url",
    [
        "https://example.org/gro\u202eexe.lmth",
        "https://exa\u200bmple.org/",
        "https://example.org/a\u2066b",
        "https://example.org/\ufeff",
        "https://example.org/a\u00adb",
    ],
)
def test_an_address_with_invisible_characters_is_refused(
    client_as: ClientAs, make_user: MakeUser, make_finding: MakeFinding, url: str
) -> None:
    assert error_code(post(client_as(make_user()), make_finding(), url)) == "invalid_address"


@pytest.mark.parametrize("note", ["\u200b\u202e", "  \ufeff ", ""])
def test_a_note_with_nothing_visible_is_no_note(
    client_as: ClientAs,
    make_user: MakeUser,
    make_finding: MakeFinding,
    offline: respx.MockRouter,
    note: str,
) -> None:
    serve_youtube_oembed()
    response = post(client_as(make_user()), make_finding(), YOUTUBE_URL, note=note)
    assert response.status_code == 201
    assert response.json()["note"] is None
