"""Every National Heritage List connector against its recorded export, through the real runner.

What the eleven share is tested here, once per source: the licence against the
work-list, two runs giving the same rows, a partial run by box and an export
that changed shape. `test_mappings.py` has the field mapping on named records.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pytest
import respx
import time_machine
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.base import BBox
from fieldclub.ingest.connectors.he_nhle_hub import NhleLayer
from fieldclub.ingest.connectors.he_nhle_scheduled_monuments import CURRENCY_STATEMENT
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from tests.connectors.nhle.support import FIXTURES, changed_copy, serve_export, worklist_entry


@dataclass(frozen=True)
class Layer:
    key: str
    fixture: str
    stored: int
    enabled: bool
    # A column the connector must find, and a box around some of the rows but not all.
    column: str
    box: BBox
    in_box: int


AVEBURY_BOX = (-1.88, 51.41, -1.80, 51.46)
WORLD = (-180.0, -90.0, 180.0, 90.0)
LAYERS = [
    Layer(
        "he-nhle-listed-buildings-points",
        "listed_buildings_points.gpkg",
        6,
        True,
        "ListEntry",
        AVEBURY_BOX,
        4,
    ),
    Layer(
        "he-nhle-listed-buildings-polygons",
        "listed_buildings_polygons.gpkg",
        3,
        False,
        "area_ha",
        AVEBURY_BOX,
        1,
    ),
    Layer(
        "he-nhle-registered-parks-and-gardens",
        "parks_and_gardens.gpkg",
        4,
        True,
        "Grade",
        (-1.5, 51.3, -0.2, 51.45),
        2,
    ),
    Layer(
        "he-nhle-registered-battlefields", "battlefields.gpkg", 3, True, "RegDate", (-1.0, 51.6, 0.5, 51.7), 1
    ),
    Layer(
        "he-nhle-world-heritage-sites",
        "world_heritage_sites.gpkg",
        4,
        True,
        "Notes",
        (-0.1, 51.4, 0.1, 51.6),
        2,
    ),
    Layer(
        "he-nhle-protected-wreck-sites", "wreck_sites.gpkg", 3, True, "DesigDate", (-1.6, 50.6, -1.4, 50.8), 1
    ),
    Layer("he-nhle-building-preservation-notices-points", "bpn_points.gpkg", 6, False, "BPNStart", WORLD, 6),
    Layer(
        "he-nhle-building-preservation-notices-polygons", "bpn_polygons.gpkg", 6, True, "BPNStart", WORLD, 6
    ),
    Layer(
        "he-nhle-certificates-of-immunity-points",
        "coi_points.gpkg",
        3,
        False,
        "NGR",
        (-0.8, 52.0, -0.7, 52.1),
        2,
    ),
    Layer(
        "he-nhle-certificates-of-immunity-polygons",
        "coi_polygons.gpkg",
        3,
        True,
        "NGR",
        (-0.8, 52.0, -0.7, 52.1),
        2,
    ),
    Layer("he-conservation-areas", "conservation_areas.gpkg", 7, True, "NAME", AVEBURY_BOX, 1),
]
pytestmark = pytest.mark.parametrize("layer", LAYERS, ids=lambda layer: layer.key)


@pytest.fixture(autouse=True)
def own_var_dir(env: Callable[..., None], tmp_path: Path) -> None:
    """Each test downloads into its own `var/`, so no test sees another's cached export."""
    env(VAR_DIR=str(tmp_path / "var"))


def connector(layer: Layer) -> NhleLayer:
    cls = registry.get(layer.key)
    assert issubclass(cls, NhleLayer)
    return cls()


def serve(layer: Layer, body: bytes | None = None) -> respx.Route:
    return serve_export(worklist_entry(layer.key)["url"], body or (FIXTURES / layer.fixture).read_bytes())


def rows(db: Session) -> list[tuple[Any, ...]]:
    db.expire_all()
    return [
        (
            r.id,
            r.external_id,
            r.name,
            r.record_type,
            r.summary,
            r.url,
            r.source_updated_at,
            bytes(r.geom.data),
            json.dumps(r.raw, sort_keys=True),
        )
        for r in db.scalars(select(Record).order_by(Record.external_id)).all()
    ]


