"""The reference connector, end to end against the recorded GeoPackage.

The fixture is eight monuments cut from the Open Data Hub export of
2026-11-10. See `tests/ingest/adapters/support.py` for how it was recorded.
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

from fieldclub.ingest import registry
from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_scheduled_monuments import HUB_EXPORT, ScheduledMonuments
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from fieldclub.models.common import point_lon_lat
from tests.ingest.adapters.support import FIXTURES

FIXTURE = FIXTURES / "scheduled_monuments.gpkg"
EXPORT_FILE = "https://export.example/National_Heritage_List_for_England_NHLE_v02_VIEW_1.gpkg"
WORKLIST = Path(__file__).parents[3] / "docs" / "sources" / "worklists" / "sources.json"
SILBURY = Point(-1.8574, 51.4156)


@pytest.fixture(autouse=True)
def own_var_dir(env: Callable[..., None], tmp_path: Path) -> None:
    """Each test downloads into its own `var/`, so no test sees another's cached export."""
    env(VAR_DIR=str(tmp_path / "var"))


def worklist_entry(key: str) -> dict[str, Any]:
    entries = json.loads(WORKLIST.read_text(encoding="utf-8"))["bulk"]
    return next(entry for entry in entries if entry["key"] == key)


def serve_hub(body: bytes) -> respx.Route:
    """The Hub's 302 to a short-lived export file, and the file."""
    respx.get(EXPORT_FILE).mock(
        return_value=httpx.Response(
            200, content=body, headers={"ETag": '"0x1"', "Content-Length": str(len(body))}
        )
    )
    return respx.get(HUB_EXPORT).mock(return_value=httpx.Response(302, headers={"Location": EXPORT_FILE}))


def rows(db: Session) -> list[tuple[Any, ...]]:
    """Every stored scheduled monument, without the columns a run is expected to change."""
    db.expire_all()
    found = db.scalars(select(Record).order_by(Record.external_id)).all()
    return [
        (
            record.id,
            record.external_id,
            record.name,
            record.category,
            record.record_type,
            record.url,
            record.source_updated_at,
            bytes(record.geom.data),
            json.dumps(record.raw, sort_keys=True),
        )
        for record in found
    ]


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get("he-nhle-scheduled-monuments") is ScheduledMonuments


def test_the_source_carries_the_work_list_licence() -> None:
    entry = worklist_entry("he-nhle-scheduled-monuments")
    info = ScheduledMonuments.source
    assert info.licence_url == entry["licence_url"]
    assert info.reuse == entry["reuse"] == "open"
    assert info.category == entry["category"]
    assert info.access == "bulk"
    assert "Open Government Licence v3.0" in info.licence
    # The work-list's attribution with the year filled in.
    assert info.attribution == entry["attribution"].replace("[year]", "2026")


@respx.mock
def test_a_run_stores_every_monument_with_its_fields(db: Session) -> None:
    serve_hub(FIXTURE.read_bytes())
    run = run_connector(ScheduledMonuments())
    assert run.status == "completed"
    assert run.stats is not None
    assert run.stats["seen"] == 8

    silbury = db.scalars(select(Record).where(Record.external_id == "1008445")).one()
    assert silbury.source_key == "he-nhle-scheduled-monuments"
    assert silbury.name.startswith("Silbury Hill: a monumental Neolithic mound")
    assert silbury.category == "designation"
    assert silbury.record_type == "Scheduled monument"
    assert silbury.url == "https://historicengland.org.uk/listing/the-list/list-entry/1008445"
    assert silbury.raw is not None
    assert silbury.raw["NGR"].startswith("SU ")
    lon, lat = point_lon_lat(silbury.centroid)
    assert Point(lon, lat).distance(SILBURY) < 0.002

    source = db.get(Source, "he-nhle-scheduled-monuments")
    assert source is not None
    assert source.record_count == 8
    assert source.licence.startswith("Open Government Licence v3.0")


@respx.mock
def test_the_oddly_written_date_is_read(db: Session) -> None:
    serve_hub(FIXTURE.read_bytes())
    run_connector(ScheduledMonuments())
    barrow = db.scalars(select(Record).where(Record.external_id == "1008099")).one()
    assert barrow.source_updated_at is not None
    assert barrow.source_updated_at.year >= 1925
    assert barrow.raw is not None
    assert barrow.raw["SchedDate"] == "1925-03-10T00:00:00+00:00"


@respx.mock
def test_running_twice_gives_the_same_rows(db: Session) -> None:
    hub = serve_hub(FIXTURE.read_bytes())
    first = run_connector(ScheduledMonuments())
    before = rows(db)
    second = run_connector(ScheduledMonuments())
    after = rows(db)

    assert len(before) == 8
    assert after == before
    assert second.stats is not None
    assert first.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (0, 8, 0)
    # The second run used the copy on disk.
    assert hub.call_count == 1


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    serve_hub(FIXTURE.read_bytes())
    run = run_connector(ScheduledMonuments(), bbox=(-1.90, 51.40, -1.82, 51.44))
    assert run.stats is not None
    assert not run.stats["full"]
    ids = set(db.scalars(select(Record.external_id)).all())
    assert {"1008445", "1015546", "1010628"} <= ids
    assert "1010140" not in ids  # Stonehenge is further south


@respx.mock
def test_an_export_that_changed_shape_fails_the_run(db: Session, tmp_path: Path) -> None:
    changed = tmp_path / "changed.gpkg"
    changed.write_bytes(FIXTURE.read_bytes())
    with sqlite3.connect(changed) as conn:
        conn.execute("ALTER TABLE Scheduled_Monuments RENAME COLUMN ListEntry TO ListEntryNumber")
    serve_hub(changed.read_bytes())
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(ScheduledMonuments())
    assert db.scalars(select(Record)).all() == []


def test_a_source_without_a_licence_or_attribution_cannot_be_registered() -> None:
    fields: dict[str, str] = {
        "key": "no-licence",
        "name": "Mystery data",
        "publisher": "Someone",
        "licence": "Open Government Licence v3.0",
        "attribution": "\u00a9 Someone",
        "category": "monument",
        "access": "bulk",
        "reuse": "open",
    }
    for missing in ("licence", "attribution"):
        with pytest.raises(AssertionError, match=f"needs a {missing}"):
            SourceInfo(**(fields | {missing: "   "}))  # pyright: ignore[reportArgumentType]
    with pytest.raises(AssertionError, match="unknown reuse class"):
        SourceInfo(**(fields | {"reuse": "probably fine"}))  # pyright: ignore[reportArgumentType]
