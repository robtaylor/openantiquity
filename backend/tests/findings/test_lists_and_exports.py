"""Lists, the map GeoJSON the frontend reads, exports, discussion, help wanted and rate limits."""

from __future__ import annotations

import csv
import io

import pytest
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Comment, Finding, Follow, Notification
from fieldclub.schemas.findings import URL_MAX
from fieldclub.services import exports, findings
from fieldclub.vocab import EvidenceKind, FeatureClass, Visible
from tests.findings.support import API, LAT, LON, add_desk_evidence, answer, create, point
from tests.helpers import ClientAs, MakeUser, error_code

# --------------------------------------------------------------------------
# Lists
# --------------------------------------------------------------------------


def _ids(response) -> list[str]:
    return [item["public_id"] for item in response.json()["items"]]


def test_filters(db: Session, client, make_user: MakeUser) -> None:
    ann, ben = make_user(handle="Ann"), make_user(handle="Ben")
    barrow = create(db, ann, feature_class=FeatureClass.HILLFORT, title="Big ramparts")
    moat = create(db, ben, feature_class=FeatureClass.MOAT, title="Square moat", lon=-1.70, lat=51.50)
    answer(db, moat, ann)
    answer(db, moat, make_user())
    withdrawn = create(db, ben, title="Oops")
    findings.withdraw_finding(db, findings.lock(db, withdrawn), ben)
    db.commit()

    def ids(**params: object) -> set[str]:
        return set(_ids(client.get(f"{API}/findings", params=params)))

    assert ids() == {barrow.public_id, moat.public_id}
    assert ids(tier="seen") == {moat.public_id}
    assert ids(feature_class=["hillfort", "moat"]) == {barrow.public_id, moat.public_id}
    assert ids(author="ann") == {barrow.public_id}
    assert ids(q="RAMP") == {barrow.public_id}
    assert ids(q=moat.public_id) == {moat.public_id}
    assert ids(q="100%_") == set()
    assert ids(state="withdrawn") == {withdrawn.public_id}
    assert ids(bbox="-1.72,51.49,-1.69,51.51") == {moat.public_id}
    assert _ids(client.get(f"{API}/findings", params={"sort": "confidence"}))[0] == moat.public_id


@pytest.mark.parametrize("sort", ["newest", "oldest", "confidence", "updated"])
def test_every_sort_pages_through_everything_once(
    db: Session, client, make_user: MakeUser, sort: str
) -> None:
    author = make_user()
    made = {create(db, author, lon=LON + 0.001 * n).public_id for n in range(7)}
    seen: list[str] = []
    cursor = None
    while True:
        params = {"limit": 3, "sort": sort} | ({"cursor": cursor} if cursor else {})
        page = client.get(f"{API}/findings", params=params).json()
        seen += [item["public_id"] for item in page["items"]]
        cursor = page["next_cursor"]
        if cursor is None:
            break
    assert sorted(seen) == sorted(made)


@pytest.mark.parametrize(
    ("params", "code"),
    [
        ({"bbox": "1,2,3"}, "invalid_bbox"),
        ({"bbox": "a,b,c,d"}, "invalid_bbox"),
        ({"bbox": "-1,52,-2,53"}, "invalid_bbox"),
        ({"bbox": "nan,51,1,52"}, "invalid_bbox"),
        ({"limit": 500}, "validation_error"),
        ({"limit": 1001, "format": "geojson"}, "validation_error"),
        ({"cursor": "garbage"}, "invalid_cursor"),
        ({"sort": "random"}, "validation_error"),
    ],
)
def test_bad_list_parameters(client, params: dict, code: str) -> None:
    assert error_code(client.get(f"{API}/findings", params=params)) == code


def test_the_map_gets_what_the_frontend_reads(db: Session, client, make_user: MakeUser) -> None:
    """What frontend/src/features/findings/types.ts reads: a Point, public_id, tier, state, obscured."""
    create(db, make_user(), feature_class=FeatureClass.ROUND_BARROW)
    body = client.get(
        f"{API}/findings", params={"bbox": "-1.861,51.42,-1.84,51.44", "format": "geojson"}
    ).json()
    assert body["type"] == "FeatureCollection"
    (feature,) = body["features"]
    assert feature["geometry"]["type"] == "Point"
    props = feature["properties"]
    assert {
        "public_id",
        "tier",
        "state",
        "sensitivity",
        "obscured",
        "square",
        "title",
        "feature_class",
    } <= set(props)
    assert (props["obscured"], props["square"], props["sensitivity"]) == (True, "SU1069", "protected")
    assert feature["id"] == props["public_id"]
    assert body["next_cursor"] is None


