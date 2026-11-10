"""The OS Open Names loader, which fills the search box's gazetteer, against entries cut from the download.

See `tests/connectors/names/support.py` for how the fixture was recorded.
"""

from __future__ import annotations

import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import respx
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.ingest import cli
from fieldclub.ingest.reference import get as get_loader
from fieldclub.ingest.reference.base import run_loader
from fieldclub.ingest.reference.os_open_names import (
    DOWNLOAD,
    HEADER,
    OpenNames,
    area_name,
    kind_rank,
    size_rank,
)
from fieldclub.ingest.runner import IngestFailedError
from fieldclub.models import IngestRun, Place, Source
from fieldclub.models.common import db_point, point_lon_lat
from fieldclub.services import search
from tests.connectors.names.support import OPEN_NAMES_ZIP, serve_file, worklist_entry, zip_with

KEY = "os-open-names"
CARDIFF_BOX = (-3.3, 51.4, -3.1, 51.6)


@pytest.fixture(autouse=True)
def own_var_dir(env: Callable[..., None], tmp_path: Path) -> None:
    env(VAR_DIR=str(tmp_path / "var"))


def places(db: Session) -> list[tuple[Any, ...]]:
    """Every place, without the id a reload gives afresh."""
    db.expire_all()
    found = db.scalars(select(Place).order_by(Place.name, Place.kind, Place.rank)).all()
    return [
        (
            place.name,
            place.kind,
            place.district,
            place.county,
            place.nation,
            place.rank,
            place.source,
            *point_lon_lat(place.geom),
        )
        for place in found
    ]


def named(db: Session, name: str) -> Place:
    return db.scalars(select(Place).where(Place.name == name)).one()


def fixture_members() -> dict[str, bytes]:
    with zipfile.ZipFile(OPEN_NAMES_ZIP) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def test_the_loader_is_registered_under_its_work_list_key() -> None:
    assert get_loader(KEY) is OpenNames


def test_the_source_carries_the_work_list_licence() -> None:
    entry = worklist_entry(KEY)
    info = OpenNames.source
    assert info.licence == entry["licence"]
    assert info.licence_url == entry["licence_url"]
    assert info.attribution == entry["attribution"]
    assert info.reuse == entry["reuse"] == "open"
    assert info.category == entry["category"] == "place"
    assert info.publisher == entry["publisher"]


@pytest.mark.parametrize(
    ("value", "name"),
    [
        ("Powys - Powys", "Powys"),
        ("Sir Ynys Mon - Isle of Anglesey", "Sir Ynys Mon - Isle of Anglesey"),
        ("Wiltshire", "Wiltshire"),
        ("", None),
        (None, None),
    ],
)
def test_a_welsh_area_named_alike_in_both_languages_is_named_once(
    value: str | None, name: str | None
) -> None:
    assert area_name(value) == name


def rank(type_: str, local_type: str, mbr: tuple[float, float, float, float]) -> int:
    base = kind_rank(type_, local_type)
    assert base is not None, f"{local_type} is left out"
    return base * 100 + size_rank(mbr)


def test_a_town_outranks_a_village_outranks_a_hill_whatever_their_size() -> None:
    small_town = rank("populatedPlace", "Town", (0, 0, 10, 10))
    big_village = rank("populatedPlace", "Village", (0, 0, 9e5, 9e5))
    big_hill = rank("landform", "Hill Or Mountain", (0, 0, 9e5, 9e5))
    assert small_town > big_village > big_hill
    # Within a kind, the bigger box comes first.
    assert size_rank((0, 0, 1000, 1000)) > size_rank((0, 0, 100, 100))
    assert 0 <= size_rank((0, 0, 0, 0)) <= size_rank((0, 0, 1e9, 1e9)) == 99


def test_postcodes_roads_and_schools_are_left_out() -> None:
    assert kind_rank("other", "Postcode") is None
    assert kind_rank("transportNetwork", "Named Road") is None
    assert kind_rank("transportNetwork", "Section Of Numbered Road") is None
    assert kind_rank("other", "Primary Education") is None
    assert kind_rank("transportNetwork", "Railway Station") is not None


@respx.mock
def test_a_run_fills_the_gazetteer(db: Session) -> None:
    serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    run = run_loader(OpenNames())
    assert run.status == "completed"
    assert run.stats is not None
    assert run.stats["read"] == 87

    avebury = named(db, "Avebury")
    assert (avebury.kind, avebury.county, avebury.district, avebury.nation) == (
        "Village",
        "Wiltshire",
        None,
        "england",
    )
    assert avebury.source == KEY
    assert 700 <= avebury.rank < 800
    lon, lat = point_lon_lat(avebury.geom)
    assert abs(lon - -1.853) < 0.01
    assert abs(lat - 51.428) < 0.01
    assert named(db, "Silbury Hill").kind == "Hill Or Mountain"
    assert named(db, "Silbury Hill").rank < named(db, "Berwick Bassett").rank

    names = set(db.scalars(select(Place.name)).all())
    assert "SN8 1PU" not in names
    assert not {"Church Lane", "High Street", "B4003"} & names
    assert not any("Primary School" in name for name in names)

    # A second name is a place of its own, at the same point.
    assert point_lon_lat(named(db, "Caerdydd").geom) == point_lon_lat(named(db, "Cardiff").geom)
    assert named(db, "Caerdydd").nation == "wales"

    source = db.get(Source, KEY)
    assert source is not None
    assert source.record_count == db.scalar(select(func.count()).select_from(Place))
    assert source.attribution.startswith("Contains OS data")
    assert "[year]" not in source.attribution
    assert source.last_ingest_at is not None
    assert f"database rights {source.last_ingest_at.year}." in source.attribution


