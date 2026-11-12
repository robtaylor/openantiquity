# England records sources

This page records what a research pass found on 2026-11-10 about services that publish England's heritage records: Historic England's open data, the research records that are not open, the Archaeology Data Service route to them, Heritage Gateway, the openly licensed local records and the public map services with unstated licences. Nothing here describes what OpenAntiquity's code does, because none of it is built.

The headline: England published its designations and half a million features mapped from aerial photographs under the Open Government Licence v3.0. It did not publish its 354,740 research records or most of its 83 local Historic Environment Records (HERs). Only Cornwall and City of York carried an explicit OGL on the dataset, and Cornwall's still needed confirmation. The per-HER detail is in [England HER coverage](england-her-coverage.md).

Reuse class and mode follow [Decision 0004](../architecture/decisions/0004-field-club-is-non-commercial.md) and [Decision 0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md). A licence that was never stated is classed `link_only`, and the Licence cell says so. A publisher that blocked scripts or forbade harvesting is `deeplink` whatever its licence. "Tested" means a request was made on 2026-11-10 and decoded. To save space, `{HE}` stands for `https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services`, Historic England's ArcGIS Online services root.

## Summary

| Source | Publisher | Coverage | Licence | Reuse | Mode | Records |
|---|---|---|---|---|---|---|
| National Heritage List for England | Historic England | England | OGL v3.0 | open | bulk | 379,685 listed; 20,006 scheduled |
| Open Data Hub download API | Historic England | England | OGL v3.0 | open | bulk | 17 datasets |
| Aerial Investigation and Mapping data | Historic England | England, partial | OGL v3.0 | open | bulk | 498,295 |
| Conservation Areas, Heritage at Risk, HER boundaries, Research Spatial Reports, de-designated sites, London APAs, Turning the Plough 2 | Historic England | England | OGL v3.0 | open | bulk | 8,749; 4,989; 83; 13,543; 2,733; 981; 2,030 |
| Aerial photo footprints | Historic England Archive | England | Not stated | link_only | live | 468,176 obliques; 103,185 verticals |
| NMP hand-drawn raster tiles | Historic England | England, partial | Reads conflicted | open | deeplink | Raster |
| Aerial photo and mapping apps | Historic England | England | Not stated | link_only | deeplink | Apps |
| Dated AIM views and OGC API | Historic England | England | Not stated; OGL on the stable service | link_only | deeplink | 498,648 |
| Cornwall and Isles of Scilly HER | Cornwall Council | Cornwall | OGL v3.0, conflicting | open | bulk | 132,100 monuments |
| City of York HER | City of York Council | York | OGL v3.0 | open | bulk | 9,662 monuments |
| Lincolnshire HER Monuments | Lincolnshire County Council | Lincolnshire | OGL label, no-commercial text | non_commercial | bulk | 42,927 |
| ADS Data Catalogue API | Archaeology Data Service | UK | ADS Terms of Use and Access | non_commercial | live | 309,769 NRHE (309,810 by collection) |
| Heritage Gateway | Historic England, HERs | England | Not for commercial reuse | link_only | deeplink | 1.3 million |
| Historic England Research Records | Historic England | England | No public release | link_only | deeplink | 354,740 |
| NRHE to HERs portal | Historic England | England | OGL v3.0 to HERs only | link_only | deeplink | Login only |
| Know Your Place HER layers | Bristol City Council | South West | Mixed, mostly not stated | link_only | live | 10 HER areas |
| Exmoor, Dartmoor, Wiltshire, Wolverhampton HERs | Each authority | Each area | Not stated | link_only | live | 80,000 or so |
| Lincoln ARCADE | City of Lincoln Council | Lincoln | Not stated | link_only | live | 18,539 |
| Natural England parklands and NHLC grid | Natural England | England | OGL v3.0 | open | bulk | 4,517; 2,111,346 |
| Opportunity Map for New Woodland | Forestry Commission | England | OGL v3.0 | open | bulk | 552,503 |
| Church of England church locations | Church of England | England | Not-for-profit notice | non_commercial | live | 19,159 |
| Planning Data platform | MHCLG | England | Upstream OGL v3.0 | open | deeplink | Secondary copy |
| Scottish council HERs | Stirling and others | Scotland, Stirling | Varies | open | bulk | 5,744 Stirling |
| Greater London HER Online | Historic England | London | Prohibits automated use | link_only | deeplink, home page | 184,086 |
| Peak District HBSMR layers; district HER extracts | Five bodies | Parts of four HERs | Not stated | link_only | deeplink | Partial |
| Stale data.gov.uk HER records | Four councils | Four areas | Restrictive | link_only | deeplink | Old |
| Keys to the Past | Durham, Northumberland | Two counties | Copyright reserved | link_only | deeplink | 66,210 Durham points |
| National Trust Heritage Records | National Trust | NT land | Site terms | link_only | deeplink | Over 97,717 |
| SHINE | Historic England, ALGAO | England | None public | link_only | deeplink | Unobtainable |
| Defence of Britain Archive | CBA via ADS | UK | ADS Terms | non_commercial | live | 20,173 site records |
| Historic England and Church Heritage Record pages | Historic England; Church of England | England | Not open data | link_only | deeplink | Pages |

## National Heritage List for England

The official designation register as a public ArcGIS service, in eleven layers.

| | |
|---|---|
| Access | ArcGIS FeatureServer |
| Address | `{HE}/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer` |
| Tested on 2026-11-10 | Yes. 200 `application/json`, a GeoJSON FeatureCollection of three scheduled monument polygons |
| Format and CRS | JSON, GeoJSON, PBF. Native EPSG:27700, and `outSR=4326` worked |
| Licence | Open Government Licence v3.0, through the Historic England Open Data Hub Terms and Conditions. Read from a Wayback snapshot of 2026-02-01, because the live page returned 403 to curl |
| Attribution | "© Historic England [year]" and for spatial data add "Contains Ordnance Survey data © Crown copyright and database right [year]." Service text: "© Crown Copyright 2026. Contains Ordnance Survey data © Crown copyright and database right 2026. Released under OGL." Historic England also recommended a currency statement beginning "The Historic England Data contained in this material was obtained on [date]..." |
| Reuse class | open |
| Suggested mode | bulk, through the Open Data Hub download. Paging needs about 190 requests per listed-building layer |
| Positional precision | `CaptureScale` per feature, 1:2500 to 1:10000 seen |
| Paging and limits | 2,000 per page. A request for 5,000 returned 2,000 with `exceededTransferLimit`. `orderByFields=OBJECTID&resultOffset=N` worked. `cache-control: public, max-age=3600`. No rate limit documented |
| CORS | Yes, `access-control-allow-origin: *` |

```
{HE}/National_Heritage_List_for_England_NHLE_v02_VIEW/FeatureServer/6/query?where=1%3D1&geometry=-1.84,51.16,-1.80,51.19&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=3&f=geojson
```

| Layer | Content | Geometry | Count |
|---|---|---|---:|
| 0 | Listed Building | MultiPoint | 379,685 |
| 1 | Building Preservation Notice | MultiPoint | 6 |
| 2 | Certificate of Immunity | MultiPoint | 222 |
| 3 | Listed Building | Polygon | 379,685 |
| 4 | Building Preservation Notice | Polygon | 6 |
| 5 | Certificate of Immunity | Polygon | 222 |
| 6 | Scheduled Monuments | Polygon | 20,006 |
| 7 | Parks and Gardens | Polygon | 1,721 |
| 8 | Battlefields | Polygon | 47 |
| 9 | Protected Wreck Sites | Polygon | 57 |
| 10 | World Heritage Sites | Polygon | 27 |

**Notes.**

