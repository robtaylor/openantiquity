"""How each Historic England layer's fields become records, on named features from the recorded fixtures."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

import pytest
import respx
from shapely.geometry import Point
from sqlalchemy import select
from sqlalchemy.orm import Session

from fieldclub.ingest.connectors.he_aim_detailed_mapping import (
    EMPTY,
    PERIOD_RULES,
    DetailedMapping,
    periods_of,
)
from fieldclub.ingest.connectors.he_aim_monument_extents import MonumentExtents
from fieldclub.ingest.connectors.he_aim_project_areas import ProjectAreas
from fieldclub.ingest.connectors.he_de_designated_sites import DeDesignatedSites
from fieldclub.ingest.connectors.he_greater_london_apas import GreaterLondonApas
from fieldclub.ingest.connectors.he_heritage_at_risk_2026 import HeritageAtRisk2026
from fieldclub.ingest.connectors.he_research_spatial_reports import ResearchSpatialReports
from fieldclub.ingest.connectors.he_turning_the_plough_2 import TurningThePlough2
from fieldclub.ingest.runner import run_connector
from fieldclub.models import Record
from fieldclub.models.common import point_lon_lat
from fieldclub.vocab import Period
from tests.connectors.he.support import serve


def stored(db: Session, key: str, connector: Any, **raw: Any) -> Record:
    """Run `connector` on the key's fixture and return the one record whose `raw` has these values."""
    serve(key)
    run_connector(connector)
    db.expire_all()
    found = [
        record
        for record in db.scalars(select(Record).order_by(Record.id)).all()
        if record.raw is not None and all(record.raw.get(name) == value for name, value in raw.items())
    ]
    assert len(found) == 1, f"{len(found)} records match {raw}"
    return found[0]


# ------------------------------------------------------------------ AIM detailed mapping


@respx.mock
def test_a_detailed_feature_keeps_its_terms_period_and_evidence(db: Session) -> None:
    barrow = stored(db, "he-aim-detailed-mapping", DetailedMapping(), OBJECTID=3250)
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
    assert barrow.raw["HE_UID"] == "943187"
    assert barrow.raw["PERIOD"] == "BRONZE AGE"
    assert barrow.raw["SOURCE_1"].startswith("NMR SU 1141/75")
    assert "SOURCE_2" not in barrow.raw
    assert barrow.raw["HE_URL1"].endswith("uid=943187&resourceID=19191")
    lon, lat = point_lon_lat(barrow.centroid)
    assert Point(lon, lat).distance(Point(-1.826, 51.178)) < 0.05


@respx.mock
def test_several_terms_periods_and_kinds_of_evidence_are_all_kept(db: Session) -> None:
    abbey = stored(db, "he-aim-detailed-mapping", DetailedMapping(), OBJECTID=148371)
    assert abbey.record_type == "Ditch"
    assert abbey.monument_types is not None
    assert abbey.monument_types[:3] == ["ABBEY", "BANK (EARTHWORK)", "BOUNDARY DITCH"]
    assert abbey.name.startswith("Abbey, Bank (earthwork), Boundary ditch")
    assert abbey.periods == ["medieval", "post_medieval"]
    assert abbey.summary is not None
    assert "documentary evidence, earthwork, extant building, ruined building" in abbey.summary
    assert abbey.raw is not None
    assert abbey.raw["EVIDENCE_1"] == "DOCUMENTARY EVIDENCE\\EARTHWORK\\EXTANT BUILDING\\RUINED BUILDING"


@respx.mock
def test_a_twentieth_century_feature_is_modern(db: Session) -> None:
    works = stored(db, "he-aim-detailed-mapping", DetailedMapping(), OBJECTID=1287)
    assert works.periods == ["modern"]
    assert works.summary is not None
    assert works.summary.startswith("Evidence: cropmark, earthwork, structure.")


