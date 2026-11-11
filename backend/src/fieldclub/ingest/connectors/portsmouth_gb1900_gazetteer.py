"""Antiquities labelled on the Ordnance Survey six-inch maps of about 1900, from the GB1900 gazetteer.

Work-list key `portsmouth-gb1900-gazetteer`. The complete gazetteer is every
piece of text on the second edition County Series six-inch maps of Great
Britain, transcribed by volunteers: 2,552,459 labels in one UTF-16 CSV inside
a 146 MB zip, a snapshot of July 2018 under CC BY-SA 4.0.

Only the labels that name an antiquity are stored, as `map_label` records:
46,468 of them, such as "Tumulus", "Moat", "Camp", "Intrenchment", "Hut
Circles", "ROMAN ROAD (Site of)", "Urn found", "Stone Cross" and "Holy
Well". The rest are footpaths, ordinary wells, boundary stones, farms, field
names, public houses and the other furniture of the map, which the map label
layer ("Antiquities on old maps") is not for. The
labels for quarries, shafts, pits, levels, kilns and mines (about 114,000)
are left out too: they are the 1900 map's record of industry, not of
antiquities, and would outnumber the antiquities in the layer more than two
to one. `is_antiquity` says which labels are kept, and
`tests/connectors/names/test_gb1900.py` pins it down.

The external id is `pin_id`, the gazetteer's own primary key, which its
README says links these rows to the project's raw dumps.

The licence is share-alike. The `sources` row carries it, with the
attribution and the link to the licence that CC BY-SA requires, and every
record response and export repeats them from that row (Decision 0004). The
source is not named "GB1900", because the gazetteer's terms forbid that name
for a derived work, and the attribution says what was changed.

The download host sends its certificate without the intermediate that
signed it, so the shared client can't verify it. The connector's client adds
that intermediate, Thawte TLS RSA CA G1, which DigiCert publishes and which
chains to DigiCert Global Root G2 in the usual trust store. The certificate
expires on 2 November 2027, and after that the download fails until it is
replaced or the host sends its full chain.
"""

from __future__ import annotations

import logging
import math
import re
import ssl
from collections.abc import Iterator
from datetime import timedelta
from functools import cache
from typing import ClassVar

import certifi
import httpx
from shapely.geometry import Point
from shapely.geometry.base import BaseGeometry

from fieldclub import http
from fieldclub.ingest.adapters import UpstreamFormatError, cache_dir
from fieldclub.ingest.adapters.common import Feature
from fieldclub.ingest.adapters.download import download
from fieldclub.ingest.adapters.files import read_csv
from fieldclub.ingest.base import BBox, Connector, RecordIn, SourceInfo
from fieldclub.ingest.registry import register
from fieldclub.vocab import RecordCategory, SourceAccess, SourceReuse

logger = logging.getLogger(__name__)

DOWNLOAD = "https://www.visionofbritain.org.uk/downloads/GB1900_gazetteer_complete_july_2018.zip"
MEMBER = "GB1900_gazetteer_complete_july_2018/gb1900_gazetteer_complete_july_2018.csv"
FIELDS = (
    "pin_id",
    "final_text",
    "nation",
    "local_authority",
    "parish",
    "osgb_east",
    "osgb_north",
    "latitude",
    "longitude",
    "notes",
)
# CC BY-SA asks for a link to the licence and a note of what was changed.
# The work-list has no licence address. This is the one in the zip's licence file.
LICENCE_URL = "https://creativecommons.org/licenses/by-sa/4.0/legalcode"
CHANGES_STATEMENT = (
    "Open Antiquity keeps only the labels that name antiquities, as transcribed, at the positions given."
)
RECORD_TYPE = "Label on the six-inch map"