- Key fields: `ListEntry` (integer), `Name`, `Grade`, the designation dates, `AmendDate`, `CaptureScale`, `hyperlink`, `area_ha`, `NGR`, `Easting`, `Northing`. Wrecks have `Latitude` and `Longitude` instead.
- No description text was published, only the hyperlink. The list description sat on the Historic England website, behind a Cloudflare challenge.
- Layer 3 held 379,685 polygons, but only 10,080 had `area_ha` above zero. The other 369,605 had it null and were about 2.5 m triangles around the point. Historic England's field notes said polygons existed only for buildings listed or substantively amended since 4 April 2011.
- `dataLastEditDate` was 2026-11-10 06:53 UTC, so the service refreshed daily. No OGC API endpoint existed ("Invalid URL").
- Suggested use: draw points for every listed building and polygons only where `area_ha IS NOT NULL`. Key records on `ListEntry`.

## Open Data Hub bulk download API

Whole-layer file exports of any Open Data Hub dataset. The research found them faster than paging for any layer above about 10,000 features.

| | |
|---|---|
| Access | ArcGIS Hub download API |
| Address | `https://opendata-historicengland.hub.arcgis.com/api/download/v1/items/{itemId}/{geoPackage|geojson|csv|shapefile}?layers={layerId}` |
| Tested on 2026-11-10 | Yes. 302 to a cached file, then 200 `application/octet-stream`, 45,322,240 bytes for NHLE layer 6. All four formats returned 302 |
| Format and CRS | GeoPackage, GeoJSON, CSV, zipped Shapefile. GeoPackage was EPSG:27700 |
| Licence | Open Government Licence v3.0, per the Open Data Hub Terms and Conditions |
| Attribution | "© Historic England [year]. Contains Ordnance Survey data © Crown copyright and database right [year]." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | The scheduled monuments GeoPackage held 20,006 rows. The Listed Building points GeoPackage was 102,936,576 bytes, modified 2026-11-10 11:42 GMT |
| Paging and limits | None documented. A fresh export returned 202 with `{"status":"ExportingData","progressInPercent":0}` until ready, then 302 |
| CORS | Yes on the 302 |

```
https://opendata-historicengland.hub.arcgis.com/api/download/v1/items/767f279327a24845bf47dfe5eae9862b/geoPackage?layers=6
```

**Notes.**

- Item ids: NHLE `767f279327a24845bf47dfe5eae9862b`, AIM `e08a1ca270ac4caa8ba5efcb74f86a74`, Conservation Areas `446bc9bf8b5b440386d0c504caa3dac5`, Heritage at Risk `5d810bb1e6894e90b4d0921acebaf04c`, Research Spatial Reports `554ad399612247b3b9315c1f436f61d8`, HER boundaries `f3a0fea2d5bf4735beb09e269810397d`, De-designated `8836370be44f4916b9ba7d350df24902`, London APAs `61b297c21a4d46ddbb11f518d0a704ae`, Turning the Plough 2 `86293b8f71414ded830d559e16fd1de9`. The hub listed 17 datasets and none was NRHE.
- Redirect filenames were ephemeral, so call the hub URL each time. AIM exports were being regenerated when re-requested, so a job needs polling with backoff.
- The terms said use must not imply Historic England endorsement, its logos were excluded, "Spatial data is provided solely to indicate the location of the area", and the data must not be used to break heritage protection laws. Sub-licences must carry the same attribution.

## Aerial Investigation and Mapping data

Archaeological features mapped from aerial photographs and lidar by the National Mapping Programme and its successors, as polygons. It is the Historic England dataset closest to earthwork work.

| | |
|---|---|
| Access | ArcGIS FeatureServer |
| Address | `{HE}/HE_AIM_data/FeatureServer` |
| Tested on 2026-11-10 | Yes. 200 `application/json`, two Stonehenge polygons |
| Format and CRS | JSON, GeoJSON, PBF, and GeoPackage or Shapefile through the hub. EPSG:27700 |
| Licence | Open Government Licence v3.0, per the Open Data Hub terms |
| Attribution | "© Historic England [year]". Service text: "© Historic England 2026. Released under OGL." |
| Reuse class | open |
| Suggested mode | bulk, then serve as vector tiles from the local database, because 498,295 polygons was too heavy for browser calls |
| Records | Layer 0 Detailed_Mapping 498,295. Layer 1 Monument_Extents 197,372. Layer 2 Project_Area 163 |
| Paging and limits | 2,000 per page |
| CORS | Yes |

```
{HE}/HE_AIM_data/FeatureServer/0/query?where=1%3D1&geometry=-1.84,51.16,-1.80,51.19&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=2&f=geojson
```

**Notes.**

- Coverage was partial. Historic England said just over half of England had been surveyed, so an empty area means unmapped, not empty. Layer 2 shows where mapping exists. Earlier hand-drawn projects were raster only. See the NMP tiles below.
- Key fields: `LAYER`, `project`, `PERIOD`, `MONUMENT_TYPE` (backslash-separated FISH terms), `EVIDENCE_1` (for example EARTHWORK, CROPMARK), `SOURCE_1` (photo references), `HE_UID`, `HER_NO`, and numbered `HE_URL` fields (legacy Heritage Gateway links with `resourceID=19191`). `HE_UID` keys into Historic England research records.
- Data last edited about 25 June 2026.

## Smaller Open Data Hub layers

Five more layers under the same Open Government Licence v3.0 and the same Open Data Hub terms. All answered 200 `application/json` on 2026-11-10 with CORS `yes`, and all were suggested for `bulk`, reuse class open.

| Layer | Address | Records | Attribution |
|---|---|---:|---|
| Conservation Areas | `{HE}/Conservation_Areas/FeatureServer/0` | 8,749 | "© Historic England and Local Planning Authorities 2026. Contains Ordnance Survey data © Crown copyright and database right 2026. Released under OGL." |
| Heritage at Risk Register 2026 | `{HE}/HAR_2026_OTHR_WGS84/FeatureServer/0` | 4,989 polygons | "© Historic England 2026. Contains Ordnance Survey data © Crown copyright and database right 2026. Released under OGL." |
| HER boundaries | `{HE}/HER_boundaries_ODH/FeatureServer/2` | 83 | "© Historic England 2026. Contains OS data © Crown Copyright and database right 2026. Released under OGL." |
| Research Spatial Reports | `{HE}/Historic_England_Research_Spatial_Reports/FeatureServer/475` | 13,543 | "© Historic England 2026. Released under OGL." |
| De-designated sites; Greater London APAs; Turning the Plough 2 | `{HE}/{Delisted|Greater_London___Archaeological_Priority_Areas|Turning_the_Plough_2_}/FeatureServer/0` | 2,733; 981; 2,030 | De-designated: "© Crown Copyright 2026. Contains Ordnance Survey data © Crown copyright and database right 2026." APAs: "© Historic England 2026. Contains Ordnance Survey data © Crown copyright and database right 2026." Turning the Plough: "© Gloucestershire County Council and Historic England" |

Tested requests:

```
{HE}/Conservation_Areas/FeatureServer/0/query?where=1%3D1&geometry=-1.80,51.06,-1.78,51.08&geometryType=esriGeometryEnvelope&inSR=4326&outFields=UID,NAME,LPA,DATE_OF_DE&outSR=4326&resultRecordCount=1&returnGeometry=false&f=geojson
{HE}/HAR_2026_OTHR_WGS84/FeatureServer/0/query?where=HeritageCa%3D%27Scheduled%20Monument%27&outFields=List_Entry,EntryName,HeritageCa,URL&outSR=4326&resultRecordCount=1&geometryPrecision=5&f=geojson
{HE}/HER_boundaries_ODH/FeatureServer/2/query?geometry=-1.826,51.179&geometryType=esriGeometryPoint&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=HER_NAME,GATEWAY_LINK&returnGeometry=false&f=json
{HE}/Historic_England_Research_Spatial_Reports/FeatureServer/475/query?where=1%3D1&geometry=-1.84,51.16,-1.80,51.19&geometryType=esriGeometryEnvelope&inSR=4326&outFields=Report_Num,Report_title,Report_URL,Project_type,Year&outSR=4326&resultRecordCount=2&f=geojson
{HE}/Delisted/FeatureServer/0/query?where=HERITAGECATEGORYDESCRIPTION%20LIKE%20%27%25Sched%25%27&returnCountOnly=true&f=json
```

