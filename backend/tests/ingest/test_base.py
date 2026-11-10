"""SourceInfo, RecordIn and the Connector base class."""

from __future__ import annotations

import dataclasses

import httpx
import pytest
from shapely.geometry import Point

from fieldclub import http
from fieldclub.config import get_settings
from fieldclub.ingest.base import (
    BRITISH_ISLES,
    Connector,
    RecordIn,
    SourceInfo,
    bbox_in_bbox,
    point_in_bbox,
)
from fieldclub.models import Record
from tests.ingest.fakes import SOURCE, FakeConnector


def test_record_in_covers_every_records_column_a_source_can_fill() -> None:
    set_by_the_runner = {"id", "created_at", "source_key", "centroid", "ingested_at", "search"}
    columns = set(Record.__table__.columns.keys()) - set_by_the_runner
    assert {field.name for field in dataclasses.fields(RecordIn)} == columns


def test_record_in_needs_only_an_id_a_name_and_a_geometry() -> None:
    record = RecordIn(external_id="1", name="Barrow", geom=Point(-1.8, 51.4))
    assert record.category is None
    assert (record.monument_types, record.periods) == ((), ())
    assert record.raw is None


@pytest.mark.parametrize(
    "changes",
    [
        {"key": "Has Spaces"},
        {"key": "UPPER"},
        {"key": ""},
        {"key": "trailing-"},
        {"key": "newline-at-the-end\n"},
        {"licence": " "},
        {"attribution": ""},
        {"name": ""},
        {"publisher": ""},
        {"access": "telepathy"},
        {"reuse": "commercial"},
        {"reuse": ""},
        {"category": ""},
    ],
)
def test_source_info_refuses_incomplete_sources(changes: dict[str, str]) -> None:
    with pytest.raises(AssertionError):
        dataclasses.replace(SOURCE, **changes)


def test_source_info_accepts_a_well_formed_source() -> None:
    info = SourceInfo(
        key="nhle-scheduled",
        name="Scheduled monuments",
        publisher="Historic England",
        licence="OGL v3.0",
        attribution="© Historic England",
        category="designation",
        access="bulk",
        reuse="open",
    )
    assert info.enabled is True
    assert (info.licence_url, info.homepage, info.coverage) == (None, None, None)


def test_source_info_has_no_default_reuse_class() -> None:
    # Every source has to say what its licence allows (Decision 0004).
    with pytest.raises(TypeError, match="reuse"):
        SourceInfo(  # pyright: ignore[reportCallIssue]
            key="nhle-scheduled",
            name="Scheduled monuments",
            publisher="Historic England",
            licence="OGL v3.0",
            attribution="© Historic England",
            category="designation",
            access="bulk",
        )
    for reuse in ("open", "share_alike", "non_commercial", "link_only"):
        assert dataclasses.replace(SOURCE, reuse=reuse).reuse == reuse


def test_connector_is_abstract() -> None:
    with pytest.raises(TypeError, match="abstract"):
        Connector()  # pyright: ignore[reportAbstractUsage]


def test_connector_defaults() -> None:
    connector = FakeConnector()
    assert connector.settings is get_settings()
    assert connector.bounds == BRITISH_ISLES
    assert Connector.is_configured(connector) is True
    assert connector.http is http.get_client()


def test_connector_uses_an_injected_http_client() -> None:
    client = httpx.Client()
    try:

        class Injected(FakeConnector):
            def __init__(self) -> None:
                Connector.__init__(self, client=client)
                self.records = []
                self.configured = True
                self.calls = []

        assert Injected().http is client
    finally:
        client.close()


def test_a_connector_whose_source_is_not_a_source_info_is_refused() -> None:
    with pytest.raises(AssertionError, match="must be a SourceInfo"):

        class Broken(FakeConnector):
            source = "not a SourceInfo"  # pyright: ignore[reportAssignmentType]

    with pytest.raises(AssertionError, match="must be a SourceInfo"):

        class AlsoBroken(Connector):
            source = "not a SourceInfo"  # pyright: ignore[reportAssignmentType]

            def fetch(self, *, bbox=None, limit=None):
                yield from ()


def test_the_box_helpers_include_the_edges() -> None:
    box = (-1.0, 50.0, 1.0, 52.0)
    assert point_in_bbox(box, -1.0, 52.0)
    assert not point_in_bbox(box, 1.01, 51.0)
    assert bbox_in_bbox(box, (-1.0, 50.0, 1.0, 52.0))
    assert not bbox_in_bbox(box, (-1.0, 50.0, 1.0, 52.1))
