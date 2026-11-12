# Scotland, Wales and Northern Ireland record sources

This page covers the national site indexes, statutory designations and local records for Scotland, Wales and Northern Ireland, plus the Isle of Man and the Channel Islands. All of it is an observation of other people's services on 2026-11-10. Nothing here describes what OpenAntiquity's code does, because none of it is built. Each nation's publisher released its national site index and its designations under the Open Government Licence v3.0, and all of those are open. Two files on trove.scot cannot be fetched by script. Local Historic Environment Records are not open in any of the three nations. trove.scot, the new home of Canmore record pages, blocks every scripted request, so its record pages are links and nothing else.

Reuse classes and access modes follow [Decision 0004](../architecture/decisions/0004-field-club-is-non-commercial.md) and [Decision 0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md). OpenAntiquity is non-commercial, so a source under a non-commercial licence is usable. A publisher that blocks scripts or forbids harvesting is `deeplink` whatever its licence.

Where the first research report and a later follow-up disagreed, the follow-up is given and the disagreement is stated. The Scottish parts of the follow-up on bot-blocked publishers were written later than the main report and win.

## Summary

Sources are grouped by nation, most useful first within each. The deep-link sources are tabulated in their own section near the end: canmore.org.uk redirects, HES Portal, PastMap, council HERs, Treasure Trove Scotland, Coflein, Cadw reports, Archwilio, the NI record pages and the Isle of Man, Jersey and Guernsey HERs.

| Source | Publisher | Coverage | Licence | Reuse | Mode | Records |
|---|---|---|---|---|---|---|
| HES NRHE points zip | Historic Environment Scotland | Scotland | OGL v3.0 | open | bulk | 314,598 terrestrial, 25,913 maritime |
| HES designation zips | Historic Environment Scotland | Scotland | OGL v3.0 | open | bulk | eight sets, SAM 8,076 |
| HES Canmore_Points MapServer | Historic Environment Scotland | Scotland | OGL v3.0 | open | live | 314,598 and 25,913 |
| HES_Designations MapServer | Historic Environment Scotland | Scotland | OGL v3.0 | open | live | eight layers |
| HES Designations WFS | Historic Environment Scotland | Scotland | OGL v3.0 | open | live | as the MapServer |
| HES map image export | Historic Environment Scotland | Scotland | OGL v3.0 | open | live | raster overlay |
| Scottish Radiocarbon Index, ArcGIS layer | Historic Environment Scotland | Scotland | OGL v3.0 per the download page | open | bulk | 952 sites |
| Scottish Radiocarbon Index spreadsheet | Historic Environment Scotland | Scotland | OGL v3.0 | open | deeplink | 5,414 determinations |
| NRHE Areas polygons | Historic Environment Scotland | Scotland | OGL, wording differs | open | deeplink | more than 100,000 |
| Spatial Hub council HERs | Improvement Service | Scotland | Restricted | link_only | deeplink, avoid | not counted |
| Historic Land-use Assessment | Historic Environment Scotland | Scotland | End User Licence | link_only | deeplink, avoid | not counted |
| Cadw Scheduled Monuments | Cadw | Wales | OGL v3.0 | open | bulk | 4,239 |
| Cadw Listed Buildings | Cadw | Wales | OGL v3.0 | open | bulk | 30,110 |
| Cadw Registered Historic Parks and Gardens | Cadw | Wales | OGL v3.0 | open | bulk | 385 |
| Cadw Registered Historic Landscapes | Cadw | Wales | OGL v3.0 | open | bulk | 58 |
| Other Cadw layers | Cadw | Wales | wrecks OGL; three layers unstated | open for wrecks | bulk for wrecks, live for the rest | 12, 6, 133, 531 |
| NMRW terrestrial sites (Coflein index) | RCAHMW | Wales | OGL v3.0 | open | bulk | 112,894 |
| NMRW maritime sites | RCAHMW | Welsh waters | OGL v3.0 | open | bulk | 8,612 |
| RCAHMW Historic Place Names | RCAHMW | Wales | OGL v3.0 | open | bulk | 666,308 |
| DataMapWales WMS | Welsh Government | Wales | as per layer | open | live | raster overlay |
| Woodland Opportunity Map HER features | Welsh Government | Wales | none stated | link_only | deeplink, avoid | 48,841 |
| HED GIS Data FeatureServer | Department for Communities | Northern Ireland | OGL v3.0 | open | bulk | 14 layers, SMR 18,521 |
| OpenDataNI HED downloads | Department for Communities | Northern Ireland | OGL v3.0 | open | bulk | NISMR 18,521 |
| HED Archaeological Investigations | Department for Communities | Northern Ireland | not stated | link_only | deeplink, avoid | 3,271 points |
| HED LiDAR surveys | Department for Communities | Northern Ireland | OGL | open | bulk, elevation only | about 40 sites |
| OSNI Townlands (2013) | OSNI | Northern Ireland | OGL | open | bulk, not tested | not recorded |
| trove.scot place pages | Historic Environment Scotland | Scotland | site terms forbid scraping | link_only | deeplink | 335,000 place records |
| Other deep-link sources | various | all five nations | see Deep link only | link_only | deeplink | not counted |

## HES NRHE points zip

A nightly shapefile of every National Record of the Historic Environment site in Scotland, which is the former Canmore index.

| Row | Observation |
|---|---|
| Access | Plain HTTPS download, no authentication. |
| Address | `https://inspire.hes.scot/AtomService/DATA/Canmore_Points.zip`. Atom feed at `https://inspire.hes.scot/AtomService/HES_AtomService.atom.en.xml`. |
| Tested on 2026-11-10 | 200 `application/x-zip-compressed`, 36,018,836 bytes, downloaded and read. Last-Modified 2026-11-09 23:01 GMT, so the file is regenerated nightly. The follow-up also took a HEAD request and saw the same size and date. |
| Format and CRS | Zipped ESRI Shapefile, UTF-8. The DBF is 593 MB uncompressed. EPSG:27700. |
| Licence | Open Government Licence v3.0. The HES portal terms say all spatial downloads are under it except Historic Land-use Assessment. The `LICENCE` field reads "Open Government Licence" on all 314,598 rows. |
| Attribution | "Contains Historic Environment Scotland and OS data © Historic Environment Scotland and Crown Copyright and [database right] (year), licensed under the Open Government Licence v3.0." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 314,598 terrestrial in `Canmore_Points.shp` and 25,913 maritime in `Canmore_Maritime.shp`. The trove.scot download page described the file as "more than 320,000 site locations". |
| Positional precision | `ACCURACY` on the terrestrial records: nearest 1 m 165,836; 10 m 108,877; 100 m 30,236; 1 km 8,416; general location 1,233. That is 53%, 35%, 10%, 2.7% and 0.4%. |
| Paging and limits | Not applicable. No rate limit stated. |
| CORS | Not applicable. |

```
curl -L -A 'Mozilla/5.0 (research)' https://inspire.hes.scot/AtomService/DATA/Canmore_Points.zip
```

Notes:

- The geometry is MultiPoint. The layer is an index only: no description text and no polygons.
- Fields: `CANMOREID`, `SITENUMBER`, `NMRSNAME`, `ALTNAME`, `BROADCLASS`, `SITETYPE`, `COUNTY`, `COUNCIL`, `PARISH`, `ARCHITECTU`, `ARCHAEOLOG`, `FORM`, `GRIDREF`, `ACCURACY`, `URL`, `ENTRYDATE`, `LASTUPDATE`, `XCOORD`, `YCOORD`, `COMPILER`, `LICENCE`. `ARCHAEOLOG` is Y on 174,142 rows. `ARCHITECTU` flags buildings.
- `BROADCLASS` and `SITETYPE` are comma-separated multi-value strings, with 3,308 distinct `BROADCLASS` combinations. They need splitting before they can be used as facets.
- The ISO metadata inside the zip says "UK Open Government Licence" but links to the Non-Commercial Government Licence URL. The portal terms and the per-row field both say OGL. The research suggested getting written confirmation if the service ever became commercial.
- A second attribution wording appears in the follow-up for trove.scot data: "Contains Historic Environment Scotland and Ordnance Survey data © Historic Environment Scotland - Scottish Charity No. SC045925 © Crown copyright and database right [year]".

## HES designation zips

Bulk shapefiles for each Scottish designation type and for properties in care.

| Row | Observation |
|---|---|
| Access | Plain HTTPS download, no authentication. |
| Address | `https://inspire.hes.scot/AtomService/DATA/{name}.zip` where name is `lb_scotland`, `sam_scotland`, `gdl_scotland`, `battlefields_scotland`, `HMPA_scotland`, `ca_scotland`, `WHS` or `pic`. |
| Tested on 2026-11-10 | HEAD on all eight returned 200 `application/x-zip-compressed`. `sam_scotland.zip` was downloaded and read: 11,872,964 bytes, 8,076 records. |
| Format and CRS | Zipped ESRI Shapefile with an attribute schema `.txt`, ISO 19139 metadata and a QGIS `.qml` style. EPSG:27700. Polygons, except listed buildings, which are points plus a boundaries layer. |
| Licence | "UK Open Government Licence v3.0", stated in `Scheduled_Monuments.txt` inside the zip. |
| Attribution | "Contains Historic Environment Scotland and Ordnance Survey data © Historic Environment Scotland - Scottish Charity No. SC045925 © Crown copyright and database right [year]" |
| Reuse class | open |
| Suggested mode | bulk |
| Records | `sam` 8,076. The other sets matched the REST counts in the next section. |
| Positional precision | `PRECISION` field, for example "Within 10m". Digitised on OS MasterMap. |
| Paging and limits | Not applicable. No rate limit stated. |
| CORS | Not applicable. |

```
curl -L -A 'Mozilla/5.0 (research)' https://inspire.hes.scot/AtomService/DATA/sam_scotland.zip
```

Notes:

- Last-Modified was 2026-11-09 for `lb`, `sam`, `gdl`, `battlefields` and `HMPA`, so those refresh nightly. `ca` was 2026-03-11, `WHS` 2024-10-23 and `pic` 2025-09-17.
- The text file in the zip adds "This data is indicative only".
- Conservation areas are compiled from councils and HES says their accuracy is not guaranteed.

## HES Canmore_Points MapServer

An ArcGIS REST service over the same NRHE points as the zip: layer 0 is terrestrial and layer 1 is maritime.

| Row | Observation |
|---|---|
| Access | ArcGIS MapServer query, also WMS. No authentication. Canmore_Points has WMS only, no WFS. |
| Address | `https://inspire.hes.scot/arcgis/rest/services/CANMORE/Canmore_Points/MapServer/{0 or 1}/query` |
| Tested on 2026-11-10 | 200 `application/geo+json`, 1,000 features, `exceededTransferLimit=true`. Size and time not recorded. |
| Format and CRS | JSON, GeoJSON, PBF. Native EPSG:27700. `outSR=4326` returns lon/lat. |
| Licence | Open Government Licence v3.0. |
| Attribution | "Contains Historic Environment Scotland and OS data © Historic Environment Scotland and Crown Copyright and [database right] (year), licensed under the Open Government Licence v3.0." |
| Reuse class | open |
| Suggested mode | live for a map overlay. Use the zip for full loads. |
| Records | 314,598 on layer 0 and 25,913 on layer 1. |
| Positional precision | `ACCURACY` field, as in the zip. |
| Paging and limits | `maxRecordCount` 1000. No rate limit stated. |
| CORS | Yes. `Access-Control-Allow-Origin` echoes the request Origin and allow-credentials is true. |

```
https://inspire.hes.scot/arcgis/rest/services/CANMORE/Canmore_Points/MapServer/0/query?where=1%3D1&geometry=-3.21,55.945,-3.19,55.955&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson
```

Notes:

- Pagination is not supported. `resultOffset` and `resultRecordCount` return 400 "Pagination is not supported." Page with `where=FID>N&orderByFields=FID`. Tested: `FID>1000` returned FIDs 1001 to 2000.
- ArcGIS Server 11.5 on IIS. The layers are shapefile-backed.
- Dates come back as epoch milliseconds. Null dates sometimes appear as -2209161600000, which is 1899-12-30. REST uses 10-character shapefile field names.

## HES_Designations MapServer

All Scottish national designations in one ArcGIS service.

| Row | Observation |
|---|---|
| Access | ArcGIS MapServer query, also WFS and WMS. No authentication. |
| Address | `https://inspire.hes.scot/arcgis/rest/services/HES/HES_Designations/MapServer/{0 to 7}/query` |
| Tested on 2026-11-10 | 200 `application/geo+json`, 36 scheduled monuments in the test box. Size and time not recorded. |
| Format and CRS | JSON, GeoJSON, PBF. Native EPSG:27700. Layer 0 is points and layers 1 to 7 are polygons. |
| Licence | Open Government Licence v3.0. |
| Attribution | "Contains Historic Environment Scotland and OS data © Historic Environment Scotland and Crown Copyright and [database right] (year), licensed under the Open Government Licence v3.0." |
| Reuse class | open |
| Suggested mode | live for overlays. The zips are the bulk route. |
| Records | See the layer table. |
| Positional precision | `PRECISION` field, for example "Within 10m". |
| Paging and limits | `maxRecordCount` 10000. Pagination not supported. |
| CORS | Yes. Echoes the Origin. |

Layers:

| Id | Layer | Count |
|---|---|---|
| 0 | Listed Buildings | 67,478 |
| 1 | Historic MPAs | 27 |
| 2 | Conservation Areas | 670 |
| 3 | Battlefields | 40 |
| 4 | Gardens and Designed Landscapes | 371 |
| 5 | Scheduled Monuments | 8,076 |
| 6 | World Heritage Sites | 10 |
| 7 | Listed Building boundaries | 745 |

```
https://inspire.hes.scot/arcgis/rest/services/HES/HES_Designations/MapServer/5/query?where=1%3D1&geometry=-3.6,56.0,-3.4,56.1&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson
```

Notes:

- Key fields: `DES_REF` with prefixes SM5287, LB172, GDL00381, BTL23, CA138 and WH1, plus `DES_TITLE`, `DES_TYPE`, `DESIGNATED`, `AMENDED`, `LINK`, `CATEGORY`, `LOCAL_AUTH` and `PARISH`. Dates are epoch milliseconds.
- Per-theme services also exist under `/HES/`, including `Properties_in_care_points` with 336 points.

## HES Designations WFS

An OGC WFS 2.0 endpoint over the same designation layers.

| Row | Observation |
|---|---|
| Access | WFS 2.0. No authentication. |
| Address | `https://inspire.hes.scot/arcgis/services/HES/HES_Designations/MapServer/WFSServer` |
| Tested on 2026-11-10 | 200 `application/json`, a GeoJSON FeatureCollection in lon/lat order. Size and time not recorded. |
| Format and CRS | GML or GEOJSON. Native EPSG:27700, 4326 on request. |
| Licence | Open Government Licence v3.0. The capabilities `AccessConstraints` reads "OS Derived data". |
| Attribution | "Contains Historic Environment Scotland and OS data © Historic Environment Scotland and Crown Copyright and [database right] (year), licensed under the Open Government Licence v3.0." |
| Reuse class | open |
| Suggested mode | live |
| Records | As the REST layers. |
| Paging and limits | Not recorded. |
| CORS | Not checked on the WFS path. The REST path on the same host echoed Origin. |

