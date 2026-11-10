# Finds and literature sources

This page records what a research pass found on 2026-11-10 about services that hold archaeological finds, fieldwork reports, scholarly papers, place gazetteers and inscription corpora. Nothing here is built. Each observation is dated and describes someone else's service. Suggestions are under "Suggested use" in each section. Two reuse classes and access modes follow [Decision 0004](../architecture/decisions/0004-field-club-is-non-commercial.md) and [Decision 0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md).

The headline: the open material is thin and mostly not about England's finds. Wikidata, DataCite, OpenAlex, Pleiades, Roman Inscriptions of Britain and Internet Archaeology were open and could be read by script. The Archaeology Data Service catalogue held 2.47 million UK records and answered every query, but 43% of them carried terms limiting use to teaching, learning and research. The Portable Antiquities Scheme relaunched in July 2026 with terms that forbid scripted access, and its only open copy stopped in May 2022. No ready-made georeferenced index of papers existed.

Where two reports disagreed, this page gives the later one and says so. Where the terms were not read, the reuse class is the most cautious one and is marked provisional.

## Summary

| Source | Publisher | Coverage | Licence | Reuse | Mode | Records |
|---|---|---|---|---|---|---|
| ADS Data Catalogue API: search | Archaeology Data Service | UK | Per record: ADS Terms, CC-BY, OGL v3, CC BY NC ND | non_commercial | live | 2,469,603 |
| ADS catalogue: map mode and geohash grid | Archaeology Data Service | UK | As search | non_commercial | live | Counts only |
| ADS catalogue: facet counts | Archaeology Data Service | UK | None published | non_commercial | live | 8 publishers |
| ADS catalogue: single record | Archaeology Data Service | UK | Per record | non_commercial | live | One per call |
| ADS grey-literature reports | Archaeology Data Service | UK, mainly England | ADS Terms, some OGL or CC BY 4.0 | non_commercial | live | 106,728 |
| Historic England Excavation Index | Historic England, hosted by ADS | England | ADS Terms | non_commercial | live | 167,822 |
| DataCite REST, prefix 10.5284 | DataCite and ADS | UK and wider | CC0 metadata | open | bulk | 146,930 DOIs |
| DataCite OAI-PMH, set BL.ADS | DataCite | UK and wider | CC0 metadata | open | bulk | 146,930 |
| DataCite public data file | DataCite | World | CC0 waiver | open | bulk | Not tested |
| Wikidata Query Service | Wikimedia Foundation | UK heritage items | CC0 | open | bulk | 398,651 NHLE items |
| PAS snapshot via ADS and ARIADNE | PAS, British Museum, via ADS | England and Wales | "CC-BY" label | open, disputed | deeplink | 902,750 or 945,228 |
| Portable Antiquities Scheme, new site | PAS, British Museum | England and Wales | CC BY-NC-SA metadata | link_only | deeplink | 1,800,000+ claimed |
| Wikimedia Commons PAS category | Commons volunteers | England and Wales | CC BY 2.0 or CC BY-SA 2.0 per file | share_alike | live | 620,669 files |
| OpenAlex | OurResearch | World | CC0 | open | live | Not counted |
| Crossref REST | Crossref | World | No statement read | open, provisional | live | 33,570 fuzzy matches |
| Internet Archaeology via Crossref | University of York | World, UK focus | CC BY 3.0 | open | bulk | 1,002 DOIs |
| CORE API v3 | The Open University | World | Terms not read | link_only, provisional | live | 61 hits for one query |
| Wikipedia geosearch | Wikimedia Foundation | World | CC BY-SA 4.0 | share_alike | live | Not counted |
| Wikimedia Commons geosearch | Wikimedia Foundation | World | Per file | share_alike | live | Not counted |
| Roman Inscriptions of Britain sites | RIB Online | Britain | CC BY 4.0 | open | bulk | 1,046 sites |
| Epigraphic Database Heidelberg | Heidelberg Academy | Roman Empire | CC BY-SA 4.0 | share_alike | bulk | 4,471 Britannia |
| Pleiades | ISAW, NYU | Ancient world | CC BY 3.0 | open | bulk | Dump 136 MB |
| ARIADNE portal API | ARIADNE | Europe | Per record | non_commercial | live | 4,168,691 |
| Europeana Search API | Europeana Foundation | Europe | CC0 metadata | open | live | Not tested |
| OASIS REST API | ADS and OASIS | UK | Login by role | link_only | deeplink | Not readable |
| ADS Library and BIAB | Archaeology Data Service | UK and Ireland | ADS Terms | non_commercial | deeplink | 391,316 |
| ADS archive pages | Archaeology Data Service | UK | ADS Terms | non_commercial | deeplink | Varies |
| Archaeological Investigations Project | Bournemouth University, ADS | England | ADS Terms | non_commercial | deeplink | 80,000+ |
| Celtic Inscribed Stones Project | UCL, ADS | Celtic regions | ADS Terms | non_commercial | deeplink | Not counted |
| Corpus of Anglo-Saxon Stone Sculpture | Durham University | England | None stated | link_only | deeplink | 532 in volume I |
| British Museum Collection Online | British Museum | World | Not verified | link_only | deeplink | Not read |

## ADS Data Catalogue API: search

An undocumented JSON search over 2,469,603 UK archaeology records, held by the Archaeology Data Service and shared with the ARIADNE portal.

| | |
|---|---|
| Access | REST JSON, no key. Found in the catalogue's front-end JavaScript. |
| Address | `https://archaeologydataservice.ac.uk/data-catalogue-api/api/search` |
| Tested on 2026-11-10 | 200 `application/json`. Cloudflare sits in front. About 350 requests at one per second saw no throttling. Response size and time were not recorded for a single call. |
| Format and CRS | JSON in the ARIADNE AO-Cat model, with `total.value`, `hits[].id` and `hits[].data`. EPSG:4326, latitude then longitude. |
| Licence | Per record in `accessRights`. See "Licence by publisher" below. No terms are published for the API. |
| Attribution | "Acknowledge in any publication the original depositors, the funders of the data collections (if different) and the ADS supplying the data materials". ADS gives this citation model: "Southampton City Council (2013) Chapel, Royal South Hants Hospital, Fanshawe Street, Southampton (SOU1570) (data-set). York: Archaeology Data Service (distributor) (doi:10.5284/1018074)." |
| Reuse class | non_commercial for the 43% under ADS Terms. open for PAS, Historic Environment Scotland and Historic England wreck records. non_commercial with no derivatives for RCAHMW. |
| Suggested mode | live |
| Records | 2,469,603. England 1,642,907, Scotland 372,568, Wales 324,896, Isle of Man 54,372 and Northern Ireland 33,442. 2,448,763 have geometry and 20,840 have none. |
| Positional precision | Points to six or more decimals for sites, events and reports. Boxes or polygons as WKT with a centroid for others. PAS records are squares. |
| Paging and limits | `size` is clamped to 50. `page` times `size` cannot pass 10,000. Page 201 at size 50 returned HTTP 200 with `{"error":{"msg":"Scrolling exceeded maximum"}}`. No rate limit or rate-limit headers. |
| CORS | `Access-Control-Allow-Origin: *`, methods GET. The open-source backend sets the header on purpose. |

```
curl -sG 'https://archaeologydataservice.ac.uk/data-catalogue-api/api/search' \
  --data-urlencode 'q=' --data-urlencode 'size=50' --data-urlencode 'page=1' \
  --data-urlencode 'bbox=52.69,-0.75,52.65,-0.70'
```

