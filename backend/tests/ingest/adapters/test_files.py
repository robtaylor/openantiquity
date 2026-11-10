from __future__ import annotations

import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pyogrio.raw
import pytest
from shapely.geometry import Point

from fieldclub.ingest.adapters.common import UpstreamFormatError
from fieldclub.ingest.adapters.files import read_csv, read_ndjson, read_vector, vector_info
from tests.ingest.adapters.support import FIXTURES, xy

GPKG = FIXTURES / "scheduled_monuments.gpkg"
SILBURY = Point(-1.8574, 51.4156)


def test_reads_every_feature_of_a_geopackage_in_wgs84() -> None:
    features = list(read_vector(GPKG))
    assert len(features) == 8
    silbury = next(feature for feature in features if feature.properties["ListEntry"] == 1008445)
    assert silbury.properties["Name"].startswith("Silbury Hill")
    assert silbury.geometry is not None
    assert silbury.geometry.contains(SILBURY)
    assert type(silbury.id) is int


def test_dates_come_back_in_utc_and_missing_ones_as_none() -> None:
    by_entry = {feature.properties["ListEntry"]: feature.properties for feature in read_vector(GPKG)}
    # Written as `1925-03-10T00:00:00.0Z`, which makes GDAL warn. The warning
    # must not escape, because a warning fails the tests.
    assert by_entry[1008099]["SchedDate"] == datetime(1925, 3, 10, tzinfo=UTC)
    assert by_entry[1001718]["SchedDate"] is None
    assert all(
        type(value) in (int, float, str, datetime, type(None))
        for row in by_entry.values()
        for value in row.values()
    )


def test_reading_in_small_chunks_gives_the_same_features() -> None:
    whole = [(f.id, f.properties["Name"]) for f in read_vector(GPKG)]
    chunked = [(f.id, f.properties["Name"]) for f in read_vector(GPKG, chunk=3)]
    assert chunked == whole


def test_a_bbox_prefilters_by_envelope() -> None:
    near_avebury = list(read_vector(GPKG, bbox=(-1.90, 51.40, -1.82, 51.44)))
    assert {f.properties["ListEntry"] for f in near_avebury} >= {1008445, 1015546, 1010628}
    assert 1010140 not in {f.properties["ListEntry"] for f in near_avebury}  # Stonehenge


def test_where_and_columns_are_passed_through() -> None:
    features = list(read_vector(GPKG, where="ListEntry = 1008445", columns=["Name"]))
    assert len(features) == 1
    assert list(features[0].properties) == ["Name"]


def test_reads_a_zipped_shapefile(tmp_path: Path) -> None:
    shp = tmp_path / "monuments.shp"
    meta, _, geometry, fields = pyogrio.raw.read(GPKG, columns=["ListEntry", "Name"])
    pyogrio.raw.write(
        shp,
        geometry,
        fields,
        fields=meta["fields"],
        crs=meta["crs"],
        geometry_type="MultiPolygon",
        driver="ESRI Shapefile",
        encoding="UTF-8",
    )
    archive = tmp_path / "monuments.zip"
    with zipfile.ZipFile(archive, "w") as bundle:
        for part in tmp_path.glob("monuments.*"):
            if part != archive:
                bundle.write(part, part.name)

    features = list(read_vector(archive))
    assert len(features) == 8
    silbury = next(f for f in features if f.properties["ListEntry"] == 1008445)
    assert silbury.geometry is not None
    assert silbury.geometry.contains(SILBURY)


def test_vector_info_reports_the_layer() -> None:
    info = vector_info(GPKG)
    assert info["crs"] == "EPSG:27700"
    assert info["features"] == 8
    assert "ListEntry" in list(info["fields"])


def test_a_file_that_isnt_a_dataset_is_an_error(tmp_path: Path) -> None:
    junk = tmp_path / "junk.gpkg"
    junk.write_text("<html>Cloudflare challenge</html>")
    with pytest.raises(UpstreamFormatError, match="could not be opened"):
        list(read_vector(junk))


# --------------------------------------------------------------------------
# CSV
# --------------------------------------------------------------------------


def test_reads_csv_with_grid_coordinates() -> None:
    features = list(
        read_csv(FIXTURES / "lincs.csv", x="Easting", y="Northing", crs="EPSG:27700", encoding="cp1252")
    )
    assert len(features) == 6
    first = features[0]
    assert first.properties["MonUID"] == "MLI10028"
    assert first.properties["Name"] == "Moated Site 480m north-east of Wyberton West Hospital"
    # Values stay as text.
    assert first.properties["Easting"] == "532101"
    # Near Boston, Lincolnshire.
    lon, lat = xy(first.geometry)
    assert -0.10 < lon < 0.0
    assert 52.9 < lat < 53.0


def test_csv_rows_without_coordinates_have_no_geometry(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    path.write_bytes("MonUID,Name,Easting,Northing\nMLI1,Caf\xe9 site,,\nMLI2,Mill,abc,1\n".encode("cp1252"))
    features = list(read_csv(path, x="Easting", y="Northing", crs="EPSG:27700", encoding="cp1252"))
    assert [f.geometry for f in features] == [None, None]
    assert features[0].properties["Name"] == "Café site"
    assert features[0].properties["Easting"] is None


def test_csv_without_the_named_columns_is_an_error() -> None:
    with pytest.raises(UpstreamFormatError, match="no column 'X'"):
        list(read_csv(FIXTURES / "lincs.csv", x="X", y="Y", encoding="cp1252"))


# --------------------------------------------------------------------------
# Newline-delimited JSON
# --------------------------------------------------------------------------


def test_reads_geojson_features_line_by_line() -> None:
    features = list(read_ndjson(FIXTURES / "itinere.ndjson"))
    assert len(features) == 3
    assert features[0].id == 9
    assert features[0].properties["segmentCertainty"] == "Conjectured"
    assert features[0].geometry is not None
    assert features[0].geometry.geom_type == "LineString"


def test_a_broken_line_is_named(tmp_path: Path) -> None:
    path = tmp_path / "broken.ndjson"
    path.write_text('{"type": "Feature", "properties": {}, "geometry": null}\n\n{"type": \n')
    with pytest.raises(UpstreamFormatError, match="line 3 is not JSON"):
        list(read_ndjson(path))


def test_plain_objects_are_kept_whole(tmp_path: Path) -> None:
    path = tmp_path / "plain.ndjson"
    path.write_text('{"id": 1, "name": "A"}\n')
    [feature] = read_ndjson(path)
    assert feature.properties == {"id": 1, "name": "A"}
    assert feature.geometry is None