```
https://inspire.hes.scot/arcgis/services/HES/HES_Designations/MapServer/WFSServer?service=WFS&version=2.0.0&request=GetFeature&typeNames=HES_HES_Designations:Scheduled_Monuments&count=1&outputFormat=GEOJSON&srsName=urn:ogc:def:crs:EPSG::4326
```

Notes:

- Type names: `HES_HES_Designations:` followed by `Listed_Buildings_by_Category`, `Historic_Marine_Protected_Areas`, `Conservation_Areas`, `Battlefields_Inventory_Boundary`, `Gardens_and_Designed_Landscapes`, `Scheduled_Monuments`, `World_Heritage_Sites` or `Listed_Buildings_boundaries`.
- WFS field names are the long aliases, for example `DESIGNATION_REFERENCE`, where REST uses `DES_REF`.

## HES map image export

A server-rendered PNG of designation or NRHE layers for any Web Mercator box, tested as an overlay source.

| Row | Observation |
|---|---|
| Access | ArcGIS MapServer `export`. WMS also available. No authentication. |
| Address | `https://inspire.hes.scot/arcgis/rest/services/HES/HES_Designations/MapServer/export` |
| Tested on 2026-11-10 | 200 `image/png`, 1,221 bytes, monuments visibly drawn. A Canmore_Points export in EPSG:3857 also worked and gave a 28 KB PNG for central Edinburgh. |
| Format and CRS | PNG. Native EPSG:27700. |
| Licence | Open Government Licence v3.0. |
| Attribution | "Contains Historic Environment Scotland and OS data © Historic Environment Scotland and Crown Copyright and [database right] (year), licensed under the Open Government Licence v3.0." |
| Reuse class | open |
| Suggested mode | live |
| Records | Raster rendering. |
| Paging and limits | No rate limit stated. Not a tile cache: `singleFusedMapCache=false`. |
| CORS | Yes, observed on the REST query. |

```
https://inspire.hes.scot/arcgis/rest/services/HES/HES_Designations/MapServer/export?bbox=-390000,7550000,-380000,7560000&bboxSR=3857&imageSR=3857&size=256,256&format=png32&transparent=true&layers=show:5&f=image
```

Notes:

- The HES_Designations WMS advertised only CRS:84, EPSG:4326 and EPSG:27700. A GetMap in EPSG:3857 returned a blank 888-byte PNG. EPSG:27700 drew features.

## Scottish Radiocarbon Index, ArcGIS layer

Point index of Scottish sites that have radiocarbon determinations, linked to their NRHE record.

| Row | Observation |
|---|---|
| Access | ArcGIS MapServer query, also WFS and WMS. No authentication. |
| Address | `https://inspire.hes.scot/arcgis/rest/services/CANMORE/Scottish_Radiocarbon_Index/MapServer/0/query` |
| Tested on 2026-11-10 | 200 `application/json`. Size and time not recorded. |
| Format and CRS | JSON, GeoJSON, PBF, GML. Native EPSG:27700. Points. |
| Licence | The service itself stated none: `copyrightText` read "HES" and data.gov.uk listed no licence. The follow-up found the trove.scot download page saying "Open Government Licence v3 (OGL)" and the catalogue record saying "No limitations to public access". The first report called the licence unverified. The follow-up's reading is given here. |
| Attribution | "Contains Historic Environment Scotland and Ordnance Survey data © Historic Environment Scotland - Scottish Charity No. SC045925 © Crown copyright and database right [year]" |
| Reuse class | open |
| Suggested mode | bulk, though the spreadsheet in the next section is the larger set. |
| Records | 952. |
| Positional precision | `ACCURACY` field, for example "NGR given to the nearest 10m". |
| Paging and limits | `maxRecordCount` 1500. Pagination not supported, so page by a FID range. |
| CORS | Yes. Reflects the Origin, credentials allowed. |

```
https://inspire.hes.scot/arcgis/rest/services/CANMORE/Scottish_Radiocarbon_Index/MapServer/0/query?where=FID%3C3&outFields=*&outSR=4326&f=geojson
```

Notes:

- The service description said it was "relatively complete up to 2005". The trove.scot page said the index "has not been systematically updated since 2009".
- Fields: `CANMOREID`, `SITENUMBER`, `NMRSNAME`, `SITETYPE`, `COUNCIL`, `PARISH`, `GRIDREF`, `ACCURACY`, `URL`, `URL_C14`, `X`, `Y`.
- This is an older and smaller set than the spreadsheet, which covered 968 sites.

## Scottish Radiocarbon Index spreadsheet

Every determination in the index, with lab code, age, material, context and site location. It exists only on trove.scot.

| Row | Observation |
|---|---|
| Access | Download page on trove.scot. A browser is needed. |
| Address | Index page `https://www.trove.scot/explore/download-our-data`. File `https://www.trove.scot/media/y3nlhgcd/scottish-radiocarbon-database-with-location.xlsx`. A second file, `/media/hhjbqzta/scottish-c14-site-locations.zip`, was named. |
| Tested on 2026-11-10 | All three `/media/` files returned 403 to curl. The page and the spreadsheet were read from the Wayback Machine capture of 2026-04-28, 1,470,113 bytes. The follow-up did not open the site locations zip. |
| Format and CRS | XLSX, 42 columns, 2 sheets. Point via `X` and `Y`. EPSG:27700. |
| Licence | "Open Government Licence" in the `Licence` column of the file. The page said "This data is available under the Open Government Licence v3 (OGL)." |
| Attribution | "Contains Historic Environment Scotland and Ordnance Survey data © Historic Environment Scotland - Scottish Charity No. SC045925 © Crown copyright and database right [year]" |
| Reuse class | open |
| Suggested mode | deeplink. The research suggested a manual browser download for bulk ingest. trove.scot blocked scripts and its terms forbade text and data mining and scraping, so the script-blocking rule gives deeplink until HES confirms in writing |
| Records | 5,414 determinations at 968 sites. 5,089 had `X`, `Y` and a trove place URL, so 325 rows had no site location. |
| Paging and limits | Not applicable. |
| CORS | Not applicable. |

```
https://web.archive.org/web/20260428211125id_/https://www.trove.scot/media/y3nlhgcd/scottish-radiocarbon-database-with-location.xlsx
```

Notes:

- Key columns: `Numlink` (the NRHE ID), `Lab Analysis Id`, `Material`, `Lab Age`, `Lab error`, `Calibrated Date`, `Delta 13c`, `Sample Desc`, `X`, `Y`, `URL`, `Licence`.
- The `/media/` path segments are content hashes that change on re-upload, so any link must be taken from the download page.
- The Wayback copy was a stopgap. The research suggested a fresh browser download.

## NRHE Areas polygons

Polygons for the known extent of NRHE sites, titled "Defining Scotland's Places". They carry no legal status. This is the only Scottish site-extent data and it could not be fetched by script.