That request returned a total of 900 and 50 hits.

Notes:

- The `bbox` order is north latitude, west longitude, south latitude, east longitude. Spatial matching is by geometry intersection, not by centroid. A 7 km box around Dorchester returned PAS squares whose centroid lay outside it. Records with national bounding boxes, such as "The Archaeological Journal", match almost everything.
- Filters are exact match and pipe-separated for OR: `publisher`, `contributor`, `owner`, `creator`, `responsible`, `ariadneSubject`, `derivedSubject`, `nativeSubject`, `country`, `dataType`, `resourceType`, `placeName`, `temporal`, `isPartOf` and `range`. `range` filters the archaeological date of the subject, and only 2,084,668 records have one. `q` is a simple query string with AND as the default. `sort` takes `_score`, `issued`, `datingfrom`, `datingto`, `publisher`, `resource` or `distance`.
- No filter exists for `accessRights` or for `issued` date. Sorting by `issued` descending gives newest first, which allows an incremental read but cannot pass 10,000. The default sort with an empty `q` has no tiebreaker.
- A hit has `title.text`, `description.text`, `accessRights`, `accessPolicy`, `publisher[]`, `contributor[]`, `ariadneSubject[]`, `derivedSubject[]` from Getty AAT, `temporal[]`, `spatial[]` with `placeName`, `geopoint`, WKT `boundingbox` or `polygon` and `centroid`, plus `isPartOf[]`, `originalId`, `landingPage`, `issued` and `resourceType`. `landingPage` was null for many inventory records, including the Excavation Index, Merseyside and Manx.
- Type counts by `ariadneSubject`: Site/monument 1,167,640, Artefact 501,127, Coin 442,095, Fieldwork 175,658, Fieldwork report 106,728, Maritime 99,865.
- The country field has errors. All 50,641 Historic England wreck records were tagged "Isle of Man". Merseyside HER records carried a second, empty publisher.
- Other endpoints in the front-end bundle: `getSearchAggregationData`, `autocompleteFilter`, `getMiniMapData`, `getRecord/{id}`, `getTotalRecordsCount` and others. `getTotalRecordsCount` returned 4,168,691, the whole ARIADNE index, not the ADS subset.
- The backend is `github.com/ARIADNE-Infrastructure/portal`, EUPL-1.2, PHP over OpenSearch, last pushed 2026-10-15. Parameters were read from `QuerySettings.php` and `Query.php`. The catalogue user guide is at `https://uoy-ads.github.io/ads-data-catalogue-docs/`.

### Licence by publisher

The `publisher` facet partitioned the catalogue exactly: the eight counts summed to 2,469,603. Licence counts were derived from facet totals, 150 sampled records per publisher and full-text token cross-checks, because `accessRights` cannot be aggregated. The follow-up report said to treat them as accurate to within a few hundred.

| Publisher | Records | `accessRights` | Reuse class |
|---|---|---|---|
| Archaeology Data Service | 1,061,169 | ADS Terms, except 144 as CC BY 4.0 and 383 as "CC BY NC ND" | non_commercial |
| British Museum, the PAS copy | 902,750 | "CC-BY" | open, disputed |
| Historic Environment Scotland, Canmore sites | 334,636 | OGL v3 | open |
| RCAHMW, Coflein | 118,452 | "CC BY NC ND" | non_commercial |
| Historic England, maritime wrecks | 50,641 | OGL v3 | open |
| Manx National Heritage | 1,916 | "CC-BY-NC" | non_commercial |
| Natural History Museum | 29 | Mixed: 24 open, 2 NC, 3 unspecified | Mixed |
| Heritage Science Data Service | 10 | ADS Terms | non_commercial |

In total 1,288,195 records (52.2%) were open, 120,753 (4.9%) were non-commercial or no-derivatives, 1,060,652 (42.9%) carried ADS Terms and 3 were unspecified. Everything unique to ADS sat in the last group: the NRHE with 309,810 sites, the Excavation Index with 167,820 events, 106,728 reports, copies of HER inventories, Defence of Britain with 20,173 and England's Rock Art with 2,103.

By record type, the open site records were 385,320 of 1,167,640: Historic Environment Scotland 334,636, Historic England wrecks 50,641 and 43 ADS CC BY 4.0. A further 120,751 were non-commercial. The other 661,569 carried ADS Terms. In England the only open site records were the wrecks. None of the 175,658 fieldwork events was open. None of the 106,728 reports was labelled open in the catalogue.

The catalogue label was unreliable. Three DOIs labelled with the ADS Terms address in the catalogue were CC BY 4.0 in DataCite: `10.5284/1145341`, `10.5284/1145201` and `10.5284/1078330`. Across the 109,833 report DOIs in DataCite, about 6,500 (6%) were open and 103,295 carried ADS Terms. The label looked like a blanket default. ADS Terms appeared in five spellings, about 901,000 and 123,000 records under the two main URLs, and `accessPolicy` was a second field that often differed from `accessRights`. Other labels seen: "CC-BY" for PAS, a CC BY 4.0 URL, an OGL v3 URL, "CC BY NC ND", "CC-BY-NC" and "Not provided".

### The three conflicting licence statements

On 2026-11-10 ADS made three different statements about the licence on catalogue metadata.

1. The Metadata Policy said: "all ADS metadata is distributed under a Creative Commons Zero (CC0) in line with existing open metadata services."
2. The website terms and conditions said: "Access to and use of discovery metadata provided by the ADS is subject to the conditions set by the Creative Commons License CC BY 4.0 unless otherwise stated." The glossary defined discovery metadata as "Descriptive information about data that aids in data discovery".
3. Every ADS-published catalogue record carried `accessRights` of ADS Terms of Use and Access, and the catalogue user guide said of that field: "Licence indicates the permitted access and reuse of the metadata."

The collection-level record "ADS Archives" was itself labelled CC-BY while its 6,792 members were labelled ADS Terms. For NRHE and HER inventories the record is arguably the depositor's data, not ADS metadata. The research did not resolve this and named it the main question for ADS.

The Deposit Agreement of July 2025, clause 3.2, said the depositor "grants the Recipient a non-exclusive, royalty-free, worldwide licence, with the right to grant sublicences, to the Metadata relating to the Data Collection". ADS can therefore sublicense metadata for archives and reports. Older inventory deposits, namely the NRHE of 2004 and HERs of 2001 to 2013, may sit under different agreements.

### The ADS Terms of Use and Access

The default ADS licence, read in full on 2026-11-10, comprises the Copyright and Liability Statement and the Common Access Agreement. It applies unless a Creative Commons or Open Government licence is attached to the collection.

| Topic | Wording recorded |
|---|---|
| Third parties | "The data must not be sold or supplied to a third party." |
| Duplication | "duplication or sale of all or part of any of the Data Collections is not permitted, except that material may be duplicated by you for your research use or educational purposes in electronic or print form. You must obtain permission for any other use." |
| Purpose | "The data should only be used for teaching, learning, and research purposes." |
| Commercial sponsorship | Research "may be commercially sponsored", but results must be "made accessible for others to use". Other purposes need permission from ADS. |
| Derivatives | Summary box: "If you remix, transform, or build upon the material, you must distribute your contributions in the public domain." "Public domain" was not defined. |