# Words that make a label an antiquity. The six-inch maps marked antiquities
# by name, with "(Site of)" or "(Remains of)" where little was left, and
# finds with "found". Matched as whole words, in any case.
_ANTIQUITY_WORDS = (
    r"tumul[iu]s?|tuml|barrows?|cairns?|camps?|forts?|earthworks?|[ei]ntrenchments?|moat(?:ed)?|mounds?"
    r"|mottes?|standing stones?|stone circles?|circle of stones|stone rows?|cromlechs?|dolmens?|menhirs?"
    r"|hut circles?|enclosures?|dykes?|dikes?|wansdyke|wansdike|ramparts?|lynchets?|cists?|kists?|kistvaens?"
    r"|brochs?|crannogs?|raths?|henges?|long ?stones?|cup and ring|tesserae|roman|british|saxon|danish"
    r"|druid(?:s|ical)?|celtic|pictish|picts'?|site of|sites of|remains of|ruins?|found|supposed"
    r"|castle|castell|tomen|chambered|battle|urns?|coins?|sculptured stones?|inscribed stones?|ancient"
    r"|settlement|fosse|vallum|earth ?houses?|erd houses?|souterrains?|grim'?s (?:ditch|dyke|dike)"
    r"|(?:stone|standing|market|high|preaching) cross(?:es)?|cross (?:base|shaft)s?"
    r"|(?:base|shaft|pedestal|socket) of (?:a |the |old |stone )?cross"
    r"|holy wells?|(?:our )?lady'?s? wells?|(?:st\.?|saint) [^\W\d_][^()]*?wells?|(?<=\()dun"
)
_ANTIQUITY = re.compile(rf"\b(?:{_ANTIQUITY_WORDS})\b", re.IGNORECASE)
# Labels that name an antiquity only as the whole label. A plain "Cross"
# marks a standing cross, where "Cross Hands" is a village. A "Dun" alone,
# or followed by a Gaelic name as in "Dun Telve", marks a fort, where
# "Dun Moss", "Dun Law" and "Duns" (a town) do not.
_NOT_GAELIC = (
    r"moss|law|cow'?s?|knowe|rig|muir|stone|cleuch|grain|brae|mount|horse|fields?|knees|side|head|fell"
)
_WHOLE_LABEL = re.compile(
    rf"\s*(?:cross(?:es)?|(?:the )?dun(?:\s+(?!(?:{_NOT_GAELIC})\b)[^\W\d_].*)?)\s*", re.IGNORECASE
)
# A label that ends with one of these names a building, a road, a farm or a
# hill called after an antiquity: "Moat Farm", "Castle Street", "Camp Hill".
_NAMED_AFTER = re.compile(
    r"\b(?:farm|fm|cottages?|cotts?|inn|hotel|house|ho|lodge|lane|road|rd|street|st|terrace|hall|school|schs?"
    r"|mill|bridge|station|sta|arms|place|avenue|gardens?|crescent|plantation|covert|wood|copse|cemetery"
    r"|works?|quarry|pit|church|chapel|chap|grange|park|green|common|hill|hills|down|moor|view|mains|villa"
    r"|villas|railway|canal|bay|point|rocks?|islands?|isle|burn|loch|brook|river|pool|barn)\.?\s*$",
    re.IGNORECASE,
)
# Kept whatever they end with: these say the label marks an antiquity.
_MARKS_ANTIQUITY = re.compile(
    r"\b(?:site of|sites of|remains of|ruins? of|found|roman|ancient|track of|stone rows?)\b", re.IGNORECASE
)
# Never antiquities, whatever else they say: railways and their initials
# ("N. B. R.", "L. & N. W. R."), and public and beer houses ("P. H.", "B. H.").
_NOT_ANTIQUITY = re.compile(
    r"\b(?:railway|burial ground|burial gd|furness|homestead|dyke row|flood dyke)\b"
    r"|\b[pb]\.\s*h\.|(?:\b[a-z]\.\s*(?:&\s*)?){1,4}r\.(?!\w)",
    re.IGNORECASE,
)
# "Roman Catholic" and "R. C." say nothing about age, so they are read as
# if absent: "R. C. Chapel" is left out, "R. C. Chapel (In Ruins)" is kept.
_CATHOLIC = re.compile(r"\broman catholic\b|\br\.\s*c\.", re.IGNORECASE)


def is_antiquity(text: str) -> bool:
    """Whether a label on the six-inch map names an antiquity."""
    text = _CATHOLIC.sub(" ", text)
    if _NOT_ANTIQUITY.search(text):
        return False
    if not (_WHOLE_LABEL.fullmatch(text) or _ANTIQUITY.search(text)):
        return False
    return bool(_MARKS_ANTIQUITY.search(text)) or not _NAMED_AFTER.search(text)