| Row | Observation |
|---|---|
| Access | Download page on trove.scot. A browser is needed. |
| Address | Index page `https://www.trove.scot/explore/download-our-data`. File link seen in the 2026-04-28 Wayback capture: `/media/5mapdvkk/nrhe_areas.zip`. |
| Tested on 2026-11-10 | The trove.scot page returned 403 (Azure WAF JavaScript challenge). The file returned 403 to curl. The catalogue link `https://www.historicenvironment.scot/media/e04lsbyn/nrhe_areas.zip` returned a genuine 404. No copy was in the Wayback Machine. The file was never downloaded. |
| Format and CRS | Zipped ESRI shapefile with layer file and metadata. EPSG:27700. Polygons. |
| Licence | The download page said "Open Government Licence v3 (OGL)". The catalogue record said "UK Open Government Licence" with attribution worded for OGL v1.0. The follow-up read the page in Wayback, which the first report could not do. |
| Attribution | "Contains public sector information licensed under the Open Government Licence v1.0 and contains Ordnance Survey data © Crown copyright and database right [year]". The research suggested using the stricter wording until HES confirmed. |
| Reuse class | open |
| Suggested mode | deeplink. The research suggested a manual versioned ingest from a browser download. The trove.scot rule above applies |
| Records | The page said "incomplete, containing polygons for more than 100,000 sites so far", dated 2026-04-28. The first report gave about 125,000 from an old Canmore page. The count is unverified. |
| Paging and limits | Not applicable. |
| CORS | Not applicable. |

Notes:

- The file was not in the HES Atom feed, on the HES ArcGIS server, on PastMap or on ArcGIS Online.
- The HES portal downloads page said that NRHE Areas and the radiocarbon data are downloadable only from trove.scot.

## Spatial Hub council HERs

The Improvement Service's amalgamation of Scottish council HER sites and events. Avoid.

| Row | Observation |
|---|---|
| Access | WFS, CSV, Shapefile and GeoJSON, behind an account or auth key. |
| Address | `https://data.spatialhub.scot/dataset/historic_environment_records-is`. WFS listed at `https://geo.spatialhub.scot/geoserver/sh_her/wfs` with type names `sh_her:pub_herst` (sites) and `sh_her:pub_herev` (events). |
| Tested on 2026-11-10 | The dataset page and the CKAN metadata returned 200. The WFS was not tested because it needs an auth key. |
| Format and CRS | EPSG:27700. |
| Licence | "Restricted", CKAN licence `other-closed`. Available to PSGA members or UK academics via Digimap and "not currently commercially available". |
| Reuse class | link_only |
| Suggested mode | deeplink, in practice nothing to link to. Avoid. |
| Records | Not recorded. Updated quarterly, last 2026-11-06. |

Notes:

- For Edinburgh, Dundee, Falkirk, Fife, Inverclyde, North Lanarkshire and Orkney the layer is just Canmore data. Seven planning authorities have no HER of their own.

## Historic Land-use Assessment

A polygon map of historic land-use types across Scotland. Avoid.

| Row | Observation |
|---|---|
| Access | Download after registration. |
| Address | `https://hlamap.org.uk/data-download/data-download-form`. Viewer at `https://map.hlamap.org.uk/`. |
| Tested on 2026-11-10 | The hlamap.org.uk home page and the viewer returned 200. The download was not attempted because it needs registration. |
| Licence | End User Licence. The HES portal terms explicitly exclude it from the OGL. |
| Reuse class | link_only |
| Suggested mode | deeplink. Avoid. |
| Records | Not recorded. |

## Cadw Scheduled Monuments

Scheduled monument polygons with bilingual name, class, period, site type and a link to the full Cadw report. It is served from DataMapWales, one GeoServer for all Welsh Government layers.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on GeoServer. No authentication. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type name `inspire-wg:Cadw_SAM`. Metadata at `https://datamap.gov.wales/layers/inspire-wg:Cadw_SAM`. |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8`, 62 matched in the test box. A full export without `count` returned 4,239 features, 26 MB, in 5 s. |
| Format and CRS | GeoJSON, GML, CSV, SHAPE-ZIP, GeoPackage, KML. Native EPSG:27700. MultiPolygon. |
| Licence | Open Government Licence v3.0. The metadata said "There are no use restrictions on this data". |
| Attribution | "Designated Historic Asset GIS Data, The Welsh Historic Environment Service (Cadw), DATE [the date that you received the data from Cadw], licensed under the Open Government Licence http://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/" |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 4,239. |
| Paging and limits | WFS `CountDefault` 1,000,000, so a whole layer came back in one request. No rate limit stated. `startIndex` with `sortBy`, and `cql_filter`, both worked. |
| CORS | Yes, `Access-Control-Allow-Origin: *`. |

```
https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=inspire-wg:Cadw_SAM&count=2&outputFormat=application/json&srsName=EPSG:4326&bbox=270000,200000,290000,220000,EPSG:27700
```

Notes:

- Fields: `RecordNumber`, `SAMNumber` (for example GM396), `Name`, `Name_cy`, `DesignationDate`, `BroadClass` and `BroadClass_cy`, `Period` and `Period_cy`, `SiteType` and `SiteType_cy`, `UnitaryAuthority` and `UnitaryAuthority_cy`, `Community`, `Report`, `easting`, `northing`.
- The layer was last updated 2026-07-18.
- The attribution wording requires the date OpenAntiquity received the data from Cadw, so the research suggested storing a retrieval date per ingest.
- `srsName=EPSG:4326` returned lon/lat GeoJSON. One endpoint served 1,502 feature types. Layer metadata, including licence text, was at `https://datamap.gov.wales/api/v2/layers?filter{alternate}={typename}`. The response starts with a UTF-8 BOM.
- Cadw and HED boundaries are indicative. The legal record is the designation document.

## Cadw Listed Buildings

Listed building points with grade, location text, class and report links.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on DataMapWales. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type name `inspire-wg:Cadw_ListedBuildings` |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8`, 130 matched in the test box. |
| Format and CRS | GeoJSON, GML, CSV, SHAPE-ZIP, GeoPackage. EPSG:27700. MultiPoint. |
| Licence | Open Government Licence v3.0. |
| Attribution | As for Cadw Scheduled Monuments. |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 30,110. |
| CORS | Yes, `*`. |

```
https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=inspire-wg:Cadw_ListedBuildings&count=2&outputFormat=application/json&srsName=EPSG:4326&bbox=270000,200000,290000,220000,EPSG:27700
```


## Cadw Registered Historic Parks and Gardens

Statutory register boundaries with grade, main phase and site type.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on DataMapWales. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type name `geonode:cadw_rhpg_registeredareas`. A companion layer `geonode:cadw_rhpg_significantviews` exists. |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8`, 2 matched in the test box. |
| Format and CRS | GeoJSON, GML, CSV, SHAPE-ZIP, GeoPackage. EPSG:27700. MultiPolygon. |
| Licence | Open Government Licence v3.0. |
| Attribution | As for Cadw Scheduled Monuments. |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 385. |
| CORS | Yes, `*`. |

```
https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:cadw_rhpg_registeredareas&count=2&outputFormat=application/json&srsName=EPSG:4326&bbox=270000,200000,290000,220000,EPSG:27700
```

Notes:

- The Welsh text in `site_type_cy` is mojibake in the source.

## Cadw Registered Historic Landscapes