**Notes.**

- Conservation Areas: native EPSG:27700. Fields `UID`, `NAME`, `DATE_OF_DE`, `LPA`. The test returned Stratford sub Castle, Wiltshire, 1984. Historic England's own description said around 10,000 exist, against 8,749 here.
- Heritage at Risk: native EPSG:3857 despite the name. Licence text "Contains public sector information licensed under the Open Government Licence v3.0". Listed Building 2,239; Scheduled Monument 2,183; Conservation Area 455; Park and Garden 105; Wreck 4; Battlefield 3. A centroid points service held 4,991. An asset can appear more than once, one row per assessment method. The register's own page for an entry has a different number from `List_Entry`, and the `URL` field holds it, so a link built from `List_Entry` goes nowhere. Historic England's downloads page said not to scrape its website for Heritage at Risk data.
- HER boundaries: the layer id is 2, and layer 0 returned "not found". Native EPSG:27700. The test point returned Wiltshire and Swindon HER. Fields `HER_NAME`, `GATEWAY_LINK`, `UAD`. The polygons sum to 132,940 km². All 83 `GATEWAY_LINK` values were old `heritagegateway.org.uk` `herdetail.aspx` URLs that returned 301 to the generic new home, so the per-HER link was effectively lost. Suggested use: the key for a per-HER registry. See [England HER coverage](england-her-coverage.md).
- Research Spatial Reports: the layer id is 475. Native EPSG:27700. A large-area project is one centre point. Fields `Report_Num`, `Report_title`, `Report_URL`, `Project_type`, `Year`. `Report_Num` is not unique and is not always a number, so use `Report_URL`, which every row has, for the link.
- De-designated sites hold sites removed from the NHLE since April 2011. The count query returned `{"count":161}` for scheduled ones. Fields `ARTICLEUID` (unique in all 2,733 rows), `ARTICLEVERSIONNAME` (the name), `OriginalListEntryNumber`, `DateRemovedFromList`, `DecisionText`. Turning the Plough 2 is a Midlands ridge-and-furrow survival survey with fields `RidgeAndFurrow`, `Survival`, `Condition`, `ConfidenceRating`, `Vulnerability`. The research judged it relevant to lidar earthwork work.

## Aerial photo footprints

Locations of digitised aerial photographs shown in Historic England's Aerial Photo Explorer. The service names carry dates and rotate.

| | Obliques | Verticals |
|---|---|---|
| Access | ArcGIS FeatureServer | ArcGIS FeatureServer |
| Address | `{HE}/Obliques_20260529_Full_view/FeatureServer/0` | `{HE}/Verticals_20260529_poly_Full_view/FeatureServer/0` |
| Tested on 2026-11-10 | Yes. 200, two points, 1,359 in the test box | Yes. 200, two USAAF 1943 footprints, 67 in the test box |
| Geometry and CRS | Point, EPSG:27700 | Polygon footprint, EPSG:27700 |
| Records | 468,176 | 103,185 |
| Licence | Not stated. Public item `3f52b72803504446b3c1add33f67b0b3`, empty licence and credit fields, not on the Open Data Hub | Not stated. Public item `7476a999827e469e84373f640243a492`, empty licence field |
| Attribution | The per-record `Copyright` field, typically "© Historic England Archive" | The per-record `Copyright` field, for example "Source Historic England Archive (USAAF photography)" |
| Reuse class | link_only | link_only |
| Suggested mode | live | live |
| CORS and paging | Yes, 2,000 per page | Yes, 2,000 per page |

```
{HE}/Obliques_20260529_Full_view/FeatureServer/0/query?where=1%3D1&geometry=-1.84,51.16,-1.80,51.19&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=2&f=geojson
```

The verticals request was the same with `Verticals_20260529_poly_Full_view` in place of the obliques service.

**Notes.**

- The first report gave 468,176 and 103,185, and a later report gave 453,090 and 96,190. The critic review settled it. They are two date-stamped snapshots. `Obliques_20260529_Full_view` and `Verticals_20260529_poly_Full_view` were current. `Obliques_update_20250304_view` with 453,090 and `New_Verticals_20250304_view` with 96,190 were stale, and the 2025 obliques view had `maxRecordCount` 15. Together the current services held 571,361 records.
- The research suggested resolving the current name at run time from the Aerial Photo Explorer web map item `98c97df2d72f4bdfb4fbda2360888885`.
- Both carry `DATE_FLOWN`, `Copyright` and `Filename`. Only digitised frames were included, a small part of the Archive's holdings.
- Thumbnail pattern `https://thumbs.smartframe.io/27025fea9afa38753501b02dbd8a40f2/{Filename}` returned 200 `image/webp` for an oblique and for `us_7ph_gp_loc37_v_5037`. Its licence was not established. The image page pattern is under Deep link only.

## NMP hand-drawn mapping raster tiles

Scanned hand-drawn National Mapping Programme transcriptions for earlier projects that have no vector data.

| | |
|---|---|
| Access | ArcGIS tiled MapServer on a custom EPSG:27700 grid |
| Address | `https://tiles-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/NMP_mapPackage_fromPro_0_11/MapServer/tile/{level}/{row}/{col}` |
| Tested on 2026-11-10 | Yes. 200 `image/png`, 256x256 RGBA, red linework around Stonehenge |
| Format and CRS | PNG. EPSG:27700, origin x=-238375, y=1376256, 14 levels from 896 m/px to 0.109375 m/px |
| Licence | The reports disagreed. The first read "© Historic England 2023", unconfirmed, with the item off the Open Data Hub. The critic review later read the item as "(c) Historic England, 2023. This resource is licensed under the Open Government Licence 3.0." It read metadata only, fetched no tile, and noted the BNG scheme might not be the same service. The later read wins |
| Attribution | "© Historic England 2023" |
| Reuse class | open, per the later read |
| Suggested mode | deeplink, to the Mapping Explorer, until Historic England gives written permission to proxy or re-tile |
| CORS | Yes, the origin was reflected |

```
https://tiles-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/NMP_mapPackage_fromPro_0_11/MapServer/tile/7/688/363
```

**Notes.** `exportTilesAllowed` was false. Item `1c11aac0cb654b5794d2550544da1ec3`. The tiles are not Web Mercator, so MapLibre cannot read them without a reprojecting proxy or re-tiling.

## AIM extents layer

The monument extents layer (`HE_AIM_data` layer 1) has no `MONUMENT_TYPE` or `PERIOD`: its fields are `layer`, `project`, `HE_UID` and `HER_No`. A record from it has no type or period of its own, and `HE_UID` reads `NONE GIVEN` on about half the rows.

## Dated AIM views and OGC API

Two Historic England AIM endpoints to avoid, because a stable one exists.

The Mapping Explorer views, such as `{HE}/All_AIM_08_06_26_OSGB_V3_view/FeatureServer/0`, answered 200 to metadata and count queries on 2026-11-10 and held 498,648 detailed features, 197,374 extents, 162 projects and 399 projects by HER. No licence was stated on the items, although the data matched the OGL `HE_AIM_data` service. The service names embed release dates and are replaced each release. The app was item `d45dabecef5541f18255e12e5cd5f85a` with web map `f94874e44ebc4b5284a53c0294fea38f`.

