"""The GB1900 connector, end to end against labels cut from the complete download.

See `tests/connectors/names/support.py` for how the fixture was recorded.
"""

from __future__ import annotations

import csv
import io
import json
import zipfile
from collections.abc import Callable
from pathlib import Path
from typing import Any

import pytest
import respx
from fastapi.testclient import TestClient
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest import registry
from fieldclub.ingest.connectors.portsmouth_gb1900_gazetteer import (
    CHANGES_STATEMENT,
    DOWNLOAD,
    LICENCE_URL,
    MEMBER,
    Gb1900Gazetteer,
    is_antiquity,
    trust_store,
)
from fieldclub.ingest.runner import IngestFailedError, run_connector
from fieldclub.models import Record, Source
from fieldclub.models.common import point_lon_lat
from tests.connectors.names.support import GB1900_ZIP, serve_file, worklist_entry, zip_with

KEY = "portsmouth-gb1900-gazetteer"
# Of the 221 labels near Avebury, 37 name antiquities, plus one each from Wales and Scotland.
ANTIQUITIES = 39


@pytest.fixture(autouse=True)
def own_var_dir(env: Callable[..., None], tmp_path: Path) -> None:
    env(VAR_DIR=str(tmp_path / "var"))


def rows(db: Session) -> list[tuple[Any, ...]]:
    db.expire_all()
    found = db.scalars(select(Record).order_by(Record.external_id)).all()
    return [
        (
            record.id,
            record.external_id,
            record.name,
            record.category,
            record.record_type,
            record.summary,
            bytes(record.geom.data),
            json.dumps(record.raw, sort_keys=True),
        )
        for record in found
    ]


def fixture_rows() -> list[dict[str, str]]:
    with zipfile.ZipFile(GB1900_ZIP) as archive:
        text = archive.read(MEMBER).decode("utf-16")
    return list(csv.DictReader(io.StringIO(text, newline="")))


def test_the_connector_is_registered_under_its_work_list_key() -> None:
    assert registry.get(KEY) is Gb1900Gazetteer


def test_the_source_carries_the_work_list_licence() -> None:
    entry = worklist_entry(KEY)
    info = Gb1900Gazetteer.source
    assert info.licence == entry["licence"]
    assert info.reuse == entry["reuse"] == "share_alike"
    assert info.category == entry["category"] == "map_label"
    assert info.access == "bulk"
    assert info.publisher == entry["publisher"]
    # The work-list's attribution as it stands, then what CC BY-SA asks: say what was changed.
    assert info.attribution == f"{entry['attribution']} {CHANGES_STATEMENT}"
    # The work-list has no licence address, and CC BY-SA asks for a link to the licence.
    # This one is the address in the licence file inside the download.
    assert entry["licence_url"] is None
    with zipfile.ZipFile(GB1900_ZIP) as archive:
        licence_file = next(name for name in archive.namelist() if "LICENCE" in name)
        assert LICENCE_URL in archive.read(licence_file).decode("utf-8", errors="replace")
    assert info.licence_url == LICENCE_URL


def test_the_derived_source_is_not_named_gb1900() -> None:
    """The gazetteer's terms keep the name for the unmodified gazetteer."""
    assert "GB1900" not in Gb1900Gazetteer.source.name


@pytest.mark.parametrize(
    "text",
    [
        "Tumulus",
        "tumuli",
        "Moat",
        "Camp",
        "Intrenchment",
        "Hut Circles",
        "Long Barrow (Tumulus)",
        "The Sanctuary (Stone Circle) (Site of)",
        "ROMAN ROAD",
        "Ridge Way or ICKNIELD WAY [ROMAN ROAD]",
        "Supposed ROMAN ROAD",
        "Stone Cist & Urn found A. D. 1848",
        "Chapel (Site of)",
        "Fish Ponds (Remains of)",
        "Wansdyke",
        "Offa's Dike",
        "Stone Row",
        "Castle (In Ruins)",
    ],
)
def test_labels_that_name_antiquities_are_kept(text: str) -> None:
    assert is_antiquity(text)


@pytest.mark.parametrize(
    "text",
    [
        "F. P.",
        "Spring",
        "Old Quarry",
        "Old Shaft",
        "Gravel Pit",
        "Fish Pond",
        "Stone",
        "Moat Farm",
        "Castle Street",
        "Camp Hill",
        "Castle Bay",
        "Rose Villa",
        "NORTH BRITISH RAILWAY",
        "Burial Ground",
        "Friends' Burial Ground (Disused)",
        "The Homestead",
        "Barrow in Furness",
        "Silbury Hill",
    ],
)
def test_other_labels_are_left_out(text: str) -> None:
    assert not is_antiquity(text)


def test_the_client_trusts_the_hosts_missing_intermediate() -> None:
    certificates: list[dict[str, Any]] = trust_store().get_ca_certs()
    names = {dict(part[0] for part in cert["subject"]).get("commonName") for cert in certificates}
    assert "Thawte TLS RSA CA G1" in names
    # The usual roots are still there, so the intermediate chains to one of them.
    assert "DigiCert Global Root G2" in names