def trust_store() -> ssl.SSLContext:
    """The usual trust store, which httpx takes from certifi, with the host's missing intermediate added."""
    context = ssl.create_default_context(cafile=certifi.where())
    context.load_verify_locations(cadata=THAWTE_TLS_RSA_CA_G1)
    return context


@cache
def _client() -> httpx.Client:
    """A client with the shared one's timeout and User-Agent, and `trust_store()`."""
    return http.build_client(verify=trust_store())


@register
class Gb1900Gazetteer(Connector):
    source: ClassVar[SourceInfo] = SourceInfo(
        key="portsmouth-gb1900-gazetteer",
        name="Antiquities on the six-inch maps of about 1900",
        publisher="GB Historical GIS, University of Portsmouth, with NLS and partners",
        licence="CC BY-SA 4.0 (complete and abridged); the raw dump is CC0 1.0",
        licence_url=LICENCE_URL,
        attribution=(
            "Acknowledge 'the Great Britain Historical GIS Project at the University of Portsmouth, "
            "the GB1900 partners and volunteers'. Derived works must not be named 'GB1900'. "
            + CHANGES_STATEMENT
        ),
        category=RecordCategory.MAP_LABEL,
        access=SourceAccess.BULK,
        reuse=SourceReuse.SHARE_ALIKE,
        homepage="https://www.visionofbritain.org.uk/",
        coverage="Great Britain",
    )
    # A snapshot of July 2018 that hasn't changed since. Look again twice a year.
    max_age: ClassVar[timedelta] = timedelta(days=180)

    @property
    def http(self) -> httpx.Client:
        return self._client or _client()

    def fetch(self, *, bbox: BBox | None = None, limit: int | None = None) -> Iterator[RecordIn]:
        path = cache_dir(self.settings, self.source.key) / "GB1900_gazetteer_complete_july_2018.zip"
        fetched = download(DOWNLOAD, path, client=self.http, max_age=self.max_age)
        self.obtained_at = fetched.fetched_at
        rows = 0
        for feature in read_csv(path, member=MEMBER, encoding="utf-16"):
            if rows == 0:
                missing = [name for name in FIELDS if name not in feature.properties]
                if missing:
                    raise UpstreamFormatError(f"The GB1900 gazetteer changed shape: missing {missing}.")
            rows += 1
            record = to_record(feature)
            if record is None:
                continue
            if bbox is not None and not _inside(record.geom, bbox):
                continue
            yield record
        if rows == 0:
            raise UpstreamFormatError("The GB1900 gazetteer has no rows.")
        logger.info("%s: read %d labels", self.source.key, rows)


def _inside(geom: BaseGeometry, bbox: BBox) -> bool:
    west, south, east, north = bbox
    x, y = geom.bounds[:2]
    return west <= x <= east and south <= y <= north


def _number(value: object, what: str, pin_id: str) -> float:
    try:
        number = float(str(value))
    except ValueError:
        raise UpstreamFormatError(f"GB1900 label {pin_id} has {what} {value!r}.") from None
    if not math.isfinite(number):
        raise UpstreamFormatError(f"GB1900 label {pin_id} has {what} {value!r}.")
    return number


def to_record(feature: Feature) -> RecordIn | None:
    """One label as a record, or None when it doesn't name an antiquity."""
    properties = feature.properties
    text = (properties["final_text"] or "").strip()
    if not is_antiquity(text):
        return None
    pin_id = (properties["pin_id"] or "").strip()
    if not pin_id:
        raise UpstreamFormatError(f"The GB1900 label {text!r} has no pin_id.")
    lon = _number(properties["longitude"], "longitude", pin_id)
    lat = _number(properties["latitude"], "latitude", pin_id)
    place = ", ".join(part for part in (properties["parish"], properties["local_authority"]) if part)
    summary = "Lettered on the Ordnance Survey six-inch map of about 1900"
    summary += f", in {place}." if place else "."
    summary += " The point is where the lettering sits, which can be beside the feature it names."
    return RecordIn(
        external_id=pin_id,
        name=text,
        geom=Point(lon, lat),
        record_type=RECORD_TYPE,
        summary=summary,
        raw=dict(properties),
    )


