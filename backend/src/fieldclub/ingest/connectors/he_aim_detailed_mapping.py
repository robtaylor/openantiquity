"""Historic England's Aerial Investigation and Mapping, detailed mapping layer.

Work-list key `he-aim-detailed-mapping`. These are the features Historic England's
interpreters drew from aerial photographs and lidar: about half a million polygons
for banks, ditches, structures, ridge and furrow, scarps and the extents of features,
covering the project areas that have been mapped (just over half of England). An empty
area means unmapped, not empty. It is read from the Open Data Hub's GeoPackage export of
the stable `HE_AIM_data` service (layer 0), not from the dated `*_view` services the
Mapping Explorer loads. The FeatureServer would give the same rows with a box filter, but
its pages grow to 50 MB or more near object id 400,000 (some polygons have tens of
thousands of vertices), take over 40 s to build and often time out. Two attempts at the full
layer by that route stalled there. The export is 4.7 GB, built by the Hub on request and
downloaded at about half a megabyte a second.

The layer has no identifier of its own. `HE_UID` is the number of the monument
record a polygon belongs to, so it is shared by every polygon of that monument, and
it reads ` NONE GIVEN` on 202,356 of the 498,295 features. The external id is a
hash of `LAYER`, `project` and the geometry in the file's own British National Grid
coordinates, to a tenth of a metre (see `FeatureKeys`), so it doesn't move with the
reprojection to WGS84. Attributes such as the monument type, and `HE_UID`, are left
out, so a corrected term, or a number assigned later, updates the record and doesn't
replace it. An edit to a polygon's outline gives it a new id.

Polygons that share layer, project and outline are not always one drawing entered
twice: about 800 such groups hold two interpretations that differ in type, period or
evidence (and sometimes in `HE_UID`). A group member whose other attributes are
identical to one already read is skipped. One that differs gets the id of the first
with a hash of its attributes after it, so re-exporting in another row order doesn't
swap the ids of two interpretations. Only the member read first keeps the bare id.

Monument types are Historic England's FISH thesaurus terms, backslash-separated,
kept as written. Periods are FISH period terms, mapped onto `vocab.Period` by
`periods_of`. Everything the source gives, other than empty values, is kept in `raw`.
"""

from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterator
from datetime import timedelta
from typing import ClassVar

from fieldclub.ingest.adapters.common import Feature, FeatureKeys, UpstreamFormatError, cache_dir, json_ready
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.adapters.files import read_vector, vector_info
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import Period, RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

LAYER_URL = (
    "https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/HE_AIM_data/FeatureServer/0"
)
FIELDS = ("LAYER", "project", "PERIOD", "MONUMENT_TYPE", "EVIDENCE_1", "EVIDENCE_2", "HE_UID")
HUB_EXPORT = (
    "https://opendata-historicengland.hub.arcgis.com/api/download/v1/items/"
    "e08a1ca270ac4caa8ba5efcb74f86a74/geoPackage?layers=0"
)
# The export is 4.7 GB and the Hub builds it on request, then serves it at about half a megabyte a
# second, so a copy is kept for a week. The layer was last edited in June 2026.
MAX_AGE = timedelta(days=7)
MAX_WAIT_S = 7200.0
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
        path = cache_dir(self.settings, self.source.key) / "detailed-mapping.gpkg"
        fetched = download(HUB_EXPORT, path, client=self.http, max_age=MAX_AGE, max_wait_s=MAX_WAIT_S)
        self.obtained_at = fetched.fetched_at
        info = vector_info(path)
        missing = [name for name in FIELDS if name not in set(info["fields"])]
        if missing or info.get("crs") != "EPSG:27700" or "Polygon" not in str(info.get("geometry_type")):
            raise UpstreamFormatError(
                f"The detailed mapping export changed shape: crs {info.get('crs')}, "
                f"geometry {info.get('geometry_type')}, missing {missing}."
            )
        keys = FeatureKeys()
        for feature in read_vector(path, bbox=bbox, info=info):
            if feature.geometry is None:
                raise UpstreamFormatError(f"AIM feature {feature.id} has no geometry.")
            record = to_record(feature, keys)
            if record is not None:
                yield record
        if keys.repeats:
            logger.info(
                "%s: %d features repeat another's layer, project and outline, and were skipped or "
                "told apart by their attributes",
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


def to_record(feature: Feature, keys: FeatureKeys) -> RecordIn | None:
    """One detailed-mapping polygon as a record, or None when it is an exact repeat of one already read."""
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
    raw = json_ready(properties, drop_empty=True)
    external_id = keys.distinct_key(
        [layer, project],
        feature.geometry,
        [json.dumps(raw, sort_keys=True, default=str)],
        native=feature.native,
    )
    if external_id is None:
        return None
    return RecordIn(
        external_id=external_id,
        name=", ".join(term.capitalize() for term in types) or record_type,
        geom=feature.geometry,
        summary=summary or None,
        record_type=record_type,
        monument_types=types,
        periods=periods_of(properties["PERIOD"]),
        raw=raw,
    )
