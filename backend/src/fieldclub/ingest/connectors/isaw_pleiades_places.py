"""Ancient places in Britain and Ireland, from the Pleiades gazetteer's GIS CSV bundle.

Work-list key `isaw-pleiades-places`. The bundle is a 36 MB zip of CSV files
rebuilt several times a week. It is fetched at most once a day and kept under
`var/ingest/`, and the three files used are unpacked beside it: `places.csv`
(42,000 places across the ancient world, a third with no position),
`places_place_types.csv` and `place_types.csv`, which give each place's types
in words (`fort`, `province`) for `monument_types`.

Only places with a representative point inside Britain and Ireland are stored,
about 1,600. A place with `location_precision` of `rough` has a point that may
be no more than the middle of a large bounding box, so its `precision_m` is
half the box's longer side, and it is left out altogether when that box
reaches beyond Britain and Ireland, since its point then says little about
the isles. The id is Pleiades's own number, which is permanent. The file gives
no time periods, so none are set.
"""

from __future__ import annotations

import csv
import logging
import math
import zipfile
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import ClassVar

import shapely
from shapely.errors import ShapelyError

from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import Feature, Polite
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.adapters.files import read_csv
from fieldclub.ingest.base import (
    BRITISH_ISLES,
    BBox,
    Connector,
    RecordIn,
    SourceInfo,
    bbox_in_bbox,
    point_in_bbox,
)
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

BUNDLE_URL = "https://atlantides.org/downloads/pleiades/gis/pleiades_gis_data.zip"
PLACE_URL = "https://pleiades.stoa.org/places/{id}"
DELAY_S = 1.0
MEMBERS = ("places.csv", "places_place_types.csv", "place_types.csv")
PLACE_COLUMNS = (
    "id",
    "title",
    "description",
    "details",
    "provenance",
    "uri",
    "created",
    "representative_latitude",
    "representative_longitude",
    "bounding_box_wkt",
    "location_precision",
)
MAX_SUMMARY = 1500
METRES_PER_DEGREE = 111_000.0


@register
class PleiadesPlaces(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="isaw-pleiades-places",
        name="Pleiades gazetteer (GIS CSV bundle)",
        publisher="ISAW (NYU) / Ancient World Mapping Center",
        licence="CC BY 3.0",
        licence_url="http://creativecommons.org/licenses/by/3.0/",
        attribution=(
            "Copyright © The Contributors. Sharing and remixing permitted under terms of the "
            "Creative Commons Attribution 3.0 License (cc-by)."
        ),
        # The work-list says "place", which is not a record category. Its sites and settlements are monuments.
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://pleiades.stoa.org/",
        coverage="Ancient world; only Britain and Ireland are stored",
    )
    max_age: ClassVar[timedelta] = timedelta(hours=20)

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        directory = cache_dir(self.settings, self.source.key)
        fetched = download(
            BUNDLE_URL,
            directory / "pleiades_gis_data.zip",
            client=self.http,
            polite=Polite(delay_s=DELAY_S),
            max_age=self.max_age,
        )
        self.obtained_at = fetched.fetched_at
        files = unpack(fetched.path, directory / "gis")
        types = place_types(files["places_place_types.csv"], files["place_types.csv"])
        seen: set[str] = set()
        for feature in read_csv(
            files["places.csv"], x="representative_longitude", y="representative_latitude"
        ):
            record = to_record(feature, types)
            if record is None:
                continue
            if record.external_id in seen:
                raise UpstreamFormatError(f"Pleiades place {record.external_id} appears twice.")
            seen.add(record.external_id)
            yield record


def unpack(bundle: Path, into: Path) -> dict[str, Path]:
    """The CSV files the connector reads, unpacked beside the bundle and again when it is newer."""
    into.mkdir(parents=True, exist_ok=True)
    try:
        with zipfile.ZipFile(bundle) as archive:
            names = {Path(name).name: name for name in archive.namelist()}
            missing = [member for member in MEMBERS if member not in names]
            if missing:
                raise UpstreamFormatError(f"The Pleiades bundle changed shape: it has no {missing}.")
            files: dict[str, Path] = {}
            for member in MEMBERS:
                target = into / member
                if not target.is_file() or target.stat().st_mtime < bundle.stat().st_mtime:
                    part = target.with_name(target.name + ".part")
                    part.write_bytes(archive.read(names[member]))
                    part.replace(target)
                files[member] = target
    except zipfile.BadZipFile:
        raise UpstreamFormatError("The Pleiades bundle is not a zip file.") from None
    return files


def place_types(links: Path, vocabulary: Path) -> dict[str, list[str]]:
    """Each place's type terms, such as `fort`, from the join file and the vocabulary."""
    with vocabulary.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if rows and not {"key", "term"} <= rows[0].keys():
        raise UpstreamFormatError(f"place_types.csv changed shape: {list(rows[0])}.")
    terms = {row["key"]: row["term"].strip() for row in rows if row["term"].strip()}
    found: dict[str, list[str]] = {}
    with links.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        if reader.fieldnames is None or not {"place_id", "place_type"} <= set(reader.fieldnames):
            raise UpstreamFormatError(f"places_place_types.csv changed shape: {reader.fieldnames}.")
        for row in reader:
            term = terms.get(row["place_type"])
            if term and term not in found.setdefault(row["place_id"], []):
                found[row["place_id"]].append(term)
    return found


def _rough_precision_m(wkt: str | None) -> float | None:
    """Half a bounding box's longer side in metres. None when it can't be read or reaches past the isles."""
    if not wkt:
        return None
    try:
        west, south, east, north = shapely.from_wkt(wkt).bounds
    except (ShapelyError, TypeError, ValueError):
        return None
    if not bbox_in_bbox(BRITISH_ISLES, (west, south, east, north)):
        return None
    width = (east - west) * METRES_PER_DEGREE * math.cos(math.radians((south + north) / 2))
    height = (north - south) * METRES_PER_DEGREE
    return max(width, height) / 2


def to_record(feature: Feature, types: dict[str, list[str]]) -> RecordIn | None:
    """One place as a record, or None when it has no point, or one outside the isles."""
    p = feature.properties
    missing = [name for name in PLACE_COLUMNS if name not in p]
    if missing:
        raise UpstreamFormatError(f"places.csv changed shape: missing {missing}.")
    geometry = feature.geometry
    if geometry is None:
        return None
    x, y = geometry.bounds[0], geometry.bounds[1]
    if not point_in_bbox(BRITISH_ISLES, x, y):
        return None
    place_id = (p["id"] or "").strip()
    if not place_id:
        raise UpstreamFormatError("A Pleiades place has no id.")
    precision: float | None = None
    if p["location_precision"] == "rough":
        precision = _rough_precision_m(p["bounding_box_wkt"])
        if precision is None:
            return None
        precision = max(precision, 1.0)
    description = (p["description"] or "").strip()
    if len(description) > MAX_SUMMARY:
        description = description[: MAX_SUMMARY - 1].rstrip() + "…"
    terms = types.get(place_id, [])
    return RecordIn(
        external_id=place_id,
        name=(p["title"] or "").strip() or f"Pleiades place {place_id}",
        geom=geometry,
        summary=description or None,
        record_type=", ".join(terms) or None,
        monument_types=terms,
        precision_m=precision,
        url=PLACE_URL.format(id=place_id),
        raw={name: p[name] for name in PLACE_COLUMNS},
    )
