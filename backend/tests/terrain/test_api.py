"""The tile, profile, coverage and point endpoints, over a small synthetic mirror."""

from __future__ import annotations

import io
from collections.abc import Iterator
from pathlib import Path

import numpy as np
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from PIL import Image
from pyproj import Transformer
from shapely.geometry import MultiPolygon, box
from sqlalchemy.orm import Session

from fieldclub.models import AdminArea
from fieldclub.models.common import to_db_geometry
from fieldclub.storage import LocalStorage
from fieldclub.terrain.cog import to_cog
from fieldclub.terrain.grid import tile_at
from fieldclub.terrain.mirror import LocalMirrorStore, LocalSourceFetcher, Mirror
from fieldclub.terrain.render import terrarium_decode
from fieldclub.terrain.service import Terrain, get_terrain
from fieldclub.terrain.sources import file_source
from tests.helpers import error_code
from tests.terrain.fakes import catalogue_of, write_source_tile

TO_LONLAT = Transformer.from_crs(27700, 4326, always_xy=True)
# The middle of SU16nw, by Avebury.
INSIDE = TO_LONLAT.transform(412_505, 167_505)


def plane(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    return 150 + 0.02 * (east - 410_000) + 0.5 * np.sin((east - 410_000) / 40.0)


@pytest.fixture(scope="module")
def mirror_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("terrain-api")
    write_source_tile(root / "src", "SU16nw", formula=plane)
    return root


@pytest.fixture
def terrain(mirror_dir: Path, tmp_path: Path) -> Terrain:
    catalogue = catalogue_of((mirror_dir / "src").glob("*.tif"), extra=["SU16ne"])
    mirror = Mirror(
        catalogue,
        LocalMirrorStore(tmp_path / "cogs"),
        [LocalSourceFetcher(mirror_dir / "src")],
        tmp_path / "work",
        convert=lambda src, dst: to_cog(src, dst, overview_count=1),
    )
    national = file_source("national", str(tmp_path / "none.tif"), exists=lambda path: False)
    return Terrain(mirror, national, LocalStorage(tmp_path / "tiles"), national_exists=lambda: False)


@pytest.fixture
def api(app: FastAPI, terrain: Terrain) -> Iterator[TestClient]:
    app.dependency_overrides[get_terrain] = lambda: terrain
    with TestClient(app, base_url="https://testserver", headers={"X-FieldClub-Client": "web"}) as client:
        yield client
    app.dependency_overrides.clear()


# --------------------------------------------------------------------------
# Tiles
# --------------------------------------------------------------------------


def test_a_lidar_tile_is_a_512_pixel_png_with_immutable_caching(api: TestClient) -> None:
    x, y = tile_at(*INSIDE, 15)
    response = api.get(f"/tiles/lidar/composite/15/{x}/{y}.png")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    assert response.headers["etag"].startswith('"')
    image = Image.open(io.BytesIO(response.content))
    assert image.size == (512, 512)


def test_an_unchanged_tile_is_answered_not_modified(api: TestClient) -> None:
    x, y = tile_at(*INSIDE, 15)
    first = api.get(f"/tiles/lidar/slope/15/{x}/{y}.png")
    again = api.get(f"/tiles/lidar/slope/15/{x}/{y}.png", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == first.headers["etag"]


def test_every_served_style_renders(api: TestClient) -> None:
    x, y = tile_at(*INSIDE, 16)
    for style in ("composite", "local_relief", "sky_view", "multi_shade", "slope"):
        assert api.get(f"/tiles/lidar/{style}/16/{x}/{y}.png").status_code == 200, style


def test_a_tile_with_no_data_is_transparent_and_fetches_nothing(api: TestClient, terrain: Terrain) -> None:
    # The North Sea, far from any catalogue tile.
    x, y = tile_at(2.5, 54.0, 14)
    response = api.get(f"/tiles/lidar/composite/14/{x}/{y}.png")
    assert response.status_code == 200
    alpha = np.asarray(Image.open(io.BytesIO(response.content)))[..., -1]
    assert alpha.max() == 0
    assert terrain.mirror.store.names() in ([], ["SU16nw"])


@pytest.mark.parametrize(
    ("path", "status", "code"),
    [
        ("/tiles/lidar/rainbow/15/0/0.png", 404, "unknown_style"),
        ("/tiles/lidar/composite/6/0/0.png", 404, "zoom_out_of_range"),
        ("/tiles/lidar/composite/17/0/0.png", 404, "zoom_out_of_range"),
        ("/tiles/lidar/composite/15/32768/0.png", 404, "tile_not_found"),
        ("/tiles/lidar/composite/15/-1/0.png", 404, "tile_not_found"),
        ("/tiles/dem/15/0/32768.png", 404, "tile_not_found"),
        ("/tiles/lidar/composite/15/a/0.png", 422, "validation_error"),
    ],
)
def test_bad_tile_addresses_are_refused(api: TestClient, path: str, status: int, code: str) -> None:
    response = api.get(path)
    assert response.status_code == status
    assert error_code(response) == code


def test_dem_tiles_are_terrarium_with_opaque_pixels(api: TestClient) -> None:
    x, y = tile_at(*INSIDE, 15)
    response = api.get(f"/tiles/dem/15/{x}/{y}.png")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=31536000, immutable"
    image = Image.open(io.BytesIO(response.content))
    assert image.mode == "RGB"
    heights = terrarium_decode(np.asarray(image))
    assert 140 < np.median(heights) < 260


def test_low_zooms_without_the_national_composite_read_the_mirror_uncached(
    api: TestClient, terrain: Terrain, tmp_path: Path
) -> None:
    terrain.mirror.ensure("SU16nw")
    x, y = tile_at(*INSIDE, 12)
    response = api.get(f"/tiles/lidar/composite/12/{x}/{y}.png")
    assert response.status_code == 200
    alpha = np.asarray(Image.open(io.BytesIO(response.content)).convert("LA"))[..., -1]
    assert alpha.max() == 255
    assert not list((tmp_path / "tiles").rglob("*.png"))


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


def test_a_profile_samples_heights_along_a_line(api: TestClient) -> None:
    start = TO_LONLAT.transform(411_000, 167_000)
    end = TO_LONLAT.transform(411_400, 167_300)
    response = api.post(
        "/api/v1/terrain/profile",
        json={"line": {"type": "LineString", "coordinates": [list(start), list(end)]}, "samples": 51},
    )
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["length_m"] == pytest.approx(500, abs=0.5)
    samples = body["samples"]
    assert len(samples) == 51
    assert samples[0]["distance_m"] == 0
    assert samples[-1]["distance_m"] == pytest.approx(500, abs=0.5)
    eastings = np.linspace(411_000, 411_400, 51)
    expected = plane(eastings, np.zeros(51))
    got = np.array([sample["elevation"] for sample in samples])
    # The source tile is at 4 m, so bilinear can't follow the 40 m ripple exactly.
    assert np.abs(got - expected).max() < 0.05
    assert samples[10]["lon"] == pytest.approx(TO_LONLAT.transform(411_080, 167_060)[0], abs=1e-6)


def test_a_profile_into_a_tile_that_cannot_be_fetched_is_unavailable(api: TestClient) -> None:
    # SU16ne is in the catalogue, but nothing here can supply it.
    start = TO_LONLAT.transform(414_900, 167_000)
    end = TO_LONLAT.transform(415_100, 167_000)
    response = api.post(
        "/api/v1/terrain/profile",
        json={"line": {"type": "LineString", "coordinates": [list(start), list(end)]}, "samples": 5},
    )
    assert response.status_code == 503
    assert error_code(response) == "elevation_unavailable"


def test_a_profile_off_the_data_has_null_heights(api: TestClient) -> None:
    # South of SU16nw, where the catalogue lists nothing.
    start = TO_LONLAT.transform(411_000, 164_990)
    end = TO_LONLAT.transform(411_000, 165_100)
    response = api.post(
        "/api/v1/terrain/profile",
        json={"line": {"type": "LineString", "coordinates": [list(start), list(end)]}, "samples": 12},
    )
    assert response.status_code == 200
    heights = [sample["elevation"] for sample in response.json()["samples"]]
    assert heights[0] is None
    assert heights[-1] is not None


@pytest.mark.parametrize(
    ("body", "code"),
    [
        ({"line": {"type": "LineString", "coordinates": [[-1.85, 51.43]]}}, "validation_error"),
        ({"line": {"type": "Point", "coordinates": [[-1.85, 51.43], [-1.84, 51.43]]}}, "validation_error"),
        (
            {"line": {"type": "LineString", "coordinates": [[-1.85, 51.43], [-1.84, 51.43]]}, "samples": 1},
            "validation_error",
        ),
        (
            {
                "line": {"type": "LineString", "coordinates": [[-1.85, 51.43], [-1.84, 51.43]]},
                "samples": 5000,
            },
            "validation_error",
        ),
        (
            {"line": {"type": "LineString", "coordinates": [[-1.85, 51.43], [-1.70, 51.43]]}},
            "invalid_profile",
        ),
        (
            {"line": {"type": "LineString", "coordinates": [[-1.85, 51.43], [-1.85, 51.43]]}},
            "invalid_profile",
        ),
        ({"line": {"type": "LineString", "coordinates": [[2.35, 48.85], [2.36, 48.85]]}}, "invalid_profile"),
        (
            {"line": {"type": "LineString", "coordinates": [[-6.26, 53.35], [-6.25, 53.35]]}},
            "invalid_profile",
        ),
    ],
)
def test_profiles_are_limited(api: TestClient, body: dict, code: str) -> None:
    response = api.post("/api/v1/terrain/profile", json=body)
    assert response.status_code in (400, 422)
    assert error_code(response) == code


# --------------------------------------------------------------------------
# Coverage
# --------------------------------------------------------------------------


def test_coverage_lists_the_catalogue_tiles_as_geojson(api: TestClient) -> None:
    response = api.get("/api/v1/terrain/coverage")
    assert response.status_code == 200
    body = response.json()
    assert body["type"] == "FeatureCollection"
    assert {feature["id"] for feature in body["features"]} == {"SU16nw", "SU16ne"}
    feature = body["features"][0]
    assert feature["geometry"]["type"] == "Polygon"
    ring = feature["geometry"]["coordinates"][0]
    assert ring[0] == ring[-1]
    assert len(ring) == 5
    assert feature["properties"]["resolution_m"] == 1


def test_coverage_can_be_limited_to_a_box(api: TestClient) -> None:
    west, south = TO_LONLAT.transform(410_100, 165_100)
    east, north = TO_LONLAT.transform(410_200, 165_200)
    response = api.get("/api/v1/terrain/coverage", params={"bbox": f"{west},{south},{east},{north}"})
    assert [feature["id"] for feature in response.json()["features"]] == ["SU16nw"]
    assert error_code(api.get("/api/v1/terrain/coverage", params={"bbox": "1,2,3"})) == "invalid_bbox"


def test_the_whole_england_coverage_is_drawable() -> None:
    from fieldclub.terrain.catalogue import england_catalogue
    from fieldclub.terrain.coverage import coverage

    body = coverage(england_catalogue())
    assert len(body["features"]) == 5_877
    lons = [point[0] for feature in body["features"] for point in feature["geometry"]["coordinates"][0]]
    assert -6.5 < min(lons) < max(lons) < 2.0


# --------------------------------------------------------------------------
# Point
# --------------------------------------------------------------------------


@pytest.fixture
def wiltshire(db: Session) -> None:
    shape = to_db_geometry(MultiPolygon([box(-2.4, 50.9, -1.4, 51.8)]))
    db.add(
        AdminArea(
            kind="nation",
            code="england",
            name="England",
            geom=to_db_geometry(MultiPolygon([box(-6, 49.8, 2, 56)])),
        )
    )
    db.add(AdminArea(kind="county", code="E06000054", name="Wiltshire", geom=shape))
    db.commit()


@pytest.mark.usefixtures("wiltshire")
def test_a_point_has_its_grid_reference_place_and_height(api: TestClient, terrain: Terrain) -> None:
    terrain.mirror.ensure("SU16nw")
    lon, lat = INSIDE
    response = api.get("/api/v1/geo/point", params={"lon": lon, "lat": lat})
    assert response.status_code == 200
    body = response.json()
    assert body["grid_ref"] == "SU 1250 6750"
    assert body["nation"] == "england"
    assert body["county"] == "Wiltshire"
    assert body["elevation"] == pytest.approx(float(plane(np.array(412_505.0), np.array(0.0))), abs=0.05)


@pytest.mark.usefixtures("wiltshire")
def test_a_point_never_fetches_and_has_no_height_where_nothing_is_mirrored(
    api: TestClient, terrain: Terrain
) -> None:
    lon, lat = INSIDE
    body = api.get("/api/v1/geo/point", params={"lon": lon, "lat": lat}).json()
    assert body["elevation"] is None
    assert not terrain.mirror.has("SU16nw")


def test_a_point_off_the_grids_has_nulls(api: TestClient) -> None:
    body = api.get("/api/v1/geo/point", params={"lon": 2.35, "lat": 48.85}).json()
    assert body == {
        "lon": 2.35,
        "lat": 48.85,
        "grid_ref": None,
        "nation": None,
        "county": None,
        "elevation": None,
    }
    assert error_code(api.get("/api/v1/geo/point", params={"lon": 200, "lat": 0})) == "validation_error"
