"""An investigation says whether it keeps back the place of a finding from its reader.

The report form leaves out where the map is on any page of an investigation
that does, so the answer comes from the same guard that holds back what is
written and drawn there (`sensitivity.PositionGuard`), not from the page.
"""

from __future__ import annotations

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub.vocab import FeatureClass, InvestigationItemKind, Sensitivity, Visibility
from tests.findings.support import create
from tests.helpers import ClientAs, MakeUser
from tests.investigations.support import add, make, url

LON, LAT = -1.812947, 51.402583


def test_a_protected_finding_held_is_kept_back_from_a_signed_out_reader_only(
    db: Session, make_user: MakeUser, client: TestClient, client_as: ClientAs
) -> None:
    finder = make_user()
    barrow = create(db, finder, lon=LON, lat=LAT, feature_class=FeatureClass.ROUND_BARROW)
    assert barrow.sensitivity == Sensitivity.PROTECTED
    notebook = make(db, finder, Visibility.PUBLIC)
    add(db, notebook, finder, kind=InvestigationItemKind.FINDING, finding=barrow.public_id)

    assert client.get(url(notebook)).json()["places_kept_back"] is True
    assert client_as(make_user()).get(url(notebook)).json()["places_kept_back"] is False


def test_an_investigation_of_open_findings_keeps_nothing_back(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    finder = make_user()
    ditch = create(db, finder, lon=LON, lat=LAT, feature_class=FeatureClass.ENCLOSURE)
    notebook = make(db, finder, Visibility.PUBLIC)
    add(db, notebook, finder, kind=InvestigationItemKind.FINDING, finding=ditch.public_id)
    assert client.get(url(notebook)).json()["places_kept_back"] is False


def test_a_view_drawn_beside_a_protected_finding_it_doesn_t_hold_counts_too(
    db: Session, make_user: MakeUser, client: TestClient
) -> None:
    finder = make_user()
    create(db, finder, lon=LON, lat=LAT, feature_class=FeatureClass.ROUND_BARROW)
    notebook = make(db, finder, Visibility.PUBLIC)
    add(
        db, notebook, finder, kind=InvestigationItemKind.VIEW,
        data={"centre": [LON + 0.001, LAT], "zoom": 16, "layer": "composite"},
    )  # fmt: skip
    assert client.get(url(notebook)).json()["places_kept_back"] is True
