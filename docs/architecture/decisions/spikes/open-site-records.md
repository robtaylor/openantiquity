# Spike — Is there an open, storable index of known archaeological sites for each UK nation?

**Status:** Resolved (2026-11-10) — PARTIAL; Scotland, Wales and Northern Ireland each published an open national site index, but England published none and only Cornwall and York of its 83 local records carried an explicit OGL on the dataset itself, and Cornwall's still needed confirmation

## Question

Does each UK nation publish an index of known archaeological sites that Field Club may download and store, under a licence that permits it?

## Why this is in question

Decision 0007 sets an access mode for every source: bulk (stored), live (queried by the browser) or deeplink. The first question about any finding is whether the place is already recorded. If every nation published an open index, all sources could be bulk and the map could answer from its own database. If none did, the answer would have to come from live queries and links. The decision needed to know which nations were in which position, and what England's alternatives were.

## Approach

The research pass of 2026-11-10 surveyed designation registers, national site indexes and local Historic Environment Records (HERs). It had four inputs: one report on England, one on Scotland, Wales and Northern Ireland, and two follow-ups, one on England's undesignated site records and one on reuse of the Archaeology Data Service (ADS) catalogue. Where a follow-up disagreed with an earlier report, this record gives the follow-up and says so.

- **Q1.** Does each nation publish a national site index under an open licence?
  - Step 1: Find the national record of each nation and read its licence and attribution text.
  - Step 2: Download or query a sample and count the records.
- **Q2.** Where the national index is not open, which other routes exist for England?
  - Step 1: Classify all 83 English HERs by whether they offer bulk data, a public query service, record pages only, or nothing online.
  - Step 2: Compute the share of England's area that each class covers, from the HER boundary polygons.
  - Step 3: Read the licence of each route, including the ADS catalogue API and the relaunched Heritage Gateway.
- **Q3.** Can the ADS catalogue be harvested, and on what terms?
  - Step 1: Read the ADS terms, metadata policy, website terms and deposit agreement.
  - Step 2: Test paging at one request per second on a bounded area.

The pass sent no request form or email, and the two draft letters it wrote were not sent. It stopped two lines of work. It did not retry trove.scot with a browser-like User-Agent, which the permission system blocked as bot-check circumvention. It stopped querying the Greater London HER after three automated requests, once it had read that site's terms.

## Decision matrix

| Outcome | Means | Action |
|---|---|---|
| No nation has an open index | Everything is live or a link | Decision 0007 would have made every source live or deeplink. |
| All four nations have one | Everything can be stored | Decision 0007 would have been a single bulk rule. Resolves YES. |
| Three nations have one, England has designations only | Three nations answer from the database, England needs a mixed approach | Decision 0007 accepted with three modes. Resolves PARTIAL. |
| A closed source had an open copy elsewhere | The licence could be taken from the copy | Rejected as a route. See the ADS findings. |

The result was the third row.

## Findings

All observations were made on 2026-11-10 unless a different date is given.

### Position by nation

| Nation | National site index | Licence | Records | Stored? |
|---|---|---|---|---|
| Scotland | HES National Record of the Historic Environment points, formerly Canmore | Open Government Licence v3.0 | 314,598 terrestrial and 25,913 maritime | Yes |
| Wales | RCAHMW National Monuments Record of Wales, via DataMapWales | Open Government Licence v3.0 | 112,894 terrestrial and 8,612 maritime | Yes |
| Northern Ireland | HED Sites and Monuments Record | UK Open Government Licence v3.0 | 18,521 | Yes |
| England | None. Historic England Research Records, formerly the NRHE, held 354,740 records on Heritage Gateway only | Not open | 354,740 | No |

England's designations were open. The National Heritage List for England and the Aerial Investigation and Mapping data were published under Open Government Licence v3.0.

### Scotland