The non-statutory Register of Landscapes of Outstanding and of Special Historic Interest in Wales, compiled with NRW and ICOMOS UK.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on DataMapWales. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type name `inspire-wg:Cadw_HistoricLandscapes` |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8`, 1 matched in the test box. |
| Format and CRS | GeoJSON, GML, CSV, SHAPE-ZIP, GeoPackage. EPSG:27700. MultiPolygon. |
| Licence | Open Government Licence v3.0. |
| Attribution | As for Cadw Scheduled Monuments. |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 58. |
| CORS | Yes, `*`. |

```
https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=inspire-wg:Cadw_HistoricLandscapes&count=2&outputFormat=application/json&srsName=EPSG:4326&bbox=270000,200000,290000,220000,EPSG:27700
```

Notes:

- Fields: `RecordNumber` (for example "HLW (D) 1"), `Name`, `Name_cy`, `DesignationDate` (a year), `RegisterType` (Outstanding or Special), `Report`. The `Report` URL contains spaces and needs encoding.

## Other Cadw heritage layers

World Heritage Site boundaries, protected wrecks, Cadw guardianship monuments and conservation area boundaries, all on DataMapWales.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on DataMapWales. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type names as in the table below. |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8` for all four. |
| Format and CRS | GeoJSON, GML, CSV, SHAPE-ZIP, GeoPackage. EPSG:27700. |
| Licence | Protected wrecks carried the Cadw wording "no use restrictions". The WHS, guardianship and conservation area layers carried no licence statement in their metadata. Heneb's Archwilio data-sources page listed the Cadw WHS and conservation area layers as OGL, which is not the publisher's own statement. The critic report confirmed these three layers were still unresolved. |
| Attribution | "Designated Historic Asset GIS Data, The Welsh Historic Environment Service (Cadw), DATE, licensed under the Open Government Licence v3.0". The research marked this as confirmed for wrecks and assumed for the others. |
| Reuse class | open for wrecks. Not stated for the other three layers. |
| Suggested mode | bulk for wrecks. Live for the other three until Cadw confirms the licence. |
| CORS | Yes, `*`. |

| Layer | Type name | Count | Geometry |
|---|---|---|---|
| World Heritage Sites | `inspire-wg:vGeoServer_WorldHeritageSites_Public` | 12 component polygons | polygons |
| Protected wrecks | `inspire-wg:Cadw_DesignatedWrecks` | 6 | polygons |
| Guardianship monuments | `geonode:cadw_guardianshipmonuments` | 133 | points |
| Conservation areas | `geonode:conservation_areas_wales` | 531 | multipolygons |

```
https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=inspire-wg:vGeoServer_WorldHeritageSites_Public&count=2&outputFormat=application/json&srsName=EPSG:4326
```

Notes:

- DataMapWales had no Welsh battlefields layer. The RCAHMW battlefields site `battlefields.rcahmw.gov.uk` did not connect on 2026-11-10.

## NMRW terrestrial sites (Coflein index)

The point index of National Monuments Record of Wales sites with NPRN, name, site type, period, evidence, grid reference and Coflein URL. This is the Welsh equivalent of the Scottish NRHE points.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on DataMapWales. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type name `geonode:rcahmw_nmrw_terrestrialsites_rcahmw_bng` |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8`, 1,572 matched in the test box. |
| Format and CRS | GeoJSON, GML, CSV, SHAPE-ZIP, GeoPackage. EPSG:27700. Points. |
| Licence | Open Government Licence v3.0. RCAHMW's legal page said "Site data held on Coflein, the Historic Wales portal and Data Map Wales is freely available under the Open Government Licence." |
| Attribution | "This site data is from the National Monuments Record of Wales (NMRW), produced by the Royal Commission on the Ancient and Historical Monuments of Wales (RCAHMW). © Crown Database Right: RCAHMW, licensed under the Open Government Licence 3.0." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 112,894. |
| Positional precision | The `location` field described the grid reference basis, for example "Grid reference taken at centre of site". |
| Paging and limits | No rate limit stated. `count=3&startIndex=50000&sortBy=nprn` worked. CQL worked: `site_type LIKE '%HILLFORT%'` matched 390. |
| CORS | Yes, `*`. |

```
https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:rcahmw_nmrw_terrestrialsites_rcahmw_bng&count=2&outputFormat=application/json&srsName=EPSG:4326&bbox=270000,200000,290000,220000,EPSG:27700
```

Notes:

- Fields: `nprn`, `name`, `site_type`, `period`, `evidence`, `osgb_ngr`, `mapsheet`, `kmsq`, `community`, `unitary_au`, `old_county`, `location`, `lastupdate`, `lat`, `long`, `url`, `osgb36east`, `osgb36notr`, plus Welsh `hen_sir`, `awdurdud_u`, `cyfnod`, `math_o_saf`. No description text.
- The layer was updated 2026-02-12.
- The ADS and ARIADNE copy of these records was labelled "CC BY NC ND", where DataMapWales stated OGL v3. The critic report said to ingest from DataMapWales.

## NMRW maritime sites

Maritime NMRW records such as wrecks and aircraft losses.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on DataMapWales. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type name `geonode:nmrw_maritimesites_rcahmw_wgs84` |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8`. |
| Format and CRS | GeoJSON, GML, CSV, SHAPE-ZIP, GeoPackage. EPSG:4326. Points. |
| Licence | Open Government Licence v3.0. |
| Attribution | "This site data is from the National Monuments Record of Wales (NMRW), produced by the Royal Commission on the Ancient and Historical Monuments of Wales (RCAHMW). © Crown Database Right: RCAHMW, licensed under the Open Government Licence 3.0." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 8,612. |
| Positional precision | Varies with the source material. |
| CORS | Yes, `*`. |

```
https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:nmrw_maritimesites_rcahmw_wgs84&count=2&outputFormat=application/json&srsName=EPSG:4326
```

Notes:


## RCAHMW Historic Place Names

Georeferenced historic place and field names with source, date and confidence.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on DataMapWales. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type name `geonode:rcahmw_historicplacenames_wales_recordednames` |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8`, 10,342 matched in the test box. |
| Format and CRS | GeoJSON, GML, CSV, SHAPE-ZIP, GeoPackage. EPSG:27700. Points. |
| Licence | Open Government Licence v3.0. |
| Attribution | "This data is from the List of Historic Place Names in Wales, produced by the Royal Commission on the Ancient and Historical Monuments of Wales (RCAHMW). © Crown Database Right: RCAHMW, licensed under the Open Government Licence 3.0." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 666,308. |
| Positional precision | `loc_conf`, for example "Within 100m". |
| Paging and limits | Page with `sortBy` plus `startIndex`. |
| CORS | Yes, `*`. |

```
https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:rcahmw_historicplacenames_wales_recordednames&count=2&outputFormat=application/json&srsName=EPSG:4326&bbox=270000,200000,290000,220000,EPSG:27700
```

Notes:

- Fields include `enw_name`, `place_type`, `blwgyn_eye` (a year), `cyfgr_grrf`, `parish`, `county`, `prim_srce`, `sec_srce`, `nodi_notes`, `url_en`, `url_cy`.
- The layer is updated quarterly. Names such as "Banwen, Cae/Field, 1841" can help interpret earthworks.

## DataMapWales WMS

A WMS rendering of any DataMapWales layer, including the Cadw and RCAHMW ones above.

| Row | Observation |
|---|---|
| Access | WMS 1.3.0 on the same GeoServer. No authentication. |
| Address | `https://datamap.gov.wales/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers={layer}&styles=&crs=EPSG:3857&bbox={bbox}&width=256&height=256&format=image/png&transparent=true` |
| Tested on 2026-11-10 | 200 `image/png`, 4,794 bytes. |
| Format and CRS | PNG. Native EPSG:27700, EPSG:3857 supported. |
| Licence | As per layer. |
| Reuse class | open, subject to the layer |
| Suggested mode | live |
| Paging and limits | No rate limit stated. The usage policy targets 99% availability. |
| CORS | Yes, `*`. |

