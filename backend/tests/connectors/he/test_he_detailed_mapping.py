"""The detailed mapping layer, read from the Hub's GeoPackage export, through the real runner.

The fixture `fixtures/he-aim-detailed-mapping.gpkg` is thirteen features cut from the Hub's 4.7 GB
export of layer 0, downloaded on 2026-11-11. `record_fixtures.py` says how it was cut. Values and
geometry are as the export has them, in EPSG:27700.
"""

from __future__ import annotations

import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import Any

import httpx
import pytest
import respx
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest.connectors.he_aim_detailed_mapping import (
    EMPTY,
    HUB_EXPORT,
    PERIOD_RULES,
    DetailedMapping,
    periods_of,
)
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record
from fieldclub.models.common import point_lon_lat
from fieldclub.vocab import Period
from tests.connectors.he.support import FIXTURES

EXPORT = FIXTURES / "he-aim-detailed-mapping.gpkg"
EXPORT_FILE = "https://export.example/HE_AIM_data_1.gpkg"
FEATURES = 13


@pytest.fixture(autouse=True)
def own_var_dir(env: Callable[..., None], tmp_path: Path) -> None:
    """Each test downloads into its own `var/`, so none sees another's cached export."""
    env(VAR_DIR=str(tmp_path / "var"))


def serve_hub(body: bytes) -> respx.Route:
    """The Hub's redirect to a short-lived export file, and the file. Call it inside `respx.mock`."""
    respx.get(EXPORT_FILE).mock(
        return_value=httpx.Response(
            200, content=body, headers={"ETag": '"0x1"', "Content-Length": str(len(body))}
        )
    )
    return respx.get(HUB_EXPORT).mock(return_value=httpx.Response(302, headers={"Location": EXPORT_FILE}))


def rows(db: Session) -> list[tuple[Any, ...]]:
    db.expire_all()
    return [
        (
            record.id,
            record.external_id,
            record.name,
            record.summary,
            record.record_type,
            record.monument_types,
            record.periods,
            bytes(record.geom.data),
            json.dumps(record.raw, sort_keys=True),
        )
        for record in db.scalars(select(Record).order_by(Record.external_id)).all()
    ]


def stored(db: Session, **raw: Any) -> Record:
    """The one stored record whose `raw` holds these values."""
    db.expire_all()
    found = [
        record
        for record in db.scalars(select(Record)).all()
        if record.raw is not None and all(record.raw.get(name) == value for name, value in raw.items())
    ]
    assert len(found) == 1, f"{len(found)} records match {raw}"
    return found[0]


@respx.mock
def test_a_run_stores_every_feature_with_the_source_and_its_attribution(db: Session) -> None:
    serve_hub(EXPORT.read_bytes())
    run = run_connector(DetailedMapping())
    assert run.status == "completed"
    assert run.stats is not None
    assert (run.stats["seen"], run.stats["duplicates"]) == (FEATURES, 0)
    assert len(db.scalars(select(Record)).all()) == FEATURES
    assert {record.category for record in db.scalars(select(Record)).all()} == {"monument"}


@respx.mock
def test_a_detailed_feature_keeps_its_terms_period_and_evidence(db: Session) -> None:
    serve_hub(EXPORT.read_bytes())
    run_connector(DetailedMapping())
    barrow = stored(db, HE_UID="943187")
    assert barrow.name == "Bell barrow"
    assert barrow.category == "monument"
    assert barrow.record_type == "Bank"
    assert barrow.monument_types == ["BELL BARROW"]
    assert barrow.periods == ["bronze_age"]
    assert barrow.summary == "Evidence: earthwork. Project: Stonehenge World Heritage Site."
    assert barrow.precision_m is None
    assert barrow.url is None
    # Nothing the source gave is lost, except the fields it left empty.
    assert barrow.raw is not None
    assert barrow.raw["PERIOD"] == "BRONZE AGE"
    assert barrow.raw["SOURCE_1"].startswith("NMR SU 1141/75")
    assert "SOURCE_2" not in barrow.raw
    assert barrow.raw["HE_URL1"].endswith("uid=943187&resourceID=19191")
    lon, lat = point_lon_lat(barrow.centroid)
    assert Point(lon, lat).distance(Point(-1.826, 51.178)) < 0.05