The OGC API at `{HE}/Historic_England_Aerial_Investigation_Mapping_data/OGCFeatureServer`, licensed OGL v3.0, listed three collections on `/collections` but returned a 400 error body, "Cannot perform query. Invalid query parameters.", for `/collections/{id}/items?limit=1` with and without a bounding box.

## Cornwall and Isles of Scilly HER

The full local HER as open data: monument points, lines and polygons, events, mapping-programme features from aerial photographs, and historic landscape characterisation.

| | |
|---|---|
| Access | ArcGIS MapServer query, WFS 2.0, WMS |
| Address | `https://map.cornwall.gov.uk/arcgis/rest/services/inspire/inspire_historic/MapServer`. WFS at `https://map.cornwall.gov.uk/arcgis/services/inspire/inspire_historic/MapServer/WFSServer` |
| Tested on 2026-11-10 | Yes. 200 `application/json`, record MCO1 decoded. WFS 200 `application/xml` |
| Format and CRS | JSON, GeoJSON, PBF, GML 3.2. EPSG:27700 |
| Licence | OGL v3.0 per the INSPIRE metadata on data.gov.uk, dated 2020-09-29: "Contains public sector information licensed under the Open Government Licence v3.0". The follow-up found a conflict. The ArcGIS Online item for the same data (`CCmap/MapServer/211`) said "non-exclusive, royalty free revocable licence solely to view the licensed data for non-commercial purposes". |
| Attribution | "Contains public sector information licensed under the Open Government Licence v3.0 (Cornwall Council)" |
| Reuse class | open, to confirm |
| Suggested mode | bulk, after Cornwall confirms the licence in writing |
| Records | Layer 0 monument points 78,387; 3 polylines 2,909; 6 polygons 50,804; 8 events 9,706; 4 mapping-programme polylines 321,335; 5 mapping-programme polygons 523,276; 7 HLC 9,507; WHS and conservation area layers 1, 2 and 9 |
| Positional precision | An `InputPrecision` field on each record |
| Paging and limits | `maxRecordCount` 1000 on the INSPIRE service, 2000 on `CCmap` and `CIoS_HE` |
| CORS | No `access-control-allow-origin` header, so ingest or proxy |

```
https://map.cornwall.gov.uk/arcgis/rest/services/inspire/inspire_historic/MapServer/0/query?where=1%3D1&outFields=*&resultRecordCount=2&resultOffset=0&orderByFields=OBJECTID&outSR=4326&f=geojson
```

**Notes.** Monument fields: `MonUID` (MCOnnn), `Name`, `MonType`, `Period`, `Summary`, `Easting`, `Northing`, `URL` (legacy Heritage Gateway link, `resourceID=1020`). Mapping-programme layers carried only `LAYER` and `SITE_ID`, or `GRIDCODE`. WFS `numberMatched` was 78,387. The Heritage Gateway held 80,196 Cornwall records.

## City of York HER

York HER monuments and events as points, lines and areas, from the council's open data.

| | |
|---|---|
| Access | ArcGIS Hub bulk download, and ArcGIS MapServer query |
| Address | `https://opendata.arcgis.com/datasets/3f0de3422ec343e498d6d7699c114858_3.geojson`. Service `https://maps.york.gov.uk/arcgis/rest/services/Public/LV_LeisureCulture/MapServer` |
| Tested on 2026-11-10 | Yes. 200 `application/json` after a redirect to hub.arcgis.com, 1.4 MB, 3,507 features. The REST service also returned 200 |
| Format and CRS | GeoJSON, CSV, KML. EPSG:4326 in the download, 27700 on the service |
| Licence | OGL-UK-3.0 on data.gov.uk. Dataset text: "The licensing for this dataset is listed as Derived data exemption - streamlined process... Open Government Licence (OGL v3.0)" |
| Attribution | The first report: "© Crown copyright and database rights 2016 Ordnance Survey 100020818" plus acknowledgement of City of York Council under OGL. The follow-up, which wins: "© Crown copyright and database rights 2016 Ordnance Survey 100020818; City of York Council, OGL v3.0" |
| Reuse class | open |
| Suggested mode | bulk |
| Records | Monuments 3,555 points, 3,648 lines, 2,459 areas. Events 7,850 points, 121 lines, 1,336 areas |
| Paging and limits | `maxRecordCount` 1000 |
| CORS | No on maps.york.gov.uk. Use the Hub download |

```
https://opendata.arcgis.com/datasets/3f0de3422ec343e498d6d7699c114858_3.geojson
```

**Notes.** Layers 0 to 2 are events, 3 to 5 monuments. Fields: `MonUID` (MYOnnn), `RecordType`, `Name`, `MonType`, `URL` (`https://her.york.gov.uk/monument/MYO1`, 200). The download adds `GatewayURL` and `FeatureDescr`. Hub items for the other layers end `_5` (areas, `398950456fe542b899698906b288dc42`) and `_4` (lines, `4deb274782c94d619f6cf1154325d202`). Only the monument points were downloaded. York completed its NRHE transfer in July 2020, with 4,568 records amended or added, so this dataset already held accessioned NRHE content.

## Lincolnshire HER Monuments

A quarterly point extract of Lincolnshire HER monuments: identifier, name and grid coordinates only.

| | |
|---|---|
| Access | CSV download from the council's open data portal |
| Address | `https://data.lincolnshire.gov.uk/dataset/monuments` |
| Tested on 2026-11-10 | Yes. 200 `text/csv` |
| Format and CRS | CSV, cp1252 and not UTF-8. EPSG:27700 integer eastings and northings |
| Licence | Labelled "UK Open Government Licence (OGL)" with an OGL v3 URL. The description said the data "should not be used in any commercial sense or as evidence to form any decisions relating to the Historic Environment". OGL permits commercial use, so the two cannot both hold. It also barred uses that could damage archaeological sites |
| Attribution | The first report: "Lincolnshire Historic Environment Record (HER), Lincolnshire County Council", with maps showing "Contains OS data © Crown copyright and database right [year]". The follow-up, which wins: "Lincolnshire Historic Environment Record, Lincolnshire County Council. Contains OS data © Crown copyright and database right [year]." |
| Reuse class | non_commercial, until Lincolnshire says which text governs |
| Suggested mode | bulk |
| Records | The reports disagreed. The first gave 42,867 rows and 3,357,959 bytes from a `20260610 Monuments` file. The follow-up, which wins, gave 42,927 rows, 41,649 with coordinates, 9.4 MB, snapshot dated 2026-09-10 |
| CORS | n-a |

```
https://blob.datopian.com/resources/0f1da869-0739-418b-b244-ff9be83a994d/Monuments%20-%20Current%20Working-vT93w9.csv
```

**Notes.** Fields: `MonUID` (MLInnn), `PrefRef`, `Name`, `Easting`, `Northing`. No type, period or description. The blob URL changed with each release, so resolve it from the dataset page.

## ADS Data Catalogue API

The Archaeology Data Service's record-level catalogue of UK archaeology, searchable by bounding box. It served the National Record of the Historic Environment (NRHE) monument inventory, the only machine route found to those records.

