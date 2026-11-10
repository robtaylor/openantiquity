"""The field mapping of each National Heritage List connector, on named records from its fixture."""

from __future__ import annotations

import hashlib
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
import respx
from shapely.geometry import Point
from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.runner import run_connector
from fieldclub.models import Record
from fieldclub.models.common import point_lon_lat
from tests.connectors.nhle.support import FIXTURES, serve_export, worklist_entry
from tests.helpers import AVEBURY

ENTRY_URL = "https://historicengland.org.uk/listing/the-list/list-entry/{}"


@pytest.fixture(autouse=True)
def own_var_dir(env: Callable[..., None], tmp_path: Path) -> None:
    env(VAR_DIR=str(tmp_path / "var"))


def run(key: str, fixture: str, db: Session) -> dict[str, Record]:
    """Run the source against its fixture and give the stored records by external id."""
    with respx.mock:
        serve_export(worklist_entry(key)["url"], (FIXTURES / fixture).read_bytes())
        run_connector(registry.get(key)())
    return {record.external_id: record for record in db.scalars(select(Record)).all()}


def test_a_listed_building_point(db: Session) -> None:
    records = run("he-nhle-listed-buildings-points", "listed_buildings_points.gpkg", db)
    dovecote = records["1286437"]
    assert dovecote.name == "Dovecote at Avebury Manor"
    assert dovecote.record_type == "Listed building"
    assert dovecote.summary == "Grade II* listed building"
    assert dovecote.url == ENTRY_URL.format(1286437)
    assert dovecote.precision_m is None
    # The later of the listing and amendment dates.
    assert dovecote.source_updated_at == datetime(2020, 8, 3, 9, 25, 58, tzinfo=UTC)
    assert dovecote.raw is not None
    assert dovecote.raw["Grade"] == "II*"
    assert dovecote.raw["NGR"]
    lon, lat = point_lon_lat(dovecote.centroid)
    assert Point(lon, lat).distance(Point(*AVEBURY)) < 0.01
    # A building never amended is dated by its listing.
    assert records["1024638"].source_updated_at == datetime(1969, 12, 11, tzinfo=UTC)
    assert records["1024638"].summary == "Grade I listed building"


def test_the_polygon_layer_keeps_only_real_outlines(db: Session) -> None:
    records = run("he-nhle-listed-buildings-polygons", "listed_buildings_polygons.gpkg", db)
    # Three rows have an area. The other three are placeholders and are not stored.
    assert set(records) == {"1286437", "1403367", "1024638"}
    assert records["1286437"].raw is not None
    assert records["1286437"].raw["area_ha"] > 0


def test_a_registered_park(db: Session) -> None:
    records = run("he-nhle-registered-parks-and-gardens", "parks_and_gardens.gpkg", db)
    rousham = records["1000107"]
    assert rousham.name == "ROUSHAM"
    assert rousham.record_type == "Registered park and garden"
    assert rousham.summary == "Grade I registered park and garden"
    assert rousham.url == ENTRY_URL.format(1000107)
    assert rousham.source_updated_at == datetime(1984, 6, 1, tzinfo=UTC)
    assert set(records) == {"1000107", "1000108", "1000109", "1000110"}


def test_a_registered_battlefield(db: Session) -> None:
    records = run("he-nhle-registered-battlefields", "battlefields.gpkg", db)
    moor = records["1000000"]
    assert moor.name == "Battle of Adwalton Moor 1643"
    assert moor.record_type == "Registered battlefield"
    assert moor.source_updated_at == datetime(2017, 9, 29, 13, 55, 59, tzinfo=UTC)
    assert moor.raw is not None
    assert moor.raw["RegDate"] == "1995-06-06T00:00:00+00:00"


def test_a_protected_wreck_site(db: Session) -> None:
    records = run("he-nhle-protected-wreck-sites", "wreck_sites.gpkg", db)
    wreck = records["1000043"]
    assert wreck.name == "HMS/m A1"
    assert wreck.record_type == "Protected wreck site"
    assert wreck.source_updated_at == datetime(2004, 10, 5, tzinfo=UTC)
    assert wreck.raw is not None
    assert wreck.raw["Latitude"] == pytest.approx(50.74251829)
    # The wreck is placed by its polygon, near Bognor Regis, not by the layer's other fields.
    lon, lat = point_lon_lat(wreck.centroid)
    assert (lon, lat) == pytest.approx((-0.9213, 50.7425), abs=0.01)


