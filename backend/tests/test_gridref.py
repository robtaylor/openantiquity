"""Grid reference conversion and parsing.

The published points below pair a site's WGS84 position with the grid reference
usually quoted for it. A site is not a point, so the test asks that the
converted position falls within 20 m of the published grid square.
"""

from __future__ import annotations

import math

import pytest
from pyproj import Geod
from shapely.geometry import Point
from shapely.ops import nearest_points

from fieldclub import gridref
from fieldclub.gridref import GridRefError, GridSystem

GEOD = Geod(ellps="WGS84")

# name, published grid reference, longitude, latitude
PUBLISHED = [
    ("Avebury", "SU 1025 6996", -1.8542, 51.4286),
    ("Stonehenge", "SU 1224 4219", -1.826189, 51.178844),
    ("Ben Nevis summit", "NN 1667 7128", -5.003508, 56.796849),
    ("Snowdon summit", "SH 6098 5437", -4.076231, 53.068497),
    ("Scafell Pike summit", "NY 2154 0721", -3.211528, 54.454222),
    # Published as the 100 m square J 338 740. Padding that to J 3380 7400 names
    # the square's south-west corner, which is on the lawn, not under the dome.
    ("Belfast City Hall", "J 338 740", -5.9301, 54.5964),
]


def metres_between(a: tuple[float, float], b: tuple[float, float]) -> float:
    _, _, distance = GEOD.inv(a[0], a[1], b[0], b[1])
    return abs(distance)


@pytest.mark.parametrize(("name", "ref", "lon", "lat"), PUBLISHED, ids=[p[0] for p in PUBLISHED])
def test_published_points_convert_to_within_20_metres(name: str, ref: str, lon: float, lat: float) -> None:
    published = gridref.parse_gridref(ref)
    system, easting, northing = gridref.to_grid(lon, lat)
    assert system is published.system

    # Distance from the converted point to the published square, in grid metres.
    dx = max(published.easting - easting, 0.0, easting - (published.easting + published.precision_m))
    dy = max(published.northing - northing, 0.0, northing - (published.northing + published.precision_m))
    assert math.hypot(dx, dy) <= 20.0, f"{name}: {easting:.0f} {northing:.0f} is too far from {ref}"

    # And the other way: the square, turned back into WGS84, is at the site.
    nearest, _ = nearest_points(published.polygon(), Point(lon, lat))
    assert metres_between((nearest.x, nearest.y), (lon, lat)) <= 20.0


@pytest.mark.parametrize(
    ("ref", "lon", "lat"),
    [
        ("SU 1224 4219", -1.826189, 51.178844),
        ("NN 1667 7128", -5.003508, 56.796849),
        ("SH 6098 5437", -4.076231, 53.068497),
        ("NY 2154 0721", -3.211528, 54.454222),
    ],
)
def test_to_gridref_gives_the_published_reference(ref: str, lon: float, lat: float) -> None:
    assert gridref.to_gridref(lon, lat, 8) == ref


@pytest.mark.parametrize(
    ("lon", "lat", "letters"),
    [
        (-0.1276, 51.5072, "TQ"),  # London
        (-5.7160, 50.0660, "SW"),  # Land's End
        (1.3200, 51.1300, "TR"),  # Dover
        (1.2970, 52.6290, "TG"),  # Norwich
        (-3.1883, 55.9533, "NT"),  # Edinburgh
        (-4.2247, 57.4778, "NH"),  # Inverness
        (-2.9600, 58.9800, "HY"),  # Kirkwall
        (-1.1500, 60.1550, "HU"),  # Lerwick
        (-4.4800, 54.1500, "SC"),  # Isle of Man
        (-5.7900, 55.3100, "NR"),  # Mull of Kintyre, 20 km from Ireland but in Great Britain
        (-6.2000, 55.6300, "NR"),  # Islay
        (-5.0500, 54.8600, "NX"),  # Rhins of Galloway
        (-6.3170, 49.9140, "SV"),  # Isles of Scilly
        (-5.5800, 55.2800, "NR"),  # Sanda Island, off Kintyre
        (-5.1200, 55.2500, "NX"),  # Ailsa Craig
        (-5.1600, 55.0000, "NW"),  # Corsewall Point, the Rhins
        (-5.1200, 54.8400, "NW"),  # Portpatrick
        (-4.8300, 54.0500, "SC"),  # Calf of Man
        (-4.7000, 53.3100, "SH"),  # South Stack, Anglesey
        (-5.6700, 51.7200, "SM"),  # The Smalls, off Pembrokeshire
        (-8.5800, 57.8100, "NF"),  # St Kilda
    ],
)
def test_osgb_letters(lon: float, lat: float, letters: str) -> None:
    ref = gridref.to_gridref(lon, lat, 6)
    assert ref.split(" ")[0] == letters
    assert gridref.grid_system(lon, lat) is GridSystem.OSGB


