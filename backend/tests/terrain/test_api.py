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
from pydantic import SecretStr
from sqlalchemy.orm import Session

from fieldclub.config import DefraSftpSettings
from fieldclub.layers import LIDAR_STYLES, build_layers, default_tile_version
from fieldclub.schemas.meta import RasterView
from fieldclub.terrain import sftp
from fieldclub.terrain.grid import tile_at
from fieldclub.terrain.mirror import SftpFetcher
from fieldclub.terrain.prefetch import Prefetcher
from fieldclub.terrain.render import terrarium_decode
from fieldclub.terrain.service import Terrain, get_terrain
from tests.helpers import admin_area, error_code
from tests.terrain.fakes import TO_LONLAT, decode_png, local_mirror, local_terrain, write_source_tile

# The middle of SU16nw, by Avebury.
INSIDE = TO_LONLAT.transform(412_505, 167_505)
# The styles `/meta` offers.
SERVED = [style_id for style_id, _, _ in LIDAR_STYLES]


def prefetch_of(terrain: Terrain) -> Prefetcher:
    assert terrain.prefetch is not None, "the API's terrain adds tiles in the background"
    return terrain.prefetch


def plane(east: np.ndarray, north: np.ndarray) -> np.ndarray:
    return 150 + 0.02 * (east - 410_000) + 0.5 * np.sin((east - 410_000) / 40.0)


@pytest.fixture(scope="module")
def mirror_dir(tmp_path_factory: pytest.TempPathFactory) -> Path:
    root = tmp_path_factory.mktemp("terrain-api")
    write_source_tile(root / "src", "SU16nw", formula=plane)
    return root


@pytest.fixture
def terrain(mirror_dir: Path, tmp_path: Path) -> Iterator[Terrain]:
    """The API's terrain: a tile the mirror lacks is added in the background, never waited for."""
    mirror = local_mirror(tmp_path, sources=mirror_dir / "src", extra=["SU16ne"])
    prefetch = Prefetcher(mirror, 1)
    yield local_terrain(mirror, tmp_path / "tiles", prefetch=prefetch)
    prefetch.wait(timeout=60)
    prefetch.close()


@pytest.fixture
def mirrored(terrain: Terrain) -> Terrain:
    """The same, with SU16nw already in the mirror."""
    terrain.mirror.ensure("SU16nw")
    return terrain


@pytest.fixture
def api(app: FastAPI, client: TestClient, terrain: Terrain) -> TestClient:
    # `client` wraps this test's own `app`, so the override ends with the test.
    app.dependency_overrides[get_terrain] = lambda: terrain
    return client


# --------------------------------------------------------------------------
# Tiles
# --------------------------------------------------------------------------


IMMUTABLE = "public, max-age=31536000, immutable"


@pytest.mark.usefixtures("mirrored")
def test_a_lidar_tile_is_a_512_pixel_png_with_immutable_caching(api: TestClient, terrain: Terrain) -> None:
    x, y = tile_at(*INSIDE, 15)
    version = terrain.renderer.version("composite")
    response = api.get(f"/tiles/lidar/composite/15/{x}/{y}.png?v={version}")
    assert response.status_code == 200
    assert response.headers["content-type"] == "image/png"
    assert response.headers["cache-control"] == IMMUTABLE
    assert response.headers["etag"].startswith('"')
    image = Image.open(io.BytesIO(response.content))
    assert image.size == (512, 512)


@pytest.mark.usefixtures("mirrored")
def test_the_meta_tile_urls_carry_the_versions_the_served_tiles_have(
    api: TestClient, terrain: Terrain
) -> None:
    layers = api.get("/api/v1/meta").json()["layers"]
    views = {view["id"]: view for view in layers["views"]}
    renderer = terrain.renderer
    for style in SERVED:
        tiles = views[style]["tiles"]
        assert tiles == [f"/tiles/lidar/{style}/{{z}}/{{x}}/{{y}}.png?v={renderer.version(style)}"]
    assert layers["dem"]["tiles"] == [f"/tiles/dem/{{z}}/{{x}}/{{y}}.png?v={renderer.version('dem')}"]
    x, y = tile_at(*INSIDE, 15)
    assert renderer.lidar_png("composite", 15, x, y).version == renderer.version("composite")