| | |
|---|---|
| Access | REST JSON |
| Address | `https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q={text}&size={n}&page={p}&bbox={north},{west},{south},{east}&contributor={name}&ariadneSubject={subject}` |
| Tested on 2026-11-10 | Yes. 200 `application/json`, 1,208 hits for the Stonehenge box |
| Format and CRS | JSON, ARIADNE AO-Cat schema, with `title`, `description`, `spatial[].geopoint`, `otherId`. WGS84 |
| Licence | ADS Terms of Use and Access, unless a collection shows a Creative Commons or OGL licence. The `accessPolicy` on every NRHE record: "Use materials for research, learning and teaching purposes"; "non-exclusive, non-transferable licence... for valid not-for-profit teaching and research purposes, providing the copyright owners are acknowledged"; "Anyone wishing to use the catalogue for any other purpose must contact the ADS". The critic review read the terms page as saying "The data must not be sold or supplied to a third party. The data should only be used for teaching, learning, and research purposes." Not OGL |
| Attribution | "Data copyright © Historic England; cite Archaeology Data Service as distributor". Otherwise acknowledge each record's copyright owner |
| Reuse class | non_commercial |
| Suggested mode | live, from the browser with no server-side cache |
| Records | An empty search returned 2,469,603. `getTotalRecordsCount` returned 4,168,691, which the follow-up explained as the whole ARIADNE index and not the ADS subset. England 1,642,907. Historic England 480,133 (site or monument 309,769, fieldwork 167,822, by contributor facet); National Trust 53,733; Yorkshire Dales NPA 30,791; Somerset 29,142; Milestone Society 26,267; Merseyside 20,707; Warwickshire 9,042 |
| Paging and limits | None published, behind Cloudflare. `size` and `page` worked. The critic review stated a 50-per-page and 10,000-result window, which this research did not test |
| CORS | Yes, `access-control-allow-origin: *`, GET |

```
https://archaeologydataservice.ac.uk/data-catalogue-api/api/search?q=&size=3&bbox=51.19,-1.84,51.17,-1.81&contributor=Historic%20England&ariadneSubject=Site/monument
```

**Notes.**

- The `bbox` order is north, west, south, east. Other orders returned `[]` or wrong results. That request returned 133 NRHE monuments around Stonehenge.
- NRHE records carried `otherId` values such as "Depositor ID: SU 14 SW 551" for the NMR number and "NMR_NATINV-1119431" for the HOB UID, and a full `description`.
- Every NRHE record was stamped issued and modified 2004-09-15, so the snapshot date was unknown and later edits or transfers to HERs are not reflected.
- Suggested use: a "recorded nearby" lookup labelled with ADS and the owner, linking to the Heritage Gateway search for the HOB UID. Ask ADS in writing before caching anything.

## Heritage Gateway

Historic England's national cross-search of local HERs and research records, relaunched on 16 September 2026 inside historicengland.org.uk.

| | |
|---|---|
| Access | Deep link only |
| Address | Record: `https://historicengland.org.uk/listing/heritage-gateway/results/record/{dataset-guid}/{record-uid}`. Coordinate search: `https://historicengland.org.uk/listing/heritage-gateway/results/?filters[0][field]=initialLatLong&filters[0][values][0]={lat},{lon}&filters[0][type]=any` |
| Tested on 2026-11-10 | Yes. The legacy URL returned 301 to the new record. Pages returned 403 with `cf-mitigated: challenge` (a Cloudflare managed challenge) to curl and 200 in a real browser |
| Format and CRS | HTML. Record pages showed easting, northing, latitude, longitude and NGR. NGRs of 6 to 10 figures were zero-padded for display, which overstated precision |
| Licence | Not open. Each record page: "Heritage Gateway data is protected by Intellectual Property Rights and is for information use only. It must not be reused commercially or used for legal or planning purposes." Help and FAQs: "Heritage Gateway records are not authorised for commercial reuse of the information and should not be used for legal or planning purposes. Please contact the relevant HER for their full records as part of a licensed search... including terms and conditions." |
| Attribution | The source HER or Historic England, per record |
| Reuse class | link_only |
| Suggested mode | deeplink |
| Records | 1,299,728 across 39 datasets: 37 HER datasets, Historic England research records 354,740 and National Trust 70,805. The first report had read "over a million" and "more than 35" from the home page. The later count wins |
| CORS | No. The internal API was same-origin behind the challenge |

```
curl -s -D - -o /dev/null 'https://www.heritagegateway.org.uk/Gateway/Results_Single.aspx?uid=MDV100&resourceID=104'
```

That returned `location: https://historicengland.org.uk/listing/heritage-gateway/results/record/c39bc47e-3b72-4a06-9863-681629e456a2/MDV100`.

**Notes.**

- Legacy `Results_Single.aspx?uid={uid}&resourceID={n}` links still returned 301 to the new record for HER datasets. `resourceID` values seen: 104 Devon, 108 Gloucestershire, 1001 Norfolk, 1003 York, 1010 Wiltshire, 1020 Cornwall, 1035 Worcester, 19191 NRHE. The redirect is readable server-side, so a `resourceID` to dataset GUID map can be built without passing the challenge.
- NRHE links (`resourceID=19191`) redirect to a text search on the HOB UID, not a record page. `http://www.pastscape.org.uk/hob.aspx?hob_id={n}` redirects to that form.
- The coordinate-search pattern came from an archived record page of 2026-09-22 and was not exercised live. Its radius is unknown.
- The first report found no API. The follow-up read the page's own call, `/api/elastic/searchheritagegateway?pageNo=&pageSize=&searchTerm=&dataset=`, with `mapZoom`, `mapBoundsTopLeft`, `mapBoundsBottomRight` and `mapSearch=true` for the map. Two same-origin calls from an open page read the totals and dataset facet. A bounding-box call was blocked by the session's permission system and not retried. It is not a published API. Whether map search returns coordinates is not tested, and neither is the Download button.

## Historic England Research Records, former NRHE

The national record of non-designated archaeology, buildings and maritime sites, formerly the NRHE, PastScape and AMIE. It was not available as open data.

| | |
|---|---|
| Access | Deep link only, as a Heritage Gateway dataset |
| Address | `https://historicengland.org.uk/listing/heritage-gateway/results/?filters[0][field]=dataset&filters[0][values][0]=Historic+England+research+records&filters[0][type]=any` |
| Tested on 2026-11-10 | Yes. The legacy link returned 301 to a Gateway text search, then 403 to curl |
| Format and CRS | HTML, a point on record pages |
| Licence | No public open release found. Heritage Gateway conditions applied. Separately, Historic England licenses terrestrial NRHE records to HERs under OGL v3.0 through the NRHE to HERs project |
| Attribution | For NRHE content inside an HER: "This record includes National Record of the Historic Environment Information provided by Historic England on [insert date data provided] licensed under the Open Government Licence." |
| Reuse class | link_only |
| Suggested mode | deeplink, with the ADS catalogue as the interim live layer |
| Records | 354,740, dataset last modified 10 September 2026. The ADS copy held 309,769 site and monument records by contributor facet and 309,810 by the NRHE `isPartOf` collection. Both came from later reports |

```
https://www.heritagegateway.org.uk/Gateway/Results_Single.aspx?uid=1363175&resourceID=19191
```

**Notes.**

- It was not on the Open Data Hub nor among Historic England's 22 data.gov.uk datasets. The follow-up found no Historic England statement or FOI response about a public release.
- NRHE was shrinking. The FAQ said "NRHE records are in the process of being transferred from Historic England to local Historic Environment Records (HERs)", so "some areas have no Historic England Research Records". The transfer site said the NRHE "contains over 550,000 digital records", 13 HERs had completed and 12 were in progress, and "the NRHE will not be actively updated or maintained". The project "started in April 2019 and aims to finish in 2026". Marine records moved to the Marine HER in September 2025.

## NRHE to HERs transfer portal

Historic England's working site for transferring NRHE records to HERs, with the licensing statement for that transfer.

