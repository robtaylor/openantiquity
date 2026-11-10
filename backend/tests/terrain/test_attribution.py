"""The LIDAR sources are rows in the sources table, so `/meta` attributes the terrain layers."""

from __future__ import annotations

import json
from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.models import Source
from fieldclub.terrain.attribution import TERRAIN_SOURCES, register_sources

WORKLIST = Path(__file__).resolve().parents[3] / "docs" / "sources" / "worklists" / "sources.json"


def worklist() -> dict[str, dict]:
    entries = json.loads(WORKLIST.read_text())
    return {entry["key"]: entry for group in entries.values() for entry in group}


def test_the_rows_match_the_work_list() -> None:
    listed = worklist()
    for info in TERRAIN_SOURCES:
        entry = listed[info.key]
        assert info.key.startswith("defra-lidar-")
        assert info.attribution == entry["attribution"]
        assert info.licence_url == entry["licence_url"]
        assert info.reuse == entry["reuse"]
        assert info.coverage == entry["coverage"]
        assert entry["licence"].startswith("Open Government Licence v3")


def test_registering_twice_leaves_one_row_each(db: Session) -> None:
    assert register_sources(db) == [info.key for info in TERRAIN_SOURCES]
    register_sources(db)
    db.commit()
    rows = db.scalars(select(Source).order_by(Source.key)).all()
    assert [row.key for row in rows] == sorted(info.key for info in TERRAIN_SOURCES)
    assert all(row.access == "bulk" and row.reuse == "open" and row.enabled for row in rows)


def test_meta_attributes_the_terrain_layers(db: Session, client: TestClient) -> None:
    register_sources(db)
    db.commit()
    sources = {source["key"]: source for source in client.get("/api/v1/meta").json()["sources"]}
    composite = sources["defra-lidar-composite-dtm-2022-1m"]
    assert composite["attribution"] == (
        "© Environment Agency copyright and/or database right 2022. All rights reserved."
    )
    assert composite["licence"] == "Open Government Licence v3.0"
    assert composite["publisher"].startswith("Environment Agency")
    assert "defra-lidar-survey-index-catalogues" in sources