- 2026-11-10: the nightly zip `Canmore_Points.zip` held 314,598 terrestrial points, last modified 2026-11-09 23:01 GMT, and `Canmore_Maritime` held 25,913. The `LICENCE` field read "Open Government Licence" on all 314,598 rows. Evidence: https://inspire.hes.scot/AtomService/DATA/Canmore_Points.zip
- 2026-11-10: the open layer was an index only. It carried names, classifications, grid reference and URL, with no description text and no polygons. Terrestrial accuracy was nearest 1 m for 165,836, 10 m for 108,877, 100 m for 30,236, 1 km for 8,416 and general location for 1,233. `ARCHAEOLOG` was Y on 174,142 rows. The ISO metadata inside the zip said "UK Open Government Licence" and linked to the Non-Commercial Government Licence, while the portal terms and the row field said OGL. Evidence: https://portal.historicenvironment.scot/termsandconditions
- 2026-11-10: the designations service held scheduled monuments 8,076, listed buildings 67,478, conservation areas 670, gardens and designed landscapes 371, battlefields 40, historic marine protected areas 27 and World Heritage Sites 10. Pagination was not supported, so paging used `where=FID>N`. Evidence: https://inspire.hes.scot/arcgis/rest/services/HES/HES_Designations/MapServer/5
- 2026-11-10: Canmore was retired and every path returned a 301 to `www.trove.scot`. trove.scot returned 403 with an Azure WAF JavaScript challenge to curl and to WebFetch. The NRHE Areas polygon download link returned 404 and its licence was recorded in the catalogue as "UK Open Government Licence" with attribution worded for OGL v1.0. Not tested: the NRHE Areas download and any trove.scot page. Evidence: https://www.trove.scot/
- 2026-11-10: Scottish local HERs were mostly not open. The Improvement Service Spatial Hub copy was "Restricted" and needed an auth key. PastMap showed council layers but gave no reuse rights. Dundee, Fife and Inverclyde contributed nothing to PastMap.
- 2026-11-10: the earlier report said no Scottish council HER was open. The follow-up found that to be wrong in one case. Stirling Council published 5,744 HER points, with the terms "open to use, you do not have to apply or ask for permission, but you do have to adhere to the terms of the Open Government Licence, the Ordnance Survey, Historic Environment Scotland... or equivalent terms." Aberdeenshire exposed 38,285 polygons but reserved copyright for "personal research only". Highland allowed free private or commercial research use but forbade circulation without written consent, and no Highland data service was found. Falkirk had 2,175 points and Dumfries and Galloway 17,365 points with attribution-only or unstated terms. Evidence: https://services-eu1.arcgis.com/cECIr59LclpO818r/arcgis/rest/services/open_data_historic_environment_records_sites/FeatureServer/0
- 2026-11-10: the Scottish Radiocarbon Index had 952 points and no stated licence.

### Wales

- 2026-11-10: the DataMapWales WFS served Cadw scheduled monuments (4,239 features, 26 MB in 5 s), listed buildings (30,110), registered parks and gardens (385) and historic landscapes (58), with `Access-Control-Allow-Origin: *`. The NMRW terrestrial layer held 112,894 points, layer updated 2026-02-12, and the maritime layer 8,612. Evidence: https://datamap.gov.wales/geoserver/ows
- 2026-11-10: Cadw's metadata read "There are no use restrictions on this data. Recipients may re-use, reproduce, disseminate this data free of charge in any format or medium, provided they do so accurately, acknowledging both the source and copyright". Its attribution wording included the date the recipient received the data. Evidence: https://datamap.gov.wales/layers/inspire-wg:Cadw_SAM
- 2026-11-10: the Cadw conservation areas (531), World Heritage Sites (12), guardianship monuments (133) and a Woodland Opportunity Map historic layer (48,841) carried no licence statement in their metadata. Heneb's Archwilio page listed two of them as OGL, which was not the publisher's own statement. The protected wrecks layer (6) carried the Cadw wording.
- 2026-11-10: RCAHMW's legal page said "Site data held on Coflein, the Historic Wales portal and Data Map Wales is freely available under the Open Government Licence." Its archive material was under the Non-commercial Government Licence or third-party copyright. Coflein had no public API, and its robots.txt carried ai-train=no and disallowed named AI crawlers including ClaudeBot. Evidence: https://coflein.gov.uk/en/legals
- 2026-11-10: the Welsh HER, Archwilio, was restricted. Its terms said data "shall not be passed to a third party without written consent", for information and research only, not for commercial projects. Evidence: https://archwilio.org.uk/wp/?page_id=801
- 2026-11-10: the RCAHMW battlefields inventory site did not connect.

### Northern Ireland

