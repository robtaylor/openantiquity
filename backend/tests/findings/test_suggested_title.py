"""The title a finding takes when none is given, spaced as the interface writes a square.

The interface suggests "Enclosure in SU 10 69", and "Enclosure in V 26 24"
for an Irish square, which has one letter (`frontend/src/features/findings/square.ts`).
The server's default is the same words, and a spaced square in a title is
still not a position for the rule that refuses one in text, exactly as a
square run together isn't.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from fieldclub import gridref
from fieldclub.schemas.findings import TITLE_MAX
from fieldclub.services import findings, text_positions
from fieldclub.vocab import FeatureClass, Role
from tests.findings.support import API, create, point
from tests.helpers import ClientAs, MakeUser, error_code

# A point on each grid, and the square the interface names for it.
PLACES = [
    pytest.param(-1.8542, 51.4286, "SU 10 69", id="british"),
    pytest.param(-9.5, 51.95, "V 96 78", id="irish"),
    pytest.param(-6.0, 54.6, "J 29 74", id="northern-irish"),
]


@pytest.mark.parametrize(("lon", "lat", "square"), PLACES)
def test_the_title_names_the_square_spaced_as_the_interface_does(
    db: Session, make_user: MakeUser, lon: float, lat: float, square: str
) -> None:
    ref = gridref.gridref_at(lon, lat, 4)
    # The interface spaces the compact square, "SU1069", into its letters and two pairs of figures.
    compact = ref.format(compact=True)
    letters = compact.rstrip("0123456789")
    assert f"{letters} {compact[len(letters) : len(letters) + 2]} {compact[len(letters) + 2 :]}" == square
    assert findings.suggested_title(FeatureClass.ENCLOSURE, lon, lat) == f"Enclosure in {square}"
    finding = create(db, make_user(), lon=lon, lat=lat, feature_class=FeatureClass.ROUND_BARROW)
    assert finding.title == f"Round barrow or mound in {square}"


def test_a_point_on_neither_grid_gets_the_class_alone() -> None:
    assert findings.suggested_title(FeatureClass.ENCLOSURE, 10.0, 10.0) == "Enclosure"


def test_the_title_fits_a_title() -> None:
    assert findings.SUGGESTED_TITLE_MAX == TITLE_MAX
    for info in FeatureClass:
        assert len(findings.suggested_title(info, -1.8542, 51.4286)) <= TITLE_MAX


@pytest.mark.parametrize(("lon", "lat", "square"), PLACES)
def test_a_spaced_square_is_not_a_position_in_text_and_a_finer_reference_still_is(
    lon: float, lat: float, square: str
) -> None:
    for title in (f"Enclosure in {square}", f"Enclosure in {square.replace(' ', '')}"):
        assert text_positions.find_positions(title) == [], title
        assert text_positions.redact(title) == title
    ref = gridref.gridref_at(lon, lat, 6)
    for finer in (ref.format(), ref.format(compact=True)):
        assert text_positions.holds_position(f"Enclosure in {finer}"), finer
        assert text_positions.PLACEHOLDER in text_positions.redact(f"Enclosure at {finer}")


@pytest.mark.parametrize(("lon", "lat", "square"), PLACES)
def test_a_protected_finding_takes_the_suggested_title_and_refuses_a_finer_one(
    client_as: ClientAs, make_user: MakeUser, lon: float, lat: float, square: str
) -> None:
    client: TestClient = client_as(make_user(Role.MEMBER))
    body = {"location": point(lon, lat), "feature_class": "round_barrow"}
    made = client.post(f"{API}/findings", json=body | {"title": f"Round barrow in {square}"})
    assert made.status_code == 201, made.text
    assert made.json()["title"] == f"Round barrow in {square}"
    finer = gridref.gridref_at(lon, lat, 6).format()
    refused = client.post(f"{API}/findings", json=body | {"title": f"Round barrow at {finer}"})
    assert (refused.status_code, error_code(refused)) == (422, "position_in_text")