@respx.mock
def test_a_run_stores_the_antiquities_with_their_fields(db: Session) -> None:
    serve_file(DOWNLOAD, GB1900_ZIP.read_bytes())
    run = run_connector(Gb1900Gazetteer())
    assert run.status == "completed"
    assert run.stats is not None
    assert run.stats["seen"] == ANTIQUITIES

    sanctuary = db.scalars(select(Record).where(Record.external_id == "58186abe2c66dc3849025d6c")).one()
    assert sanctuary.source_key == KEY
    assert sanctuary.name == "The Sanctuary (Stone Circle) (Site of)"
    assert sanctuary.category == "map_label"
    assert sanctuary.record_type == "Label on the six-inch map"
    assert sanctuary.summary is not None
    assert sanctuary.summary.startswith(
        "Lettered on the Ordnance Survey six-inch map of about 1900, in Avebury, "
    )
    assert sanctuary.url is None
    assert sanctuary.raw is not None
    assert sanctuary.raw["parish"] == "Avebury"
    assert sanctuary.raw["osgb_east"].startswith("411624.")
    lon, lat = point_lon_lat(sanctuary.centroid)
    # On Overton Hill, where the Sanctuary was.
    assert Point(lon, lat).distance(Point(-1.8343, 51.4107)) < 0.0005

    names = set(db.scalars(select(Record.name)).all())
    assert "F. P." not in names
    assert {"Tumulus", "Long Barrow (Tumulus)", "Camp", "tronach castle"} <= names

    source = db.get(Source, KEY)
    assert source is not None
    assert source.record_count == ANTIQUITIES
    assert source.reuse == "share_alike"


@respx.mock
def test_the_share_alike_terms_go_with_every_record(db: Session, client: TestClient) -> None:
    serve_file(DOWNLOAD, GB1900_ZIP.read_bytes())
    run_connector(Gb1900Gazetteer())
    record_id = db.scalars(select(Record.id).where(Record.name == "Long Barrow (Tumulus)").limit(1)).one()
    body = client.get(f"/api/v1/records/{record_id}").json()
    assert body["source"]["reuse"] == "share_alike"
    assert body["source"]["licence"].startswith("CC BY-SA 4.0")
    assert body["source"]["licence_url"] == LICENCE_URL
    assert "the GB1900 partners and volunteers" in body["source"]["attribution"]


@respx.mock
def test_running_twice_gives_the_same_rows(db: Session) -> None:
    host = serve_file(DOWNLOAD, GB1900_ZIP.read_bytes())
    run_connector(Gb1900Gazetteer())
    before = rows(db)
    second = run_connector(Gb1900Gazetteer())
    assert len(before) == ANTIQUITIES
    assert rows(db) == before
    assert second.stats is not None
    assert (second.stats["inserted"], second.stats["updated"], second.stats["deleted"]) == (0, ANTIQUITIES, 0)
    # The second run used the copy on disk.
    assert host.call_count == 1


@respx.mock
def test_a_partial_run_by_bbox(db: Session) -> None:
    serve_file(DOWNLOAD, GB1900_ZIP.read_bytes())
    run = run_connector(Gb1900Gazetteer(), bbox=(-1.90, 51.38, -1.80, 51.46))
    assert run.stats is not None
    assert not run.stats["full"]
    assert run.stats["seen"] == ANTIQUITIES - 2
    nations = {record.raw["nation"] for record in db.scalars(select(Record)) if record.raw}
    assert nations == {"England"}


def changed(rename: tuple[str, str]) -> bytes:
    """The fixture with one column heading renamed."""
    with zipfile.ZipFile(GB1900_ZIP) as archive:
        members = {name: archive.read(name) for name in archive.namelist()}
    text = members[MEMBER].decode("utf-16")
    heading, rest = text.split("\r\n", 1)
    members[MEMBER] = (heading.replace(*rename) + "\r\n" + rest).encode("utf-16")
    return zip_with(members)


@respx.mock
def test_a_download_that_changed_shape_fails_the_run(db: Session) -> None:
    serve_file(DOWNLOAD, changed(("final_text", "text")))
    with pytest.raises(IngestFailedError, match="changed shape"):
        run_connector(Gb1900Gazetteer())
    assert db.scalars(select(Record)).all() == []


@respx.mock
def test_a_label_without_a_usable_position_fails_the_run(db: Session) -> None:
    labels = fixture_rows()
    labels[0] |= {"final_text": "Tumulus", "latitude": "not a number"}
    out = io.StringIO(newline="")
    writer = csv.DictWriter(out, fieldnames=list(labels[0]), lineterminator="\r\n")
    writer.writeheader()
    writer.writerows(labels)
    serve_file(DOWNLOAD, zip_with({MEMBER: out.getvalue().encode("utf-16")}))
    with pytest.raises(IngestFailedError, match="latitude 'not a number'"):
        run_connector(Gb1900Gazetteer())