```
https://datamap.gov.wales/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=inspire-wg:Cadw_SAM&styles=&crs=EPSG:3857&bbox=-430000,6740000,-410000,6760000&width=256&height=256&format=image/png&transparent=true
```

Notes:

- The GeoWebCache WMTS path `/geoserver/gwc/service/wmts` returned 400, so WMS is the route. `lle.gov.wales` redirects to DataMapWales. The capabilities held 2,064 layers.

## Woodland Opportunity Map HER features

Buffered polygons flagging mapped HER features, derived from Welsh Archaeological Trust (now Heneb) data. Avoid.

| Row | Observation |
|---|---|
| Access | WFS 2.0 on DataMapWales. |
| Address | `https://datamap.gov.wales/geoserver/ows`, type name `geonode:wom_historic_environment_feature`. `geonode:GWC21_Historic_Environment_Feature` is an identical copy. |
| Tested on 2026-11-10 | 200 `application/json;charset=UTF-8`, 1,031 matched in the test box. |
| Format and CRS | GeoJSON and others. EPSG:27700. MultiPolygon, amalgamated management areas. |
| Licence | No licence statement in the metadata. The stated purpose was "created for the Woodland Opportunity Map (WOM) only, and may not reflect the most current dataset". |
| Reuse class | link_only |
| Suggested mode | deeplink, in practice nothing to link to. Avoid. |
| Records | 48,841. |
| CORS | Yes, `*`. |

Notes:

- Fields: `objectid`, `wat` (CPAT, DAT, GAT or GGAT), `shape_length`, `shape_area`. There is no PRN, so a record cannot be linked to Archwilio.

## HED GIS Data FeatureServer

The authoritative monthly snapshot of 14 Historic Environment Division layers, hosted on ArcGIS Online. HED said users were strongly encouraged to use the web service.

| Row | Observation |
|---|---|
| Access | ArcGIS FeatureServer. No authentication. |
| Address | `https://services2.arcgis.com/BdBkthNLO9mzGAMO/arcgis/rest/services/Historic_Environment_Division_GIS_Data/FeatureServer/{layer}/query` |
| Tested on 2026-11-10 | 200 `application/json; charset=utf-8`, a GeoJSON FeatureCollection with 115 SMR points in the test box. Size and time not recorded. |
| Format and CRS | JSON, GeoJSON, PBF. EPSG:29902 (wkid 29900, latestWkid 29902, Irish Grid). `outSR=4326` returns lon/lat. Points, except polygons for layers 6, 7, 8, 9 and 10. |
| Licence | "UK Open Government Licence (OGL) v3.0", per the OpenDataNI dataset "Historic Environment Division ESRI REST API". |
| Attribution | No bespoke statement was published. The layer `copyrightText` read "Historic Environment Division, Department for Communities". The research suggested adding the standard OGL v3.0 acknowledgement. |
| Reuse class | open |
| Suggested mode | bulk |
| Records | See the layer table. |
| Positional precision | `Located` field on the SMR. 1,709 records were "Unlocated" and still had point geometry. |
| Paging and limits | `maxRecordCount` 2000. `resultOffset` paging worked: offset 18000 returned the last 521. No rate limit stated. |
| CORS | Yes, `Access-Control-Allow-Origin: *`. |

Layers. Id 11 was not reported by the research.

| Id | Layer | Count |
|---|---|---|
| 0 | SMR | 18,521 |
| 1 | Historic Buildings | 15,884 |
| 2 | Industrial Heritage | 15,788 |
| 3 | Heritage at Risk | 1,617 |
| 4 | Defence Heritage | 4,611 |
| 5 | Ship Wrecks | 461 |
| 6 | Areas of Archaeological Potential | 132 |
| 7 | Areas of Significant Archaeological Interest | 12 |
| 8 | Battlesites | 324 |
| 9 | Historic Parks, Gardens and Demesnes | 252 |
| 10 | Scheduled Zones | 2,099 |
| 12 | Aircraft Wrecks | 13 |
| 13 | Logboats | 230 |
| 14 | Gazetteer of Historic Nucleated and Urban Settlements | 672 |

```
https://services2.arcgis.com/BdBkthNLO9mzGAMO/arcgis/rest/services/Historic_Environment_Division_GIS_Data/FeatureServer/0/query?where=1%3D1&geometry=-6.75,54.32,-6.65,54.38&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson
```

Notes:

- The service description read "Current update published 3rd November 2026". Updates are monthly.
- SMR fields: `MONID`, `SMRNo` (for example ARM012:109), `Townland_s_`, `Edited_Type`, `General_Type`, `General_Period`, `Protection`, `Grid_Reference`, `Council`, `Located`, `X`, `Y`.
- Scheduled Zones fields: `SMNO`, `EDITED_TYP`, `Consult_zo`, `Date_added`. HED called scheduled zones "an indicative dataset only". Official scheduling declarations come from HERoNI.
- The Historic Buildings layer mixed listed buildings with records that were not listed. `CurrentGra`: Record Only 6,183; B2 3,844; B1 3,437; B 1,018; B+ 679; D1 Record Only 491; A 224; Delisted 8. About 9,200 were actually listed, so grade must be checked before a record is called listed.
- `HED_Consultation_Zones` is a sibling service. The same ArcGIS organisation exposed many draft, backup and dated services. Only the service above was the official one, and pointing at another would load stale or unofficial data.

## OpenDataNI HED bulk downloads

Shapefile and GeoJSON downloads of the same HED datasets, through the OpenDataNI CKAN catalogue.

| Row | Observation |
|---|---|
| Access | CKAN API and direct file download. No authentication. |
| Address | `https://admin.opendatani.gov.uk/api/3/action/package_show?id={dataset}`. Dataset ids: `northern-ireland-sites-and-monuments-record`, `scheduled-historic-monument-areas`, `listed-buildings-northern-ireland`, `industrial-heritage-record`, `defence-heritage`, `historic-parks-and-gardens`, `areas-of-archaeological-potential`, `areas-of-significant-archaeological-interest`, `logboatrecord-ni`, `gazetteer-of-historic-nucleated-and-urban-settlements`. |
| Tested on 2026-11-10 | The NISMR GeoJSON `https://admin.opendatani.gov.uk/dataset/46240fa5-db15-469e-b1c8-0460504b951c/resource/a2af36e6-d3f0-4abc-9314-b1b72d5a9e06/download/nismr_05112026.geojson` returned 200 `application/geo+json`, 7,215,463 bytes, 18,521 features. |
| Format and CRS | GeoJSON and zipped Shapefile. The GeoJSON declared EPSG:29902 and the coordinates were Irish Grid metres, not lon/lat. |
| Licence | "UK Open Government Licence (OGL) v3.0", `https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/` |
| Attribution | None specified beyond OGL. |
| Reuse class | open |
| Suggested mode | bulk. The FeatureServer is the route HED recommends. |
| Records | NISMR 18,521. Protection: Scheduled 2,065; State Care and Scheduled 105; State Care 98. Located: Unlocated 1,709. |
| CORS | Yes, `*` on the CKAN API. |

Notes:

- File names carry the publication date, for example `nismr_05112026.geojson`. A fixed URL would break each month, so the research suggested resolving the address through CKAN `package_show` on every run.
- Field names are shapefile-truncated (`Townland_s`, `Edited_Typ`, `General_Ty`, `General_Pe`, `Grid_Refer`), unlike the FeatureServer.

## HED Archaeological Investigations

Excavation and investigation points with summaries, their extent polygons, and World Heritage Site boundaries used by the HED Map Viewer. Avoid until HED agrees.