No ADS page documented the catalogue API or set terms for harvesting, robots or text mining. `robots.txt` banned only named bots: Baiduspider, Yandex, UT-Dorkbot, PetalBot, turnitinbot, SemrushBot, AhrefsBot and Amazonbot. `/.well-known/tdmrep.json` returned 404. The only relevant website clause said users "must not use our website in any way or take any action that causes, or may cause, damage to the website or impair the performance, availability or accessibility of the website".

### Harvest test

A bounding-box partition completed beyond the 10,000 window at one request per second. A 900-record cell paged with zero duplicate ids. Its halves returned 843 and 519 ids, their union equalled the parent, and 462 ids sat in both. A quadtree of boxes with de-duplication on `id` was therefore complete. Records with no geometry need a partition by `isPartOf`, `contributor` or `nativeSubject`.

The `isPartOf` filter takes the prefix `https://ariadne-infrastructure.eu/aocat/Collection/` followed by one of these:

| Collection | Suffix | Records |
|---|---|---|
| NRHE | `ADS/AAA81A6D-56F3-341C-BAF0-791C31BC7F73` | 309,810 |
| Excavation Index | `ADS/F350D267-D463-33DE-883B-3561AA523168` | 160,701 |
| Grey Literature Library | `ADS/5910411B-ED97-364E-8D28-6024558AA14B` | 106,708 |
| Defence of Britain | `ADS/C2BC1925-493E-3047-858E-A720403D1F68` | 20,173 |
| England's Rock Art | `ADS/0D3BE6DB-061C-3C13-B188-322AEB50773C` | 2,103 |

### Freshness

The newest `issued` date per set: reports 2026-10-30, Excavation Index 2020-06-08, RCAHMW 2023-09-07, Historic Environment Scotland 2022-05-27, PAS 2022-05-12, Historic England wrecks 2012-12-19 and the NRHE 2004-09-15 for every record. The NRHE text still cited the retired Pastscape site, and `issued` may be a collection date, so its true age was unknown.

### Suggested use

ADS's own follow-up recommended treating all 1,060,652 ADS-terms records as live-query only until ADS answers: the user's browser calls the API, nothing is cached on the server, and every display shows the depositor, "Archaeology Data Service (distributor)" and a link. A finding linked to an ADS record would store only the catalogue id and URL. That reading is the research's interpretation. ADS did not say it. The API was undocumented and nothing invited third-party clients. A tool run for profit would fall outside "not-for-profit teaching and research" even with no cache.

The research also suggested taking PAS, Canmore and Historic England wreck records from their publishers, not from this catalogue, because the copies were snapshots. It suggested licensing user findings openly, since the ADS terms require derivatives to be placed in the public domain. A draft permission request to ADS sits in `followup-ads-catalogue-reuse-and-harvest-terms.json`. It was not sent.

## ADS catalogue: map mode and geohash grid

The same search with `mapq=true`, which returns up to 500 trimmed marker records, or a geohash grid when the viewport holds more.

| | |
|---|---|
| Access | REST JSON, no key |
| Address | `https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q=&mapq=true&bbox={N},{W},{S},{E}` and `.../api/getMiniMapData?q=&bbox={N},{W},{S},{E}&ghp={precision}` |
| Tested on 2026-11-10 | 200 `application/json`. Map mode with 450 markers returned 0.5 MB. `getMiniMapData` at `ghp=6` returned 20 KB. |
| Format and CRS | JSON. `aggregations.geogridCentroid.grids.buckets[{key, doc_count}]`. EPSG:4326, geohash keys. |
| Licence | As search |
| Attribution | As search |
| Reuse class | non_commercial |
| Suggested mode | live |
| Records | Counts only. The earlier report's top bucket at `ghp=6` near Maiden Castle held 518. |
| Positional precision | Markers are points. Map mode grid cells are geohash 7, about 150 m. |
| Paging and limits | Up to 500 markers, otherwise zero hits and a grid. The grid is capped at the 5,000 busiest cells. |
| CORS | `*` |

```
curl -sG 'https://archaeologydataservice.ac.uk/data-catalogue-api/api/search' \
  --data-urlencode 'q=' --data-urlencode 'mapq=true' \
  --data-urlencode 'bbox=52.675,-0.735,52.665,-0.720'
```

That returned a total of 450 and 450 hits, each with title, description, spatial, publisher, `ariadneSubject` and `resourceType`.

Notes: the grid is not clipped to the bounding box, so it undercounts at regional zoom. In one Midlands test with 112,358 site records, the buckets covered 26,560 of 169,904 centroids. The grid supports a heatmap, not cluster counts. Exact counts per cell would need one `size=1` request per cell.

## ADS catalogue: facet counts and single record

Two smaller endpoints on the same API, both 200 on 2026-11-10 with CORS `*`, reuse class non_commercial and suggested mode live.

| Endpoint | Address | Observed |
|---|---|---|
| Facet counts | `https://archaeologydataservice.ac.uk/data-catalogue-api/api/getSearchAggregationData?q=&publisher=Archaeology%20Data%20Service` | Site/monument 661,995, Fieldwork 175,658, Fieldwork report 106,728. 8 publishers, 2,697 contributors, 16 resource types. No `accessRights` facet. The `total` ignored filters when `q` was empty. |
| Facet list | `.../api/autocompleteFilter?q=&filterName=contributor&filterSize=3000` | Returned the full facet list. Null unless `filterQuery` or `filterSize` was given. |
| Single record | `.../api/getRecord/{id}`, with `/xml` for XML | 46 KB JSON, per-record licence, nearby, similar and parent-collection lists. Example id `49EB20A5-69EE-3A0B-9EC0-5138FFDF47AF`. |

The research suggested using `getRecord` to fill in a finding's linked record at display time, not to store its content.

## ADS grey-literature reports

Unpublished fieldwork reports such as evaluations, watching briefs and building records, with abstract, author, DOI and a point location.

| | |
|---|---|
| Access | REST JSON through the ADS search endpoint |
| Address | `https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q=&ariadneSubject=Fieldwork%20report&bbox={N},{W},{S},{E}&size=50` |
| Tested on 2026-11-10 | 200 `application/json` |
| Format and CRS | JSON, EPSG:4326 |
| Licence | ADS Terms of Use and Access on the sampled records. Some newer DOIs carried "Open Government Licence" in DataCite. |
| Attribution | Author, organisation and DOI, plus "Archaeology Data Service (distributor)", per the ADS citation example |
| Reuse class | non_commercial |
| Suggested mode | live |
| Records | 106,728, of which 104,677 fell inside a UK bounding box |
| Positional precision | Point in `spatial[]`, held separately from `placeName`. Precision not stated. Descriptions often quoted a 10-figure NGR. |
| Paging and limits | As the ADS search endpoint |
| CORS | `*` |

```
https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q=&ariadneSubject=Fieldwork%20report&bbox=50.72,-2.52,50.66,-2.42&size=3
```

That returned 129 hits, for example `https://doi.org/10.5284/1040209`.

Notes: the research called this the nearest thing to a georeferenced literature index for the UK. Report descriptions contained explicit grid references such as "centred on NGR SY 68960 90557". Landing pages are DOIs that resolve to ADS Library pages, which were challenged for scripts. The catalogue licence label was a blanket default, so the per-report licence has to come from DataCite.

## Historic England Excavation Index

An index of archaeological investigations with a short description and a point, inherited from the NRHE fieldwork events. They include excavations, watching briefs and surveys.