@respx.mock
def test_several_terms_periods_and_kinds_of_evidence_are_all_kept(db: Session) -> None:
    serve_hub(EXPORT.read_bytes())
    run_connector(DetailedMapping())
    abbey = next(r for r in db.scalars(select(Record)).all() if "POND70449" in (r.monument_types or []))
    assert abbey.record_type == "Bank"
    assert abbey.monument_types is not None
    assert abbey.monument_types[:3] == ["ABBEY", "BANK (EARTHWORK)", "BOUNDARY DITCH"]
    assert abbey.name.startswith("Abbey, Bank (earthwork), Boundary ditch")
    # The source's own mangled term is kept as it is.
    assert abbey.monument_types[-1] == "POND70449"
    assert abbey.periods == ["medieval", "post_medieval"]
    assert abbey.summary is not None
    assert "documentary evidence, earthwork, extant building, ruined building" in abbey.summary
    assert abbey.raw is not None
    assert abbey.raw["EVIDENCE_1"] == "DOCUMENTARY EVIDENCE\\EARTHWORK\\EXTANT BUILDING\\RUINED BUILDING"


@respx.mock
def test_a_twentieth_century_feature_is_modern(db: Session) -> None:
    serve_hub(EXPORT.read_bytes())
    run_connector(DetailedMapping())
    works = stored(db, HE_UID="1368175")
    assert works.periods == ["modern"]
    assert works.summary is not None
    assert works.summary.startswith("Evidence: cropmark, earthwork, structure.")


@respx.mock
def test_features_with_no_record_say_so_without_inventing_a_type_or_period(db: Session) -> None:
    serve_hub(EXPORT.read_bytes())
    run_connector(DetailedMapping())
    empty = [
        r
        for r in db.scalars(select(Record)).all()
        if r.raw and r.raw["MONUMENT_TYPE"] == " NO MONUMENT RECORD"
    ]
    assert len(empty) == 2
    assert all(r.name == "Bank" and not r.monument_types and not r.periods for r in empty)
    # Only the project is said, not the evidence "NO MONUMENT RECORD".
    assert all(r.summary is not None and r.summary.startswith("Project: ") for r in empty)
    assert all(r.raw is not None and r.raw["PERIOD"] == " NO MONUMENT RECORD" for r in empty)


@respx.mock
def test_features_of_one_monument_get_different_ids_and_a_missing_monument_number_is_no_problem(
    db: Session,
) -> None:
    serve_hub(EXPORT.read_bytes())
    run_connector(DetailedMapping())
    airfield = db.scalars(select(Record).where(Record.raw["HE_UID"].astext == "1408409")).all()
    assert len(airfield) == 2
    assert len({record.external_id for record in airfield}) == 2
    nameless = db.scalars(select(Record).where(Record.raw["HE_UID"].astext == " NONE GIVEN")).all()
    assert len(nameless) >= 4
    assert all(len(record.external_id) == 20 for record in [*nameless, *airfield])


@respx.mock
def test_running_twice_gives_the_same_rows_and_the_second_run_uses_the_copy_on_disk(db: Session) -> None:
    hub = serve_hub(EXPORT.read_bytes())
    first = run_connector(DetailedMapping())
    before = rows(db)
    second = run_connector(DetailedMapping())
    assert rows(db) == before
    assert first.stats is not None
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (0, FEATURES, 0)
    assert hub.call_count == 1


@respx.mock
def test_a_partial_run_by_bbox_reads_only_that_area(db: Session) -> None:
    serve_hub(EXPORT.read_bytes())
    run = run_connector(DetailedMapping(), bbox=(-1.84, 51.16, -1.80, 51.19))
    assert run.stats is not None
    assert not run.stats["full"]
    stored_ids = db.scalars(select(Record.raw["HE_UID"].astext)).all()
    assert "943187" in stored_ids
    assert "1408409" not in stored_ids
    assert 0 < len(stored_ids) < FEATURES