| Row | Observation |
|---|---|
| Access | ArcGIS FeatureServer, publicly reachable. |
| Address | `https://services2.arcgis.com/BdBkthNLO9mzGAMO/arcgis/rest/services/Archaeological_Investigations/FeatureServer/{0 or 1}/query` and `https://services2.arcgis.com/BdBkthNLO9mzGAMO/arcgis/rest/services/World_Heritage_Sites/FeatureServer/0/query` |
| Tested on 2026-11-10 | 200 `application/json`, 786 points in the test box. |
| Format and CRS | JSON, GeoJSON, PBF. EPSG:29902. Points and MultiPolygons. |
| Licence | Not stated. HED said the layer "is not currently available through via our web service or as a standalone download". It was not listed on OpenDataNI and not covered by the OGL statement. |
| Reuse class | link_only |
| Suggested mode | deeplink, in practice nothing to link to. Ask HED first. |
| Records | Investigations 3,271 points and 3,377 extents. World Heritage Sites 2. |
| Positional precision | `POSITIONAL_ACCURACY` and `CAPTURE_SCALE` fields. |
| CORS | Yes, `*`. |

```
https://services2.arcgis.com/BdBkthNLO9mzGAMO/arcgis/rest/services/Archaeological_Investigations/FeatureServer/0/query?where=1%3D1&geometry=-7.0,54.2,-6.0,54.7&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&f=geojson
```

Notes:

- The `LICENCE` field holds excavation licence numbers such as AE/00/016, not a data licence.

## HED LiDAR surveys of archaeological sites

Site-specific LiDAR for about 40 Northern Irish monuments, flown 2008 to 2014. It is not a record source. It is listed because it belongs in the LIDAR pages.

| Row | Observation |
|---|---|
| Access | Zip per site, plus ArcGIS cached tile services. |
| Address | `https://opendatani.blob.core.windows.net/archaeologylidar/{Site}.zip` and `https://tiles.arcgis.com/tiles/BdBkthNLO9mzGAMO/arcgis/rest/services/{Site}_DTM/MapServer` |
| Tested on 2026-11-10 | Zip HEAD returned 200 `application/zip`, Navan 1,700,932,038 bytes. Tile service metadata returned 200 JSON. Zip contents and individual tiles were not fetched. |
| Format and CRS | Zip with contents not inspected. Cached raster tiles in the Irish Grid scheme, 15 levels, EPSG:29902, not Web Mercator. |
| Licence | "UK Open Government Licence (OGL)", per the OpenDataNI datasets "Historic Environment Division Lidar 2008/2009/2012/2013/2014". |
| Reuse class | open |
| Suggested mode | bulk, as elevation data |
| Records | About 40 sites, including Navan, Tullaghoge, Dunluce, Devenish, the Dorsey and Black Pig's Dyke. |
| CORS | Not checked. |

Notes:

- The tiles are not Web Mercator, so MapLibre would need reprojected copies.

## OSNI Townlands (2013)

A townland boundary dataset on OpenDataNI. It was found by the critic report and not tested.

| Row | Observation |
|---|---|
| Access | OpenDataNI CKAN. |
| Address | The dataset "OSNI Open Data - Largescale Boundaries - Townlands (2013)" was seen in the CKAN API listing. |
| Tested on 2026-11-10 | Not tested. The listing was seen and the file was not downloaded. |
| Licence | OGL, from the listing. |
| Reuse class | open |
| Suggested mode | bulk |
| Records | Not recorded. |

Notes:

- The critic report also found 12 OpenDataNI datasets of "OSNI Open Data - Historical Six Inch to One Mile County Series", Edition 1 (1829 to 1835) and Edition 2 (1838 to 1862), under OGL, as zipped sheet scans of roughly 0.3 to 0.5 GB per zip. They were not assessed.

## Deep link only

These sources cannot be read by script, or their terms forbid it, or they carry no reuse licence. Decision 0007 has OpenAntiquity store the identifier and the address and nothing else. The tests of 2026-11-10 are in the notes below: all patterns returned 200 except where stated.

| Source | Link pattern |
|---|---|
| trove.scot place page | `https://www.trove.scot/place/{CANMOREID}` |
| trove.scot map search | `https://www.trove.scot/search/map?q=*&page_type=Places&coords={easting},{northing},{zoom}` |
| canmore.org.uk legacy link | `https://canmore.org.uk/site/{id}` |
| HES Portal designation | `https://portal.historicenvironment.scot/designation/{DES_REF}` |
| PastMap | `https://pastmap.org.uk/map` |
| Highland council HER | `https://her.highland.gov.uk/monument/{MHGnnnn}` |
| Treasure Trove Scotland | `https://treasuretrovescotland.co.uk/search/object-detail?id={internal id}` |
| Coflein site page | `https://coflein.gov.uk/en/site/{NPRN}` |
| Cadw full report | `https://cadwpublic-api.azurewebsites.net/reports/{type}/FullReport?lang={en or cy}&id={RecordNumber}` |
| Archwilio | `https://archwilio.org.uk/arch/query/page.php?watprn={PRN}` |
| NISMR record | `https://apps.communities-ni.gov.uk/NISMR-public/Details.aspx?MonID={MONID}` |
| NI Buildings record | `https://apps.communities-ni.gov.uk/Buildings/buildview.aspx?id={MainID}&js=false` |
| NI Heritage at Risk record | `https://apps.communities-ni.gov.uk/HARNI/barniview.aspx?id={Main_ID}&js=false` |
| Isle of Man HER | `https://isleofmanher.im/report/{resourceinstanceid}` |
| Jersey HER | `https://her.jerseyheritage.org/report/{resourceinstanceid}` |

### trove.scot and Canmore

Canmore's successor is run by Historic Environment Scotland. The state found on 2026-11-10 was as follows.

- `canmore.org.uk` was retired. Every path returned 301 to the same path on `www.trove.scot`, including `/site/{id}`, `/collection/{id}`, `/c14index/{id}/` and `/content/data-downloads`. The redirect host was not challenged. The first report had not tested whether `/site/` resolved. The follow-up found that `https://www.trove.scot/site/{id}` gave 308 to `/place/{id}` in Wayback captures of 2025-10-12 and 2026-05-16.
- The HES retired-services page said Canmore's Places and Archive records were now on trove.scot. A web search summary gave a February 2025 launch and a Canmore switch-off on 24 June 2025, unconfirmed on an HES page.
- `https://www.trove.scot/` and `/explore/download-our-data` returned 403 with an "Azure WAF JS Challenge" page to curl and to WebFetch. The challenge also covered `robots.txt` and file downloads. No API was found.
- A retry with a browser-like User-Agent was blocked by the permission classifier as bot-check circumvention and was not pursued. Nothing else was tried to get past the challenge.
- The place pattern was confirmed three ways: the `URL` column of HES's radiocarbon spreadsheet, the PastMap code line `featureObj.Url = '//www.trove.scot/place/'+feature.get('ID')`, and the redirects. The home page gave 335,000 place records in a Wayback capture of 2026-10-09.
- Terms, last updated 15 July 2024, read from Wayback of 2025-02-14. Clause 7.1: "You shall not conduct, facilitate, authorise or permit any text or data mining or web scraping in relation to the Website". Clause 9.7: "Spatial data is licensed for use under the Open Government Licence." Clause 14.1: "You may link to the Website, provided you do so in a way that is fair and legal and does not damage our reputation or take advantage of it." Clause 14.3: "The Website must not be framed on any other website." Clause 6.1 still held an unfilled placeholder for licence descriptions.
- Downloads that needed a browser: NRHE Areas, the radiocarbon spreadsheet and the radiocarbon site locations zip. Downloads that worked with curl: Canmore_Points.zip and the designation zips on `inspire.hes.scot`.