| | |
|---|---|
| Access | REST JSON through the ADS search endpoint |
| Address | `https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q=&ariadneSubject=Fieldwork&contributor=Historic%20England&bbox={N},{W},{S},{E}&size=50` |
| Tested on 2026-11-10 | 200 `application/json` |
| Licence | ADS Terms of Use and Access |
| Attribution | "Historic England and Archaeology Data Service" |
| Reuse class | non_commercial |
| Suggested mode | live |
| Records | 167,822: the Excavation Index with 160,701 and the Microfilm index with 7,119 |
| Positional precision | Point, with some place-name-only records |
| CORS | `*` |

```
https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?size=1&q=&ariadneSubject=Fieldwork&contributor=Historic%20England
```

The first hit was "OLD CHAPEL", Milcombe, at 52.007805,-1.4029. Notes: the newest `issued` date was 2020-06-08. The pattern `https://archaeologydataservice.ac.uk/archsearch/record?titleId={originalId}` returned a 301 to `/data-catalogue/?titleId=...` and then 200. Whether that page opened the record in a browser was not verified.

## DataCite REST API, ADS prefix 10.5284

DOI metadata for ADS archives, reports and articles, with the true per-item licence in `rightsList`.

| | |
|---|---|
| Access | REST JSON:API, no key |
| Address | `https://api.datacite.org/dois?client-id=bl.ads&page[cursor]=1&page[size]=1000` |
| Tested on 2026-11-10 | 200 `application/json`. Newest update in the set was 2026-11-10. |
| Format and CRS | JSON:API, also DataCite XML and JSON-LD. EPSG:4326. |
| Licence | CC0: "All metadata contained in the file is freely available under a CC0 waiver". The reports keep their own licence in `rightsList`. A later report quoted the ADS website as putting discovery metadata under CC BY 4.0. |
| Attribution | None required for CC0 metadata. Cite the DOIs. |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 146,930 DOIs: 109,833 reports, 7,048 datasets or archives, 311 collections |
| Positional precision | A point on 14,393 DOIs, a place name or box on 56,272, nothing on the rest |
| Paging and limits | 3,000 requests per 5 minutes per IP, from DataCite support documents. Page size up to 1,000 with a cursor. |
| CORS | The first report saw the Origin header echoed. Not needed for a server-side ingest. |

```
curl -sG https://api.datacite.org/dois --data-urlencode 'client-id=bl.ads' \
  --data-urlencode 'page[cursor]=1' --data-urlencode 'page[size]=3'
```

That returned `meta.total` 146,930 and a `links.next` cursor.

Notes: rights across the prefix were 120,597 ADS Terms, 25,759 Creative Commons (18,467 cc-by-4.0, 2,215 cc-by-sa-4.0, 245 by-nc), 520 OGL and 54 none. Facets were no longer returned in `meta`, so counts need a query such as `rightsList.rightsIdentifier:cc-by-4.0`. The join key to the ADS catalogue is the DOI in `landingPage`. DataCite did not cover the NRHE, the Excavation Index or HER records. A box around Maiden Castle returned 4 DOIs here against 129 reports in the catalogue. A DOI resolves with a 302 to an ADS page that was blocked to scripts. Dataset DOIs: AIP `10.5284/1050106`, CISP `10.5284/1000215`, CASSS `10.5284/1124431`, Rural Settlement of Roman Britain `10.5284/1030449`.

Suggested use: ingest the metadata for a clean index of reports and archives, take location from the ADS catalogue joined on the DOI, and use the DOI as the deep link.

## DataCite OAI-PMH, set BL.ADS

The same ADS DOI metadata by OAI-PMH, at `https://oai.datacite.org/oai?verb=ListRecords&metadataPrefix=oai_datacite&set=BL.ADS`. Tested on 2026-11-10: 200 `application/xml`, `completeListSize` 146,930. Only `ListIdentifiers` with `oai_dc` was run, which returned 50 identifiers and a resumption token. `ListRecords` with `oai_datacite` was not run. CC0, reuse class open, suggested mode bulk.

## DataCite public data file

An annual dump of all DataCite DOI metadata at `https://datafiles.datacite.org/`. Not tested: it was far larger than needed and might require contact details. CC0 waiver under the DataCite Data File Use Policy. Reuse class open. The REST cursor or OAI set covers 146,930 records.

## Wikidata Query Service

Structured items for UK heritage sites with coordinates and external identifiers that link to the national records.

| | |
|---|---|
| Access | SPARQL, no key |
| Address | `https://query.wikidata.org/sparql?format=json&query={SPARQL}` |
| Tested on 2026-11-10 | 200 `application/sparql-results+json`. An Atlas of Hillforts query returned 4,188 rows in 3.8 s, and a `SERVICE wikibase:box` query took 5.4 s. A seven-property UNION count timed out at 65 s. |
| Format and CRS | SPARQL JSON, or CSV with `Accept: text/csv`. WKT `Point(lon lat)`, EPSG:4326. |
| Licence | CC0 |
| Attribution | None required |
| Reuse class | open |
| Suggested mode | bulk |
| Records | See the table below |
| Positional precision | Point (P625). Precision varies by source import. |
| Paging and limits | 60 s query timeout. 429 with `retry-after: 8` after about seven rapid calls from a generic User-Agent. Calls spaced 1.5 to 3 s apart avoided it. |
| CORS | `*` |

```
SELECT ?item ?nhle ?coord WHERE { ?item wdt:P1216 ?nhle ; wdt:P625 ?coord }
```

That returned 401,438 CSV rows in 47 s, close to the limit, so the research suggested one property per query.

| Identifier | Property | Items | With P625 |
|---|---|---|---|
| NHLE | P1216 | 398,651 | 398,650 |
| British Listed Buildings | P12485 | 476,898 | 476,894 |
| Canmore | P718 | 105,099 | 105,079 |
| Historic Environment Scotland | P709 | 75,779 | 75,776 |
| Cadw Building | P1459 | 29,951 | 29,951 |
| Coflein | P4658 | 29,074 | 29,009 |
| NIEA building | P1460 | 14,890 | 14,887 |
| Heritage Gateway | P8169 | 11,876 | 11,867 |
| Cadw Monument | P3007 | 4,242 | 4,088 |
| Atlas of Hillforts | P4102 | 4,146 | 4,146 |
| Historic England research records | P4117 | 3,889 | 3,843 |
| PAS record | P14426 | 27 | 8 |
| RIB | P13241 | 21 | 6 |

Other counts: scheduled monuments with coordinates 32,605, UK archaeological sites with coordinates 49,236, and items with a national heritage identifier, coordinates and an English Wikipedia article 25,677. The PAS and RIB identifiers were barely used, so Wikidata could not stand in for a finds or inscriptions index. Suggested use: a cross-walk between national identifiers, coordinates and Wikipedia articles.

## Portable Antiquities Scheme

The Portable Antiquities Scheme (PAS) records finds reported by the public in England and Wales, and relaunched its site in late July 2026.