| | |
|---|---|
| Access | Deep link only. The map and records need a login |
| Address | `https://nrhe-to-her.esdm.co.uk/licensing-copyright` |
| Tested on 2026-11-10 | Yes. 200 `text/html` for licensing, FAQs and home. Map and progress pages redirected to login |
| Licence | "Historic England (HE) will make available the terrestrial database records from the National Record of the Historic Environment (NRHE) for inclusion in Historic Environment Records (HERs) pursuant to the Open Government Licence v3.0 (OGL)". GIS data "has been put through the OS Public Sector Mapping Agreement (PSMA) licence exemptions process by HE and will be issued under the terms of OGL v3.0" |
| Attribution | The NRHE statement quoted above |
| Reuse class and mode | link_only, deeplink. Reference only |

```
https://nrhe-to-her.esdm.co.uk/faqs
```

**Notes.** The follow-up drafted, and did not send, a request to Historic England for an OGL extract, a licence for the aerial photograph footprints and stable service names. The FAQ said an HER "cannot charge for information that has been supplied by Historic England under the OGL, nor can it charge for the supply of HER data" but can charge for services. An HER that edits a geometry moves it to its own Ordnance Survey licence.

## Know Your Place HER layers

Queryable HER monument layers for ten HER areas on one Bristol City Council ArcGIS server, published for the Know Your Place web maps.

| | |
|---|---|
| Access | ArcGIS MapServer query |
| Address | `https://maps2.bristol.gov.uk/server2/rest/services/ext/{her_2026|banes_hist_2024|devon_hist_2021_v2|glo_hist_2021|nsom_hist_2022_v2|sgc_hist_2020_v2|som_hist_2022|wilts_her_2022_v2|worcester_city}/MapServer` |
| Tested on 2026-11-10 | Yes. 200 `application/json`. Count queries and layer metadata on eight or nine services |
| Format and CRS | JSON, GeoJSON, PBF. EPSG:27700 |
| Licence | No open licence. Know Your Place guidance: "All HER data... has been selected and published by HER officers across the region in keeping with their local authority's approach on providing public access to this data". Bristol's catalogue: Exmoor "Open Government Licence"; North Somerset "Public Sector End User Licence"; Bristol Monuments "GIS User Agreement for external use"; Devon and Gloucestershire blank or constraints with no text; Somerset unspecified. All flagged `freetouse=false` |
| Attribution | Per source HER. `copyrightText` read "Bristol City Council" |
| Reuse class | link_only |
| Suggested mode | live, showing the HER's name and a record link on every result, and asking each HER in writing for permission to cache |
| Records | Devon 49,473 points and 71,369 polygons. Exmoor 12,322. Somerset 37,380. Gloucestershire 27,362. Wiltshire 32,920. BANES 9,008. North Somerset 7,948, 50 and 2,122. South Gloucestershire 6,400. Bristol 3,733. Worcester City 2,614 and 534 |
| Paging and limits | `maxRecordCount` 1000 or 2000 per service |
| CORS | Not checked in the first report. Yes in the follow-up, with the origin echoed and `allow-credentials` true |

```
https://maps2.bristol.gov.uk/server2/rest/services/ext/devon_hist_2021_v2/MapServer/4/query?where=1%3D1&outFields=*&resultRecordCount=1&outSR=4326&f=json
```

**Notes.**

- Field depth varied. Devon had name, type, summary, period and a Heritage Gateway URL. Wiltshire added `DESCRIPTION` and `SOURCES`. Somerset and BANES had only `PRN` and `NAME`.
- Currency varied. Devon was published in October 2023, Exmoor and Somerset updated "daily", and Gloucestershire was a 2017 snapshot with "update not planned". Service names carry years.
- Metadata JSON was at `https://maps.bristol.gov.uk/metadata/datasets/{dataset name}` as `Dataset.json` and `Constraints.json`. `kypwest.org.uk` was dead. Only Exmoor was clearly ingestible, and only on Bristol's catalogue entry.

## Exmoor, Dartmoor, Wiltshire and Wolverhampton HERs

Four HERs that serve their own monument layers, with no licence stated on the services. All four answered 200 `application/json` on 2026-11-10. Reuse class link_only, suggested mode live.

| | Exmoor | Dartmoor | Wiltshire and Swindon | Wolverhampton and Walsall |
|---|---|---|---|---|
| Publisher | Exmoor National Park Authority | Dartmoor National Park Authority | Wiltshire Council | City of Wolverhampton Council |
| Address | `https://services-eu1.arcgis.com/nvL9EDc30lviBdlc/arcgis/rest/services/MonPoly020525_PhotoNo/FeatureServer/0` | `https://services-eu1.arcgis.com/ygaMbwTQr2O0LMlb/arcgis/rest/services/Heritage_Environment_Record/FeatureServer` | `https://maps.wiltshire.gov.uk/arcgis/rest/services/Website/Monuments/MapServer` | `https://services2.arcgis.com/5K9ykSNwoxdIgeYH/arcgis/rest/services/HER_polys_260121/FeatureServer/0` |
| Records | `MonPoint020525` 3,369; `MonLine020525` 399; `MonPoly020525` 8,337, May 2025 | `HER_points` 6,904; `HER_areas` 25,391, August 2026 | `Mon_line` 21,134; `Mon_point` 25,432; `Mon_poly` 23,959 | `HER_points_260121` 755; lines 119; polygons 1,971 |
| CRS, paging, CORS | 3857 hosted, 2000, yes | 3857 hosted, 2000, yes | 27700, 1000, yes | 3857 hosted, 2000, yes |
| Attribution | "© Exmoor National Park Authority" | Dartmoor National Park Authority, "© Crown copyright and database rights 2026 OS AC0000823576" | Wiltshire Council Archaeology Service | City of Wolverhampton Council |

Each was tested with `{address}/query?where=1%3D1&outFields=*&resultRecordCount=1&outSR=4326&f=json`, using layer 0, except Wiltshire layer 2 (`.../MapServer/2/query?...`).

**Notes.**

- Exmoor: the items credited "© Copyright 2024 Exmoor National Park". The first report took OGL from Bristol's catalogue entry for the Know Your Place copy. The follow-up found that Exmoor's caveat page said NRHE data was "provided to the ENPHER under the terms of the Open Government Licence v3.0" but stated no licence for the layers. Fields `MonUID` (MDE, MSO, MEM, MMO prefixes), `Name`, `MonType`, `Summary`, `URL` (`https://www.exmoorher.co.uk/Monument/MDE1021`, 200). The website robots.txt set `Crawl-delay` 1000.
- Dartmoor: fields `monuid` (MDVnnn, sharing numbering with Devon), `name`, `montype`, with no description or period. Last edited 2026-08-06. Joining on the MDV number to the Devon layers gives summaries.
- Wiltshire: layers 1 line, 2 point, 3 polygon. The service sat in the "Website" folder, not the "OpenData" folder. Fields `MonUID` (MWInnn), `Name`, `MonType`, `Period`, `URL`. The layer description said "Update Frequency: Daily". The Know Your Place copy is a 2022 snapshot.
- Wolverhampton: fields `MonUID` (MBLnnn), `Name`, `Summary`, `MonType`, `Period`, `More_info` (new Heritage Gateway URL). Last edited 2026-09-22. The Heritage Gateway listed 4,787 records against 2,845 features here.

## Lincoln ARCADE

The City of Lincoln Council's heritage database, an Arches system with a public search API that returned points and geometries.

| | |
|---|---|
| Access | REST JSON |
| Address | `https://arcade.lincoln.gov.uk/search/resources?paging-filter={page}&tiles=true` |
| Tested on 2026-11-10 | Yes. 200 `application/json`. The first hit, "Lincoln Roman Colonia (Lindum)", had a point, a polygon and a full description |
| Format and licence | JSON with GeoJSON inside, WGS84. Licence unstated, with no terms page and robots.txt returning 404 |
| Reuse class | link_only |
| Suggested mode | live, after getting permission for any systematic use. The same platform at the Greater London HER carried an explicit scraping ban |
| Records | 18,539 resources of all types |
| Paging and limits | 25 per page |
| CORS | Not tested |