@pytest.mark.parametrize(
    ("lon", "lat", "letter"),
    [
        (-5.9301, 54.5964, "J"),  # Belfast
        (-7.3200, 54.9960, "C"),  # Derry
        (-7.6400, 54.3440, "H"),  # Enniskillen
        (-6.2100, 55.2950, "D"),  # Rathlin Island
        (-6.2600, 53.3500, "O"),  # Dublin
        (-8.4700, 51.9000, "W"),  # Cork
        (-9.0500, 53.2700, "M"),  # Galway
        (-5.5400, 54.6800, "J"),  # Copeland Islands, off the Ards peninsula
        (-5.4300, 54.4900, "J"),  # Burr Point, the easternmost point of Ireland
        (-6.0600, 55.2000, "D"),  # Torr Head, 20 km from Kintyre
        (-7.2400, 55.4300, "C"),  # Inishtrahull, the northernmost island
        (-10.6600, 52.0700, "V"),  # Tearaght, the westernmost island
        (-9.6000, 51.3900, "V"),  # Fastnet Rock, the southernmost point
        (-5.9980, 52.9650, "T"),  # Wicklow Head
        (-5.9257, 53.3110, "O"),  # Kish Bank lighthouse, off Dublin
    ],
)
def test_irish_letters(lon: float, lat: float, letter: str) -> None:
    ref = gridref.to_gridref(lon, lat, 6)
    assert ref.split(" ")[0] == letter
    assert gridref.grid_system(lon, lat) is GridSystem.IRISH


@pytest.mark.parametrize(
    ("text", "system", "easting", "northing", "precision"),
    [
        ("SU 1025 6996", GridSystem.OSGB, 410250, 169960, 10),
        ("SU10256996", GridSystem.OSGB, 410250, 169960, 10),
        ("su 1025 6996", GridSystem.OSGB, 410250, 169960, 10),
        ("  SU1025 6996 ", GridSystem.OSGB, 410250, 169960, 10),
        ("SU 102 699", GridSystem.OSGB, 410200, 169900, 100),
        ("SU 10250 69960", GridSystem.OSGB, 410250, 169960, 1),
        ("SU16", GridSystem.OSGB, 410000, 160000, 10_000),
        ("SU 1 6", GridSystem.OSGB, 410000, 160000, 10_000),
        ("SU1069", GridSystem.OSGB, 410000, 169000, 1000),
        ("NN 1667 7128", GridSystem.OSGB, 216670, 771280, 10),
        ("TQ 30 80", GridSystem.OSGB, 530000, 180000, 1000),
        ("HU 4741", GridSystem.OSGB, 447000, 1141000, 1000),
        ("J 338 740", GridSystem.IRISH, 333800, 374000, 100),
        ("J338740", GridSystem.IRISH, 333800, 374000, 100),
        ("j 3380 7400", GridSystem.IRISH, 333800, 374000, 10),
        ("C 43 16", GridSystem.IRISH, 243000, 416000, 1000),
        ("A 00 00", GridSystem.IRISH, 0, 400000, 1000),
        ("Z 99 99", GridSystem.IRISH, 499000, 99000, 1000),
    ],
)
def test_parse_gridref(text: str, system: GridSystem, easting: int, northing: int, precision: int) -> None:
    ref = gridref.parse_gridref(text)
    assert (ref.system, ref.easting, ref.northing, ref.precision_m) == (system, easting, northing, precision)


@pytest.mark.parametrize(
    "text",
    [
        "",
        "SU",  # a bare 100 km square is too easily a word
        "SU 123",  # odd number of digits
        "SU 12345 1234",  # uneven halves
        "SU 123456 123456",  # finer than a metre
        "SI 12 34",  # the letter I is never used
        "XX 12 34",  # no such square in Great Britain
        "I 338 740",
        "12 34",
        "Avebury",
        "SU 12 3x",
        "SU-12-34",
    ],
)
def test_parse_gridref_rejects_nonsense(text: str) -> None:
    with pytest.raises(GridRefError):
        gridref.parse_gridref(text)


def test_try_parse_returns_none_instead_of_raising() -> None:
    assert gridref.try_parse_gridref("Avebury") is None
    assert gridref.try_parse_gridref("SU 1025 6996") is not None


@pytest.mark.parametrize("digits", [2, 4, 6, 8, 10])
@pytest.mark.parametrize(
    ("lon", "lat"),
    [(-1.8542, 51.4286), (-5.0036, 56.7969), (-5.9301, 54.5964), (0.5, 52.2), (-7.3, 54.99), (-1.15, 60.155)],
)
def test_round_trip(lon: float, lat: float, digits: int) -> None:
    text = gridref.to_gridref(lon, lat, digits)
    ref = gridref.parse_gridref(text)
    assert ref.digits == digits
    assert ref.format() == text
    assert gridref.parse_gridref(ref.format(compact=True)) == ref
    # The point lies inside the square the reference names.
    _, easting, northing = gridref.to_grid(lon, lat)
    assert ref.easting <= easting < ref.easting + ref.precision_m
    assert ref.northing <= northing < ref.northing + ref.precision_m
    # And the square's centre is no further away than half its diagonal.
    limit = ref.precision_m * math.sqrt(2) / 2 + 0.5
    assert metres_between(ref.centre(), (lon, lat)) <= limit


