"""The gazetteer behind the map's search box, from OS Open Names.

Work-list key `os-open-names`. The download is a 103 MB zip of about 820 CSV
files, one per 10 km square, with no heading row: the headings are in
`Doc/OS_Open_Names_Header.csv`. It has 3,050,396 rows for Great Britain.

The search box is for getting to a place on the map, so the gazetteer keeps
what someone would type to go somewhere in the countryside: every populated
place (cities to hamlets), named landforms (hills, valleys, headlands,
islands), water (rivers, lakes, bays, waterfalls), named woods and other land
cover, and the airfields, airports, harbours and railway stations people
navigate by. That is about 270,000 of the rows. It leaves out:

- 1,743,934 postcodes. They are exact codes, not names, and the search finds
  places by trigram similarity, which would offer a dozen near-identical
  postcodes for a mistyped name. A postcode lookup needs an exact match of
  its own.
- 990,000 named and numbered roads and their sections. "Church Lane" alone
  is thousands of rows, which would bury the villages in the results, and a
  road is rarely what someone exploring earthworks wants to reach.
- schools, hospitals and utilities, which are not places on this map.

Each place gets a `rank`: its kind sets the hundreds, so any town outranks
any village and any village outranks a hill or a wood, and the size of its
bounding box adds up to 99 within the kind, so a big wood comes before a
small one. A Welsh or Gaelic second name is stored as a place of its own at
the same point, so "Caerdydd" finds Cardiff.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import zipfile
from collections.abc import Iterator
from datetime import timedelta
from pathlib import Path
from typing import Any, ClassVar

from shapely.geometry import Point
from sqlalchemy import ColumnElement

from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir, to_wgs84
from fieldclub.ingest.adapters.common import bbox_from_wgs84
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.adapters.files import read_csv
from fieldclub.ingest.base import BBox, SourceInfo
from fieldclub.ingest.reference import register
from fieldclub.ingest.reference.base import Loader
from fieldclub.models import Place
from fieldclub.vocab import Nation, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

DOWNLOAD = "https://api.os.uk/downloads/v1/products/OpenNames/downloads?area=GB&format=CSV&redirect"
HEADER = "Doc/OS_Open_Names_Header.csv"
FIELDS = (
    "ID",
    "NAME1",
    "NAME2",
    "TYPE",
    "LOCAL_TYPE",
    "GEOMETRY_X",
    "GEOMETRY_Y",
    "MBR_XMIN",
    "MBR_YMIN",
    "MBR_XMAX",
    "MBR_YMAX",
    "DISTRICT_BOROUGH",
    "COUNTY_UNITARY",
    "COUNTRY",
)

# The rank's hundreds for each kind of place kept. Settlements first, by
# size, then the named features of the landscape.
RANKS: dict[str, dict[str, int]] = {
    "populatedPlace": {
        "City": 9,
        "Town": 8,
        "Village": 7,
        "Suburban Area": 6,
        "Hamlet": 5,
        "Other Settlement": 4,
    },
    "landform": {
        "Hill Or Mountain Ranges": 3,
        "Group Of Islands": 3,
        "Island": 3,
        "Hill Or Mountain": 2,
        "Valley": 2,
        "Coastal Headland": 2,
        "Cliff Or Slope": 2,
        "Cirque Or Hollow": 2,
        "Other Coastal Landform": 1,
        "Other Landform": 1,
        "Spot Height": 1,
    },
    "hydrography": {
        "Sea": 3,
        "Estuary": 3,
        "Bay": 2,
        "Channel": 2,
        "Tidal Water": 2,
        "Inland Water": 2,
        "Waterfall": 2,
    },
    "landcover": {
        "Woodland Or Forest": 2,
        "Wetland": 1,
        "Beach": 1,
        "Urban Greenspace": 1,
        "Other Landcover": 1,
    },
}
# Of the two types mostly left out, the places people navigate by.
KEPT_ELSEWHERE: dict[str, dict[str, int]] = {
    "transportNetwork": {"Airport": 3, "Airfield": 2, "Harbour": 2, "Railway Station": 2},
    "other": {},
}
NATIONS = {"England": Nation.ENGLAND, "Scotland": Nation.SCOTLAND, "Wales": Nation.WALES}


def kind_rank(type_: str, local_type: str) -> int | None:
    """The rank's hundreds for a kind of entry, or None when the gazetteer leaves it out.

    Raises `UpstreamFormatError` for a kind it doesn't know, so a new kind of
    place is decided on rather than dropped without a word.
    """
    if type_ in RANKS:
        base = RANKS[type_].get(local_type)
        if base is None:
            raise UpstreamFormatError(f"OS Open Names has a new kind of {type_}: {local_type!r}.")
        return base
    if type_ in KEPT_ELSEWHERE:
        return KEPT_ELSEWHERE[type_].get(local_type)
    raise UpstreamFormatError(f"OS Open Names has a new type of entry: {type_!r}.")


def size_rank(mbr: tuple[float, float, float, float]) -> int:
    """0 to 99 from the diagonal of a bounding box in metres: 100 m gives 30, 1 km 45, 10 km 60."""
    xmin, ymin, xmax, ymax = mbr
    return min(99, max(0, round(15 * math.log10(1 + math.hypot(xmax - xmin, ymax - ymin)))))


def _number(value: Any, what: str, place_id: str) -> float:
    try:
        number = float(value)
    except (TypeError, ValueError):
        raise UpstreamFormatError(f"OS Open Names entry {place_id} has {what} {value!r}.") from None
    if not math.isfinite(number):
        raise UpstreamFormatError(f"OS Open Names entry {place_id} has {what} {value!r}.")
    return number


def area_name(value: str | None) -> str | None:
    """A district or county name, with a Welsh area named the same in both languages given once.

    OS Open Names writes Welsh areas as "Welsh - English", so Powys is
    "Powys - Powys". "Sir Ynys Mon - Isle of Anglesey" stays as it is.
    """
    if not value:
        return None
    welsh, dash, english = value.partition(" - ")
    return welsh if dash and welsh == english else value


def headings(path: Path) -> list[str]:
    """The column headings, from the zip's own heading file."""
    try:
        with zipfile.ZipFile(path) as archive, archive.open(HEADER) as raw:
            row = next(csv.reader(io.TextIOWrapper(raw, encoding="utf-8-sig")), [])
    except (KeyError, zipfile.BadZipFile):
        raise UpstreamFormatError(f"{path.name} has no {HEADER}.") from None
    missing = [name for name in FIELDS if name not in row]
    if missing:
        raise UpstreamFormatError(f"OS Open Names changed shape: its headings lack {missing}.")
    return row