```
https://arcade.lincoln.gov.uk/search/resources?paging-filter=1&tiles=true
```

## Other national layers

Five national layers outside Historic England. Each was tested on 2026-11-10 and answered 200 with the request `{address}/query?where=1%3D1&outFields=*&returnGeometry=false&resultRecordCount=1&f=json`, except the planning platform. CORS was `yes` for the Forestry Commission layer and not checked on the others.

| Layer | Address | Licence and attribution | Class and mode | Records |
|---|---|---|---|---|
| England's Historic Parklands (Undesignated), Natural England | `https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/Englands_Historic_Parklands_Undesignated/FeatureServer/0` | "Use of this data is subject to the Open Government Licence". "© Natural England 2025, Contains historical maps provided by the National Library of Scotland, © Historic England 2025 Contains Ordnance Survey data © Crown copyright and database right 2025" | open, bulk | 4,517 polygons |
| NHLC 250 m grid, Natural England, Historic England, ALGAO | `https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/NHLC_250/FeatureServer/0` | Open Government Licence v3.0. "© Natural England copyright. Contains Ordnance Survey data © Crown copyright and database right [year]. © Historic England © ALGAO" | open, bulk from the hub download | 2,111,346 cells |
| Historic Environment Opportunity Map for New Woodland, Forestry Commission | `https://services2.arcgis.com/mHXjwgl3OARRqqD4/arcgis/rest/services/Historic_Environment_Opportunity_Map_For_New_Woodland/FeatureServer/0` | "Open Government Licence v3.0 applies". "Forestry Commission, OGL v3.0" | open, bulk as an optional hint layer | 552,503 polygons |
| Active Church of England churches, Church of England Data Services | `https://services5.arcgis.com/KDRjxGRQDVgVtFTS/arcgis/rest/services/Active_Church_of_England_Churches/FeatureServer/0` | Not open: "This data is supplied on a not for profit basis. Any reproduction of the data should include the notice '© Church of England, Data Services, 2026'" | non_commercial, live with the notice | 15,757 open. Closed layer `.../ChurchesNotOpenForPublicWorshipMaster/FeatureServer/0` 3,402 |
| Planning Data platform, MHCLG | `https://files.planning.data.gov.uk/dataset/{dataset}.geojson` | Not read, because the platform was down. Upstream data is OGL v3.0 | open upstream, deeplink. Prefer Historic England directly | Secondary copy |

**Notes.**

- NHLC is a context layer, not site records. Fields include `DominantBroadType`, `DominantType`, `EnclosureTypeGroup`, `DominantTypePeriodDescr`. EPSG:27700, 1,000 per page.
- Opportunity map: "Unclassified (No SHINE supplied)" was 27,738 polygons covering 7,448,388 ha, more than half of England. The first report said reference only and the follow-up, which wins, said bulk.
- Church fields include `Asset_ID`, `Listed_building__Grade_`, `Church_Heritage_Record`, `At_Risk`. EPSG:4326, 2,000 per page.
- Planning Data: a ranged request on `scheduled-monument.geojson` returned 206 `application/geo+json`, with `reference` set to the NHLE list entry. `entity.geojson` and `dataset.json` returned 503, and the error page said the platform had been unavailable since Friday 6 November 2026. EPSG:4326.

## Scottish council HER services

Public HER feature services from Scottish councils, checked to test a claim that none is open. They belong to the Scotland sources and are here because the follow-up covered them.

| | |
|---|---|
| Access | ArcGIS FeatureServer |
| Address | Stirling: `https://services-eu1.arcgis.com/cECIr59LclpO818r/arcgis/rest/services/open_data_historic_environment_records_sites/FeatureServer/0` |
| Tested on 2026-11-10 | Yes. 200 `application/json` |
| Format and CRS | JSON, GeoJSON. EPSG:3857 for Stirling, 27700 for the others |
| Licence | Stirling: "Data published by the Council at a URL beginning data.stirling.gov.uk is open to use, you do not have to apply or ask for permission, but you do have to adhere to the terms of the Open Government Licence, the Ordnance Survey, Historic Environment Scotland... or equivalent terms." Aberdeenshire: "Copyright is reserved... intended to be used for personal research only". Highland: "may be freely used for private or commercial research but the source must be acknowledged", but data may not be "circulated without our prior written consent". Falkirk: "Copyright Falkirk Council, contains Ordnance Survey data © Crown copyright and database right (year)" |
| Reuse class | open for Stirling. link_only for Aberdeenshire. Falkirk and Dumfries and Galloway attribution only or not stated |
| Suggested mode | bulk for Stirling. live only for Aberdeenshire, given its terms |
| Records | Stirling 5,744 points. Aberdeenshire 38,285 polygons. Falkirk 2,175 points and 29 lines. Dumfries and Galloway 17,365 points |
| Paging and limits | `maxRecordCount` 1000 to 2000 |
| CORS | Yes, hosted |

```
https://services-eu1.arcgis.com/cECIr59LclpO818r/arcgis/rest/services/open_data_historic_environment_records_sites/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=1&outSR=4326&f=json
```

**Notes.** The claim that no Scottish council HER was open was wrong in one case, Stirling. Aberdeenshire served Aberdeenshire, Moray, Angus and Aberdeen City, edited November 2026. Falkirk's service was archived in 2024. Dumfries and Galloway's stated no licence. WoSAS offered search only, with no download, service or licence statement on the pages read. Highland had no data service found. Perth and Kinross items existed but their ArcGIS subscription was cancelled.

## Avoid

### Greater London HER Online

Address `https://glher.historicengland.org.uk/`. Tested on 2026-11-10: the home page returned 200 `text/html` and `/search/resources` returned 200 `application/json` with 184,086 Arches resources of all types. Reuse class link_only, mode deeplink to the home page only. CORS not tested.

Terms: "You shall not conduct, facilitate, authorise or permit any text or data mining or web scraping"; "not intended to be a source for bulk downloads"; "You must not use any part of the content on GLHER Online for commercial purposes"; "nor may you create a link to any part of GLHER Online other than the home page". Anything beyond a home-page link needs written permission from `glher@HistoricEngland.org.uk`.

### Peak District NPA HBSMR reference layers

Twenty-seven internal reference layers at `https://arcportal.peakdistrict.gov.uk/server/rest/services/Cultural_Heritage/PDNPA_HBSMR_Layers/FeatureServer`. Tested on 2026-11-10 with read-only queries only: 200 `application/json`, EPSG:27700, CORS no. Licence unstated, because the portal item had empty licence and credit fields. Reuse class link_only, mode deeplink.

The service advertised "Query,Create,Update,Delete,Uploads,Editing,Extract" with no token. Whether writes succeeded was not tested. Attributes leaked internal file paths. The layers are survey data, not the HER monument table. The largest layer was Digitised Peak Archaeology, layer 9, with 14,569 polygons.

### District and partial HER extracts

Four public ArcGIS Online services that held part of a county HER. Licence unstated, tested 200 `application/json`, CORS yes, reuse class link_only, mode deeplink.

