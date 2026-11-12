"""Creating, editing and withdrawing findings, in the service and over HTTP."""

from __future__ import annotations

import pytest
from shapely.geometry import Point, box
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.models import Activity, Finding, Follow
from fieldclub.services import findings, ids
from fieldclub.services.findings import NotFinderError, OutsideBritishIslesError
from fieldclub.vocab import FeatureClass, Sensitivity
from tests.findings.support import API, LAT, LON, create, point, square_around
from tests.helpers import ClientAs, MakeUser, count, error_code, lon_lat


def test_a_new_finding_is_spotted_assessed_followed_and_announced(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder, view_state={"layer": "slope", "zoom": 16})
    assert finding.tier == "spotted"
    assert finding.state == "open"
    assert finding.confidence == 10
    assert finding.title == "Enclosure in SU 10 69"
    assert finding.grid_ref == gridref.to_gridref(LON, LAT)
    assert lon_lat(finding.location) == pytest.approx((LON, LAT))
    assert finding.assessment["version"] == 1
    assert finding.open_steps == ["need_observers"]
    assert finding.answers_to_next == 2
    assert ids.normalise(finding.public_id) == finding.public_id
    assert db.scalar(select(Follow).where(Follow.finding_id == finding.id, Follow.user_id == finder.id))
    assert db.scalars(select(Activity.kind)).all() == ["finding_created"]


@pytest.mark.parametrize(
    ("feature_class", "requested", "role", "expected"),
    [
        ("enclosure", None, "member", "open"),
        ("round_barrow", None, "member", "protected"),
        ("round_barrow", "open", "member", "protected"),
        ("round_barrow", "restricted", "member", "restricted"),
        ("round_barrow", "open", "moderator", "open"),
        ("enclosure", "restricted", "member", "restricted"),
    ],
)
def test_the_starting_level_is_the_higher_of_class_and_request_unless_a_moderator_lowers_it(
    db: Session, make_user: MakeUser, feature_class: str, requested: str | None, role: str, expected: str
) -> None:
    finding = create(db, make_user(role), feature_class=feature_class, requested_sensitivity=requested)
    assert finding.sensitivity == expected