def test_without_a_terrain_service_the_layers_carry_the_unbuilt_token() -> None:
    layers = build_layers()
    view = next(view for view in layers.views if isinstance(view, RasterView) and view.id == "composite")
    assert view.tiles == [
        f"/tiles/lidar/composite/{{z}}/{{x}}/{{y}}.png?v={default_tile_version('composite')}"
    ]


@pytest.mark.usefixtures("mirrored")
@pytest.mark.parametrize("query", ["", "?v=old"])
def test_a_tile_without_the_current_version_is_cached_for_an_hour(api: TestClient, query: str) -> None:
    x, y = tile_at(*INSIDE, 15)
    response = api.get(f"/tiles/lidar/composite/15/{x}/{y}.png{query}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == "public, max-age=3600"


@pytest.mark.usefixtures("mirrored")
def test_an_unchanged_tile_is_answered_not_modified(api: TestClient) -> None:
    x, y = tile_at(*INSIDE, 15)
    first = api.get(f"/tiles/lidar/slope/15/{x}/{y}.png")
    again = api.get(f"/tiles/lidar/slope/15/{x}/{y}.png", headers={"If-None-Match": first.headers["etag"]})
    assert again.status_code == 304
    assert again.content == b""
    assert again.headers["etag"] == first.headers["etag"]


@pytest.mark.usefixtures("mirrored")
def test_every_served_style_renders(api: TestClient) -> None:
    x, y = tile_at(*INSIDE, 16)
    for style in SERVED:
        assert api.get(f"/tiles/lidar/{style}/16/{x}/{y}.png").status_code == 200, style


def test_a_tile_with_no_data_is_transparent_and_fetches_nothing(api: TestClient, terrain: Terrain) -> None:
    # The North Sea, far from any catalogue tile.
    x, y = tile_at(2.5, 54.0, 14)
    response = api.get(f"/tiles/lidar/composite/14/{x}/{y}.png")
    assert response.status_code == 200
    alpha = decode_png(response.content)[..., -1]
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


@pytest.mark.usefixtures("mirrored")
def test_dem_tiles_are_terrarium_with_opaque_pixels(api: TestClient, terrain: Terrain) -> None:
    x, y = tile_at(*INSIDE, 15)
    response = api.get(f"/tiles/dem/15/{x}/{y}.png?v={terrain.renderer.version('dem')}")
    assert response.status_code == 200
    assert response.headers["cache-control"] == IMMUTABLE
    image = Image.open(io.BytesIO(response.content))
    assert image.mode == "RGB"
    heights = terrarium_decode(np.asarray(image))
    assert 140 < np.median(heights) < 260


def test_low_zooms_before_any_overview_build_read_the_mirror_uncached(
    api: TestClient, terrain: Terrain, tmp_path: Path
) -> None:
    x, y = tile_at(*INSIDE, 12)
    version = terrain.renderer.version("composite")
    path = f"/tiles/lidar/composite/12/{x}/{y}.png?v={version}"
    empty = api.get(path)
    assert empty.headers["cache-control"] == "no-cache"
    terrain.mirror.ensure("SU16nw")
    response = api.get(path, headers={"If-None-Match": empty.headers["etag"]})
    # The same URL draws differently as the mirror fills, so it is never immutable.
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-cache"
    assert response.headers["etag"] != empty.headers["etag"]
    alpha = np.asarray(Image.open(io.BytesIO(response.content)).convert("LA"))[..., -1]
    assert alpha.max() == 255
    assert not list((tmp_path / "tiles").rglob("*.png"))
    dem = api.get(f"/tiles/dem/12/{x}/{y}.png?v={terrain.renderer.version('dem')}")
    assert dem.headers["cache-control"] == "no-cache"


def test_a_tile_on_the_far_side_of_the_world_is_transparent_and_fetches_nothing(
    api: TestClient, terrain: Terrain
) -> None:
    x, y = tile_at(179.9, 0.0, 7)
    response = api.get(f"/tiles/lidar/composite/7/{x}/{y}.png")
    assert response.status_code == 200
    assert decode_png(response.content)[..., -1].max() == 0
    assert terrain.mirror.store.names() == []


# --------------------------------------------------------------------------
# Profile
# --------------------------------------------------------------------------


@pytest.mark.usefixtures("mirrored")
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


@pytest.mark.usefixtures("mirrored")
def test_a_profile_reports_the_level_it_really_read(api: TestClient) -> None:
    start = TO_LONLAT.transform(410_500, 167_500)
    end = TO_LONLAT.transform(414_500, 167_500)
    line = {"type": "LineString", "coordinates": [list(start), list(end)]}
    # 1 km between samples reads the mirror's coarsest copy, not its 8 m one.
    sparse = api.post("/api/v1/terrain/profile", json={"line": line, "samples": 5}).json()
    assert sparse["resolution_m"] == 1000
    # 80 m between samples reads the 40 m copy.
    middling = api.post("/api/v1/terrain/profile", json={"line": line, "samples": 51}).json()
    assert middling["resolution_m"] == 40
    # The source tiles here are 4 m, so a close spacing can read no finer than that.
    close = api.post("/api/v1/terrain/profile", json={"line": line, "samples": 1000}).json()
    assert close["resolution_m"] == 4


@pytest.mark.usefixtures("mirrored")
def test_a_profile_into_a_tile_that_cannot_be_fetched_is_prepared_then_unavailable(
    api: TestClient, terrain: Terrain
) -> None:
    # SU16ne is in the catalogue, but nothing here can supply it.
    start = TO_LONLAT.transform(414_900, 167_000)
    end = TO_LONLAT.transform(415_100, 167_000)
    line = {"line": {"type": "LineString", "coordinates": [list(start), list(end)]}, "samples": 5}
    first = api.post("/api/v1/terrain/profile", json=line)
    assert first.status_code == 503
    assert error_code(first) == "elevation_preparing"
    assert first.json()["error"]["details"] == {"tiles": ["SU16ne"]}
    assert prefetch_of(terrain).pending() <= {"SU16ne"}
    prefetch_of(terrain).wait(timeout=60)
    # The background attempt failed, so asking again says so rather than "being prepared".
    again = api.post("/api/v1/terrain/profile", json=line)
    assert again.status_code == 503
    assert error_code(again) == "elevation_unavailable"


@pytest.mark.usefixtures("mirrored")
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


@pytest.mark.parametrize(
    "bbox", ["1,2,3", "a,b,c,d", "-1.85,51.4,-1.85,51.5", "-1.8,51.4,-1.9,51.5", "0,0,0,0"]
)
def test_coverage_refuses_a_box_with_no_area(api: TestClient, bbox: str) -> None:
    response = api.get("/api/v1/terrain/coverage", params={"bbox": bbox})
    assert response.status_code == 400
    assert error_code(response) == "invalid_bbox"


def test_coverage_carries_the_years_each_tile_was_flown(api: TestClient) -> None:
    features = {feature["id"]: feature for feature in api.get("/api/v1/terrain/coverage").json()["features"]}
    # Avebury was flown from December 2018 to January 2019.
    assert features["SU16nw"]["properties"]["years"] == [2018, 2019]
    assert features["SU16nw"]["properties"]["capture"] == "2022 composite"


def test_coverage_has_an_etag_from_its_edition_and_a_minute_of_caching(api: TestClient) -> None:
    first = api.get("/api/v1/terrain/coverage")
    assert first.headers["cache-control"] == "public, max-age=60"
    etag = first.headers["etag"]
    assert etag.startswith('"')
    again = api.get("/api/v1/terrain/coverage", headers={"If-None-Match": etag})
    assert again.status_code == 304
    assert again.content == b""
    boxed = api.get("/api/v1/terrain/coverage", params={"bbox": "-1.9,51.4,-1.8,51.5"})
    assert boxed.headers["etag"] == etag


def test_the_coverage_edition_changes_with_the_capture_years(monkeypatch: pytest.MonkeyPatch) -> None:
    from fieldclub.terrain import coverage as coverage_module
    from fieldclub.terrain.catalogue import england_catalogue

    before = coverage_module.coverage_edition(england_catalogue())
    monkeypatch.setattr(coverage_module, "years_edition", lambda: "different")
    assert coverage_module.coverage_edition(england_catalogue()) != before


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
    db.add(admin_area("nation", "england", "England", (-6, 49.8, 2, 56)))
    db.add(admin_area("county", "E06000054", "Wiltshire", (-2.4, 50.9, -1.4, 51.8)))
    db.commit()


@pytest.mark.usefixtures("wiltshire", "mirrored")
def test_a_point_has_its_grid_reference_place_and_height(api: TestClient) -> None:
    lon, lat = INSIDE
    response = api.get("/api/v1/geo/point", params={"lon": lon, "lat": lat})
    assert response.status_code == 200
    body = response.json()
    assert body["grid_ref"] == "SU 1250 6750"
    assert body["nation"] == "england"
    assert body["county"] == "Wiltshire"
    assert body["elevation"] == pytest.approx(float(plane(np.array(412_505.0), np.array(0.0))), abs=0.05)
    assert body["elevation_status"] == "ready"


@pytest.mark.usefixtures("wiltshire")
def test_a_point_never_fetches_and_has_no_height_where_nothing_is_mirrored(
    api: TestClient, terrain: Terrain
) -> None:
    lon, lat = INSIDE
    body = api.get("/api/v1/geo/point", params={"lon": lon, "lat": lat}).json()
    assert body["elevation"] is None
    # The 1 m data exists there and isn't in the mirror yet, and the read didn't start fetching it.
    assert body["elevation_status"] == "preparing"
    assert prefetch_of(terrain).pending() == frozenset()
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
        "elevation_status": "none",
        "sources": [],
        "place": None,
    }
    assert error_code(api.get("/api/v1/geo/point", params={"lon": 200, "lat": 0})) == "validation_error"


