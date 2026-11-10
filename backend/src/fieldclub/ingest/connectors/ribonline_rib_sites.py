"""Sites with Roman inscriptions, from the map feed of Roman Inscriptions of Britain Online.

Work-list key `ribonline-rib-sites`. The site's map page is fed by one GeoJSON
answer holding all 1,046 sites, found by asking for every site within 600 km of
a point in Yorkshire. It is not a documented API. The site's `robots.txt` asks
for 20 seconds between requests, so this is one request, kept under `var/` for a
day. A position is the site, not the findspot of each inscription.

Ten sites sit in the section "Outside Britain" (Auvergne, Alderney, Saint
Valery sur Somme and the like) at placeholder points inside Britain, so they are
left out. Some "sites" are areas, such as the county of Yorkshire or the sector
Housesteads to Great Chesters. They are kept, with their type, and are
placed at the point the site gives. `id_code` is RIB's own number for the site.

The page address drops the `site-` that begins every `site_key`, the way the
feed's own map popups do (`/sites/victoria-cave`).
"""

from __future__ import annotations

import logging
from collections.abc import Iterator
from datetime import timedelta
from typing import Any, ClassVar

from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import Feature, Polite
from fieldclub.ingest.adapters.files import geojson_geometry
from fieldclub.ingest.adapters.rest import RestJson
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import Period, RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

FEED_URL = "https://romaninscriptionsofbritain.org/findspot.php"
FEED_PARAMS = {
    "format": "json",
    "entity": "site",
    "qtype": "radius",
    "key": "",
    "radius": "600",
    "lat": "54.09",
    "lng": "-2.2",
}
SITE_URL = "https://romaninscriptionsofbritain.org/sites/{slug}"
# The site's robots.txt: Crawl-delay 20.
DELAY_S = 20.0
REQUIRED = ("id_code", "site_key", "name", "type", "region", "section")
PLACEHOLDER_SECTION = "Outside Britain"


@register
class RibSites(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="ribonline-rib-sites",
        name="Roman Inscriptions of Britain: sites",
        publisher="Roman Inscriptions of Britain Online",
        licence=(
            "'The texts of RIB and the TEI XML from which they are derived are published under a "
            "Creative Commons Attribution 4.0 International License'; photographs reserved"
        ),
        licence_url="https://creativecommons.org/licenses/by/4.0/",
        attribution="Roman Inscriptions of Britain (romaninscriptionsofbritain.org), CC BY 4.0",
        category=RecordCategory.FIND,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://romaninscriptionsofbritain.org/",
        coverage="Britain",
    )
    max_age: ClassVar[timedelta] = timedelta(hours=20)

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        pages = RestJson(self.http, polite=Polite(delay_s=DELAY_S), where="RIB Online")
        path = cache_dir(self.settings, self.source.key) / "sites.json"
        body, self.obtained_at = pages.document(FEED_URL, dest=path, params=FEED_PARAMS, max_age=self.max_age)
        features = body.get("features") if isinstance(body, dict) else None
        if not isinstance(features, list) or body.get("type") != "FeatureCollection":
            raise UpstreamFormatError("The RIB sites feed is not a GeoJSON FeatureCollection.")
        seen: set[str] = set()
        for item in features:
            if not isinstance(item, dict) or not isinstance(item.get("properties"), dict):
                raise UpstreamFormatError("A RIB site has no properties.")
            feature = Feature(
                item["properties"], geojson_geometry(item.get("geometry"), where="a RIB site"), None
            )
            record = to_record(feature)
            if record is None:
                continue
            if record.external_id in seen:
                raise UpstreamFormatError(f"RIB site {record.external_id} appears twice.")
            seen.add(record.external_id)
            yield record


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def to_record(feature: Feature) -> RecordIn | None:
    """One site as a record, or None when it has no real position."""
    p = feature.properties
    missing = [name for name in REQUIRED if name not in p]
    if missing:
        raise UpstreamFormatError(f"A RIB site changed shape: missing {missing}.")
    if feature.geometry is None or p["section"] == PLACEHOLDER_SECTION:
        return None
    site_key = _text(p["site_key"])
    slug = site_key.removeprefix("site-")
    latin, region = _text(p.get("name_latin")), _text(p["region"])
    summary = ". ".join(part for part in (f"Latin name: {latin}" if latin else "", region) if part)
    return RecordIn(
        external_id=str(p["id_code"]),
        name=_text(p["name"]),
        geom=feature.geometry,
        summary=summary or None,
        record_type=_text(p["type"]) or None,
        periods=[Period.ROMAN.value],
        url=SITE_URL.format(slug=slug) if slug else None,
        raw={key: p.get(key) for key in (*REQUIRED, "name_latin")},
    )