@respx.mock
def test_the_search_box_finds_the_loaded_places(db: Session) -> None:
    serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    run_loader(OpenNames())
    labels = [hit.label for hit in search.places(db, "avebury")]
    assert labels[0] == "Avebury"
    assert set(labels) >= {"Avebury Trusloe", "Avebury Down"}
    assert search.places(db, "avebry")[0].label == "Avebury"
    assert search.places(db, "caerdydd")[0].label == "Caerdydd"
    hill = search.places(db, "silbury")[0]
    assert (hill.label, hill.detail, hill.zoom) == ("Silbury Hill", "Wiltshire", 14)


@respx.mock
def test_a_misspelt_name_finds_the_closest_name_before_a_bigger_place(db: Session) -> None:
    serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    run_loader(OpenNames())
    # A real hamlet whose name shares much with the misspelling, and outranks a hill.
    db.add(Place(name="Gilbert's End", kind="Hamlet", geom=db_point(-2.25, 52.07), rank=543, source="test"))
    db.commit()
    assert search.places(db, "silbery")[0].label == "Silbury Hill"


@respx.mock
def test_running_twice_gives_the_same_places(db: Session) -> None:
    host = serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    run_loader(OpenNames())
    before = places(db)
    second = run_loader(OpenNames())
    assert places(db) == before
    assert second.stats is not None
    assert second.stats["inserted"] == second.stats["deleted"] == len(before)
    assert host.call_count == 1


@respx.mock
def test_a_partial_run_by_bbox_replaces_only_the_places_inside_it(db: Session) -> None:
    serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    run_loader(OpenNames())
    before = places(db)
    run = run_loader(OpenNames(), bbox=CARDIFF_BOX)
    assert run.stats is not None
    assert not run.stats["full"]
    assert run.stats["deleted"] == run.stats["inserted"] == 4  # Cardiff, Caerphilly and their Welsh names
    assert places(db) == before


@respx.mock
def test_a_limit_is_refused_and_keeps_every_place(db: Session, capsys: pytest.CaptureFixture[str]) -> None:
    """A habitual `--limit 1` smoke test must not empty the gazetteer."""
    host = serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    run_loader(OpenNames())
    before = places(db)
    runs = db.scalar(select(func.count()).select_from(IngestRun))
    assert cli.main(["run", KEY, "--limit", "1"]) == 1
    assert "takes no --limit" in capsys.readouterr().err
    assert places(db) == before
    assert db.scalar(select(func.count()).select_from(IngestRun)) == runs
    assert host.call_count == 1


@respx.mock
def test_a_download_that_changed_shape_fails_and_keeps_the_places(
    db: Session, env: Callable[..., None], tmp_path: Path
) -> None:
    serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    run_loader(OpenNames())
    before = places(db)
    members = fixture_members()
    members[HEADER] = members[HEADER].replace(b"NAME1,", b"NAME,")
    serve_file(DOWNLOAD, zip_with(members))
    # A fresh var/, so the changed file is downloaded instead of the cached copy reused.
    env(VAR_DIR=str(tmp_path / "later"))
    with pytest.raises(IngestFailedError, match="headings lack"):
        run_loader(OpenNames())
    assert places(db) == before
    failed = db.scalars(select(IngestRun).order_by(IngestRun.id.desc()).limit(1)).one()
    assert failed.status == "failed"


@respx.mock
def test_a_new_kind_of_place_fails_the_run(db: Session) -> None:
    members = fixture_members()
    members["Data/SU06.csv"] = members["Data/SU06.csv"].replace(b",Village,", b",Ecovillage,", 1)
    serve_file(DOWNLOAD, zip_with(members))
    with pytest.raises(IngestFailedError, match="new kind of populatedPlace: 'Ecovillage'"):
        run_loader(OpenNames())
    assert db.scalar(select(func.count()).select_from(Place)) == 0


@respx.mock
def test_a_run_far_smaller_than_what_it_replaces_fails(db: Session) -> None:
    db.add_all(
        Place(name=f"Old place {n}", kind="Hamlet", geom=db_point(-1.8, 51.4), rank=500, source=KEY)
        for n in range(400)
    )
    db.commit()
    serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    with pytest.raises(IngestFailedError, match="allow-shrink"):
        run_loader(OpenNames())
    assert db.scalar(select(func.count()).select_from(Place)) == 400
    run_loader(OpenNames(), allow_shrink=True)
    assert db.scalar(select(func.count()).select_from(Place).where(Place.name.like("Old place%"))) == 0


@respx.mock
def test_the_command_runs_the_loader(db: Session, capsys: pytest.CaptureFixture[str]) -> None:
    serve_file(DOWNLOAD, OPEN_NAMES_ZIP.read_bytes())
    assert cli.main(["list"]) == 0
    assert KEY in capsys.readouterr().out
    assert cli.main(["run", KEY, "--bbox", "-3.3,51.4,-3.1,51.6"]) == 0
    assert "os-open-names: 4 rows from 87 read upstream (replacing 0)" in capsys.readouterr().out
    assert db.scalar(select(func.count()).select_from(Place)) == 4