def test_a_change_to_a_more_sensitive_class_raises_the_level_and_never_lowers_it(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = create(db, finder)
    findings.update_finding(
        db, findings.lock(db, finding), finder, {"feature_class": FeatureClass.ROUND_BARROW}
    )
    db.commit()
    assert finding.sensitivity == "protected"
    findings.update_finding(db, findings.lock(db, finding), finder, {"feature_class": FeatureClass.ENCLOSURE})
    db.commit()
    assert finding.sensitivity == "protected"
    # The finder's class counts towards class support, so it is reassessed.
    assert finding.assessment["class_support"] == {"enclosure": 1.0}


def test_moving_a_finding_keeps_the_grid_reference_and_public_position_in_step(
    db: Session, make_user: MakeUser
) -> None:
    finder = make_user()
    finding = create(db, finder, feature_class="round_barrow")
    moved = Point(-1.8263, 51.4110)
    findings.update_finding(db, findings.lock(db, finding), finder, {"location": moved})
    db.commit()
    db.expire_all()
    assert finding.grid_ref == gridref.to_gridref(moved.x, moved.y)
    assert lon_lat(finding.location_public) == pytest.approx(
        gridref.square_1km(moved.x, moved.y).polygon.centroid.coords[0], abs=1e-4
    )


def test_only_the_finder_edits_or_withdraws(db: Session, make_user: MakeUser) -> None:
    finding = create(db, make_user())
    stranger = make_user("moderator")
    with pytest.raises(NotFinderError):
        findings.update_finding(db, findings.lock(db, finding), stranger, {"title": "Mine now"})
    with pytest.raises(NotFinderError):
        findings.withdraw_finding(db, findings.lock(db, finding), stranger)


def test_withdrawing_records_the_state_change(db: Session, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder)
    result = findings.withdraw_finding(db, findings.lock(db, finding), finder)
    db.commit()
    assert (result.state_before.value, result.state_after.value) == ("open", "withdrawn")
    assert finding.state == "withdrawn"
    assert finding.open_steps == []
    changed = db.scalars(select(Activity).where(Activity.kind == "state_changed")).one()
    assert changed.data == {"from": "open", "to": "withdrawn", "reason": None}
    with pytest.raises(findings.FindingClosedError):
        findings.withdraw_finding(db, findings.lock(db, finding), finder)


@pytest.mark.parametrize(
    ("lon", "lat"),
    [
        (2.3522, 48.8566),  # Paris
        (1.8587, 50.9513),  # Calais
        (-1.62, 49.64),  # Cherbourg
        (-2.13, 49.21),  # Jersey: British Isles, but on neither grid
        (5.32, 60.39),  # Bergen
        (-20.0, 55.0),  # the Atlantic
    ],
)
def test_positions_outside_the_british_isles_are_refused(
    db: Session, make_user: MakeUser, lon: float, lat: float
) -> None:
    with pytest.raises(OutsideBritishIslesError):
        create(db, make_user(), lon=lon, lat=lat)


@pytest.mark.parametrize(
    ("lon", "lat"),
    [(-6.30, 49.92), (-5.93, 54.60), (-6.26, 53.35), (-1.15, 60.15), (1.40, 51.36), (-4.48, 54.15)],
)
def test_the_edges_of_the_british_isles_are_accepted(
    db: Session, make_user: MakeUser, lon: float, lat: float
) -> None:
    # Scilly, Belfast, Dublin, Shetland, Margate, the Isle of Man.
    assert create(db, make_user(), lon=lon, lat=lat).grid_ref is not None


def test_an_outline_must_be_near_its_point_and_not_too_big(db: Session, make_user: MakeUser) -> None:
    """An outline is read as an all-corner path, held to the limits in `services.shapes`."""
    author = make_user()
    assert (
        create(db, author, outline=box(LON - 0.001, LAT - 0.001, LON + 0.001, LAT + 0.001)).outline
        is not None
    )
    with pytest.raises(findings.ValidationFailedError) as far:
        create(db, author, outline=box(LON + 0.1, LAT, LON + 0.11, LAT + 0.01))
    assert far.value.code == "outline_too_far"
    with pytest.raises(findings.ValidationFailedError) as big:
        create(db, author, outline=box(LON - 0.2, LAT - 0.2, LON + 0.2, LAT + 0.2))
    assert big.value.code == "shape_too_big"


def test_a_public_id_clash_is_retried_by_inserting_again(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = create(db, make_user()).public_id
    choices = iter([taken, taken, "7K3QXM"])
    monkeypatch.setattr(ids, "generate", lambda: next(choices))
    finding = create(db, make_user())
    assert finding.public_id == "7K3QXM"
    assert count(db, Finding) == 2


def test_running_out_of_public_ids_is_a_clear_error(
    db: Session, make_user: MakeUser, monkeypatch: pytest.MonkeyPatch
) -> None:
    taken = create(db, make_user()).public_id
    monkeypatch.setattr(ids, "generate", lambda: taken)
    with pytest.raises(ids.IdGenerationError):
        create(db, make_user())


# --------------------------------------------------------------------------
# Over HTTP
# --------------------------------------------------------------------------


def test_create_over_http(client_as: ClientAs, make_user: MakeUser) -> None:
    response = client_as(make_user()).post(
        f"{API}/findings",
        json={
            "location": point(),
            "feature_class": "hillfort",
            "title": "Ramparts on the ridge",
            "description": "Two banks.",
            "period": "iron_age",
            "outline": square_around(),
            "view_state": {"layer": "slope", "zoom": 16.5, "sun_azimuth": 315},
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert (body["title"], body["period"], body["tier"]) == ("Ramparts on the ridge", "iron_age", "spotted")
    assert body["location"]["outline"]["type"] == "Polygon"
    assert body["view_state"]["sun_azimuth"] == 315
    assert body["following"] is True
    assert response.headers["cache-control"] == "private, no-cache"


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"location": point(2.35, 48.85), "feature_class": "enclosure"}, "outside_british_isles"),
        ({"location": square_around(), "feature_class": "enclosure"}, "validation_error"),
        ({"location": point(), "feature_class": "castle"}, "validation_error"),
        (
            {"location": point(), "feature_class": "enclosure", "view_state": {"centre": [1, 2]}},
            "validation_error",
        ),
        ({"location": point(), "feature_class": "enclosure", "secret": 1}, "validation_error"),
        ({"location": point(), "feature_class": "enclosure", "title": "x" * 121}, "validation_error"),
    ],
)
def test_create_refuses_bad_input(client_as: ClientAs, make_user: MakeUser, body: dict, code: str) -> None:
    response = client_as(make_user()).post(f"{API}/findings", json=body)
    assert response.status_code == 422
    assert error_code(response) == code