def test_a_world_heritage_site_in_two_parts_is_two_records(db: Session) -> None:
    records = run("he-nhle-world-heritage-sites", "world_heritage_sites.gpkg", db)
    assert set(records) == {
        "1000089-core-area",
        "1000096-core-area",
        "1000096-buffer-zone",
        "1000103-core-area",
    }
    assert records["1000096-core-area"].name == "Maritime Greenwich"
    assert records["1000096-buffer-zone"].name == "Maritime Greenwich (buffer zone)"
    assert records["1000096-buffer-zone"].summary == "World Heritage Site: buffer zone"
    assert records["1000096-core-area"].summary == "World Heritage Site: core area"
    assert records["1000096-core-area"].url == ENTRY_URL.format(1000096)
    assert records["1000096-core-area"].record_type == "World Heritage Site"


def test_building_preservation_notices_are_dated_by_their_start(db: Session) -> None:
    records = run("he-nhle-building-preservation-notices-polygons", "bpn_polygons.gpkg", db)
    farm = records["1497176"]
    assert farm.name == "BPN Low Lickbarrow Farm"
    assert farm.record_type == "Building preservation notice"
    assert farm.summary == "Notice served 13 May 2026, expiring 13 November 2026"
    # The expiry is still to come, so it is not the date the entry changed.
    assert farm.source_updated_at == datetime(2026, 5, 13, tzinfo=UTC)
    assert farm.url == ENTRY_URL.format(1497176)


def test_a_certificate_over_two_places_is_two_records(db: Session) -> None:
    for key, fixture in (
        ("he-nhle-certificates-of-immunity-polygons", "coi_polygons.gpkg"),
        ("he-nhle-certificates-of-immunity-points", "coi_points.gpkg"),
    ):
        db.execute(delete(Record))
        db.commit()
        records = run(key, fixture, db)
        assert set(records) == {"1431354-TQ2898180692", "1495772-SP8547238825", "1495772-SP8545138855"}
        bond = records["1431354-TQ2898180692"]
        assert bond.name == "163 New Bond Street"
        assert bond.record_type == "Certificate of immunity from listing"
        assert bond.summary == "Certificate issued 29 June 2022, expiring 28 June 2027"
        assert bond.source_updated_at == datetime(2022, 6, 29, tzinfo=UTC)
        assert bond.url == ENTRY_URL.format(1431354)


def test_conservation_areas(db: Session) -> None:
    records = run("he-conservation-areas", "conservation_areas.gpkg", db)
    avebury_id = hashlib.sha256(b"wiltshire|avebury|24/01/1975").hexdigest()[:20]
    avebury = records[avebury_id]
    assert avebury.name == "Avebury"
    assert avebury.record_type == "Conservation area"
    assert avebury.summary == "Conservation area designated by Wiltshire on 24/01/1975"
    assert avebury.url is None
    assert avebury.source_updated_at is None
    assert avebury.raw is not None
    assert avebury.raw["LPA"] == "Wiltshire"
    lon, lat = point_lon_lat(avebury.centroid)
    assert Point(lon, lat).distance(Point(*AVEBURY)) < 0.02

    # The layer's UID is 0 for several areas, so it plays no part in the id.
    assert len(records) == 7
    assert {record.raw["UID"] for record in records.values() if record.raw} >= {0.0, 1.0, 4606.0}


def test_a_conservation_area_with_nothing_but_a_boundary(db: Session) -> None:
    records = run("he-conservation-areas", "conservation_areas.gpkg", db)
    bare = [record for record in records.values() if record.raw and record.raw["LPA"] == "Wokingham"]
    assert len(bare) == 1
    assert bare[0].name == "Conservation area in Wokingham"
    assert bare[0].summary == "Conservation area designated by Wokingham"
