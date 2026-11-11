"""What a visitor is shown for each source: a short licence name and a credit line fit to sit beside a map.

A source's `licence` and `attribution` hold what the research recorded:
the licence as the publisher states it, with notes, and the attribution as
the publisher asks for it, with notes too ("None required for CC0 metadata;
cite DOIs", what a derived work may not be called). Those stay, for the
source's page and for exports. These are kept apart from them:

- `licence_label`, the licence's short name, such as "OGL v3" or "CC BY 4.0";
- `credit`, the line to show. Where the publisher prescribes words, the
  credit is those words as the work-list gives them
  (`docs/sources/worklists/sources.json`), less the research's notes and the
  licence, which `licence_label` names beside it. Where it prescribes none,
  the credit names the publisher and the dataset. `[year]` and `[date]` are
  filled in when the row is stored, as the attribution's are.

Historic England's National Heritage List data also asks for a statement of
when it was obtained. That stays in the attribution, which the source's page
shows in full, rather than beside the map.

`ingest.base.SourceInfo` takes its two fields from here, so every source a
connector, loader or the terrain declares is credited here by its key.
`tests/test_credits.py` fails for a declared source with no entry.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Credit:
    licence_label: str
    credit: str


OGL = "OGL v3"
CC_BY = "CC BY 4.0"
CC0 = "CC0 1.0"

HISTORIC_ENGLAND = "© Historic England [year]"
WITH_OS = "Contains Ordnance Survey data © Crown copyright and database right [year]."
EA_2022 = "© Environment Agency copyright and/or database right 2022. All rights reserved."
NHLE = Credit(OGL, f"{HISTORIC_ENGLAND}. {WITH_OS}")

CREDITS: dict[str, Credit] = {
    "aarhus-itinere-roman-roads": Credit(
        CC_BY,
        "Itiner-e: the digital atlas of ancient roads © 2024 by Brughmans, Pažout, de Soto and "
        "Bjerregaard Vahlstrup is licensed under CC BY 4.0",
    ),
    "bern-xronos-radiocarbon": Credit(CC_BY, "XRONOS, University of Bern"),
    "datacite-ads-dois": Credit(CC0, "DataCite, for reports in the Archaeology Data Service"),
    "defra-lidar-composite-dtm-2022-1m": Credit(OGL, EA_2022),
    "defra-lidar-survey-index-catalogues": Credit(OGL, EA_2022),
    "he-aim-detailed-mapping": Credit(OGL, HISTORIC_ENGLAND),
    "he-aim-monument-extents": Credit(OGL, HISTORIC_ENGLAND),
    "he-aim-project-areas": Credit(OGL, HISTORIC_ENGLAND),
    "he-conservation-areas": Credit(
        OGL, f"© Historic England and Local Planning Authorities [year]. {WITH_OS}"
    ),
    "he-de-designated-sites": Credit(OGL, f"© Crown Copyright [year]. {WITH_OS}"),
    "he-greater-london-apas": Credit(OGL, f"{HISTORIC_ENGLAND}. {WITH_OS}"),
    "he-heritage-at-risk-2026": Credit(OGL, f"{HISTORIC_ENGLAND}. {WITH_OS}"),
    "he-nhle-building-preservation-notices-points": NHLE,
    "he-nhle-building-preservation-notices-polygons": NHLE,
    "he-nhle-certificates-of-immunity-points": NHLE,
    "he-nhle-certificates-of-immunity-polygons": NHLE,
    "he-nhle-listed-buildings-points": NHLE,
    "he-nhle-listed-buildings-polygons": NHLE,
    "he-nhle-protected-wreck-sites": NHLE,
    "he-nhle-registered-battlefields": NHLE,
    "he-nhle-registered-parks-and-gardens": NHLE,
    "he-nhle-scheduled-monuments": NHLE,
    "he-nhle-world-heritage-sites": NHLE,
    "he-research-spatial-reports": Credit(OGL, HISTORIC_ENGLAND),
    "he-turning-the-plough-2": Credit(OGL, "© Gloucestershire County Council and Historic England"),
    "hull-beresford-lost-villages": Credit("CC BY-NC-SA 4.0", "© 2009-2024 The University of Hull"),
    "isaw-pleiades-places": Credit("CC BY 3.0", "Pleiades, © The Contributors"),
    "ne-historic-parklands-undesignated": Credit(
        OGL,
        "© Natural England 2025, Contains historical maps provided by the National Library of Scotland, "
        "© Historic England 2025 Contains Ordnance Survey data © Crown copyright and database right 2025",
    ),
    "ons-counties-2025": Credit(
        OGL,
        "Source: Office for National Statistics licensed under the Open Government Licence v.3.0. "
        "Contains OS data © Crown copyright and database right [year].",
    ),
    "ons-countries-2025": Credit(
        OGL,
        "Source: Office for National Statistics licensed under the Open Government Licence v.3.0. "
        "Contains OS data © Crown copyright and database right [year].",
    ),
    "os-open-names": Credit(
        OGL,
        "Contains OS data © Crown Copyright and database rights [year]. Contains Royal Mail data © Royal "
        "Mail copyright and database right [year]. Contains National Statistics data © Crown copyright and "
        "database right [year].",
    ),
    "oxford-edinburgh-atlas-of-hillforts": Credit(
        "CC BY-SA 4.0",
        "Lock, Gary and Ralston, Ian. 2024. Atlas of Hillforts of Britain and Ireland. "
        "Available at: https://hillforts.arch.ox.ac.uk",
    ),
    "portsmouth-gb1900-gazetteer": Credit(
        "CC BY-SA 4.0",
        "The Great Britain Historical GIS Project at the University of Portsmouth, "
        "the GB1900 partners and volunteers",
    ),
    "ribonline-rib-sites": Credit(CC_BY, "Roman Inscriptions of Britain (romaninscriptionsofbritain.org)"),
    "wikimedia-wikidata-heritage-items": Credit(CC0, "Wikidata"),
    "york-her-monuments": Credit(
        OGL, "© Crown copyright and database rights 2016 Ordnance Survey 100020818; City of York Council"
    ),
}


def credit_for(key: str) -> Credit | None:
    """The source's licence label and credit, or None for a source not credited here yet."""
    return CREDITS.get(key)