@respx.mock
def test_features_of_one_monument_get_different_ids_and_a_missing_monument_number_is_no_problem(
    db: Session,
) -> None:
    serve("he-aim-detailed-mapping")
    run_connector(DetailedMapping())
    airfield = db.scalars(select(Record).where(Record.raw["HE_UID"].astext == "1408409")).all()
    assert len(airfield) == 2
    assert len({record.external_id for record in airfield}) == 2
    nameless = db.scalars(select(Record).where(Record.raw["HE_UID"].astext == " NONE GIVEN")).all()
    assert len(nameless) >= 4
    assert all(len(record.external_id) == 20 for record in [*nameless, *airfield])


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


# ------------------------------------------------------------------ AIM extents and project areas


@respx.mock
def test_a_monument_extent_is_named_for_its_historic_england_record(db: Session) -> None:
    extent = stored(db, "he-aim-monument-extents", MonumentExtents(), OBJECTID=45679)
    assert extent.name == "Monument extent (Historic England record 1066506)"
    assert extent.record_type == "Monument extent"
    assert extent.summary == "Project: Stonehenge World Heritage Site."
    assert extent.monument_types is None
    assert extent.periods is None
    assert extent.raw is not None
    assert extent.raw["layer"] == "MONUMENT_POLYGON"
    assert extent.raw["HE_UID1"] == "1066506"


@respx.mock
def test_a_project_area_keeps_its_report_and_completion_date(db: Session) -> None:
    suffolk = stored(db, "he-aim-project-areas", ProjectAreas(), OBJECTID=3)
    assert suffolk.name == "Suffolk Coast"
    assert suffolk.record_type == "Mapping project area"
    assert suffolk.url == "https://historicengland.org.uk/research/results/reports/81-2005"
    assert (
        suffolk.summary
        == "Mapped from vertical aerial photographs, oblique aerial photographs. Status: completed."
    )
    assert suffolk.source_updated_at == datetime(2005, 1, 1, tzinfo=UTC)
    assert suffolk.raw is not None
    assert suffolk.raw["Completed"] == "2005-01-01T00:00:00+00:00"
    assert suffolk.raw["Team_u"].startswith("Sufffolk")  # sic, as the source has it


@respx.mock
def test_two_project_polygons_with_the_same_name_keep_separate_ids(db: Session) -> None:
    serve("he-aim-project-areas")
    run_connector(ProjectAreas())
    derbyshire = db.scalars(select(Record).where(Record.name.startswith("Derbyshire"))).all()
    assert len(derbyshire) == 2
    assert derbyshire[0].external_id != derbyshire[1].external_id


# ------------------------------------------------------------------ the smaller layers


@respx.mock
def test_a_heritage_at_risk_entry_links_to_the_registers_own_page(db: Session) -> None:
    entry = stored(db, "he-heritage-at-risk-2026", HeritageAtRisk2026(), List_Entry=1008075)
    assert entry.external_id == "{84A31E09-9A55-4E28-9A07-036CA1171AF3}"
    assert entry.name.startswith("Pair of round barrows 400 metres west of the Ridgeway")
    assert entry.category == "designation"
    assert entry.record_type == "Scheduled Monument"
    assert entry.summary == "On the Heritage at Risk Register 2026, assessed by the Archaeology method."
    # The register's number (35546) is not the list entry's (1008075).
    assert (
        entry.url == "https://historicengland.org.uk/advice/heritage-at-risk/search-register/list-entry/35546"
    )
    assert entry.raw is not None
    assert entry.raw["Risk_Metho"] == "Archaeology"