| | |
|---|---|
| Access | Website and API behind a Cloudflare challenge |
| Address | `https://finds.org.uk/` |
| Tested on 2026-11-10 | 403 with `cf-mitigated: challenge` to scripts. `robots.txt` was readable. Most other evidence came from Wayback captures, dated below. |
| Format and CRS | HTML, a client-rendered Vue app on a Drupal site. The API returns JSON. |
| Licence | Terms of service updated 21/01/2026, read in a Wayback capture of 2026-10-13: "Metadata and catalogue data about a find object that is submitted to our site will be made publicly available under a Creative Commons CC-BY-NC-SA licence." No version was given. |
| Attribution | "The Portable Antiquities Scheme/The Trustees of the British Museum". For images: "Available under a Creative Commons CC-BY 3.0 Licence. The Portable Antiquities Scheme/The Trustees of the British Museum." |
| Reuse class | link_only |
| Suggested mode | deeplink |
| Records | "1,800,000+ artefacts on the database", a home-page claim in a Wayback capture of 2026-10-29. Not counted. |
| Positional precision | Anonymous users saw a parish, or a district where there was no parish |
| Paging and limits | Unknown. No public bounding-box or latitude and longitude search on the new site. |
| CORS | Not applicable |

Notes on the 2026 relaunch:

- The FAQ dated 31/07/2026 referred to "the first week of launch". The old code base at `github.com/findsorguk/findsorguk` was archived on 2026-08-05 with the note "This version of the PAS software is now archived and ceases to be maintained... The replacement website is still live and at the same address".
- The old JSON search at `https://finds.org.uk/database/search/results/format/json` returned a 301 to `https://finds.org.uk/database` on 2026-11-10, as did every `/database/search/*` path. Its last archived response, 2025-05-05, held 1,078,932 records, was fetched anonymously, and accepted `bbox` and `lat`, `lon`, `d`. Page size was 20, capped at 100 through `show`. The first report saw only the 403 and called the endpoint blocked. The later report is followed here.

The current terms, from the 2026-10-13 capture:

| Topic | Wording recorded |
|---|---|
| Commercial use | "you must not use any part of the content of our site for commercial purposes without obtaining a licence to do so from us" |
| Scraping and mining | "For the avoidance of doubt no text or data mining or web scraping is permitted." The clause covered any "robot", "bot", "spider", "scraper" or other automated device, and AI training, "without our express written permission". |
| Contacts | Licence requests to `permissions@britishmuseum.org`. General contact `info@finds.org.uk`. |
| Images | "Images of found objects (the Find Images) are the copyright of the individual photographer or institution who took them... Whilst many of the Find Images are licensed under a Creative Commons CC-BY 3.0 Licence, the Rightsholders may specify a different licence". One archived record carried both "CC-BY" and "All rights reserved", so images need a per-image check. |
| Links | "You may link to our home page, provided you do so in a way that does not damage our reputation". For other use: "please contact info@finds.org.uk". Record-page links were not pre-authorised. |

The old terms, from a capture of 2026-02-05, said: "We licence all our work under a Creative Commons Share-Alike agreement (CC BY 3.0)." The words said Share-Alike while the link went to CC BY 3.0. They had no image clause and no findspot clause, and were in force when the 2022 snapshot was made.

### Findspot precision policy

The higher-level access terms, updated 31/03/2026, said: "Finds location data can be published online, in hard-copy or any other format to no greater precision than a 4-figure NGR (1 km) or using the agreed alias for sensitive findspots." Data finer than that, or flagged sensitive, was "not transferable to a third party, including through AI". The old public site gave a 1 km square in `fourFigure`, `fourFigureLat` and `fourFigureLon`. The new site gave anonymous users a parish or district as `fuzzy_location` with a centroid, seen in four archived API responses of 2026-10-15.

### Robots and crawlers

`finds.org.uk`, `api.finds.org.uk` and `historicengland.org.uk` each returned the same Cloudflare-managed `robots.txt`: `Content-Signal: search=yes,ai-train=no,use=reference`, `Allow: /`, then `Disallow: /` for named AI crawlers including ClaudeBot, anthropic-ai, Claude-Web, GPTBot and CCBot.

### Suggested use

Treat PAS as deep link only until written permission arrives, and draw any PAS location as an area, never a point. The research drafted an email to PAS asking for an API token or the daily export, for confirmation of deep links and for the licence version. It was not sent.

## PAS safety warning: precise grid references in archived API responses

All four archived anonymous responses from `api.finds.org.uk/api/recorded-finds/{ID}/`, captured by Wayback on 2026-10-15, included a field named `legacy_national_grid_reference`. It held a 10-figure grid reference with about 1 m effective precision, beside the intended parish-level `fuzzy_location`. That conflicts with PAS's own 1 km rule and looked unintended. The research did not use or reproduce the values.

This field must never be ingested, stored or displayed. The research recommended a deny-list on any PAS ingest path for `legacy_national_grid_reference`, `location`, `national_grid_reference`, `easting` and `northing`, and a cap on all finds geometry at a 4-figure NGR, which is 1 km. PAS should be told privately, not publicly. Showing finds over high-resolution LIDAR at finer precision than PAS supplies, or inviting users to refine a PAS location, would work against PAS's protection. Whether the exposure was still live on 2026-11-10 was not tested, because the live API returned 403.

Four archived JSON files holding these precise findspots sit in the research scratch folder. They should be deleted with the owner's consent and never copied into the project.

## PAS snapshot via ADS and ARIADNE, May 2022

A copy of PAS find records made by the Archaeology Data Service for ARIADNEplus, searchable as JSON.

| | |
|---|---|
| Access | REST JSON, no key |
| Address | `https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q=&publisher=British%20Museum&bbox={N},{W},{S},{E}&size=50&page={n}`, and the same path on `https://portal.ariadne-infrastructure.eu/api/search` |
| Tested on 2026-11-10 | 200 `application/json` on both hosts |
| Format and CRS | JSON. Polygon box with a centroid, WGS84, derived from the OSGB grid. |
| Licence | `accessRights` "CC-BY" on every sampled record. `accessPolicy` pointed to `https://finds.org.uk/info/termsandconditions`, the old CC BY 3.0 terms. PAS's current terms say CC BY-NC-SA. |
| Attribution | "The Portable Antiquities Scheme/ The Trustees of the British Museum", the old-terms wording |
| Reuse class | open by label only, disputed by the current terms |
| Suggested mode | deeplink under Decision 0007 |
| Records | The ADS catalogue held 902,750, of which 902,666 fell in a UK box. The ARIADNE portal held 945,228 under publisher "British Museum". The later report called the difference unexplained. |
| Positional precision | Squares only, never a point. In a non-random sample of 500, 250 newest and 250 oldest, 147 were about 1 km and 353 about 10 km. |
| Paging and limits | As the ADS search endpoint |
| CORS | `*` on both hosts |

```
curl -G 'https://portal.ariadne-infrastructure.eu/api/search' \
  --data-urlencode 'q=OXON-CDA4F5' --data-urlencode 'size=2'
```

That returned one hit with `originalId` `OXON-CDA4F5` and `landingPage` `https://finds.org.uk/database/artefacts/record/id/1064818`.

Notes: the reports disagreed on square size. The first measured 1 km and 10 km squares in the sample above. The later one described 1 km squares and gave no sample. Both are recorded. The newest `issued` date was 2022-05-12, so the copy was about four and a half years old and, by the later report's estimate, missed about 135,000 later records to May 2025. The collection description said "Records are available with differing levels of information, depending on the type of user account". `originalId` is the PAS find ID and builds the new deep link. A 4 by 3 km box returned 794 hits with some centroids outside it. The later report suggested a visible "snapshot May 2022" label and asking PAS whether it objected.

## Wikimedia Commons: PAS category

