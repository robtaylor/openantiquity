"""A connector that yields whatever a test hands it."""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from typing import ClassVar

from shapely.geometry import Point

from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo

SOURCE = SourceInfo(
    key="fake-monuments",
    name="Fake monuments",
    publisher="The test suite",
    licence="Open Government Licence v3.0",
    licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
    attribution="Contains made-up data",
    homepage="https://example.org/fake",
    coverage="Wiltshire",
    category="monument",
    access="bulk",
    reuse="open",
)


def record(
    external_id: str, name: str | None = None, lon: float = -1.85, lat: float = 51.43, **fields
) -> RecordIn:
    return RecordIn(
        external_id=external_id,
        name=name or f"Barrow {external_id}",
        geom=fields.pop("geom", Point(lon, lat)),
        **fields,
    )


class FakeConnector(Connector):
    source: ClassVar[SourceInfo] = SOURCE

    def __init__(self, records: Iterable[RecordIn | Exception] = (), *, configured: bool = True) -> None:
        super().__init__()
        self.records = list(records)
        self.configured = configured
        self.calls: list[dict] = []

    def is_configured(self) -> bool:
        return self.configured

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        self.calls.append({"bbox": bbox, "limit": limit})
        for item in self.records:
            if isinstance(item, Exception):
                raise item
            yield item
