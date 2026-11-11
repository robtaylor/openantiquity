"""Historic England's Aerial Investigation and Mapping, detailed mapping layer.

Work-list key `he-aim-detailed-mapping`. These are the features Historic England's
interpreters drew from aerial photographs and lidar: about half a million polygons
for banks, ditches, structures, ridge and furrow, scarps and the extents of features,
covering the project areas that have been mapped (just over half of England). An empty
area means unmapped, not empty. The layer is read from the stable `HE_AIM_data`
FeatureServer, layer 0, 2,000 a page, not from the dated `*_view` services the
Mapping Explorer loads. The work-list names the Hub download as the first choice,
but the Hub was regenerating its AIM exports when tested, and the FeatureServer
gives the same rows with a bounding-box filter.

The layer has no identifier of its own. `HE_UID` is the number of the monument
record a polygon belongs to, so it is shared by every polygon of that monument, and
it reads ` NONE GIVEN` on 202,356 of the 498,295 features. The external id is a
hash of `LAYER`, `project`, `HE_UID` and the geometry (see `FeatureKeys`). Attributes
such as the monument type are left out, so a corrected term updates the record
and doesn't replace it. An edit to a polygon's outline gives it a new id.

Monument types are Historic England's FISH thesaurus terms, backslash-separated,
kept as written. Periods are FISH period terms, mapped onto `vocab.Period` by
`periods_of`. Everything the source gives, other than empty values, is kept in `raw`.
"""

from __future__ import annotations

import logging
import re
from collections.abc import Iterator
from typing import ClassVar

from fieldclub.ingest.adapters.arcgis import ArcGISLayer
from fieldclub.ingest.adapters.common import Feature, FeatureKeys, json_ready
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import Period, RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

LAYER_URL = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/HE_AIM_data/FeatureServer/0"
)
FIELDS = ("OBJECTID", "LAYER", "project", "PERIOD", "MONUMENT_TYPE", "EVIDENCE_1", "EVIDENCE_2", "HE_UID")
# Six decimal places of a degree is about a tenth of a metre, finer than the drawing. A few slivers
# are smaller still and collapse to nothing.
GEOMETRY_PRECISION = 6
PAGE_SIZE = 250
PAGE_TIMEOUT_S = 120.0
# What the interpreters write when they have nothing to say.
EMPTY = frozenset({"", "NONE GIVEN", "NO MONUMENT RECORD", "NO MORPH RECORD"})
LAYER_NAMES = {
    "BANK": "Bank",
    "DITCH": "Ditch",
    "STRUCTURE": "Structure",
    "RIDGE_AND_FURROW_AREA": "Ridge and furrow area",
    "RIDGE_AND_FURROW_ALIGNMENT": "Ridge and furrow alignment",
    "EXTENT_OF_FEATURE": "Extent of feature",
    "SCARP_SLOPE_EDGE": "Scarp or slope edge",
}

# FISH period terms onto `vocab.Period`, tried in order, so that "post medieval" is not read as "medieval".
PERIOD_RULES: tuple[tuple[re.Pattern[str], Period], ...] = tuple(
    (re.compile(pattern), period)
    for pattern, period in (
        (
            r"\bPOST[ -]?MEDIEVAL\b|TUDOR|STUART|GEORGIAN|HANOVERIAN|VICTORIAN|\b(17|18|19)TH CENTURY",
            Period.POST_MEDIEVAL,
        ),
        (r"EARLY MEDIEVAL|ANGLO[ -]SAXON|\bSAXON\b|VIKING|ANGLO[ -]SCANDINAVIAN", Period.EARLY_MEDIEVAL),
        (r"MEDIEVAL", Period.MEDIEVAL),
        (r"NEOLITHIC", Period.NEOLITHIC),
        (r"BRONZE AGE", Period.BRONZE_AGE),
        (r"IRON AGE", Period.IRON_AGE),
        (r"ROMAN", Period.ROMAN),
        (r"PREHISTORIC|PALAEOLITHIC|MESOLITHIC", Period.PREHISTORIC),
        (
            r"\b(20|21)(TH|ST) CENTURY|TWENTIETH CENTURY|WORLD WAR|COLD WAR|EDWARDIAN|\bMODERN\b",
            Period.MODERN,
        ),
        (r"UNCERTAIN|UNKNOWN", Period.UNKNOWN),
    )
)
_unmapped: set[str] = set()