Bulk-uploaded PAS find photographs with a per-file licence, at `https://commons.wikimedia.org/w/api.php?action=query&prop=categoryinfo&titles=Category:Portable%20Antiquities%20Scheme&format=json&origin=*`. Tested on 2026-11-10: 200 `application/json`, CORS `*` with `origin=*`. 620,669 files, 619,551 with a FindID in the title. No coordinates, county only. Licence per file, CC BY 2.0 or CC BY-SA 2.0, with attribution "The Portable Antiquities Scheme/ The Trustees of the British Museum" plus the named photographer. Reuse class share_alike. Suggested mode live.

```
https://commons.wikimedia.org/w/api.php?action=query&list=search&srsearch=incategory:%22Portable%20Antiquities%20Scheme%22%20intitle:FindID&srnamespace=6&srlimit=4&format=json
```

Notes: titles carry the old numeric FindID, for example "(FindID 658243)". The bulk upload ended about 2019. Suggested use: an openly licensed image beside a PAS deep link.

## OpenAlex

An open catalogue of scholarly works with title and abstract search, topics and open-access links.

| | |
|---|---|
| Access | REST JSON, and a bulk snapshot |
| Address | `https://api.openalex.org/works?filter=title_and_abstract.search:{phrase},primary_topic.field.id:12\|33&per-page={1-100}&select=id,doi,title,publication_year,open_access` |
| Tested on 2026-11-10 | 200 `application/json` |
| Format and CRS | JSON. Snapshot as JSONL and Parquet on S3. No coordinates. |
| Licence | CC0: "Every record is released under a CC0 public-domain license" |
| Attribution | None required. Citation requested. |
| Reuse class | open |
| Suggested mode | live |
| Records | 144 works for "Maiden Castle" in fields 12 and 33 |
| Paging and limits | Budget-metered. Without a key, all requests from one IP shared $0.10 per day. A free key gave $1 per day. A search cost $1 per 1,000 calls, a filtered list $0.10 per 1,000, single lookups were free. |
| CORS | `*` |

Notes: the free quarterly snapshot at `https://openalex.s3.amazonaws.com/?list-type=2&prefix=data/&delimiter=/` listed `data/jsonl/` and `data/parquet/`. A key needs an email-verified account, which the research did not create. `open_access.oa_url` carries the open-access link. On shared cloud egress the keyless budget would be unpredictable. Suggested use: first choice for paper discovery by site name, cached per monument and not called on every map move.

## Crossref REST API

Bibliographic metadata and DOIs for articles, books and chapters, at `https://api.crossref.org/works?query.bibliographic={text}&rows={n}&select=DOI,title,container-title,issued,type,license`. Tested on 2026-11-10: 200 `application/json`, CORS `*`. No licence statement was read, and the research noted Crossref metadata is generally treated as open facts. Reuse class open, provisional. Suggested mode live. A query for "Maiden Castle" Dorset hillfort returned 33,570 fuzzy matches, topped by Wheeler 1943 and a 2011 PPS paper. Limits from documentation updated 2025-10-16: public pool 5 requests per second with concurrency 1, polite pool with a `mailto` 10 per second with concurrency 3. The polite pool needs a project contact email. Ranking was fuzzy and returned many irrelevant matches, so the suggested use is DOI resolution and a fallback behind OpenAlex.

## Internet Archaeology via Crossref

An open-access journal from the University of York, read through Crossref's prefix 10.11141 at `https://api.crossref.org/prefixes/10.11141/works?rows={n}&cursor=*`. Tested on 2026-11-10: 200 `application/json`, CORS `*`. 1,002 DOIs. Licence "Creative Commons Attribution 3.0 (CC BY) Unported licence" except where otherwise noted. Attribution "attribution to the author(s), the title of the work, the Internet Archaeology journal and the relevant URL/DOI". Reuse class open, suggested mode bulk. No coordinates: article HTML carried Dublin Core and citation fields only, so georeferencing needs a gazetteer. `robots.txt` disallowed `/about/stats/`, `/cfm/`, `/cgi-bin/` and `/news/`. No OAI endpoint answered at `/oai/` or `intarch.ac.uk/oai/articles/OAIHandler`, both 404.

## CORE API v3

Aggregated open-access papers with full text, at `https://api.core.ac.uk/v3/search/works/?q={query}&limit={n}`. Tested on 2026-11-10: the first call returned 500 with "Azure search failed with status code: 503", and the retry returned 200 `application/json`. Free access "subject to our T&Cs", which the research did not read in full, so the reuse class is link_only, provisional. Suggested mode live, server-side only, because a request with an Origin header returned 403. 61 hits for `"Maiden Castle" AND hillfort`. Limit "One batch request or five single requests per 10 seconds". The path without the trailing slash returned a 301. Suggested use: mining grid references and place names from open full text, treated as best-effort.

## Wikipedia geosearch API

Wikipedia articles with coordinates near a point or inside a small box, with Wikidata id, short description and thumbnail.

| | |
|---|---|
| Access | REST JSON, no key |
| Address | `https://en.wikipedia.org/w/api.php?action=query&generator=geosearch&ggsbbox={N}\|{W}\|{S}\|{E}&ggslimit={1-500}&prop=coordinates\|pageprops\|description\|pageimages&ppprop=wikibase_item&format=json&origin=*` |
| Tested on 2026-11-10 | 200 `application/json` |
| Format and CRS | JSON, point per article, EPSG:4326 |
| Licence | Article text CC BY-SA 4.0, the standard licence, not re-read on the day. Images per file. |
| Attribution | Link to the article and state the licence |
| Reuse class | share_alike |
| Suggested mode | live |
| Paging and limits | `gsradius` 10 to 10,000 m. `gslimit` at most 500. A 0.5 by 1.0 degree box returned `toobig`. Rapid anonymous use returned 429. |
| CORS | `*` with `origin=*` |

Notes: a box around Maiden Castle returned Maiden Castle (Q1232816) and Clandon Barrow (Q1095021). For bulk use the research pointed to `https://dumps.wikimedia.org/enwiki/latest/enwiki-latest-geo_tags.sql.gz`, HEAD 200, 54 MB, dated 2026-11-07, not downloaded.

## Wikimedia Commons geosearch API

Geotagged photographs near a point, with thumbnail, author and licence per file, at `https://commons.wikimedia.org/w/api.php?action=query&generator=geosearch&ggscoord={lat}|{lon}&ggsradius={10-10000}&ggslimit={n}&ggsnamespace=6&prop=coordinates|imageinfo&iiprop=url|extmetadata&iiurlwidth=320&format=json&origin=*`. Tested on 2026-11-10: 200 `application/json`, CORS `*` with `origin=*`. Point at the camera position, EPSG:4326. Licence per file. All five samples near Maiden Castle were "CC BY-SA 2.0" with `AttributionRequired` true, imported from Geograph. Attribution from `Artist` and licence in extmetadata. Reuse class share_alike, suggested mode live, same limits as the Wikipedia API. Bulk coordinates: `https://dumps.wikimedia.org/commonswiki/latest/commonswiki-latest-geo_tags.sql.gz`, HEAD 200, 768 MB, dated 2026-10-03, not downloaded.

## Roman Inscriptions of Britain Online: sites

Point locations of every site with RIB inscriptions or tablets, with modern and Latin names.