- 2026-11-10: the HED FeatureServer held 14 layers, refreshed monthly, with the service note "Current update published 3rd November 2026". SMR had 18,521 points, historic buildings 15,884, industrial heritage 15,788, defence heritage 4,611, battle sites 324 and scheduled zones 2,099. The OpenDataNI GeoJSON of the SMR was 7,215,463 bytes, in Irish Grid with shapefile-truncated field names and a dated filename. Evidence: https://services2.arcgis.com/BdBkthNLO9mzGAMO/arcgis/rest/services/Historic_Environment_Division_GIS_Data/FeatureServer
- 2026-11-10: 1,709 SMR records were "Unlocated" but still had point geometry. The historic buildings layer held 6,183 "Record Only" and 491 "D1 Record Only" entries beside the listed ones. HED called scheduled zones "an indicative dataset only".
- 2026-11-10: the Archaeological Investigations service (3,271 points, 3,377 extents) was publicly reachable. HED said it "is not currently available through via our web service or as a standalone download". The earlier report advised asking before use.
- 2026-11-10: the NISMR detail pages redirected to a disclaimer page on first visit.

### England: designations and mapped features

- 2026-11-10: the National Heritage List for England FeatureServer had 11 layers, updated daily, Open Government Licence v3.0, `access-control-allow-origin: *`. Counts were listed building points 379,685, scheduled monuments 20,006, parks and gardens 1,721, battlefields 47, protected wrecks 57 and World Heritage Sites 27. Pages were capped at 2,000, so the report preferred the Open Data Hub bulk download, which returned a verified 45,322,240-byte GeoPackage of 20,006 scheduled monuments. Only 10,080 of 379,685 listed-building polygons were real footprints. The rest were about 2.5 m placeholder triangles. Evidence: https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer
- 2026-11-10: the open data carried no description text, only a hyperlink to the list entry on historicengland.org.uk.
- 2026-11-10: the Aerial Investigation and Mapping service held 498,295 detailed-mapping polygons, 197,372 monument extents and 163 project areas, under Open Government Licence v3.0. By `LAYER` it counted DITCH 164,310, BANK 114,319, RIDGE_AND_FURROW_AREA 69,157, RIDGE_AND_FURROW_ALIGNMENT 63,192, STRUCTURE 41,833, EXTENT_OF_FEATURE 32,428 and SCARP_SLOPE_EDGE 13,056. Coverage was project areas only, so an empty area meant unmapped. Evidence: https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/HE_AIM_data/FeatureServer
- 2026-11-10: other open Historic England layers were Conservation Areas (8,749 of about 10,000), Heritage at Risk 2026 (4,989 polygons), Research Spatial Reports (13,543 points), HER boundaries (83), de-designated sites (2,733), Greater London Archaeological Priority Areas (981) and Turning the Plough 2 (2,030). Natural England published undesignated historic parklands (4,517) and the national 250 m historic landscape characterisation grid (2,111,346 cells) under Open Government Licence v3.0.
- 2026-11-10: the Aerial Photo Explorer footprint layers, 468,176 obliques and 103,185 verticals, had no stated licence. Their ArcGIS items had empty licence fields and per-record copyright text. The hand-drawn National Mapping Programme raster tiles carried "© Historic England 2023", with `exportTilesAllowed` false, and Historic England said the raster mapping was not available for download. Service names carried dates and would rotate.
- 2026-11-10: the Historic England licence wording came from a Wayback capture dated 2026-02-01, because the live page returned 403 to curl. Required statements were "© Historic England [year]" and, for spatial data, "Contains Ordnance Survey data © Crown copyright and database right [year]." The currency statement that Historic England recommended began "The Historic England Data contained in this material was obtained on [date]." Evidence: https://web.archive.org/web/20260201214649/https://historicengland.org.uk/terms/website-terms-conditions/open-data-hub/

### England: the national record of undesignated sites

