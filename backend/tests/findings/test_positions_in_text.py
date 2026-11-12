"""Positions written in a finding's free text (Decision 0005).

A finding that isn't open refuses a title or description that says where it
is more closely than its 1 km square. Text written while it was open, and
text other people wrote, reaches anyone who doesn't see the exact position
with every such position replaced.
"""

from __future__ import annotations

from typing import Any

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import update
from sqlalchemy.orm import Session

from fieldclub.models import Finding
from fieldclub.services import findings, sensitivity
from fieldclub.services.text_positions import PLACEHOLDER
from fieldclub.vocab import EvidenceKind, FeatureClass, InvestigationItemKind, Sensitivity, Visible
from tests.findings.support import API, add_desk_evidence, answer, create, point
from tests.helpers import ClientAs, MakeUser, error_code
from tests.investigations.support import add, make
from tests.moderation.support import comment, mention

# A position in each free-text field, each written a different way, so a leak names its field.
WRITTEN = {
    "title": "Bank at SU 1025 6996",
    "description": "Seen from 51.4286, -1.8542 at dusk",
    "evidence_title": "Estate map, plot at ST 123 456",
    "evidence_note": "Gate at ///filled.count.soap",
    "comment": "Park at su 10200 69900 and walk",
    "answer_note": "Faint at E 410250 N 169960",
    "mention_title": "Walk to SK 111 222",
    "mention_note": "From 51°25'43\"N 1°51'15\"W",
    "item_note": "Recheck at TL 333 444",
    # Map links, as people paste them, in a comment, an evidence link and a mention's address.
    "map_comment": "Bing https://www.bing.com/maps?cp=51.42879~-1.85403&lvl=18 and Google "
    "https://www.google.com/maps/place/51%C2%B025%2743.5%22N+1%C2%B051%2715.5%22W",
    "evidence_url": "https://www.openstreetmap.org/?mlat=51.42877&mlon=-1.85401#map=18/51.42877/-1.85401",
    "mention_url": "https://www.openstreetmap.org/?mlat=51.42871&mlon=-1.85409",
}
POSITIONS = (
    "1025 6996",
    "51.4286",
    "ST 123 456",
    "filled.count",
    "10200 69900",
    "410250",
    "SK 111 222",
    '43"N',
    "333 444",
    "42879",
    "2743.5",
    "42877",
    "42871",
)


def _create(client: TestClient, **fields: Any):
    return client.post(f"{API}/findings", json={"location": point(), **fields})


def test_a_protected_finding_refuses_a_position_in_its_title_or_description(
    client_as: ClientAs, make_user: MakeUser
) -> None:
    client = client_as(make_user())
    refused = _create(
        client, feature_class="round_barrow", title=WRITTEN["title"], description=WRITTEN["description"]
    )
    assert refused.status_code == 422
    assert error_code(refused) == "position_in_text"
    assert [detail["field"] for detail in refused.json()["error"]["details"]] == [
        "body.title",
        "body.description",
    ]
    only = _create(client, feature_class="enclosure", sensitivity="protected", description="At ///a.bb.ccc")
    assert error_code(only) == "position_in_text"
    assert [detail["field"] for detail in only.json()["error"]["details"]] == ["body.description"]
    # The 1 km square, and an open finding, are fine.
    assert _create(client, feature_class="round_barrow", title="Barrow in SU 10 69").status_code == 201
    assert _create(client, feature_class="enclosure", title=WRITTEN["title"]).status_code == 201


@pytest.mark.parametrize(
    "description",
    [
        "Lat: 51.4286, Long: -1.8542",
        "Bank at SU 123-456",
        "GPS N51 25.716 W1 51.250",
        "Centre 410250 169960",
        "51d25m43s N 1d51m15s W",
        "51,4286 -1,8542",
        # Full-width figures, a plus code, and short links to map sites.
        "Barrow \uff33\uff35\uff11\uff10\uff12\uff13\uff16\uff19\uff19\uff16",
        "Plus code C4HW+F8 Avebury",
        "See https://maps.app.goo.gl/AbCdEf123",
        "See https://geohash.org/gcnstf3c",
    ],
)
def test_positions_written_loosely_are_refused_too(
    client_as: ClientAs, make_user: MakeUser, description: str
) -> None:
    refused = _create(client_as(make_user()), feature_class="round_barrow", description=description)
    assert refused.status_code == 422, description
    assert error_code(refused) == "position_in_text"


