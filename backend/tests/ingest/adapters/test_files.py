from __future__ import annotations

import json
import zipfile
from datetime import UTC, datetime
from pathlib import Path

import pytest
from shapely.geometry import Point

from fieldclub.ingest.adapters import ogr
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
    meta, _, geometry, fields = ogr.read(GPKG, columns=["ListEntry", "Name"])
    ogr.write(
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


def test_csv_in_the_wrong_encoding_is_named(tmp_path: Path) -> None:
    path = tmp_path / "rows.csv"
    path.write_bytes("MonUID,Name\nMLI1,Mill\nMLI2,Caf\xe9 site\n".encode("cp1252"))
    with pytest.raises(UpstreamFormatError, match=r"rows\.csv isn't utf-8-sig: .*Pass encoding="):
        list(read_csv(path))


def test_csv_without_the_named_columns_is_an_error() -> None:
    with pytest.raises(UpstreamFormatError, match="no column 'X'"):
        list(read_csv(FIXTURES / "lincs.csv", x="X", y="Y", encoding="cp1252"))


def test_reads_a_utf16_csv_inside_a_zip(tmp_path: Path) -> None:
    """As the GB1900 gazetteer comes: one UTF-16 CSV in a zip, read without unpacking it."""
    path = tmp_path / "labels.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("labels/README.txt", "not a csv")
        rows = (
            "pin_id,final_text,longitude,latitude\r\na1,Tumulus,-1.85,51.41\r\na2,Dùn (Site of),-5.1,57.2\r\n"
        )
        archive.writestr("labels/labels.csv", rows.encode("utf-16"))
    features = list(
        read_csv(path, member="labels/labels.csv", encoding="utf-16", x="longitude", y="latitude")
    )
    assert [f.properties["final_text"] for f in features] == ["Tumulus", "D\u00f9n (Site of)"]
    assert xy(features[0].geometry) == (-1.85, 51.41)


def test_headings_can_be_given_for_a_csv_without_them(tmp_path: Path) -> None:
    """As each tile of OS Open Names comes: no heading row, the headings in another file."""
    path = tmp_path / "names.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Data/SU16.csv", "osgb1,Avebury,Village\nosgb2,Silbury Hill,Hill Or Mountain\n")
    features = list(read_csv(path, member="Data/SU16.csv", fieldnames=["ID", "NAME1", "LOCAL_TYPE"]))
    assert [f.properties for f in features] == [
        {"ID": "osgb1", "NAME1": "Avebury", "LOCAL_TYPE": "Village"},
        {"ID": "osgb2", "NAME1": "Silbury Hill", "LOCAL_TYPE": "Hill Or Mountain"},
    ]
    assert all(f.geometry is None for f in features)


def test_a_missing_zip_member_or_a_file_that_isnt_a_zip_is_an_error(tmp_path: Path) -> None:
    path = tmp_path / "names.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("Data/SU16.csv", "a,b\n1,2\n")
    with pytest.raises(UpstreamFormatError, match=r"names\.zip has no Data/SU17\.csv"):
        list(read_csv(path, member="Data/SU17.csv"))
    not_zip = tmp_path / "plain.zip"
    not_zip.write_text("a,b\n1,2\n", encoding="utf-8")
    with pytest.raises(UpstreamFormatError, match=r"plain\.zip is not a zip file"):
        list(read_csv(not_zip, member="Data/SU16.csv"))


def test_a_zip_member_in_the_wrong_encoding_is_named(tmp_path: Path) -> None:
    path = tmp_path / "labels.zip"
    with zipfile.ZipFile(path, "w") as archive:
        archive.writestr("labels.csv", "a,b\n1,Caf\xe9\n".encode("cp1252"))
    with pytest.raises(UpstreamFormatError, match=r"labels\.csv isn't utf-8-sig"):
        list(read_csv(path, member="labels.csv"))


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


def test_a_publisher_s_polygon_with_an_empty_hole_is_refused_before_geos_sees_it(tmp_path: Path) -> None:
    ring = [[-1.8, 51.45], [-1.799, 51.45], [-1.799, 51.451], [-1.8, 51.45]]
    feature = {
        "type": "Feature",
        "properties": {},
        "geometry": {"type": "Polygon", "coordinates": [ring, []]},
    }
    path = tmp_path / "holes.ndjson"
    path.write_text(json.dumps(feature) + "\n")
    with pytest.raises(UpstreamFormatError, match="line 1 isn't valid GeoJSON"):
        list(read_ndjson(path))


def test_plain_objects_are_kept_whole(tmp_path: Path) -> None:
    path = tmp_path / "plain.ndjson"
    path.write_text('{"id": 1, "name": "A"}\n')
    [feature] = read_ndjson(path)
    assert feature.properties == {"id": 1, "name": "A"}
    assert feature.geometry is None


def test_nan_and_infinity_become_none_all_the_way_down(tmp_path: Path) -> None:
    path = tmp_path / "odd.ndjson"
    path.write_text(
        '{"type": "Feature", "properties": {"len": NaN, "parts": [1, Infinity, {"w": -Infinity}]}, '
        '"geometry": null}\n{"a": Infinity, "b": "text"}\n'
    )
    first, second = read_ndjson(path)
    assert first.properties == {"len": None, "parts": [1, None, {"w": None}]}
    assert second.properties == {"a": None, "b": "text"}
    # What the runner does with `raw`.
    json.dumps([first.properties, second.properties], allow_nan=False)


def test_ndjson_in_the_wrong_encoding_is_named(tmp_path: Path) -> None:
    path = tmp_path / "rows.ndjson"
    path.write_bytes('{"name": "Caf\xe9"}\n'.encode("cp1252"))
    with pytest.raises(UpstreamFormatError, match=r"rows\.ndjson isn't utf-8: .*Pass encoding="):
        list(read_ndjson(path))