def data_files(path: Path) -> list[str]:
    with zipfile.ZipFile(path) as archive:
        names = sorted(
            name for name in archive.namelist() if name.startswith("Data/") and name.lower().endswith(".csv")
        )
    if not names:
        raise UpstreamFormatError(f"{path.name} has no data files.")
    return names


@register
class OpenNames(Loader):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="os-open-names",
        name="OS Open Names",
        publisher="Ordnance Survey",
        licence="Open Government Licence (OS OpenData licence)",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution=(
            "Contains OS data © Crown Copyright and database rights [year]. "
            "Contains Royal Mail data © Royal Mail copyright and database right [year]. "
            "Contains National Statistics data © Crown copyright and database right [year]."
        ),
        category="place",
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://www.ordnancesurvey.co.uk/products/os-open-names",
        coverage="Great Britain",
    )
    model = Place
    # Updated quarterly.
    max_age: ClassVar[timedelta] = timedelta(days=30)

    def owned(self) -> ColumnElement[bool]:
        return Place.source == self.source.key

    def fetch(self, *, bbox: BBox | None = None) -> Iterator[dict[str, Any]]:
        path = cache_dir(self.settings, self.source.key) / "opname_csv_gb.zip"
        fetched = download(DOWNLOAD, path, client=self.http, max_age=self.max_age)
        self.obtained_at = fetched.fetched_at
        fieldnames = headings(path)
        grid_box = bbox_from_wgs84(bbox, "EPSG:27700") if bbox is not None else None
        self.read = 0
        for member in data_files(path):
            for feature in read_csv(path, member=member, fieldnames=fieldnames):
                self.read += 1
                yield from to_places(feature.properties, grid_box)
        logger.info("%s: read %d entries", self.source.key, self.read)


def to_places(
    properties: dict[str, Any], grid_box: tuple[float, float, float, float] | None = None
) -> Iterator[dict[str, Any]]:
    """The places one entry gives: none, one, or two when it has a second name."""
    base = kind_rank(properties["TYPE"] or "", properties["LOCAL_TYPE"] or "")
    if base is None:
        return
    place_id = properties["ID"] or "?"
    xmin, ymin, xmax, ymax = (
        _number(properties[name], name, place_id) for name in ("MBR_XMIN", "MBR_YMIN", "MBR_XMAX", "MBR_YMAX")
    )
    easting = _number(properties["GEOMETRY_X"], "GEOMETRY_X", place_id)
    northing = _number(properties["GEOMETRY_Y"], "GEOMETRY_Y", place_id)
    if grid_box is not None and not (
        grid_box[0] <= easting <= grid_box[2] and grid_box[1] <= northing <= grid_box[3]
    ):
        return
    country = properties["COUNTRY"]
    if country not in NATIONS:
        raise UpstreamFormatError(f"OS Open Names entry {place_id} is in {country!r}.")
    common = {
        "kind": properties["LOCAL_TYPE"],
        "district": area_name(properties["DISTRICT_BOROUGH"]),
        "county": area_name(properties["COUNTY_UNITARY"]),
        "nation": NATIONS[country].value,
        "geom": to_wgs84(Point(easting, northing), "EPSG:27700"),
        "rank": base * 100 + size_rank((xmin, ymin, xmax, ymax)),
        "source": OpenNames.source.key,
    }
    names = [(properties["NAME1"] or "").strip(), (properties["NAME2"] or "").strip()]
    if not names[0]:
        raise UpstreamFormatError(f"OS Open Names entry {place_id} has no name.")
    for name in dict.fromkeys(name for name in names if name):
        yield {"name": name, **common}