@register
class DetailedMapping(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="he-aim-detailed-mapping",
        name="Aerial Investigation and Mapping: detailed mapping",
        publisher="Historic England",
        licence="Open Government Licence v3.0 (HE Open Data Hub Terms and Conditions)",
        licence_url="https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/",
        attribution="© Historic England [year]",
        category=RecordCategory.MONUMENT,
        access=SourceAccess.BULK,
        reuse=SourceReuse.OPEN,
        homepage="https://opendata-historicengland.hub.arcgis.com/",
        coverage="England, where the mapping projects have been done",
    )

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        # Some of the layer's polygons are huge: pages of 1,000 near object id 400,000 are 50 to 75 MB,
        # took 40 s to build and sometimes answered 504. Small pages and a long timeout get through.
        layer = ArcGISLayer(
            LAYER_URL,
            client=self.http,
            geometry_precision=GEOMETRY_PRECISION,
            page_size=PAGE_SIZE,
            timeout_s=PAGE_TIMEOUT_S,
        )
        layer.require_shape(FIELDS, "esriGeometryPolygon")
        keys = FeatureKeys()
        collapsed = 0
        for feature in layer.features(bbox=bbox):
            if feature.geometry is None:
                # A sliver smaller than the requested precision has no shape left. See `GEOMETRY_PRECISION`.
                collapsed += 1
                continue
            yield to_record(feature, keys)
        if collapsed:
            logger.info("%s: %d features were too small to keep their shape", self.source.key, collapsed)
        if keys.repeats:
            logger.info(
                "%s: %d features repeat another's layer, project, monument and outline",
                self.source.key,
                keys.repeats,
            )


def terms_of(text: object) -> list[str]:
    """FISH terms from a backslash-separated field, as written, without the empty ones and repeats."""
    if not isinstance(text, str):
        return []
    found: dict[str, None] = {}
    for term in text.split("\\"):
        term = term.strip()
        if term.upper() not in EMPTY:
            found[term] = None
    return list(found)


def periods_of(text: object) -> list[str]:
    """`vocab.Period` values for a FISH period field such as `MEDIEVAL\\POST MEDIEVAL`.

    Terms are joined by a backslash, and sometimes a slash. A term that means
    no period is dropped, and `unknown` is kept only when it is all there is.
    """
    if not isinstance(text, str):
        return []
    found: dict[str, None] = {}
    for term in re.split(r"[\\/]", text.replace("<Null>", "")):
        term = term.strip().upper()
        if term in EMPTY:
            continue
        for pattern, period in PERIOD_RULES:
            if pattern.search(term):
                found[period.value] = None
                break
        else:
            if term not in _unmapped:
                _unmapped.add(term)
                logger.warning("AIM period %r has no vocab period, so it is only in raw.", term)
    if len(found) > 1:
        found.pop(Period.UNKNOWN.value, None)
    return list(found)


def to_record(feature: Feature, keys: FeatureKeys) -> RecordIn:
    """One detailed-mapping polygon as a record."""
    properties = feature.properties
    assert feature.geometry is not None, "the caller skips features with no shape"
    layer = str(properties["LAYER"] or "").strip()
    record_type = LAYER_NAMES.get(layer) or layer.replace("_", " ").capitalize() or "Mapped feature"
    types = terms_of(properties["MONUMENT_TYPE"])
    evidence = [
        term.lower() for field in ("EVIDENCE_1", "EVIDENCE_2") for term in terms_of(properties[field])
    ]
    project = str(properties["project"] or "").strip()
    summary = " ".join(
        sentence
        for sentence in (
            f"Evidence: {', '.join(dict.fromkeys(evidence))}." if evidence else "",
            f"Project: {project}." if project else "",
        )
        if sentence
    )
    return RecordIn(
        external_id=keys.key([layer, project, properties["HE_UID"]], feature.geometry),
        name=", ".join(term.capitalize() for term in types) or record_type,
        geom=feature.geometry,
        summary=summary or None,
        record_type=record_type,
        monument_types=types,
        periods=periods_of(properties["PERIOD"]),
        raw=json_ready(properties, drop_empty=True),
    )