def test_the_source_carries_the_work_list_licence(layer: Layer) -> None:
    entry = worklist_entry(layer.key)
    info = registry.get(layer.key).source
    assert info.name == entry["name"]
    assert info.publisher == entry["publisher"]
    assert info.licence == entry["licence"]
    assert info.licence_url == entry["licence_url"]
    assert info.reuse == entry["reuse"] == "open"
    assert info.category == entry["category"]
    assert info.access == "bulk"
    if layer.key == "he-conservation-areas":
        assert info.attribution == entry["attribution"]
    else:
        # The work-list's attribution as it stands, then the currency statement from its gotchas.
        statement = next(note for note in entry["gotchas"] if "currency statement" in note)
        assert CURRENCY_STATEMENT in statement
        assert info.attribution == f"{entry['attribution']} {CURRENCY_STATEMENT}"


def test_the_export_address_is_the_work_lists(layer: Layer) -> None:
    assert connector(layer).export_url == worklist_entry(layer.key)["url"]


@respx.mock
def test_a_run_stores_the_rows_and_enables_the_source_as_decided(layer: Layer, db: Session) -> None:
    serve(layer)
    run = run_connector(connector(layer))
    assert run.status == "completed"
    assert run.stats is not None
    assert run.stats["seen"] == layer.stored
    source = db.get(Source, layer.key)
    assert source is not None
    assert source.record_count == layer.stored
    assert source.enabled is layer.enabled
    assert {r.category for r in db.scalars(select(Record)).all()} == {"designation"}


@respx.mock
def test_the_stored_attribution_is_dated_from_the_download(layer: Layer, db: Session) -> None:
    serve(layer)
    with time_machine.travel(datetime(2027, 1, 2, 9, tzinfo=UTC), tick=False):
        run_connector(connector(layer))
    source = db.get(Source, layer.key)
    assert source is not None
    assert "[year]" not in source.attribution
    assert "[date]" not in source.attribution
    if layer.key != "he-conservation-areas":
        assert "database right 2027" in source.attribution
        assert "obtained on 2 January 2027" in source.attribution


@respx.mock
def test_running_twice_gives_the_same_rows(layer: Layer, db: Session) -> None:
    hub = serve(layer)
    run_connector(connector(layer))
    before = rows(db)
    second = run_connector(connector(layer))
    assert len(before) == layer.stored
    assert rows(db) == before
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (
        0,
        layer.stored,
        0,
    )
    assert hub.call_count == 1  # the second run used the copy on disk


@respx.mock
def test_a_partial_run_by_bbox(layer: Layer, db: Session) -> None:
    serve(layer)
    run = run_connector(connector(layer), bbox=layer.box)
    assert run.stats is not None
    assert not run.stats["full"]
    assert run.stats["seen"] == layer.in_box
    assert len(db.scalars(select(Record.id)).all()) == layer.in_box


@respx.mock
def test_an_export_that_changed_shape_fails_the_run(layer: Layer, db: Session, tmp_path: Path) -> None:
    sql = f"ALTER TABLE {{table}} RENAME COLUMN {layer.column} TO Renamed"
    serve(layer, changed_copy(layer.fixture, tmp_path / "changed.gpkg", sql))
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(connector(layer))
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_two_rows_with_one_id_fail_the_run(layer: Layer, db: Session, tmp_path: Path) -> None:
    sql = "UPDATE {table} SET ListEntry = 1000000, NGR = 'SU 1 1'"
    if layer.key == "he-nhle-world-heritage-sites":
        sql = "UPDATE {table} SET ListEntry = 1000000, Notes = 'Core Area'"
    if layer.key == "he-conservation-areas":
        sql = "UPDATE {table} SET NAME = 'Avebury', DATE_OF_DE = '24/01/1975', LPA = 'Wiltshire'"
    serve(layer, changed_copy(layer.fixture, tmp_path / "changed.gpkg", sql))
    with pytest.raises(IngestFailedError, match="two rows with the id"):
        run_connector(connector(layer))
    assert db.scalars(select(Record)).all() == []