### Other Scottish records

- HES Portal: the `LINK` field in the designation data already held the portal address. Conservation area `LINK` values pointed to council pages and World Heritage Site values to `historicenvironment.scot`. Portal terms allowed material for private or non-commercial use.
- PastMap is a Drupal 10 site on OpenLayers 3. Its HER layers loaded through same-origin proxies, which the research did not call. `/her-participation` listed each council's contribution as FULL or NONE. Dundee, Fife and Inverclyde contributed nothing. The terms said "intended for information only", with no reuse licence for HER layers.
- Council HERs in use: Highland, Aberdeenshire (also covering Moray, Angus and Aberdeen City), Western Isles and WoSAS. The first three ran HBSMR Web v8 from Exegesis or Idox. Only the Highland pattern was fetched. `johngraycentre.org`, for East Lothian and Midlothian, returned 403. Records are the council's copyright with no open licence stated.
- Treasure Trove Scotland ran a public database for 2020 to 2026. Search was a multipart POST form. Detail pages gave no findspot, only local authority, town and parish. A search for "brooch" returned 265 rows and internal ids from 481 to 14674 were seen. There was no export, API or licence statement. `robots.txt` set Crawl-Delay: 5. The follow-up suggested treating it as all rights reserved. Northern Ireland had no finds dataset.

### Welsh records

- Coflein had no public API. `robots.txt` carried Content-Signal `search=yes`, `ai-train=no`, `use=reference` and disallowed named AI crawlers including ClaudeBot, so the research said not to crawl and to use the DataMapWales index. Archive material was Crown copyright under the Non-commercial Government Licence, or third-party. Attribution given: "© Crown: Royal Commission on the Ancient and Historical Monuments of Wales: archive number".
- Cadw full reports (Cof Cymru): `{type}` was `sam`, `listedbuilding`, `parkgarden`, `historiclandscape`, `worldheritagesite` or `wreck`, and the first three were tested. The `id` is `RecordNumber`, not `SAMNumber`. The `Report` field in the data used `http://`, which redirected to https. Output was HTML only and the root, `/api` and `/swagger` returned 403 or 404.
- Archwilio: Heneb, the merged Welsh archaeological trusts, runs the statutory HER under the Historic Environment (Wales) Act 2023. PRN prefixes were CPAT, DAT, GAT and GGAT. Terms: "Information obtained from Archwilio shall not be passed to a third party without written consent". Use was for information and research only, not commercial projects, with copyright Heneb and prior written permission needed to publish or compile resources. Users had to "acknowledge the use made of Archwilio in any document or published report". It is a custom PHP and JavaScript app with no documented API, and its internal endpoints were not probed. Bulk access went through the Heneb HER enquiry form and its Access and Cost Recovery Policy. Archwilio and Jersey both warned that listed sites were mostly on private land with no right of access.

### Northern Irish records

- The patterns came from the popup configuration of the official web map, item `da21bff543d5432ea4275b030b24a6e5`. The viewer was `https://experience.arcgis.com/experience/8bb16b64f0994385a5c141027ae9d33e/`. The older viewer cited on OpenDataNI no longer resolved.
- NISMR details redirected to `/NISMR-public/Disclaimer.aspx` on the first visit. Whether a link worked directly after one acceptance was not tested.
- No detail pattern was found for industrial or defence heritage. Two guessed patterns returned 404. Page terms were not verified and the pages were Crown copyright.

### Isle of Man and Channel Islands

Both island HERs ran the Arches platform and returned bulk JSON without authentication. That made harvesting technically easy and it is not licensed, so the research treated both as link-only.

- Isle of Man, Manx National Heritage, 17,843 resources. Use the bare domain `isleofmanher.im`, because `www.isleofmanher.im` returned 400. `https://isleofmanher.im/search/resources?paging-filter=1` returned 200 `application/json`, 20 per page. A report page returned 200 `text/html` and `/resources/{id}?format=json` returned 200. EPSG:4326 in the API. Licence: "Copyright © 2024 Manx National Heritage. The contents of this site, including all images and text, are for personal, educational, non-commercial use only. The contents of this site may not be reproduced in any form without the permission of Manx National Heritage." An IOMHER Access and Charging Policy existed. CORS not checked.
- Jersey, Jersey Heritage, 11,508 records, including listed buildings and places. `https://her.jerseyheritage.org/search/resources?paging-filter=1` returned 200 `application/json`, 500 per page. A report page returned 200 `text/html`. EPSG:4326 in the API. The footer read "2019 © All Rights Reserved" and no reuse licence was stated. CORS not checked. `opendata.gov.je` held nothing heritage-related.
- Guernsey: no online HER or SMR was found. The Jersey HER links page pointed Guernsey SMR enquiries to the Island Archives. Nothing else was tested.

## Suggested use

These are suggestions from the research, not descriptions of built behaviour.

- Bulk-ingest three national sources first: the HES zips, the DataMapWales Cadw and NMRW layers, and the NI HED FeatureServer. The research counted roughly 340,000, 160,000 and 76,000 records, all under OGL v3.
- Scotland: nightly zips, with Last-Modified to skip unchanged files. Wales: one WFS request per layer, paging large layers with `sortBy` and `startIndex`. Northern Ireland: the FeatureServer with `resultOffset` pages of 2000.
- Keep native coordinates beside the 4326 geometry and carry each positional accuracy field. About 13% of NRHE points are located to 100 m or worse and 1,709 NI SMR records are "Unlocated", so snapping to a LIDAR feature without it would mislead.
- Hold per-dataset attribution with licence, exact string and retrieval date. Cadw's wording needs the date received and HES wording needs the year.
- Do not crawl record pages or frame trove.scot. Google Cloud cannot reach trove.scot, so the follow-up suggested checking links only against unchallenged redirect hosts such as `canmore.org.uk`.
- No service published a rate limit, except the 99% availability aim on DataMapWales, and HES runs one ArcGIS Server host. The research suggested serving OpenAntiquity's own tiles.
- The follow-up drafted, and did not send, requests to HES (`trove@hes.scot`) for NRHE Areas and the radiocarbon files on `inspire.hes.scot`, and to the Treasure Trove Unit (`treasuretrove@nms.ac.uk`) about a licence and an export.

## Open questions

- What is the current download address, record count and licence for NRHE Areas on trove.scot? The page said OGL v3, the catalogue said OGL v1.0 wording, and the catalogue link is dead. A person has to read it in a browser.
- Does HES plan a public API for trove.scot, or an allow-list for link checks?
- Does the HES retirement notice affect `inspire.hes.scot`? The critic follow-up read the notice as listing the Historic Environment Portal and PastMap for later retirement with no date, and not mentioning `inspire.hes.scot`.
- Where does `https://www.trove.scot/c14index/{id}/` land, and is there a per-place radiocarbon view to link to?
- Will Cadw or Welsh Government confirm OGL for the conservation area, World Heritage Site and guardianship layers?
- Will HED license the Archaeological Investigations layer, 3,271 excavation records with summaries?
- Would Heneb, the Improvement Service, individual Scottish councils, Manx National Heritage or Jersey Heritage grant a licence for HER points, even name, type and link only?
- What are the feature count, fields and licence text of the OSNI Townlands file, and do the 12 Six Inch map datasets have georeferenced sheets? Neither was downloaded.