- 2026-11-10: no open bulk NRHE dataset existed on the Open Data Hub or data.gov.uk. The public route was Heritage Gateway, as "Historic England Research Records", 354,740 records. Historic England licensed terrestrial NRHE records to HERs under Open Government Licence v3.0 through the NRHE-to-HERs project, with 13 HERs complete and 12 in progress. Marine records moved to the Marine HER in September 2025. The portal said "the NRHE will not be actively updated or maintained". Evidence: https://nrhe-to-her.esdm.co.uk/licensing-copyright
- 2026-11-10: the follow-up read the same fact as a policy question. Publication of the NRHE terrestrial extract was a choice for Historic England and not a rights problem, except for third-party quotations inside descriptions. No Historic England statement or FOI response on public release was found in two web searches. As HERs accession their records, Historic England removes them from the national dataset, and those HERs were mostly not open.
- 2026-11-10: Heritage Gateway was relaunched on 16 September 2026 inside historicengland.org.uk. The earlier report had put the move at around September 2026. It held 1,299,728 records from 37 HER datasets plus Historic England research records (354,740) and the National Trust (70,805). 25 HERs that were on the old site were not yet on the new one. The FAQ said "We anticipate adding more than 20 datasets during this financial year", with a target of 95% coverage for HER monument records in England in 2027. Evidence: https://historicengland.org.uk/listing/heritage-gateway/help/
- 2026-11-10: Heritage Gateway's terms read "Heritage Gateway records are not authorised for commercial reuse of the information and should not be used for legal or planning purposes." The earlier report quoted the record conditions as "for information use only. It must not be reused commercially or used for legal or planning purposes." All historicengland.org.uk pages returned 403 with a Cloudflare challenge to curl, with either a generic or a Chrome user agent. No published API was found. The site's internal search endpoint was reached from an open browser page only, and a bounding-box query to it was blocked by the session's permission system and not retried. Whether map search returns coordinates was not tested.
- 2026-11-10: legacy `heritagegateway.org.uk` links returned a 301 to the new site. Legacy NRHE links (`resourceID=19191`) redirected to a text search on the old UID. Legacy HER profile links dropped to the generic home page. The redirect responses were readable server-side. The coordinate-search link pattern came from archived HTML and was not exercised live.
- 2026-11-10: SHINE, the Selected Heritage Inventory for Natural England, could not be obtained as a dataset. It was available per holding through portals keyed on a Single Business Identifier. The Forestry Commission's opportunity map for new woodland (552,503 polygons, Open Government Licence v3.0) showed about 7.45 million ha of England as "No SHINE supplied".

### England: the 83 Historic Environment Records

- 2026-11-10: the 83 HER boundary polygons summed to 132,940 km2. The follow-up classed them as in the table below. Class shares are of that area.


| Class | HERs | Share of area | Members |
|---|---|---|---|
| Bulk, licence to confirm for two | 3 | 7.5% | Cornwall and Isles of Scilly, City of York, Lincolnshire |
| Live, public query service | 15 | 16.0% | Bath and North East Somerset, Bristol, City of Lincoln, Dartmoor, Devon, Exmoor, Gloucestershire, North Somerset, Somerset, South Gloucestershire, Wiltshire and Swindon, Wolverhampton and Walsall, Worcester City, and Merseyside and Yorkshire Dales through ADS only |
| Deeplink | 53 | 68.2% | Record pages only |
| Closed | 12 | 8.3% | Greater London, whose terms prohibit automated use and deep links, and 11 with no public online record found |

The per-HER table was at `research/followup-england-undesignated-site-records/data/her_table.csv` in the research scratchpad. The 11 "no public online record found" were classed on absence. The follow-up did not open each HER's Heritage Gateway profile or council site, so some may have a viewer it missed. Hampshire and Surrey were classed deeplink without verification, because their sites refused curl.