@respx.mock
def test_an_export_that_changed_shape_fails_the_run_and_writes_nothing(db: Session, tmp_path: Path) -> None:
    changed = tmp_path / "changed.gpkg"
    changed.write_bytes(EXPORT.read_bytes())
    with sqlite3.connect(changed) as conn:
        conn.execute("ALTER TABLE Detailed_Mapping RENAME COLUMN MONUMENT_TYPE TO MONUMENT_KIND")
    serve_hub(changed.read_bytes())
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(DetailedMapping())
    assert db.scalars(select(Record)).all() == []


@pytest.mark.parametrize(
    ("text", "expected"),
    [
        ("BRONZE AGE", ["bronze_age"]),
        ("MEDIEVAL\\POST MEDIEVAL", ["medieval", "post_medieval"]),
        ("POST MEDIEVAL\\MEDIEVAL", ["post_medieval", "medieval"]),
        ("MEDIEVAL/POST MEDIEVAL", ["medieval", "post_medieval"]),
        ("POST-MEDIEVAL", ["post_medieval"]),
        ("EARLY MEDIEVAL", ["early_medieval"]),
        ("EARLY MEDIEVAL\\MEDIEVAL\\POST MEDIEVAL", ["early_medieval", "medieval", "post_medieval"]),
        ("IRON AGE/ROMAN", ["iron_age", "roman"]),
        ("LATE NEOLITHIC\\EARLY BRONZE AGE\\MEDIEVAL", ["neolithic", "bronze_age", "medieval"]),
        ("LATER PREHISTORIC\\ROMAN", ["prehistoric", "roman"]),
        ("VICTORIAN\\POST MEDIEVAL", ["post_medieval"]),
        ("VICTORIAN\\SECOND WORLD WAR\\MID 20TH CENTURY", ["post_medieval", "modern"]),
        ("FIRST WORLD WAR\\SECOND WORLD WAR", ["modern"]),
        ("WORLD WAR II", ["modern"]),
        ("ROMAN<Null>", ["roman"]),
        ("POST MEDIEVAL\\UNCERTAIN", ["post_medieval"]),
        ("UNCERTAIN", ["unknown"]),
        ("NO MORPH RECORD", []),
        ("NONE GIVEN", []),
        ("", []),
        (None, []),
    ],
)
def test_fish_periods_map_onto_the_vocabulary(text: str | None, expected: list[str]) -> None:
    assert periods_of(text) == expected


def test_every_period_term_in_the_layer_maps_or_means_nothing() -> None:
    # The 46 distinct terms in the whole layer on 2026-11-10, from its 498,295 features.
    terms = (
        "POST MEDIEVAL MEDIEVAL|SECOND WORLD WAR|ROMAN|UNCERTAIN|IRON AGE|20TH CENTURY|BRONZE AGE|"
        "LATER PREHISTORIC|FIRST WORLD WAR|PREHISTORIC|EARLY MEDIEVAL|VICTORIAN|NEOLITHIC|MID 20TH CENTURY|"
        "EARLY BRONZE AGE|WORLD WAR II|EARLY 20TH CENTURY|GEORGIAN|21ST CENTURY|LATE IRON AGE|LATE NEOLITHIC|"
        "EARLY IRON AGE|LATE 20TH CENTURY|LATE BRONZE AGE|EARLY NEOLITHIC|HANOVERIAN|WORLD WAR I|"
        "MIDDLE BRONZE AGE|COLD WAR|MIDDLE IRON AGE|EDWARDIAN|19TH CENTURY|NO MORPH RECORD|"
        "NO MONUMENT RECORD|LATE 19TH CENTURY|TUDOR|MODERN|STUART|NONE GIVEN|EARLY 21ST CENTURY|"
        "ANGLO-SAXON|POST-MEDIEVAL|TWENTIETH CENTURY"
    ).replace("POST MEDIEVAL MEDIEVAL", "POST MEDIEVAL|MEDIEVAL")
    for term in terms.split("|"):
        mapped = periods_of(term)
        assert mapped or term in EMPTY, term
        assert all(period in Period for period in mapped)


def test_the_period_rules_name_only_vocabulary_periods() -> None:
    assert {period for _, period in PERIOD_RULES} <= set(Period)