def test_writes_need_a_contributor(client, client_as: ClientAs, make_user: MakeUser, newcomer) -> None:
    body = {"location": point(), "feature_class": "enclosure"}
    assert error_code(client.post(f"{API}/findings", json=body)) == "unauthorised"
    assert error_code(client_as(newcomer).post(f"{API}/findings", json=body)) == "onboarding_required"


def test_edit_over_http(client_as: ClientAs, make_user: MakeUser, db: Session) -> None:
    finder = make_user()
    finding = create(db, finder, description="First go")
    response = client_as(finder).patch(
        f"{API}/findings/{finding.public_id}",
        json={"title": "Better title", "description": None, "location": point(-1.8263, 51.4110)},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert (body["title"], body["description"]) == ("Better title", None)
    assert body["location"]["grid_ref"] == gridref.to_gridref(-1.8263, 51.4110)
    other = client_as(make_user()).patch(f"{API}/findings/{finding.public_id}", json={"title": "Nope"})
    assert error_code(other) == "not_finder"
    assert error_code(
        client_as(finder).patch(f"{API}/findings/{finding.public_id}", json={"location": None})
    ) == ("location_required")


def test_unknown_and_malformed_ids_are_not_found(client) -> None:
    assert error_code(client.get(f"{API}/findings/ZZZZZZ")) == "finding_not_found"
    assert error_code(client.get(f"{API}/findings/not-an-id-at-all")) == "finding_not_found"


def test_a_hidden_finding_is_seen_only_by_its_finder_and_moderators(
    db: Session,
    client,
    client_as: ClientAs,
    make_user: MakeUser,
) -> None:
    from datetime import UTC, datetime

    finder = make_user()
    finding = create(db, finder)
    finding.hidden_at = datetime.now(UTC)
    db.commit()
    path = f"{API}/findings/{finding.public_id}"
    assert client.get(path).status_code == 404
    assert client_as(make_user()).get(path).status_code == 404
    assert client_as(make_user("trusted")).get(path).status_code == 404
    assert client_as(finder).get(path).status_code == 200
    assert client_as(make_user("moderator")).get(path).status_code == 200
    assert client.get(f"{API}/findings").json()["items"] == []


def test_level_changes_follow_decision_0005(db: Session, client_as: ClientAs, make_user: MakeUser) -> None:
    finder = make_user()
    finding = create(db, finder)
    path = f"{API}/findings/{finding.public_id}/sensitivity"
    assert client_as(make_user()).put(path, json={"level": "protected"}).status_code == 403
    assert client_as(finder).put(path, json={"level": "protected"}).json()["sensitivity"] == "protected"
    # Restricted is no longer a level anyone can set (Decision 0032).
    assert client_as(make_user("trusted")).put(path, json={"level": "restricted"}).status_code == 422
    lowered = client_as(finder).put(path, json={"level": "open"})
    assert error_code(lowered) == "sensitivity_change_forbidden"
    assert error_code(client_as(make_user("trusted")).put(path, json={"level": "open"})) == (
        "sensitivity_change_forbidden"
    )
    # A moderator lowers a level only through the moderation route, which logs it with a reason.
    moderator = client_as(make_user("moderator"))
    refused = moderator.put(path, json={"level": "open"})
    assert (refused.status_code, error_code(refused)) == (403, "lower_through_moderation")
    lowered = moderator.put(
        f"{API}/mod{path.removeprefix(API)}", json={"level": "open", "reason": "Not a barrow."}
    )
    assert lowered.json()["sensitivity"] == "open"
    db.expire_all()
    assert Sensitivity(finding.sensitivity) is Sensitivity.OPEN
    assert lon_lat(finding.location_public) == pytest.approx((LON, LAT))


def _ring(points: int, lon: float = LON, lat: float = LAT, radius: float = 0.001) -> list[list[float]]:
    # Wide enough that 2,000 corners stay the 1e-6 degrees apart a path needs (`shapes.read_path`).
    import math

    ring = [
        [lon + radius * math.cos(2 * math.pi * i / points), lat + radius * math.sin(2 * math.pi * i / points)]
        for i in range(points)
    ]
    return [*ring, ring[0]]


def test_an_outline_has_at_most_two_thousand_points(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    """Every list of findings carries the outline, so one huge outline costs every visitor."""
    from fieldclub.schemas.common import GEOMETRY_MAX_POINTS

    client = client_as(make_user())
    fits = {"type": "Polygon", "coordinates": [_ring(GEOMETRY_MAX_POINTS - 1)]}
    made = client.post(
        f"{API}/findings", json={"location": point(), "feature_class": "enclosure", "outline": fits}
    )
    assert made.status_code == 201, made.text
    path = f"{API}/findings/{made.json()['public_id']}"
    huge = {"type": "Polygon", "coordinates": [_ring(GEOMETRY_MAX_POINTS)]}
    refused = client.post(
        f"{API}/findings", json={"location": point(), "feature_class": "enclosure", "outline": huge}
    )
    assert refused.status_code == 422
    assert error_code(refused) == "geometry_too_complex"
    assert error_code(client.patch(path, json={"outline": huge})) == "geometry_too_complex"
    # Many small parts count too.
    parts = {
        "type": "MultiPolygon",
        "coordinates": [
            [
                [
                    [LON + i * 1e-5, LAT],
                    [LON + i * 1e-5 + 5e-6, LAT],
                    [LON + i * 1e-5, LAT + 5e-6],
                    [LON + i * 1e-5, LAT],
                ]
            ]
            for i in range(300)
        ],
    }
    assert error_code(client.patch(path, json={"outline": parts})) == "geometry_too_complex"
    assert count(db, Finding) == 1


def test_a_shape_with_an_empty_hole_is_refused_and_the_api_keeps_answering(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    """GEOS crashed the whole process testing such a shape against the British Isles."""
    client = client_as(make_user())
    ring = [[LON, LAT], [LON + 0.001, LAT], [LON + 0.001, LAT + 0.001], [LON, LAT]]
    holed = {"type": "Polygon", "coordinates": [ring, []]}
    refused = client.post(
        f"{API}/findings", json={"location": point(), "feature_class": "enclosure", "outline": holed}
    )
    assert refused.status_code == 422, refused.text
    assert error_code(refused) == "validation_error"
    made = client.post(f"{API}/findings", json={"location": point(), "feature_class": "enclosure"}).json()
    assert error_code(client.patch(f"{API}/findings/{made['public_id']}", json={"outline": holed})) == (
        "validation_error"
    )
    area = client.post(f"{API}/investigations", json={"title": "Holes", "area": holed})
    assert error_code(area) == "validation_error"
    assert client.get("/healthz").status_code == 200


def test_the_map_answer_draws_points_and_carries_no_outline(
    db: Session, client_as: ClientAs, make_user: MakeUser
) -> None:
    client = client_as(make_user())
    outline = {"type": "Polygon", "coordinates": [_ring(500)]}
    assert (
        client.post(
            f"{API}/findings", json={"location": point(), "feature_class": "enclosure", "outline": outline}
        ).status_code
        == 201
    )
    features = client.get(f"{API}/findings", params={"format": "geojson"}).json()["features"]
    assert [feature["geometry"]["type"] for feature in features] == ["Point"]
    assert "outline" not in str(features)