| | |
|---|---|
| Access | GeoJSON from the site's own map feed, not a documented API |
| Address | `https://romaninscriptionsofbritain.org/findspot.php?format=json&entity=site&qtype=radius&key=&radius={km}&lat={lat}&lng={lon}` |
| Tested on 2026-11-10 | 200 `application/json`, 473 KB, 1,046 features. Time not recorded. |
| Format and CRS | GeoJSON with `id_code`, `site_key`, `name`, `name_latin`, `type`, `region`, `section`. EPSG:4326. |
| Licence | "The texts of RIB and the TEI XML from which they are derived are published under a Creative Commons Attribution 4.0 International License". Photographs reserved to their owners. |
| Attribution | "Roman Inscriptions of Britain (romaninscriptionsofbritain.org), CC BY 4.0" |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 1,046 sites |
| Positional precision | Point per site, not per findspot. City of London 51.513335,-0.088949 matched the Pleiades point for Londinium. |
| Paging and limits | `robots.txt` Crawl-delay 20. Disallowed `/search/`, `/search.php`, `/includes/`, `/misc/`, `/admin/`. |
| CORS | None observed |

```
https://romaninscriptionsofbritain.org/findspot.php?format=json&entity=site&qtype=radius&key=&radius=600&lat=54.09&lng=-2.2
```

Notes: site pages at `/sites/{slug}` link GeoNames and Wikidata. Inscription pages at `/inscriptions/{n}` link EDH, Trismegistos and Historic England numbers. Per-inscription harvesting at a 20 s delay would be slow. One request for the sites plus deep links was enough.

## Epigraphic Database Heidelberg

Latin inscriptions of the Roman Empire including Britannia, at `https://edh.ub.uni-heidelberg.de/data/api/inschrift/suche?provinz=Bri&limit={n}&offset={n}`. Tested on 2026-11-10: 200 `application/json` with curl's default User-Agent. With a `Mozilla/5.0` User-Agent the same URL returned an Anubis bot-check page, HTTP 200 `text/html`. CORS `*`. Licence "All data of the Open Data Repository by the Epigraphic Database Heidelberg can be reused under the CC BY-SA 4.0 licence". Attribution "Epigraphic Database Heidelberg, CC BY-SA 4.0". Reuse class share_alike, suggested mode bulk. 4,471 Britannia inscriptions of 81,882. Inscription records had no coordinates, only `findspot_modern` and `findspot_ancient` names. A separate geography API was not tested. A bounding-box parameter in the form tried was ignored. The sample record was last updated in 2019. Keep EDH fields separable.

```
https://edh.ub.uni-heidelberg.de/data/api/inschrift/suche?provinz=Bri&limit=2
```

## Pleiades gazetteer of ancient places

An ancient-world gazetteer including Roman Britain, at `https://pleiades.stoa.org/places/{id}/json`, with a dump at `https://atlantides.org/downloads/pleiades/json/pleiades-places-latest.json.gz`. Tested on 2026-11-10: 200 `application/json` for place 79574, Londinium/Augusta at `[-0.088949, 51.513335]`. The dump returned HEAD 200, 136 MB, dated 2026-11-10, and was not downloaded. CORS `*`. EPSG:4326, `reprPoint` and a box. Licence "Sharing and remixing permitted under terms of the Creative Commons Attribution 3.0 License (cc-by)". Attribution "Pleiades", "Copyright © The Creators", CC BY 3.0. Reuse class open, suggested mode bulk.

## ARIADNE portal API

The parent index behind the ADS catalogue, with 4,168,691 European records, at `https://portal.ariadne-infrastructure.eu/api/search?q={text}&bbox={N},{W},{S},{E}&publisher={name}&size={1-50}&page={n}`. The first report got 200 `application/json` and 3,072 hits around Maiden Castle. The follow-up reached the host through a web-fetch tool because curl could not resolve it from its sandbox, so it has no status line. The first report saw `access-control-allow-origin: *`. The follow-up could not observe it, though the backend source sets it. The reports also differed on hosting: the first said the Swedish National Data Service built the portal, the later one said D4Science hosts it. Licence per record with the ADS labels, and no catalogue-wide licence. The portal said third-party material "may be subject to specific use constraints". Software EUPL-1.2. Reuse class non_commercial. Suggested mode live, only for Ireland, with 161,818 records, and cross-border context. ADS publisher records totalled 1,061,169. The 50 and 10,000 limits matched ADS, so it offered no route round the ADS Terms.

## Europeana Search API

Aggregated European museum, library and archive metadata, at `https://api.europeana.eu/record/v2/search.json?query={q}&wskey={key}`. Tested on 2026-11-10: 401 `application/json`, "Invalid API key provided!". No data was retrieved because a key is required and the research did not sign up, so geographic filtering and UK archaeology coverage are not tested. Metadata licence: "All Metadata available on europeana.eu are published free of restrictions, under the terms of the Creative Commons CC0 1.0 Universal Public Domain Dedication". Media per item rights statement. Attribution encouraged, to the data provider. Reuse class open for metadata. Suggested mode live, once a key exists.

## Deep link only

These sources could not be read by script on 2026-11-10, or had no machine route to the records. Do not fetch or check them server-side. A server can check only the redirect hosts, which answered without a challenge: `doi.org`, `canmore.org.uk`, `www.heritagegateway.org.uk`, `list.historicengland.org.uk` and `pastscape.org.uk`. A 301 or 302 there shows a link is alive.

| Source | Link pattern | What was observed |
|---|---|---|
| PAS record page | `https://finds.org.uk/pas/recorded-find/{FIND-ID}` | 403 live. 200 in Wayback on 2026-08-11 for `BERK-F72627`. Reuse class link_only. |
| PAS legacy record URL | `https://finds.org.uk/database/artefacts/record/id/{numeric id}` | 403 live. 301 in Wayback on 2026-08-21 to `/pas/recorded-find/YORYM-9526A2`. These are the snapshot's `landingPage` values. Old thumbnail URLs returned 404. |
| PAS search | `https://finds.org.uk/pas/recorded-find/search?q={text}&sort_by=updated_at_desc&per_page=48&page=1` | 403 live. 200 in Wayback on 2026-10-15. Other parameters: `object_types`, `county`, `district`, `broad_period`, and `distance` with `reference_find_id`. No public bounding-box parameter. Behaviour needs a browser check. |
| ADS catalogue record | `https://archaeologydataservice.ac.uk/data-catalogue/resource/{id}` | 200, a 2.5 KB app shell. Old `archsearch/record?titleId=N` links redirect to `/data-catalogue/?titleId=N`. |
| ADS report or archive | `https://doi.org/10.5284/{id}` | The DOI returns 302 to an ADS page that returned 403 to scripts. |
| ADS Library and BIAB | `https://archaeologydataservice.ac.uk/library/browse/details.xhtml?recordId={id}` | Home, about and statistics pages 200. Record pages 403. 391,316 bibliographic records, 170,299 with an open-access document. BIAB, 150,000+ references from 1695, was merged in 2016. No public API found. |
| Archaeological Investigations Project | `https://doi.org/10.5284/1050106` | 302 to an ADS archive page that returned 403. 80,000+ projects in England, 1990 to 2010. ADS Terms. A person would need to download the archive in a browser to assess its fields. |
| Celtic Inscribed Stones Project | `https://doi.org/10.5284/1000215` | UCL's page returned 403, and the ADS archive page `cisp_2003` challenged scripts. ADS Terms. A 2026 registry entry existed in the Open Digital Epigraphy Hub as `10.82261/zspg-dq23`. |
| ADS thematic archives | `https://archaeologydataservice.ac.uk/archives/view/dob/`, `.../archives/view/era_eh_2009/` and DOI `10.5284/1030449` | 403 on all three. ADS Terms. The catalogue API held Defence of Britain with 20,173 points and England's Rock Art with 2,103 to 2,106 points. The Rural Settlement of Roman Britain, about 3,600 sites, had one collection-level record with a national box, so its sites were reachable only through the blocked interface. |
| Corpus of Anglo-Saxon Stone Sculpture | `https://chacklepie.com/ascorpus/catvol{1-14}.php?pageNum_urls={n}&totalRows_urls={total}` | 200 `text/html`. Volume I had 532 entries. Grid references at 6 figures, 100 m. No open licence stated. The ADS version, DOI `10.5284/1124431`, said "ADS Terms and Conditions apply to reuse". Crawl-Delay 20. The site said it was moving to ADS and due offline January to April 2026, yet still served pages. |
| British Museum Collection Online | `https://www.britishmuseum.org/collection` | 403 challenge for `/collection`, `/api/_search` and the terms page. Licence not verified. The research recalled, unchecked, that collection images are CC BY-NC-SA 4.0. The old SPARQL host did not resolve. |
| OASIS | `https://api.oasis.ac.uk/v1/projects` | HTTP 200 with body `{"error":{"status":401,"detail":"Unauthorised"}}`. Basic authentication by role. Client-side calls fail by same-origin policy. Level 7 "Specialist Data Users" access was by application to the OASIS Management Board. Signed-off reports reach the ADS catalogue. |