def test_editing_refuses_a_position_once_the_finding_is_not_open(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    client = client_as(finder)
    protected = create(db, finder, feature_class=FeatureClass.ROUND_BARROW)
    path = f"{API}/findings/{protected.public_id}"
    refused = client.patch(path, json={"description": "Centre 410250, 169960"})
    assert error_code(refused) == "position_in_text"
    assert refused.json()["error"]["details"][0]["field"] == "body.description"
    assert client.patch(path, json={"description": "A low mound"}).status_code == 200

    # An open finding may hold one, until a change of class would protect it.
    open_one = create(db, finder, feature_class=FeatureClass.ENCLOSURE, title=WRITTEN["title"])
    path = f"{API}/findings/{open_one.public_id}"
    assert client.patch(path, json={"period": "roman"}).status_code == 200
    raised = client.patch(path, json={"feature_class": "round_barrow"})
    assert error_code(raised) == "position_in_text"
    assert raised.json()["error"]["details"][0]["field"] == "body.title"
    db.refresh(open_one)
    assert (open_one.feature_class, open_one.sensitivity) == ("enclosure", "open")
    fixed = client.patch(path, json={"feature_class": "round_barrow", "title": "Barrow"})
    assert fixed.status_code == 200
    assert fixed.json()["sensitivity"] == "protected"


class World:
    """An open finding with a position written into every kind of text, then raised to restricted."""

    def __init__(self, db: Session, make_user: MakeUser, client_as: ClientAs, client: TestClient) -> None:
        self.finder, self.helper, self.member, self.trusted = (
            make_user(),
            make_user(),
            make_user(),
            make_user("trusted"),
        )
        finding = create(
            db, self.finder, feature_class=FeatureClass.ENCLOSURE, title=WRITTEN["title"],
            description=WRITTEN["description"],
        )  # fmt: skip
        add_desk_evidence(
            db, finding, self.helper, EvidenceKind.HISTORIC_MAP,
            title=WRITTEN["evidence_title"], note=WRITTEN["evidence_note"], url=WRITTEN["evidence_url"],
        )  # fmt: skip
        comment(db, finding, self.helper, WRITTEN["comment"])
        comment(db, finding, self.helper, WRITTEN["map_comment"])
        answer(db, finding, self.member, Visible.YES, note=WRITTEN["answer_note"])
        made = mention(db, finding, self.helper, title=WRITTEN["mention_title"])
        made.note = WRITTEN["mention_note"]
        # As `unfurl.canonical` stores an OpenStreetMap link: the fragment goes, the query stays.
        linked = mention(db, finding, self.helper, title="Where it is")
        linked.url = linked.canonical_url = WRITTEN["mention_url"]
        linked.provider = "openstreetmap.org"
        notebook = make(db, self.helper)
        add(
            db, notebook, self.helper,
            kind=InvestigationItemKind.FINDING, finding=finding.public_id, note=WRITTEN["item_note"],
        )  # fmt: skip
        sensitivity.change_sensitivity(db, findings.lock(db, finding), self.finder, Sensitivity.RESTRICTED)
        db.commit()
        self.finding: Finding = finding
        self.notebook = notebook
        self.clients = {
            "signed_out": client,
            "member": client_as(self.member),
            "finder": client_as(self.finder),
            "trusted": client_as(self.trusted),
        }

    def paths(self) -> list[str]:
        f, i = f"/findings/{self.finding.public_id}", f"/investigations/{self.notebook.public_id}"
        return [
            f,
            "/findings",
            "/findings?format=geojson",
            "/findings/export?format=csv",
            "/findings/export?format=geojson",
            f + "/export?format=csv",
            f + "/observations",
            f + "/comments",
            f + "/mentions",
            "/mentions/recent",
            "/activity",
            f"/users/{self.helper.handle}/contributions",
            f"/geo/search?q={self.finding.public_id}",
            "/review/tasks",
            i + "/items",
            i + "/export?format=csv",
            i + "/export?format=geojson",
            i + "/export?format=html",
        ]


@pytest.fixture
def world(db: Session, make_user: MakeUser, client_as: ClientAs, client: TestClient) -> World:
    return World(db, make_user, client_as, client)


def _leaks(text: str) -> list[str]:
    return [position for position in POSITIONS if position in text]


@pytest.mark.parametrize("viewer", ["signed_out", "member"])
def test_no_route_gives_a_written_position_to_someone_who_sees_only_the_square(
    world: World, viewer: str
) -> None:
    client = world.clients[viewer]
    hidden = 0
    for path in world.paths():
        response = client.get(API + path)
        assert response.status_code in (200, 403), (path, response.status_code)
        assert _leaks(response.text) == [], (viewer, path)
        hidden += response.text.count(PLACEHOLDER)
    assert hidden > 0


def test_the_finding_page_hides_every_field_but_keeps_the_rest_of_the_words(world: World) -> None:
    page = world.clients["member"].get(f"{API}/findings/{world.finding.public_id}").json()
    assert page["location"]["obscured"] is True
    assert page["title"] == f"Bank at {PLACEHOLDER}"
    assert page["description"] == f"Seen from {PLACEHOLDER} at dusk"
    (item,) = page["evidence"]
    assert (item["title"], item["note"]) == (f"Estate map, plot at {PLACEHOLDER}", f"Gate at {PLACEHOLDER}")
    assert page["my_observation"]["note"] == f"Faint at {PLACEHOLDER}"


@pytest.mark.parametrize("viewer", ["finder", "trusted"])
def test_those_who_see_the_exact_position_read_the_text_as_written(world: World, viewer: str) -> None:
    client = world.clients[viewer]
    page = client.get(f"{API}/findings/{world.finding.public_id}").json()
    assert (page["title"], page["description"]) == (WRITTEN["title"], WRITTEN["description"])
    comments = client.get(f"{API}/findings/{world.finding.public_id}/comments").json()["items"]
    assert comments[0]["body"] == WRITTEN["comment"]
    listed = client.get(f"{API}/findings/{world.finding.public_id}/mentions").json()["items"]
    by_title = {item["title"]: item for item in listed}
    assert by_title[WRITTEN["mention_title"]]["note"] == WRITTEN["mention_note"]
    assert (
        by_title["Where it is"]["url"] == by_title["Where it is"]["canonical_url"] == WRITTEN["mention_url"]
    )


def test_a_title_search_reads_the_hidden_title_for_those_who_see_only_the_square(world: World) -> None:
    def found(viewer: str, q: str) -> list[str]:
        items = world.clients[viewer].get(f"{API}/findings", params={"q": q}).json()["items"]
        return [item["public_id"] for item in items]

    mine = [world.finding.public_id]
    for q in ("1025", "SU 1025 6996", "6996"):
        assert found("signed_out", q) == [], q
        assert found("member", q) == [], q
        assert found("trusted", q) == mine, q
    assert found("signed_out", "Bank") == mine
    assert found("signed_out", world.finding.public_id) == mine


def test_a_download_hides_what_its_position_hides(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    """A member sees a protected finding exactly on its page, but downloads it by its square."""
    finder, member = make_user(), make_user()
    finding = create(db, finder, feature_class=FeatureClass.ENCLOSURE, description=WRITTEN["description"])
    sensitivity.change_sensitivity(db, findings.lock(db, finding), finder, Sensitivity.PROTECTED)
    db.commit()
    client = client_as(member)
    assert client.get(f"{API}/findings/{finding.public_id}").json()["description"] == WRITTEN["description"]
    csv = client.get(f"{API}/findings/{finding.public_id}/export", params={"format": "csv"}).text
    assert "51.4286" not in csv
    assert PLACEHOLDER in csv
    assert "51.4286" in client_as(finder).get(f"{API}/findings/{finding.public_id}/export?format=csv").text


def test_a_stale_hidden_title_catches_up_the_next_time_the_finding_is_saved(
    db: Session, client: TestClient, make_user: MakeUser
) -> None:
    """A title stored under older rules, or by a write that skipped the ORM, is redone at the next save."""
    finding = create(db, make_user(), feature_class=FeatureClass.ENCLOSURE, title="Bank at SU 123-456")
    db.commit()

    def found(q: str) -> bool:
        items = client.get(f"{API}/findings", params={"q": q}).json()["items"]
        return finding.public_id in [item["public_id"] for item in items]

    finding.sensitivity = Sensitivity.PROTECTED.value
    db.commit()
    assert not found("123-456")
    # As the rules before hyphens counted, and as a row written by Core would leave it.
    for stale in ("Bank at SU 123-456", None):
        db.execute(update(Finding).where(Finding.id == finding.id).values(title_public=stale))
        db.commit()
        db.refresh(finding)
        findings.reassess(db, findings.lock(db, finding), None)
        db.commit()
        db.refresh(finding)
        assert finding.title_public == f"Bank at {PLACEHOLDER}"
        assert not found("123-456")
        assert found("Bank")


@pytest.mark.parametrize("viewer", ["signed_out", "member"])
def test_a_mention_s_address_reaches_only_those_who_see_the_exact_position(
    world: World, db: Session, viewer: str
) -> None:
    """A page's address can say where the finding is in any form, so it goes only to those who see it.

    A video's or a DOI's address is rebuilt from its identifier alone, so it is kept.
    """
    video = mention(db, world.finding, world.helper, title="On YouTube")
    video.provider, video.url = "youtube", "https://youtu.be/dQw4w9WgXcQ?t=30&si=tracking"
    video.canonical_url = "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    video.thumbnail_url = "https://i.ytimg.com/vi/dQw4w9WgXcQ/hqdefault.jpg"
    db.commit()
    client = world.clients[viewer]
    for path in (f"/findings/{world.finding.public_id}/mentions", "/mentions/recent"):
        items = {item["title"]: item for item in client.get(API + path).json()["items"]}
        assert (items["Where it is"]["url"], items["Where it is"]["canonical_url"]) == (None, None), path
        assert items["On YouTube"]["url"] == items["On YouTube"]["canonical_url"] == video.canonical_url
        assert items["On YouTube"]["thumbnail_url"] == video.thumbnail_url
        assert "si=tracking" not in str(items)


def test_a_map_link_is_refused_on_a_finding_that_is_not_open(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    client = client_as(finder)
    protected = create(db, finder, feature_class=FeatureClass.ROUND_BARROW)
    path = f"{API}/findings/{protected.public_id}"
    for link in (WRITTEN["mention_url"], "https://www.bing.com/maps?cp=51.42879~-1.85403&lvl=18"):
        refused = client.post(f"{path}/mentions", json={"url": link})
        assert refused.status_code == 422, link
        assert error_code(refused) == "position_in_text"
        assert refused.json()["error"]["details"][0]["field"] == "body.url"
        evidence = client_as(make_user()).post(
            f"{path}/evidence", json={"kind": "historic_map", "title": "OS map", "url": link}
        )
        assert error_code(evidence) == "position_in_text", evidence.text
    # The same links are fine on an open finding, whose position everyone sees.
    open_one = create(db, finder, feature_class=FeatureClass.ENCLOSURE)
    added = client_as(make_user()).post(
        f"{API}/findings/{open_one.public_id}/evidence",
        json={"kind": "historic_map", "title": "OS map", "url": WRITTEN["mention_url"]},
    )
    assert added.status_code == 201, added.text