def test_formatting() -> None:
    assert gridref.to_gridref(-1.826189, 51.178844) == "SU 1224 4219"
    assert gridref.to_gridref(-1.826189, 51.178844, 6) == "SU 122 421"
    assert gridref.to_gridref(-1.826189, 51.178844, 4, compact=True) == "SU1242"
    assert gridref.to_gridref(-1.826189, 51.178844, 10) == "SU 12246 42193"


@pytest.mark.parametrize("digits", [-2, 0, 3, 12])
def test_to_gridref_rejects_bad_digit_counts(digits: int) -> None:
    with pytest.raises(GridRefError):
        gridref.to_gridref(-1.8542, 51.4286, digits)


@pytest.mark.parametrize(
    ("lon", "lat"),
    [(2.3522, 48.8566), (-74.0, 40.7), (0.0, 0.0), (-30.0, 55.0), (float("nan"), 51.0), (-1.8, 91.0)],
)
def test_points_outside_both_grids_raise(lon: float, lat: float) -> None:
    with pytest.raises(GridRefError):
        gridref.to_gridref(lon, lat)


def test_square_1km() -> None:
    square = gridref.square_1km(-1.8542, 51.4286)
    assert square.ref == "SU1069"
    assert square.polygon.contains(Point(-1.8542, 51.4286))
    # A 1 km square is very nearly a square kilometre on the ground.
    area, _ = GEOD.geometry_area_perimeter(square.polygon)
    assert abs(area) == pytest.approx(1_000_000, rel=0.002)
    # Corners run south-west, south-east, north-east, north-west and close.
    coords = list(square.polygon.exterior.coords)
    assert len(coords) == 5
    assert coords[0] == coords[-1]
    assert coords[0][0] < coords[1][0]
    assert coords[1][1] < coords[2][1]


def test_square_1km_in_northern_ireland() -> None:
    square = gridref.square_1km(-5.9301, 54.5964)
    assert square.ref == "J3373"
    assert square.polygon.contains(Point(-5.9301, 54.5964))


def test_centre_of_square() -> None:
    lon, lat = gridref.centre_of_square("SU1069")
    assert gridref.square_1km(lon, lat).ref == "SU1069"
    _, easting, northing = gridref.to_grid(lon, lat)
    assert easting == pytest.approx(410_500, abs=0.01)
    assert northing == pytest.approx(169_500, abs=0.01)
    # The centre is at most 708 m from anywhere in the square.
    assert metres_between((lon, lat), (-1.8542, 51.4286)) < 708


def test_centre_of_square_accepts_any_precision() -> None:
    lon, lat = gridref.centre_of_square("J 338 740")
    _, easting, northing = gridref.to_grid(lon, lat)
    assert easting == pytest.approx(333_850, abs=0.01)
    assert northing == pytest.approx(374_050, abs=0.01)


def test_one_km_reference_of_a_finer_reference() -> None:
    assert gridref.parse_gridref("SU 1025 6996").at_precision(1000).format(compact=True) == "SU1069"
    with pytest.raises(GridRefError):
        gridref.parse_gridref("SU16").at_precision(1000)


# --------------------------------------------------------------------------
# Against PostGIS
# --------------------------------------------------------------------------

SPREAD = [
    (-1.8542, 51.4286),  # Avebury
    (-5.7160, 50.0660),  # Land's End
    (1.7500, 52.4800),  # Lowestoft
    (-3.1883, 55.9533),  # Edinburgh
    (-6.3900, 58.2100),  # Stornoway
    (-1.1500, 60.1550),  # Lerwick
    (-4.0762, 53.0685),  # Snowdon
    (-5.9301, 54.5964),  # Belfast
    (-7.6400, 54.3440),  # Enniskillen
    (-6.2100, 55.2950),  # Rathlin Island
]


@pytest.mark.parametrize(("lon", "lat"), SPREAD)
def test_conversion_agrees_with_postgis(db, lon: float, lat: float) -> None:
    """PostGIS has its own PROJ, so this checks our use of pyproj against a second opinion."""
    from sqlalchemy import text

    system, easting, northing = gridref.to_grid(lon, lat)
    srid = {GridSystem.OSGB: 27700, GridSystem.IRISH: 29903}[system]
    row = db.execute(
        text(
            "SELECT ST_X(p), ST_Y(p) FROM "
            "(SELECT ST_Transform(ST_SetSRID(ST_MakePoint(:lon, :lat), 4326), :srid) AS p) AS q"
        ),
        {"lon": lon, "lat": lat, "srid": srid},
    ).one()
    assert math.hypot(easting - row[0], northing - row[1]) < 2.0

    # And back again: the centre of the 1 m square returns to within a couple of metres.
    back_lon, back_lat = gridref.gridref_at(lon, lat, 10).centre()
    assert metres_between((back_lon, back_lat), (lon, lat)) < 2.0