- 2026-11-10: openly licensed HER data covered 2.94% of England's area strictly (Cornwall 3,636 km2 and York 272 km2, together 3,908 km2). With Lincolnshire it covered 7.50% (9,975 km2), and with Exmoor 8.02% (10,668 km2). Machine-readable coverage under any licence was 23.5% (18 HERs, 31,190 km2). The earlier report had listed Cornwall, York and Exmoor as clearly open and Lincolnshire as conflicting. The follow-up found conflicts on Cornwall and Exmoor as well, so its figures are the later ones.
- 2026-11-10: licence conflicts needing a human decision. Cornwall's INSPIRE metadata said "Contains public sector information licensed under the Open Government Licence v3.0", while its ArcGIS Online item for the same records granted a "non-exclusive, royalty free revocable licence solely to view the licensed data for non-commercial purposes". Lincolnshire's licence field and rights URL said OGL v3, while its description said the data "should not be used in any commercial sense or as evidence to form any decisions relating to the Historic Environment". OGL permits commercial use, so the two could not both hold. Exmoor's OGL appeared only in Bristol's catalogue for the Know Your Place copy. North Somerset's copy was catalogued as "Public Sector End User Licence". Evidence: https://data.lincolnshire.gov.uk/dataset/monuments
- 2026-11-10: Cornwall held 78,387 monument points, 2,909 lines and 50,804 polygons, 9,706 events, and 321,335 lines plus 523,276 polygons of aerial mapping. Its server sent no CORS header. Its data.gov.uk metadata was dated 2020-09-29. Evidence: https://map.cornwall.gov.uk/arcgis/rest/services/inspire/inspire_historic/MapServer
- 2026-11-10: York's monuments came to 3,507 points in the Hub GeoJSON of 1.4 MB, under OGL v3.0 with the Ordnance Survey derived-data exemption. The follow-up counted 3,555 monument points, 3,648 lines and 2,459 areas on the service. York completed its NRHE transfer in July 2020, with 4,568 records amended or added, so its open data already carried NRHE content. Evidence: https://opendata.arcgis.com/datasets/3f0de3422ec343e498d6d7699c114858_3.geojson
- 2026-11-10: Lincolnshire's CSV held 42,867 rows in the earlier report and 42,927 rows, 41,649 with coordinates, in the follow-up. The fields were ID, name and grid coordinates only. The follow-up wins. The file was cp1252 encoded and its URL changed with each release.
- 2026-11-10: the Know Your Place server at `maps2.bristol.gov.uk` exposed queryable HER layers for ten areas with CORS, among them Devon (49,473 points and 71,369 polygons), Wiltshire (32,920), Somerset (37,380) and Exmoor (12,322). Bristol's metadata gave Exmoor "Open Government Licence", North Somerset "Public Sector End User Licence" and Bristol "GIS User Agreement for external use". Devon and Gloucestershire were blank. All were flagged `freetouse=false` in the earlier report. Service names carried years. Gloucestershire's layer was a 2017 snapshot with "update not planned". Evidence: https://maps2.bristol.gov.uk/server2/rest/services/ext/
- 2026-11-10: Durham's Keys to the Past service held 66,210 points with no licence stated, while its copyright page said "You may not resell, sub-license or distribute any of the content in any form". The Peak District service advertised Create, Update and Delete to anonymous users and exposed internal file paths. Its write access was not tested.
- 2026-11-10: the Greater London HER's terms said "You shall not conduct, facilitate, authorise or permit any text or data mining or web scraping" and "nor may you create a link to any part of GLHER Online other than the home page". The follow-up sent three automated requests before reading them and stopped.

### Archaeology Data Service catalogue