# Thawte TLS RSA CA G1, from http://cacerts.thawte.com/ThawteTLSRSACAG1.crt, the
# address the download host's own certificate names. Issued by DigiCert Global
# Root G2, valid from 2 November 2017 to 2 November 2027. SHA-256 fingerprint
# 4B:CC:5E:23:4F:E8:1E:DE:4E:AF:88:3A:A1:9C:31:33:5B:0B:26:E8:5E:06:6B:99:45:E4:CB:61:53:EB:20:C2.
THAWTE_TLS_RSA_CA_G1 = """\
-----BEGIN CERTIFICATE-----
MIIEizCCA3OgAwIBAgIQCQ7oxd5b+mLSri/3CXxIVzANBgkqhkiG9w0BAQsFADBh
MQswCQYDVQQGEwJVUzEVMBMGA1UEChMMRGlnaUNlcnQgSW5jMRkwFwYDVQQLExB3
d3cuZGlnaWNlcnQuY29tMSAwHgYDVQQDExdEaWdpQ2VydCBHbG9iYWwgUm9vdCBH
MjAeFw0xNzExMDIxMjI0MjVaFw0yNzExMDIxMjI0MjVaMF4xCzAJBgNVBAYTAlVT
MRUwEwYDVQQKEwxEaWdpQ2VydCBJbmMxGTAXBgNVBAsTEHd3dy5kaWdpY2VydC5j
b20xHTAbBgNVBAMTFFRoYXd0ZSBUTFMgUlNBIENBIEcxMIIBIjANBgkqhkiG9w0B
AQEFAAOCAQ8AMIIBCgKCAQEAxjngmPhVetC0b/ozbYJdzOBUA1sMog47030cAP+P
23ANUN8grXECL8NhDEF4F1R9tL0wY0mczHaR0a7lYanlxtwWo1s2uGnnyDs6mOCs
66ew2w3YETr6Tb14xgjpu1gGFtAeewaikO9Fud8hxGJTSwn8xeNkfKVWpD2L4vFN
36FNgxeilK6aE4ykgGAzNlokTp6hNOLAYpDySdLAPKzuJSQ7JCEZ6O+SDKywIdXL
oMTnpxuBKGSG88NWTo3CHCOGmQECia2yqdPDjgLqnEiYNjwQL8uMqj8rOvlMgviB
cHA7xty+7/uYLN6ZS7Vq1/F/lVhVOf5ej6jZdmB85szFbQIDAQABo4IBQDCCATww
HQYDVR0OBBYEFKWM/jLM6w8s1BnGCLgAJIhdw8W3MB8GA1UdIwQYMBaAFE4iVCAY
lebjbuYP+vq5Eu0GF485MA4GA1UdDwEB/wQEAwIBhjAdBgNVHSUEFjAUBggrBgEF
BQcDAQYIKwYBBQUHAwIwEgYDVR0TAQH/BAgwBgEB/wIBADA0BggrBgEFBQcBAQQo
MCYwJAYIKwYBBQUHMAGGGGh0dHA6Ly9vY3NwLmRpZ2ljZXJ0LmNvbTBCBgNVHR8E
OzA5MDegNaAzhjFodHRwOi8vY3JsMy5kaWdpY2VydC5jb20vRGlnaUNlcnRHbG9i
YWxSb290RzIuY3JsMD0GA1UdIAQ2MDQwMgYEVR0gADAqMCgGCCsGAQUFBwIBFhxo
dHRwczovL3d3dy5kaWdpY2VydC5jb20vQ1BTMA0GCSqGSIb3DQEBCwUAA4IBAQC6
km0KA4sTb2VYpEBm/uL2HL/pZX9B7L/hbJ4NcoBe7V56oCnt7aeIo8sMjCRWTCWZ
D1dY0+2KZOC1dKj8d1VXXAtnjytDDuPPf6/iow0mYQTO/GAg/MLyL6CDm3FzDB8V
tsH/aeMgP6pgD1XQqz+haDnfnJTKBuxhcpnx3Adbleue/QnPf1hHYa8L+Rv8Pi5U
h4V9FwHOfphdMXOxi14OqmsiTbc5cOs9/uukH+YVsuFdWTna6IVw1qh+tEtyH16R
vmi7pkqyZYULOPMIE7avrljVVBZuikwARtY8tCVV6Pp9l3VeagBqb2ffgqNJt3C0
TYNYQI+BXG1R1cABlold
-----END CERTIFICATE-----
"""
