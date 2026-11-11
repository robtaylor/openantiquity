"""Every source has a short licence name and a credit line fit to show, apart from the research's notes."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub import credits
from fieldclub.ingest import reference, registry
from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.runner import upsert_source
from fieldclub.models import Source
from fieldclub.terrain.attribution import TERRAIN_SOURCES
from fieldclub.vocab import SourceAccess, SourceReuse
from tests.helpers import add_source


def declared() -> list[SourceInfo]:
    return [
        *(connector.source for connector in registry.all_connectors()),
        *(loader.source for loader in reference.all_loaders()),
        *TERRAIN_SOURCES,
    ]


# Research notes that once stood where a credit should.
NOTES = ("None required", "cite DOIs", "Acknowledge", "must not", "stated in", "Derived works")


def test_every_declared_source_is_credited_and_nothing_else_is() -> None:
    keys = {info.key for info in declared()}
    assert keys - set(credits.CREDITS) == set(), "a source with no credit: add it to fieldclub/credits.py"
    assert set(credits.CREDITS) - keys == set(), "a credit for a source nothing declares"


@pytest.mark.parametrize("info", declared(), ids=lambda info: info.key)
def test_a_declared_source_carries_a_short_label_and_a_credit_fit_to_show(info: SourceInfo) -> None:
    assert info.licence_label is not None
    assert info.credit is not None
    assert len(info.licence_label) <= 16, info.licence_label
    assert len(info.credit) <= 250, info.credit
    assert not any(note in info.credit for note in NOTES), info.credit
    # Only the placeholders the runner fills.
    assert "[" not in info.credit.replace("[year]", "").replace("[date]", ""), info.credit


def test_a_stored_source_has_its_credit_with_the_year_filled(db: Session) -> None:
    info = next(info for info in declared() if info.key == "he-nhle-scheduled-monuments")
    upsert_source(db, info, datetime(2027, 3, 1, tzinfo=UTC))
    row = db.get(Source, info.key)
    assert row is not None
    assert row.licence_label == "OGL v3"
    assert row.credit == (
        "© Historic England 2027. Contains Ordnance Survey data © Crown copyright and database right 2027."
    )
    # The full terms stay as they were.
    assert row.licence == info.licence
    assert "obtained on 1 March 2027" in row.attribution


def test_a_source_can_be_given_its_own_label_and_credit() -> None:
    info = SourceInfo(
        key="someone-elses-data",
        name="Data",
        publisher="Someone",
        licence="Their licence, with notes",
        attribution="Their attribution, with notes",
        category="monument",
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        licence_label="Theirs",
        credit="© Someone",
    )
    assert (info.licence_label, info.credit) == ("Theirs", "© Someone")


def test_sources_are_served_with_their_label_and_credit(db: Session, client: TestClient) -> None:
    add_source(db, "credited", licence_label="OGL v3", credit="© The test suite")
    # A row stored before it had either shows its full terms in their place.
    add_source(db, "older", licence="Open Government Licence v3.0", attribution="© Older")
    db.commit()
    served = {item["key"]: item for item in client.get("/api/v1/sources").json()}
    assert (served["credited"]["licence_label"], served["credited"]["credit"]) == (
        "OGL v3",
        "© The test suite",
    )
    assert (served["older"]["licence_label"], served["older"]["credit"]) == (
        "Open Government Licence v3.0",
        "© Older",
    )
    meta = {item["key"]: item for item in client.get("/api/v1/meta").json()["sources"]}
    assert meta["credited"]["credit"] == "© The test suite"
