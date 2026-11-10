"""Certificates of immunity from listing as points, from NHLE layer 2 of the Open Data Hub export.

Work-list key `he-nhle-certificates-of-immunity-points`. 222 points. The
polygon layer holds the same certificates with real outlines and is the one
stored, so this source is registered disabled and no certificate is found
twice (`he_nhle_certificates_of_immunity_polygons.py`).

The layer has `COIStart` and `COIExpire` where the others have `AmendDate`.
The expiry is in the future, so only the start says when the entry changed.
A certificate can cover two separate places under one list entry number
(1495772 is one), so the id is the list entry and the grid reference, such as
`1495772-SP8547238825`. The grid reference is written with and without
spaces, so spaces are dropped.
"""

from __future__ import annotations

from typing import Any, ClassVar

from fieldclub.ingest.adapters import UpstreamFormatError
from fieldclub.ingest.base import SourceInfo
from fieldclub.ingest.connectors.he_nhle_hub import NHLE_ITEM, NhleLayer, hub_export_url, nhle_source
from fieldclub.ingest.registry import register


@register
class CertificateOfImmunityPoints(NhleLayer):
    source: ClassVar[SourceInfo] = nhle_source(
        "he-nhle-certificates-of-immunity-points", "NHLE: Certificates of immunity (points)", enabled=False
    )
    export_url: ClassVar[str] = hub_export_url(NHLE_ITEM, 2)
    file_name: ClassVar[str] = "certificates-of-immunity-points"
    geometry_kinds: ClassVar[tuple[str, ...]] = ("MultiPoint", "Point")
    record_type: ClassVar[str] = "Certificate of immunity from listing"
    date_fields: ClassVar[tuple[str, ...]] = ("COIStart",)
    extra_fields: ClassVar[tuple[str, ...]] = ("COIExpire", "NGR")

    def external_id(self, properties: dict[str, Any]) -> str:
        grid_reference = "".join(str(properties["NGR"] or "").split())
        if not grid_reference:
            raise UpstreamFormatError(f"Certificate {properties[self.id_field]} has no grid reference.")
        return f"{super().external_id(properties)}-{grid_reference}"

    def summary(self, properties: dict[str, Any]) -> str | None:
        start, expire = properties["COIStart"], properties["COIExpire"]
        if start is None or expire is None:
            return None
        return f"Certificate issued {start:%-d %B %Y}, expiring {expire:%-d %B %Y}"