def test_a_refused_bulk_supply_never_puts_its_address_in_the_log(
    app: FastAPI, client: TestClient, mirror_dir: Path, tmp_path: Path, caplog: pytest.LogCaptureFixture
) -> None:
    # The API logs a 5xx error with its traceback, chained exceptions included.
    known_hosts = tmp_path / "known_hosts"
    known_hosts.write_text("")
    settings = DefraSftpSettings(
        defra_sftp_host="127.0.0.1",
        defra_sftp_port=1,
        defra_sftp_user="someone-secret",
        defra_sftp_password=SecretStr("not-a-real-password"),
        defra_sftp_known_hosts=known_hosts,
    )
    fetcher = SftpFetcher(lambda: sftp.defra_connector(settings), max_failures=2, sleep=lambda seconds: None)
    mirror = local_mirror(tmp_path, sources=mirror_dir / "src", extra=["SU16ne"], fetchers=[fetcher])
    prefetch = Prefetcher(mirror, 1)
    terrain = local_terrain(mirror, tmp_path / "tiles", prefetch=prefetch)
    app.dependency_overrides[get_terrain] = lambda: terrain
    start = TO_LONLAT.transform(414_900, 167_000)
    end = TO_LONLAT.transform(415_100, 167_000)
    line = {"line": {"type": "LineString", "coordinates": [list(start), list(end)]}, "samples": 5}
    with caplog.at_level("DEBUG"):
        preparing = client.post("/api/v1/terrain/profile", json=line)
        prefetch.wait(timeout=60)
        response = client.post("/api/v1/terrain/profile", json=line)
    prefetch.close()
    assert error_code(preparing) == "elevation_preparing"
    assert response.status_code == 503
    assert error_code(response) == "elevation_fetch_failed"
    assert "Traceback" in caplog.text
    for secret in ("127.0.0.1", "port 1", "someone-secret", "not-a-real-password", "composite/2022"):
        assert secret not in caplog.text, secret
        assert secret not in response.text, secret