# --------------------------------------------------------------------------
# Exports
# --------------------------------------------------------------------------


def test_csv_has_the_her_columns(db: Session, client, make_user: MakeUser) -> None:
    author = make_user(handle="Ann", display_name="Ann Example")
    finding = create(
        db, author, feature_class=FeatureClass.HILLFORT, title="=HYPERLINK(1)", period="iron_age"
    )
    add_desk_evidence(db, finding, make_user(), EvidenceKind.HISTORIC_MAP, title="OS 1888")
    add_desk_evidence(db, finding, make_user(), EvidenceKind.AERIAL)
    add_desk_evidence(db, finding, make_user(), EvidenceKind.AERIAL)
    response = client.get(f"{API}/findings/{finding.public_id}/export", params={"format": "csv"})
    assert response.headers["content-type"].startswith("text/csv")
    assert (
        response.headers["content-disposition"] == f'attachment; filename="fieldclub-{finding.public_id}.csv"'
    )
    (row,) = list(csv.DictReader(io.StringIO(response.text)))
    assert tuple(row) == exports.COLUMNS
    assert row["name"] == "'=HYPERLINK(1)"
    assert (row["monument_type"], row["period"], row["licence"]) == ("HILLFORT", "Iron Age", "CC BY 4.0")
    assert row["grid_reference"] == finding.grid_ref
    assert (row["grid"], row["position_precision_m"]) == ("osgb", "10")
    assert 400_000 < int(row["easting"]) < 420_000
    assert row["evidence_summary"] == "Aerial photo (2); Old map: OS 1888"
    assert row["compiler"] == "Ann Example"
    assert row["url"].endswith(f"/f/{finding.public_id}")


def test_geojson_export(db: Session, client, make_user: MakeUser) -> None:
    finding = create(db, make_user())
    response = client.get(f"{API}/findings/{finding.public_id}/export")
    assert response.headers["content-type"] == "application/geo+json"
    (feature,) = response.json()["features"]
    assert feature["geometry"]["coordinates"] == [LON, LAT]
    assert feature["properties"]["monument_type"] == "ENCLOSURE"
    assert feature["properties"]["obscured"] is False


def test_a_filtered_export_pages(db: Session, client, make_user: MakeUser) -> None:
    author = make_user()
    for n in range(3):
        create(db, author, lon=LON + 0.001 * n)
    first = client.get(f"{API}/findings/export", params={"format": "csv", "limit": 2})
    assert len(list(csv.DictReader(io.StringIO(first.text)))) == 2
    rest = client.get(
        f"{API}/findings/export",
        params={"format": "csv", "limit": 2, "cursor": first.headers["x-next-cursor"]},
    )
    assert len(list(csv.DictReader(io.StringIO(rest.text)))) == 1
    assert "x-next-cursor" not in rest.headers


# --------------------------------------------------------------------------
# Discussion and follows
# --------------------------------------------------------------------------


def test_comments_threads_and_follows(db: Session, client, client_as: ClientAs, make_user: MakeUser) -> None:
    finder, talker = make_user(), make_user()
    finding = create(db, finder)
    path = f"{API}/findings/{finding.public_id}/comments"
    posted = client_as(talker).post(path, json={"body": "Is that a bank?"})
    assert posted.status_code == 201
    first = posted.json()
    reply = client_as(finder).post(path, json={"body": "I think so.", "parent_id": first["id"]}).json()
    assert reply["parent_id"] == first["id"]
    assert (
        error_code(client_as(finder).post(path, json={"body": "x", "parent_id": 999_999}))
        == "comment_not_found"
    )
    assert client_as(talker).post(path, json={"body": ""}).status_code == 422
    # The commenter follows the finding, and the finder heard about the comment.
    assert db.scalar(select(Follow).where(Follow.user_id == talker.id, Follow.finding_id == finding.id))
    assert db.scalars(select(Notification.kind).where(Notification.user_id == finder.id)).all() == [
        "comment_added"
    ]

    assert error_code(client_as(finder).delete(f"{API}/comments/{first['id']}")) == "comment_forbidden"
    assert client_as(talker).delete(f"{API}/comments/{first['id']}").status_code == 204
    listed = client.get(path).json()["items"]
    assert (listed[0]["deleted"], listed[0]["body"], listed[0]["author"]) == (True, None, None)
    assert listed[1]["body"] == "I think so."
    db.expire_all()
    assert db.get(Finding, finding.id).comment_count == 1  # pyright: ignore[reportOptionalMemberAccess]

    follow = f"{API}/findings/{finding.public_id}/follow"
    assert client_as(talker).delete(follow).json() == {"following": False}
    assert client_as(talker).get(f"{API}/findings/{finding.public_id}").json()["following"] is False
    assert client_as(talker).put(follow).json() == {"following": True}
    assert client_as(talker).put(follow).json() == {"following": True}
    assert client.put(follow).status_code == 401


