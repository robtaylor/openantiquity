"""Historic England's Heritage at Risk Register 2026, the polygons of the non-building entries.

Work-list key `he-heritage-at-risk-2026`. The `HAR_2026_OTHR_WGS84` FeatureServer, layer 0,
about 5,000 polygons for scheduled monuments, registered parks and gardens, battlefields
and wrecks that are at risk. The service name carries the year and says WGS84, but the
layer is stored in Web Mercator. The reader asks the server for WGS84 either way.
Each row is one assessment, so an asset can appear more than once. `uid` is the row's
own GUID and is the external id. The two rows for one asset share a name and an outline, so the
method is added to the name, "(archaeology)" or "(building or structure)", to tell them apart in a list.

`List_Entry` is the National Heritage List number, but the register's own page for an
entry has a different number, which is in `URL`. The work-list's address template fills
in `List_Entry`, which gives pages that don't exist, so each record links to `URL` instead.
Historic England asks that its Heritage at Risk pages are not scraped: only the link is kept.

Each year is a separate service, and replaces the last. A new year is a new connector and a
new key.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, UpstreamFormatError, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import OGL_URL
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

LAYER_URL = "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/HAR_2026_OTHR_WGS84/FeatureServer/0"
FIELDS = ("FID", "uid", "List_Entry", "HeritageCa", "Risk_Metho", "EntryName", "URL")
REGISTER_PAGE = "https://historicengland.org.uk/advice/heritage-at-risk/search-register/list-entry/"


@register
class HeritageAtRisk2026(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-heritage-at-risk-2026",
        name="Heritage at Risk Register 2026",
        publisher="Historic England",
        licence=(
            "Open Government Licence v3.0 "
            "('Contains public sector information licensed under the Open Government Licence v3.0')"
        ),
        licence_url=OGL_URL,
        attribution=(
            "© Historic England 2026. Contains Ordnance Survey data © Crown copyright and "
            "database right 2026. Released under OGL."
        ),
        category=RecordCategory.DESIGNATION,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://historicengland.org.uk/advice/heritage-at-risk/",
        coverage="England",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        layer = ArcGISLayer(LAYER_URL, client=self.http, geometry_precision=6)
        layer.require(FIELDS, geometry_type="esriGeometryPolygon")
        for feature in layer.features(bbox=bbox):
            yield to_record(feature)


def to_record(feature: Feature) -> RecordIn:
    """One assessment on the register as a record."""
    properties = feature.properties
    uid = str(properties["uid"] or "").strip()
    if not uid:
        raise UpstreamFormatError(f"Heritage at Risk feature {feature.id} has no uid.")
    if feature.geometry is None:
        raise UpstreamFormatError(f"Heritage at Risk entry {uid} has no geometry.")
    method = str(properties["Risk_Metho"] or "").strip()
    url = str(properties["URL"] or "").strip()
    return RecordIn(
        external_id=uid,
        name=entry_name(str(properties["EntryName"] or ""), method),
        geom=feature.geometry,
        summary="On the Heritage at Risk Register 2026"
        + (f", assessed by the {method} method." if method else "."),
        record_type=str(properties["HeritageCa"] or "").strip() or None,
        url=url if url.startswith(REGISTER_PAGE) else None,
        raw=json_ready(properties),
    )


def entry_name(name: str, method: str) -> str:
    """The entry's name with its assessment method after it, so the two rows for one asset differ."""
    name = name.strip() or "Unnamed entry on the Heritage at Risk Register"
    return f"{name} ({method.lower()})" if method else name