| Publisher | Address | Records |
|---|---|---|
| Stafford Borough Council | `https://services-eu1.arcgis.com/TZlAwZ6z4m2tSwbS/arcgis/rest/services/SBC_LP_HER_Point/FeatureServer/0` | 3,880 points, February 2026 |
| Lichfield District Council | `https://services6.arcgis.com/pCNvuqillBxYX3LQ/arcgis/rest/services/HER/FeatureServer` | 4,172 points, 2,643 lines, 5,889 polygons, 2018 |
| Salford City Council | `https://services-eu1.arcgis.com/kkZ3q6EOlzIRG0yO/arcgis/rest/services/DEV_Salford_HER_Point_Public/FeatureServer/0` | 1,665 points, 16 lines, 280 regions, 2025 |
| North York Moors NPA | `https://services-eu1.arcgis.com/V8zL4RLJ5DGg9eTG/arcgis/rest/services/HER_Monuments/FeatureServer` | 319 points, 29 lines, 135 polygons, 2026 |

Unlicensed third-party copies of the Oxfordshire HER, Historic England Research Records and Northumberland HER points sat in Oxford University student and AOC Archaeology accounts. They were not to be used.

### Stale data.gov.uk HER records

Older catalogue entries for HER data. Reuse class link_only, mode deeplink. The Bristol Monuments CSV at `https://www.bristol.gov.uk/files/documents/4629-bristol-monuments-open-data/file` returned 200 `text/csv`, 2.8 MB, 3,626 rows, latest edit January 2011, with no licence on data.gov.uk. Wolverhampton's record had no resources and "Public Sector End User Licence - INSPIRE". Southend's WMS 1.3.0 capabilities returned 200 for layer `sos_hbsmr_march2013` under the same INSPIRE licence. Barnet's snapshot of 05/02/2015, 3.5 MB with 541 monument IDs, was for personal use with no commercial exploitation. Bristol's live layer is on the Know Your Place server and Wolverhampton's on ArcGIS Online. Cheshire East and Cheshire West "HBSMR" datasets were designations and constraint zones, not monuments.

### Keys to the Past map server

Address `https://spatial.durham.gov.uk/arcgis/rest/services/External/VectorPoint/MapServer/12`. Tested on 2026-11-10: 200, record D1, Cromwell's Bridge, Dalton-le-Dale. EPSG:27700, 66,210 points, fields `PRN`, `NAME`, `EASTING`, `NORTHING`, `LOCAL_LIST`. CORS not checked. Licence not stated on the service, and the website's copyright terms are under Deep link only. Reuse class link_only, mode deeplink.

### SHINE

The Selected Heritage Inventory for Natural England, non-designated features compiled by HERs for agri-environment schemes. Address `https://www.myshinedata.org.uk/retrieve-hefer`, tested 200 `text/html`. Access was per holding by a nine-digit Single Business Identifier, giving PDF reports. SFI reports at `https://hefer-data.org.uk/` needed registration. No SHINE layer was found on data.gov.uk or ArcGIS Online. Land App's download said "Data may only be used for Environmental Land Management Planning" and "Not all ALGAO authorities have given permission to Land App to access the data". Reuse class link_only, mode deeplink. It cannot be had as a dataset without agreement from ALGAO and each HER.

## Deep link only

Sources that could not be read by script, or whose terms forbade it. Each pattern was observed on 2026-11-10 unless stated. Historic England pages returned a Cloudflare challenge to curl, so a link checker cannot verify them and they should open in the user's browser.

| Source | Link pattern | Notes |
|---|---|---|
| NHLE list entry | `https://historicengland.org.uk/listing/the-list/list-entry/{ListEntry}` | 403 with `cf-mitigated: challenge` to curl with a generic or Chrome user agent. Website content is not covered by the Open Data Hub licence |
| Aerial photo record, research report | `https://historicengland.org.uk/images-books/archive/collections/aerial-photos/record/{Filename}`; `https://historicengland.org.uk/research/results/reports/{n}` | 403 to curl |
| Heritage at Risk entry | `https://historicengland.org.uk/advice/heritage-at-risk/search-register/list-entry/{id}` | Not fetched. Historic England asked people not to scrape |
| Aerial Photo Explorer and Mapping Explorer | `https://historicengland.maps.arcgis.com/apps/webappviewer/index.html?id=2626ed0c37484d96b8954dd33187084e&center={lon},{lat}&level={zoom}` | 200 `text/html`, shell only. Mapping Explorer id `d45dabecef5541f18255e12e5cd5f85a`. `center` and `level` are standard Web AppBuilder parameters, not checked in a browser |
| Heritage Gateway | Record, legacy and NRHE search patterns are in the Heritage Gateway section | 301 from legacy links. Keep legacy links stored in source data |
| Keys to the Past | `https://keystothepast.info/search-records/results-of-search/results-of-search-2/site-details/?PRN={N|D}{number}` | 200. N is Northumberland, D is Durham. "It is unlawful to duplicate or distribute any element of this, without expressed written permission"; "You may not resell, sub-license or distribute any of the content in any form". Linking: "you do not have to ask permission to link directly to pages hosted on this website". Framing not permitted. |
| National Trust | `https://heritagerecords.nationaltrust.org.uk/HBSMR/MonRecord.aspx?uid={MNA id}` | 200, Corfe Castle MNA136633. Terms 10.4: "No other use (including, without limitation, the alteration, deletion, utilisation or extraction) of the content ... is permitted without Our written permission." Terms 11.1: "You must not link to the Site for commercial purposes without our written agreement." No heritage dataset on its open data hub. Record ids were reachable through the ADS API with `contributor=National Trust` |
| Church Heritage Record | `https://heritage.churchofengland.org/buildings/{Asset_ID}` | 200 after redirect from the old `facultyonline.churchofengland.org/CHR/ChurchDetails.aspx?id={n}`. Pages give the NHLE list entry number. Licence not stated |
| HER record pages | `https://heritage.suffolk.gov.uk/Monument/{MSFnnn}`; `https://www.heritage.norfolk.gov.uk/record-details?{MNFnnn}`; `https://heritage-explorer.lincolnshire.gov.uk/Monument/{MLInnn}`; `https://her.york.gov.uk/monument/{MYOnnn}`; `https://www.exmoorher.co.uk/Monument/{MDEnnn}`; `https://twsitelines.info/SMR/{n}` | All 200. Site terms "all rights reserved unless stated", not read for every site. |
| Defence of Britain | `https://doi.org/10.5284/1000327` | Not tested. Archive and download pages returned 403. The first report saw 15,416 phrase hits and an unverified licence. The ADS follow-up, which wins, found 20,173 site-level records in the catalogue API and DataCite gave "ADS Terms and Conditions apply to reuse". See the ADS section. |

Other HER home pages returned 200 or failed to curl. No documented public HER API was found.

## Open questions

- Does Heritage Gateway map search return coordinates, and what radius does `initialLatLong` use?
- Will Historic England licence the aerial photo footprints and thumbnails for a third-party map? Does the NMP raster service itself carry OGL 3.0, and will it permit proxying or re-tiling?
- Can Historic England supply the terrestrial NRHE records as an OGL bulk file, given it already licenses them to HERs?
- What is the snapshot date of the NRHE copy in ADS? Do ADS terms allow a public non-commercial tool to show results through a caching proxy?
- Which text governs Lincolnshire's extract? Will Cornwall confirm OGL v3.0 for its INSPIRE service despite the non-commercial text on its ArcGIS Online item, and is the service current given metadata of 2020-09-29? Does Exmoor regard its layers as OGL? Would the Know Your Place partners permit caching?
- Which 13 HERs had completed the NRHE transfer? Why does Essex appear on the new Gateway while the FAQ listed it as unavailable? The eleven HERs with no public record are listed in [England HER coverage](england-her-coverage.md).
- Is SHINE available on request? Would the National Trust licence its records?
- What licence will the Planning Data platform state once restored?
- What licence and format does the Defence of Britain archive carry? Does WoSAS supply HER data on request?
- The follow-up recommended repeating the survey in spring 2027, because Heritage Gateway was adding datasets.