- 2026-11-10: the ADS Data Catalogue API returned JSON with CORS `*`. It was undocumented, with parameters read from the front-end bundle and the EUPL-1.2 backend source. Page size was capped at 50 and `page` times `size` at 10,000. About 350 requests at one per second saw no throttling. bbox order was north, west, south, east. Evidence: https://archaeologydataservice.ac.uk/data-catalogue-api/api/search
- 2026-11-10: it held 2,469,603 records. The earlier report quoted 4,168,691, which the follow-up found to be the whole ARIADNE index. The ADS-published share was 1,061,169. NRHE site and monument records numbered 309,769 in the earlier report and 309,810 in the follow-up. The follow-up wins.
- 2026-11-10: licences by publisher partitioned the catalogue exactly. Open were 1,288,195 records (52.2%): British Museum copy of the Portable Antiquities Scheme 902,750 "CC-BY", Historic Environment Scotland 334,636 OGL v3, Historic England wrecks 50,641 OGL v3 and 144 ADS records CC BY 4.0. Non-commercial or no-derivatives were 120,753 (4.9%): RCAHMW 118,452 "CC BY NC ND", Manx National Heritage 1,916 "CC-BY-NC" and Northern Ireland wrecks 383. ADS Terms covered 1,060,652 (42.9%), which included every record unique to ADS. The pass marked these as accurate to within a few hundred and not as a census.
- 2026-11-10: no England site or event record was open except wrecks. The ADS Terms group held the NRHE (309,810), the Excavation Index (167,820 events), 106,728 reports, the HER copies, Defence of Britain (20,173) and England's Rock Art (2,103). The open copies of Portable Antiquities Scheme and Historic Environment Scotland records were stale: newest issue dates were 2022-05-12 and 2022-05-27.
- 2026-11-10: the ADS Terms of Use and Access said "The data must not be sold or supplied to a third party." and "The data should only be used for teaching, learning, and research purposes." The licence was granted "for valid not-for-profit teaching and research purposes, providing the copyright owners are acknowledged", and "Anyone wishing to use the catalogue for any other purpose must contact the ADS to seek permission." Research funded commercially was allowed, and a commercial product was not. Evidence: https://archaeologydataservice.ac.uk/about/policies/use-access-to-data/ads-terms-of-use-and-access/
- 2026-11-10: ADS gave three licences for its metadata. Its Metadata Policy said "all ADS metadata is distributed under a Creative Commons Zero (CC0)". Its website terms said discovery metadata was under "CC BY 4.0 unless otherwise stated". Each catalogue record carried `accessRights` of ADS Terms, and the catalogue guide said that field "indicates the permitted access and reuse of the metadata". Whether ADS or the depositor held the rights in NRHE and HER inventories was unresolved. The deposit agreement of July 2025 let ADS sublicense metadata, but older deposits, among them the NRHE in 2004 and HERs from 2001 to 2013, might sit under different agreements.
- 2026-11-10: the terms also asked that work building on the material be distributed "in the public domain". The summary box and the binding text conflicted on redistribution. The meaning of "public domain" was not defined.
- 2026-11-10: the catalogue's licence label was unreliable for reports. Of 109,833 report DOIs in DataCite, 5,980 were CC BY 4.0, 19 other Creative Commons and 520 OGL, about 6,500 or 6% open. The catalogue labelled them ADS Terms. 50,641 English wrecks were tagged country "Isle of Man".
- 2026-11-10: the NRHE copy was of unknown age. Every record carried `issued` 2004-09-15, and the collection text still cited the retired PastScape site. The Excavation Index was last issued 2020-06-08.
- 2026-11-10: bulk routes other than the API did not work. The ADS OAI-PMH targets returned 404. The ADS SPARQL site returned "This website is currently under maintenance". Zenodo held no catalogue dump. The ARIADNE SPARQL endpoint needed a D4Science login and was not tested. DataCite was the only working bulk route, at 146,930 DOIs under CC0, but it covered DOIs only and 14,393 had a point. Rate limit was 3,000 requests per 5 minutes per IP. Evidence: https://api.datacite.org/dois?client-id=bl.ads
- 2026-11-10: a harvest test around Rutland found bounding-box partitioning complete and duplicate-free. A 900-record cell and its two halves returned 900, 843 and 519 unique ids with no duplicates across pages. 462 ids appeared in both halves. 2,448,763 of 2,469,603 records had geometry, and the other 20,840 needed a non-spatial partition. There was no date filter. Default paging had no tiebreaker, so stability beyond what was observed was not guaranteed.
- 2026-11-10: the follow-up read the terms as consistent with browser-direct live query for a free non-commercial tool, since each user obtained records from ADS's own server and the service never held them. It called this an interpretation and not an ADS statement. A tool run for profit would fall outside the licence even with no cache.
- 2026-11-10: map mode (`mapq=true`) returned up to 500 marker records when the viewport held that many or fewer, and otherwise a geohash-7 grid capped at the 5,000 busiest cells and not clipped to the bounding box. In a Midlands test the buckets covered 26,560 of 169,904 centroids.
- 2026-11-10: ADS archive pages (`/archives/view/`) returned 403 with a Cloudflare challenge to curl. The API was not blocked. Defence of Britain and England's Rock Art had point records in the API. Rural Settlement of Roman Britain had one collection-level record only. Defence of Britain was not tested for download.
- 2026-11-10: the ADS follow-up drafted a permission request to ADS and the England follow-up drafted one to Historic England. Neither was sent. The ADS draft asked which licence governs catalogue records, whether caching is allowed, whether ADS would supply an export, whether "public domain" allows CC0 or CC BY 4.0, whether browser-direct query is acceptable, and whether a donation-funded service counts as not-for-profit.

### Other record sources

- 2026-11-10: the National Trust Heritage Records Online held "over 97,717" records. Its terms allowed personal reference only and said "You must not link to the Site for commercial purposes without our written agreement." No open National Trust heritage dataset was found. NT record identifiers (`NTSMR-MNA`) could be read from the ADS catalogue.
- 2026-11-10: Church of England church locations (15,757 open, 3,402 closed) were "supplied on a not for profit basis" with the notice "© Church of England, Data Services, 2026". Church Heritage Record pages gave no licence and carried the NHLE list entry number.
- 2026-11-10: the Isle of Man HER (17,843 resources) and Jersey HER (11,508) both ran Arches with public JSON search endpoints. Manx terms were "personal, educational, non-commercial use only", and Jersey showed "All Rights Reserved". No online Guernsey HER was found.
- 2026-11-10: `planning.data.gov.uk` had been down since 6 November 2026, though its bulk files still served. It was a secondary copy of Historic England data.
- 2026-11-10: the Defence of Britain archive download page could not be read, so its licence and format were not tested.

