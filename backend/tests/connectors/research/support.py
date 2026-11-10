"""Shared by the research connectors' tests: the work-list, the recorded fixtures and the stored rows.

Every fixture in `fixtures/` was recorded from the live source on 2026-11-10,
politely: a handful of requests a second or more apart, with the project's
`User-Agent`. Each connector's test module says what it holds and how it was
cut down. None holds anything the source doesn't publish openly.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest.base import SourceInfo
from fieldclub.models import Record

WORKLIST = Path(__file__).parents[4] / "docs" / "sources" / "worklists" / "sources.json"
FIXTURES = Path(__file__).parent / "fixtures"


def worklist_entry(key: str) -> dict[str, Any]:
    entries = json.loads(WORKLIST.read_text(encoding="utf-8"))["bulk"]
    return next(entry for entry in entries if entry["key"] == key)


def fixture_json(name: str) -> Any:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def assert_source_matches_worklist(info: SourceInfo, **expected: Any) -> None:
    """The source's licence, attribution and reuse class, word for word as the work-list has them.

    `expected` overrides a field the connector deliberately adds to, such as an attribution.
    """
    entry = worklist_entry(info.key)
    assert info.key == entry["key"]
    assert info.name == entry["name"]
    assert info.publisher == entry["publisher"]
    for field in ("licence", "licence_url", "attribution", "reuse", "category"):
        want = expected.get(field, entry[field])
        assert getattr(info, field) == want, field
    assert info.access == "bulk"


def rows(db: Session, source_key: str) -> list[tuple[Any, ...]]:
    """Every stored record of the source, without the columns a run is expected to change."""
    db.expire_all()
    found = db.scalars(
        select(Record).where(Record.source_key == source_key).order_by(Record.external_id)
    ).all()
    return [
        (
            record.id,
            record.external_id,
            record.name,
            record.summary,
            record.category,
            record.record_type,
            record.monument_types,
            record.periods,
            record.precision_m,
            record.url,
            record.source_updated_at,
            bytes(record.geom.data),
            json.dumps(record.raw, sort_keys=True),
        )
        for record in found
    ]