@respx.mock
def test_a_research_report_location_links_to_the_report(db: Session) -> None:
    report = stored(db, "he-research-spatial-reports", ResearchSpatialReports(), Report_Num="2027")
    assert report.name == "AVEBURY: CHARCOAL"
    assert report.category == "document"
    assert report.record_type == "Ancient Monuments Laboratory (AML) Series"
    assert report.summary == "Report from the Ancient Monuments Laboratory (AML) - Old Series"
    assert report.url == "https://historicengland.org.uk/research/results/reports/2027"
    assert isinstance(Point(*point_lon_lat(report.centroid)), Point)
    lon, lat = point_lon_lat(report.centroid)
    assert abs(lon - -1.85) < 0.05
    assert abs(lat - 51.43) < 0.05
    assert report.raw is not None
    assert report.raw["Year"] == 1976
    assert report.raw["Keyword"] == "Charcoal; Plant Remains"


@respx.mock
def test_a_removed_listing_says_what_was_removed_and_when(db: Session) -> None:
    mills = stored(db, "he-de-designated-sites", DeDesignatedSites(), ARTICLEUID=1423345)
    assert mills.external_id == "1423345"
    assert mills.name == "UPPER AND VICTORIA MILLS FORMER STOVE RACK AND ADJACENT BUILDING"
    assert mills.category == "designation"
    assert mills.record_type == "Removed from the list (listing)"
    assert mills.summary is not None
    assert mills.summary.startswith("This building has been assessed for de-listing")
    assert mills.source_updated_at == datetime(2014, 11, 4, 10, 4, 26, tzinfo=UTC)
    assert mills.raw is not None
    assert mills.raw["OriginalListEntryNumber"] == 1021531
    assert mills.raw["DateRemovedFromList"] == "2014-11-04T10:04:26+00:00"


@respx.mock
def test_a_removed_scheduling_is_a_scheduled_monument_that_was_removed(db: Session) -> None:
    serve("he-de-designated-sites")
    run_connector(DeDesignatedSites())
    types = set(db.scalars(select(Record.record_type)).all())
    assert "Removed from the list (scheduling)" in types


@respx.mock
def test_london_priority_areas_are_named_by_tier_and_reference_with_plain_descriptions(db: Session) -> None:
    area = stored(db, "he-greater-london-apas", GreaterLondonApas(), OBJECTID=10395)
    assert area.name == "Archaeological Priority Area - Tier III (HER reference 76923)"
    assert area.record_type == "Archaeological Priority Area - Tier III"
    assert area.category == "designation"
    assert area.summary is not None
    assert area.summary.startswith("Summary and Definition 8.3.1 The Archaeological Priority Area covers")
    assert "\xa0" not in area.summary
    markup = stored_html_summary(db)
    assert "<" not in markup


def stored_html_summary(db: Session) -> str:
    """The summary of the area whose description in the layer is HTML."""
    record = db.scalars(select(Record).where(Record.raw["primary_re"].astext == "77135")).one()
    assert record.summary is not None
    assert record.summary.startswith("Summary and Definition This Archaeological Priority Area includes")
    return record.summary


@respx.mock
def test_the_parts_of_one_priority_area_keep_separate_ids(db: Session) -> None:
    serve("he-greater-london-apas")
    run_connector(GreaterLondonApas())
    parts = db.scalars(select(Record).where(Record.raw["primary_re"].astext == "220942")).all()
    assert len(parts) == 3
    assert len({part.external_id for part in parts}) == 3


@respx.mock
def test_a_ridge_and_furrow_polygon_carries_the_surveys_judgements(db: Session) -> None:
    field = stored(db, "he-turning-the-plough-2", TurningThePlough2(), FeatureID="1:02")
    assert field.name == "Ridge and furrow, Ashendon"
    assert field.category == "monument"
    assert field.record_type == "Ridge and furrow survey"
    assert field.monument_types == ["RIDGE AND FURROW"]
    assert field.periods is None
    assert field.summary == (
        "Survival: present. Condition: slightly degraded. Vulnerability: none identified. "
        "Confidence: high. Previously recorded in early 1990s"
    )
    assert field.source_updated_at == datetime(2012, 1, 6, tzinfo=UTC)
    assert field.raw is not None
    assert field.raw["Parish"] == " Ashendon"