### Sources and suggested use

Reuse class and access mode follow Decision 0004 and Decision 0007. Where a publisher blocks scripts or forbids harvesting, the suggested mode is deeplink whatever its licence. The suggestions come from the research reports. Nothing was built.

| Source | Reuse class | Suggested access mode | Licence and attribution as recorded |
|---|---|---|---|
| HES NRHE points, designations and designation zips | open | bulk | Open Government Licence v3.0. "Contains Historic Environment Scotland and OS data © Historic Environment Scotland and Crown Copyright and [database right] (year), licensed under the Open Government Licence v3.0." |
| HES NRHE Areas polygons | open, unconfirmed | none until a person downloads it in a browser | catalogue says OGL v1.0 wording |
| trove.scot record pages | link_only | deeplink | not machine-readable; blocks scripts |
| HES Historic Land-use Assessment | link_only, End User Licence | deeplink | excluded from OGL in the portal terms |
| Scottish Radiocarbon Index | link_only, licence not stated | deeplink | copyrightText "HES" |
| Stirling Council HER | open | bulk | terms quoted above; attribution "Stirling Council" |
| Aberdeenshire, Falkirk, Dumfries and Galloway HER services | link_only, terms reserve copyright or are unstated | live, as the research suggested for Aberdeenshire | Falkirk: "Copyright Falkirk Council, contains Ordnance Survey data © Crown copyright and database right (year)" |
| Highland HER, WoSAS, Spatial Hub HER | link_only | deeplink | Spatial Hub "Restricted" |
| Cadw designations and NMRW, via DataMapWales | open | bulk | Cadw: "Designated Historic Asset GIS Data, The Welsh Historic Environment Service (Cadw), DATE [the date that you received the data from Cadw], licensed under the Open Government Licence http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/". NMRW: "This site data is from the National Monuments Record of Wales (NMRW), produced by the Royal Commission on the Ancient and Historical Monuments of Wales (RCAHMW). © Crown Database Right: RCAHMW, licensed under the Open Government Licence 3.0." |
| Cadw conservation areas, World Heritage Sites, guardianship | open, claimed second-hand | bulk after Cadw confirms | no publisher statement |
| Coflein pages, Cadw report pages | link_only | deeplink | Coflein robots.txt opts out of AI use |
| Archwilio, Welsh HER | link_only | deeplink | "shall not be passed to a third party without written consent" |
| NI HED FeatureServer and OpenDataNI downloads | open | bulk | UK Open Government Licence v3.0. "Historic Environment Division, Department for Communities" with the standard OGL acknowledgement |
| NI Archaeological Investigations service | link_only, not released | none until HED confirms | not covered by the OGL statement |
| NI record pages and map viewer | link_only | deeplink | Crown copyright; disclaimer page first |
| NHLE, AIM, Conservation Areas, Heritage at Risk, Research Spatial Reports, HER boundaries, de-designated sites, Turning the Plough | open | bulk | Open Government Licence v3.0. "© Historic England [year]. Contains Ordnance Survey data © Crown copyright and database right [year]." Turning the Plough: "© Gloucestershire County Council and Historic England" |
| Natural England historic parklands and NHLC grid | open | bulk | "© Natural England 2025, Contains historical maps provided by the National Library of Scotland, © Historic England 2025 Contains Ordnance Survey data © Crown copyright and database right 2025" for parklands |
| Historic England aerial photo footprints | link_only, licence not stated | live, as the research suggested, with the per-record Copyright field shown | per-record Copyright field |
| NMP hand-drawn raster tiles | link_only, unconfirmed | deeplink | "© Historic England 2023" |
| Heritage Gateway and Historic England Research Records | link_only | deeplink | "not authorised for commercial reuse"; blocks scripts |
| historicengland.org.uk record pages | link_only | deeplink | Cloudflare challenge |
| Cornwall HER | open, licence to confirm | bulk after one-line written confirmation | "Contains public sector information licensed under the Open Government Licence v3.0" |
| City of York HER | open | bulk | "© Crown copyright and database rights 2016 Ordnance Survey 100020818" and the OGL acknowledgement of City of York Council |
| Lincolnshire HER | non_commercial until confirmed | bulk after written confirmation | "Lincolnshire Historic Environment Record (HER), Lincolnshire County Council" and "Contains OS data © Crown copyright and database right [year]" |
| Exmoor HER | open, unconfirmed | live until confirmed | "This record includes National Record of the Historic Environment Information provided by Historic England on [date] licensed under the Open Government Licence" for NRHE-derived records |
| Know Your Place HER layers, Dartmoor, Wiltshire, Wolverhampton and Walsall | link_only, no open licence | live | per source HER |
| ADS Data Catalogue API, ADS-terms records | non_commercial, ADS Terms of Use and Access | live | depositor, "Archaeology Data Service (distributor)" and a link; "Data copyright © Historic England" for the NRHE |
| ADS archive pages | link_only | deeplink | Cloudflare challenge |
| DataCite records, prefix 10.5284 | open, CC0 | bulk | none required; cite DOIs |
| National Trust Heritage Records | link_only | deeplink | no extraction without written permission |
| Church of England church points | non_commercial | live | "© Church of England, Data Services, 2026" |
| Greater London HER, Isle of Man HER, Jersey HER | link_only | deeplink, home page only for London | London bars deep links beyond the home page |

