"""Suggested records for a finding, and that they never give away a position the viewer can't see."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import respx
from shapely.geometry import Point
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.ingest.connectors.he_nhle_scheduled_monuments import ScheduledMonuments
from fieldclub.ingest.runner import run_connector
from fieldclub.models import Record
from fieldclub.models.common import point_lon_lat
from fieldclub.services import records
from fieldclub.vocab import FeatureClass, Sensitivity
from tests.helpers import MakeFinding, MakeUser, add_record, add_source
from tests.records.support import MONUMENTS_GPKG, SILBURY, serve_hub


def at(record: Record) -> dict[str, float]:
    """`lon` and `lat` of a record's point, as keyword arguments for `make_finding`."""
    lon, lat = point_lon_lat(record.centroid)
    return {"lon": lon, "lat": lat}


def ids(suggestions: records.SuggestionList) -> list[int]:
    return [item.result.record.id for item in suggestions.items]


@pytest.fixture
def scattered(db: Session) -> list[Record]:
    """Records scattered over the 1 km square SU 10 68, which holds Silbury Hill."""
    source = add_source(db)
    square = gridref.parse_gridref("SU1068")
    made = []
    for step in range(10):
        east = square.easting + 50 + step * 100
        north = square.northing + 950 - step * 90
        lon, lat = gridref.to_lonlat(square.system, east, north)
        made.append(add_record(db, source, f"Bowl barrow {step}", lon, lat))
    db.commit()
    return made


def test_an_open_finding_is_measured_from_its_exact_position(
    db: Session, make_finding: MakeFinding, scattered: list[Record]
) -> None:
    target = scattered[3]
    finding = make_finding(**at(target), feature_class=FeatureClass.ENCLOSURE)
    result = records.suggest_for_finding(db, finding, None)
    assert not result.origin.obscured
    assert result.items[0].result.record.id == target.id
    assert result.items[0].result.distance_m == 0


def test_a_protected_finding_is_measured_from_its_square_for_the_public(
    db: Session, make_finding: MakeFinding, make_user: MakeUser, scattered: list[Record]
) -> None:
    target = scattered[3]
    finding = make_finding(**at(target), feature_class=FeatureClass.ROUND_BARROW)
    assert finding.sensitivity == Sensitivity.PROTECTED

    public = records.suggest_for_finding(db, finding, None)
    assert public.origin.obscured
    assert public.origin.square == "SU1068"
    assert (public.origin.lon, public.origin.lat) == pytest.approx(gridref.centre_of_square("SU1068"))
    # Distances are to the square, so every record in it is 0 m away, the one
    # on the exact spot included. Ties go by the public centre, not the spot.
    assert [item.result.distance_m for item in public.items] == [0] * len(scattered)
    centre = Point(public.origin.lon, public.origin.lat)
    from_centre = [centre.distance(Point(item.result.lon, item.result.lat)) for item in public.items]
    assert from_centre == sorted(from_centre)

    # A member may see a protected finding exactly, and gets the exact answer.
    member = records.suggest_for_finding(db, finding, make_user())
    assert not member.origin.obscured
    assert member.items[0].result.record.id == target.id
    assert member.items[0].result.distance_m == 0


def test_two_findings_in_one_square_get_the_same_suggestions_for_the_public(
    db: Session, make_finding: MakeFinding, make_user: MakeUser, scattered: list[Record]
) -> None:
    """If the answer depended on the exact position, comparing answers would locate it."""
    first = make_finding(**at(scattered[0]), sensitivity="restricted")
    second = make_finding(**at(scattered[9]), sensitivity="restricted")
    member = make_user()
    for viewer in (None, member):
        a = records.suggest_for_finding(db, first, viewer)
        b = records.suggest_for_finding(db, second, viewer)
        assert a.origin == b.origin
        assert ids(a) == ids(b)
        assert [item.result.distance_m for item in a.items] == [item.result.distance_m for item in b.items]


def test_the_finder_and_trusted_see_a_restricted_finding_exactly(
    db: Session, make_finding: MakeFinding, make_user: MakeUser, scattered: list[Record]
) -> None:
    finder = make_user()
    finding = make_finding(finder, **at(scattered[5]), sensitivity="restricted")
    for viewer in (finder, make_user("trusted")):
        result = records.suggest_for_finding(db, finding, viewer)
        assert not result.origin.obscured
        assert result.items[0].result.record.id == scattered[5].id


def test_type_fit_lifts_a_record_above_a_slightly_nearer_one(db: Session, make_finding: MakeFinding) -> None:
    source = add_source(db)
    here = Point(-1.80, 51.40)
    nearer = add_record(db, source, "Lime kiln", here.x + 0.0005, here.y)
    fitting = add_record(db, source, "Bowl barrow", here.x + 0.0010, here.y)
    db.commit()
    finding = make_finding(
        lon=here.x, lat=here.y, feature_class=FeatureClass.ROUND_BARROW, sensitivity="open"
    )
    result = records.suggest_for_finding(db, finding, None)
    assert ids(result) == [fitting.id, nearer.id]
    assert result.items[0].type_fit
    assert not result.items[1].type_fit


def test_the_community_class_counts_too(db: Session) -> None:
    source = add_source(db)
    kiln = add_record(db, source, "Lime kiln", -1.8, 51.4)
    assert records.type_fits(["round_barrow", "industrial"], kiln)
    assert not records.type_fits(["round_barrow"], kiln)
    assert not records.type_fits(["unknown"], kiln)


def test_a_hidden_finding_is_not_found_except_by_a_moderator(
    db: Session, make_finding: MakeFinding, make_user: MakeUser
) -> None:
    finding = make_finding(hidden_at=datetime(2026, 11, 1, tzinfo=UTC))
    with pytest.raises(records.FindingNotFoundError):
        records.load_finding(db, finding.public_id, None)
    with pytest.raises(records.FindingNotFoundError):
        records.load_finding(db, finding.public_id, make_user("trusted"))
    assert records.load_finding(db, finding.public_id, make_user("moderator")) is not None
    with pytest.raises(records.FindingNotFoundError):
        records.load_finding(db, "ZZZZZZ", None)


@respx.mock
def test_a_finding_on_silbury_hill_is_offered_its_scheduled_monument_first(
    db: Session, make_finding: MakeFinding, make_user: MakeUser, env: Callable[..., None], tmp_path: Path
) -> None:
    """The exit criterion of WS5 in the v1 plan, against the recorded export."""
    env(VAR_DIR=str(tmp_path))
    serve_hub(MONUMENTS_GPKG.read_bytes())
    run_connector(ScheduledMonuments())

    finder = make_user()
    for feature_class in (FeatureClass.ROUND_BARROW, FeatureClass.UNKNOWN, FeatureClass.RITUAL):
        finding = make_finding(finder, lon=SILBURY[0], lat=SILBURY[1], feature_class=feature_class)
        result = records.suggest_for_finding(db, finding, finder)
        assert not result.origin.obscured
        assert result.items, f"no suggestions for a {feature_class} on Silbury Hill"
        assert result.items[0].result.record.name.startswith("Silbury Hill"), feature_class
        assert result.items[0].result.distance_m == 0
        # The public sees a protected one by its square, and Silbury Hill is still offered.
        public = records.suggest_for_finding(db, finding, None)
        assert any(item.result.record.name.startswith("Silbury Hill") for item in public.items)