Suggested use: ask PAS to confirm record links, since its terms name only the home page. Link to OASIS reports through their ADS DOIs and do not integrate its API.

## Unavailable or avoided

| Source | Address | Reason |
|---|---|---|
| PAS API, new | `https://api.finds.org.uk/api/recorded-finds/{FIND-ID}/` | Live search returned 403. Structure was read from archived front-end bundles and four archived responses and was not queried. Terms forbid automated access without written permission. Archived anonymous responses carried the full-precision grid field described above. |
| PAS old JSON search | `https://finds.org.uk/database/search/results/format/json` | Retired. 301 to `/database`. Last 200 in Wayback on 2025-05-05. |
| ADS OAI-PMH | `https://archaeologydataservice.ac.uk/oai/archives/OAIHandler?verb=Identify` | 404 on archives, OASIS and journals paths. Documented until at least January 2024, then removed. The research suggested asking ADS to restore it. |
| ADS Linked Data and SPARQL | `https://data.archaeologydataservice.ac.uk/query/` | 200 with only "This website is currently under maintenance". The 2020 Linked Data Strategy planned to decommission it. |
| ARIADNE knowledge base SPARQL | `https://ariadne.d4science.org/` | Not tested. Reachable only inside a D4Science research environment that needs an account. |
| Europeana SPARQL, PAS records | `https://api.europeana.eu/sparql/` | 200, but only a 2016 aggregation of 428,204 PAS records with district-level names and no coordinates. Metadata CC0, `edm:rights` CC BY 3.0. Preview links 404. |
| Unpaywall | `https://api.unpaywall.org/v2/{doi}?email={address}` | 422, "Email address required in API call". OpenAlex exposes the same open-access status. |
| Zenodo | `https://zenodo.org/api/records` | 200, but no dump of the ADS catalogue, NRHE or Excavation Index. A PAS search found small subsets only, such as record 15272359, medieval coins, CC BY 4.0. |
| PASampo | `https://ldf.fi/pas/sparql` | 404, as was `/pasampo/sparql`. A 2024 paper described it as not yet online. |
| `findsorguk` on GitHub | `https://github.com/findsorguk` | 20 repositories of code and boundary geodata. No finds dump. |

## Georeferencing papers: suggested method

None of OpenAlex, Crossref, CORE or Internet Archaeology metadata carried subject coordinates. The closest existing indexes were ADS grey-literature reports with points, the Excavation Index with points, DataCite geolocations on about 10% of ADS DOIs, and Wikipedia articles with coordinates. Journal literature would have to be georeferenced by the project. The research suggested building the index in tiers and storing the geometry, `precision_m`, method and confidence on every link.

| Tier | Method | Precision | Sources | Display |
|---|---|---|---|---|
| A | Explicit coordinates or grid references | 100 m or better. For a grid reference, the precision equals its digit count. | ADS report points, DataCite geolocations, and NGRs extracted from abstracts by pattern, for example "centred on NGR SY 68960 90557", then converted from OSGB to WGS84 | Pin |
| B | Title or abstract matched to a gazetteer of named monuments, disambiguated by a co-mentioned county or parish | Monument extent, typically under 250 m | NHLE, Canmore, Coflein and Wikidata labels | Pin, labelled as a match |
| C | Match to a parish or settlement | Roughly 1 to 5 km | OS Open Names or parish polygons | Area list, never a pin |
| D | County | County | County name in the text | Filter only |

Users would confirm or reject links, which fits the corroboration model. Common site names produce false matches. Many places are called "Maiden Castle" or "Castle Hill". Without a county or parish and user confirmation the links would be unreliable.

For discovery the research suggested OpenAlex first with `filter=title_and_abstract.search:"<site name>",primary_topic.field.id:12|33`, Crossref `query.bibliographic` for DOIs, and CORE server-side for open full text. All Wikimedia, OpenAlex and Crossref calls would go through one backend service with a descriptive project User-Agent, backoff on 429 and `Retry-After`, and a cache.

Records whose geometry is a national or regional box should be filtered before showing bounding-box results, with a maximum-area threshold at ingest or query time. Linked resources arrive as points, grid squares, parish names and national boxes, so the schema needs geometry, precision in metres, method, licence and source per link, and the map should draw squares and areas as such.

## Open questions

- What do the current PAS terms say about the CC BY-NC-SA version, record deep links and image licences? Will PAS grant an API token or the daily export to a non-commercial open project?
- Does the `legacy_national_grid_reference` exposure still exist, and how does PAS want it reported?
- Is the 902,750-record PAS copy in the ADS catalogue a subset of the 945,228 in ARIADNE? Are the squares 1 km, or a mix of 1 km and 10 km?
- What does a new PAS record page show for location to a logged-out visitor? That needs a browser.
- Which licence governs ADS catalogue records as metadata: CC0, CC BY 4.0 or ADS Terms? Does the answer differ for depositor inventories such as the NRHE and the HERs?
- Can ADS allow caching of NRHE and Excavation Index records, or must Historic England consent? How current is the NRHE copy?
- Does "distribute your contributions in the public domain" mean a CC0-style dedication? Does a donation-funded service with no paywall count as not-for-profit?
- Will ADS supply an export, restore OAI-PMH or name harvest limits? Does it accept browsers calling the API directly, which CORS allows but no policy states?
- Why does the catalogue label every report ADS Terms when DataCite shows about 6,500 reports as open?
- Does `/data-catalogue/?titleId=N` open the matching record in a browser?
- Are the Rural Settlement of Roman Britain site records available by any route other than the blocked web interface?
- Has the Corpus of Anglo-Saxon Stone Sculpture moved to ADS, and under what licence?
- Are RCAHMW records available under OGL elsewhere? The Scotland, Wales and Northern Ireland reports found OGL v3 on DataMapWales.
- Does Europeana hold georeferenced UK archaeology beyond what ADS and ARIADNE expose? Untested without a key.
- Can the project obtain OASIS Level 7 access, and would it add anything beyond what reaches the ADS catalogue?
- What does the British Museum say about collection image licences? The CC BY-NC-SA 4.0 recollection is unverified.