Suggested use, from the research reports:

- Bulk-ingest the three national indexes first: HES zips, the DataMapWales WFS and the NI HED FeatureServer. That was roughly 340,000, 160,000 and 76,000 records.
- Load Scotland from the nightly zips and not the 1,000-row REST pages. Wales takes one WFS request per layer. NI takes the FeatureServer, or the OpenDataNI files resolved through CKAN each run.
- Keep each source's native coordinates beside WGS84 geometry and carry its positional-accuracy field. About 13% of Scottish NRHE points were located to 100 m or worse.
- Store the exact attribution string, licence and retrieval date per source. Cadw's wording needs the date received.
- In England, bulk-ingest Historic England's open layers, then Cornwall and York. Ask Cornwall and Lincolnshire for one-line confirmation of their licences first.
- Query the Know Your Place and other HER services live, with the HER's name and a record link on each result, and ask each HER for permission to cache. Start with Exmoor and Devon.
- Use the ADS catalogue as the interim NRHE layer by live browser query only, with nothing stored. Ingest DataCite for reports. Do not take Portable Antiquities Scheme, Canmore or Historic England wreck records from ADS, because the copies are stale snapshots.
- Link, and do not crawl, Heritage Gateway, trove.scot, Coflein, the National Trust and the Church Heritage Record.
- Show coverage per HER area as indexed, live, link only or no public record.
- Write to Historic England asking for an OGL extract of the NRHE terrestrial records, and to ADS with the draft questions. Ask the Peak District authority to fix its open write access.
- Decide a policy for precise locations of undesignated sites. Publishers warned against uses that could damage sites.
- Show every HER's disclaimer that online data is not a substitute for a formal HER search.
- Re-run the England survey in spring 2027.

### Not tested

- Whether the Heritage Gateway map search returns coordinates, and what its Download button exports.
- The NRHE Areas download and any trove.scot page, both behind a script challenge.
- The Defence of Britain download.
- Write access on the Peak District service.
- CORS for the Bristol, Durham, York, Natural England, Forestry Commission and Church of England services in the earlier report. The follow-up recorded the Know Your Place server as CORS-enabled.
- About 70 of the 83 HERs were not examined individually in the earlier report. The follow-up classified all 83 but opened only some of the 11 "no public online record" profiles.
- The Portable Antiquities Scheme was not assessed in these inputs.

## Outcome

Scotland, Wales and Northern Ireland each published an open national index of known sites under the Open Government Licence, with 314,598, 112,894 and 18,521 terrestrial records, so those three could be stored. England had no such index. Its designations and aerial-mapped features were open, but its 354,740 research records were only on Heritage Gateway, which forbade commercial reuse and blocked scripts. Of England's 83 local HERs, only Cornwall and York carried an explicit OGL on the dataset itself, and Cornwall's still needed confirmation. Together they covered 2.94% of the country, and 15 more offered public query services with unstated or restrictive licences. The ADS catalogue gave a live route to England's undesignated sites under terms for not-for-profit research and teaching, and ADS contradicted itself on the metadata licence. The answer is PARTIAL.