def test_comments_page(db: Session, client, make_user: MakeUser) -> None:
    finding = create(db, make_user())
    talker = make_user()
    for n in range(5):
        db.add(Comment(finding_id=finding.id, user_id=talker.id, body=f"Comment {n}"))
    db.commit()
    first = client.get(f"{API}/findings/{finding.public_id}/comments", params={"limit": 3}).json()
    rest = client.get(
        f"{API}/findings/{finding.public_id}/comments", params={"limit": 3, "cursor": first["next_cursor"]}
    ).json()
    assert [c["body"] for c in first["items"] + rest["items"]] == [f"Comment {n}" for n in range(5)]


# --------------------------------------------------------------------------
# Help wanted
# --------------------------------------------------------------------------


def test_tasks_are_grouped_by_code_and_page_within_one(
    db: Session, client, client_as: ClientAs, make_user: MakeUser
) -> None:
    finder = make_user()
    waiting = [create(db, finder, lon=LON + 0.001 * n) for n in range(3)]
    seen = create(db, finder, lon=LON - 0.01)
    answer(db, seen, make_user(), Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    answer(db, seen, make_user(), Visible.YES, feature_class=FeatureClass.ENCLOSURE)
    groups = {g["code"]: g for g in client.get(f"{API}/review/tasks").json()["groups"]}
    assert groups["need_observers"]["total"] == 3
    assert groups["need_strand"]["total"] == 1
    (strand,) = groups["need_strand"]["items"]
    assert strand["finding"]["title"] == "Enclosure"
    assert strand["step"]["strands_needed"] == 2
    assert "historic_map" in strand["step"]["missing_strands"]

    # The finder isn't offered second looks at their own findings.
    mine = {g["code"]: g for g in client_as(finder).get(f"{API}/review/tasks").json()["groups"]}
    assert mine["need_observers"]["total"] == 0

    page = client.get(f"{API}/review/tasks", params={"code": "need_observers", "limit": 2}).json()
    (group,) = page["groups"]
    assert len(group["items"]) == 2
    rest = client.get(
        f"{API}/review/tasks", params={"code": "need_observers", "limit": 2, "cursor": group["next_cursor"]}
    ).json()["groups"][0]
    assert {t["public_id"] for t in group["items"] + rest["items"]} == {f.public_id for f in waiting}
    assert (
        error_code(client.get(f"{API}/review/tasks", params={"cursor": group["next_cursor"]}))
        == "code_required"
    )


# --------------------------------------------------------------------------
# Rate limits
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("limits_on")
def test_writes_are_rate_limited(client_as: ClientAs, make_user: MakeUser) -> None:
    client = client_as(make_user())
    body = {"location": point(), "feature_class": "enclosure"}
    statuses = [client.post(f"{API}/findings", json=body).status_code for _ in range(61)]
    assert statuses[:60] == [201] * 60
    assert statuses[60] == 429


def test_repeated_filters_and_long_links_are_capped(
    db: Session, client, client_as: ClientAs, make_user: MakeUser
) -> None:
    many = client.get(f"{API}/findings", params=[("tier", "seen")] * 500)
    assert (many.status_code, error_code(many)) == (422, "validation_error")
    assert client.get(f"{API}/findings", params=[("tier", "seen")] * 2).status_code == 200

    finding = create(db, make_user())
    path = f"{API}/findings/{finding.public_id}/evidence"
    helper = client_as(make_user())
    base = "https://example.org/"
    too_long = helper.post(path, json={"kind": "aerial", "url": base + "a" * (URL_MAX - len(base) + 1)})
    assert error_code(too_long) == "validation_error"
    assert (
        helper.post(path, json={"kind": "aerial", "url": base + "a" * (URL_MAX - len(base))}).status_code
        == 201
    )
