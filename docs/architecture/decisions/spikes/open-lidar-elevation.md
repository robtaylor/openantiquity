# Spike — Is raw 1 m LIDAR elevation openly available for the whole UK?

**Status:** Resolved (2026-11-10) — PARTIAL; raw 1 m elevation was open for 99.73% of England and all of Wales, but only 39.4% of Scotland and 16.6% of Northern Ireland

## Question

Is raw 1 m (or finer) LIDAR elevation, as float values and not as a rendered picture, openly available for the whole UK?

## Why this is in question

Decision 0006 renders terrain tiles from raw elevation, not from publishers' ready-made hillshades. That only works if raw elevation can be fetched or mirrored in every nation, under a licence that allows it. Nothing was known about how much of each nation was covered, what each publisher offered, or whether the National Library of Scotland, Defra, Welsh Government and the Northern Ireland departments published anything in a form a program could read.

## Approach

The research pass of 2026-11-10 tested every route to UK LIDAR that it could find. It had three inputs: one report on England, one on Scotland, Wales and Northern Ireland, and a follow-up on coverage holes and the England bulk path. Where the follow-up and the earlier reports disagreed, this record gives the follow-up and says so.

- **Q1.** Does each nation publish raw float elevation, as opposed to colour ramps or hillshades?
  - Step 1: Call each publisher's raster services (WCS, ImageServer, WMS, WMTS) and read the pixel values.
  - Step 2: List and download one sample tile or window from each bulk source and decode it.
  - Step 3: Read the licence and attribution text on each publisher's own record.
- **Q2.** How much of each nation does open raw elevation cover?
  - Step 1: Fetch the published footprint or tile-index polygons for each nation.
  - Step 2: Clip them to the ONS Countries (December 2025) polygons and sum the area.
  - Step 3: Test known monuments against the footprints and read pixel windows where the footprints were doubtful.
- **Q3.** Can the data be bulk-copied, and how big is it?
  - Step 1: Measure sample tile sizes and transfer rates.
  - Step 2: Re-encode one England tile as cloud-optimised GeoTIFF with several codecs.

The pass downloaded about 241 MB of England tile zips, one Northern Ireland Historic Environment Division tile of 4.2 MB, one OSNI 10 m sheet of 5.2 MB, one OS Terrain 50 tile of 1.3 MB, and range-read windows from Scottish, Welsh and Copernicus files. It submitted no request form and contacted no publisher.

## Decision matrix

| Outcome | Means | Action |
|---|---|---|
| Raw elevation is open in no nation | Rendering from raw elevation is impossible | Decision 0006 is dropped. Field Club would have shown publishers' own renderings. |
| Open in every nation at full coverage | One pipeline serves the whole UK | Decision 0006 is accepted unchanged. Resolves YES. |
| Open in every nation, but with large coverage holes | The pipeline works, but must show where it has no data | Decision 0006 is accepted with a coverage layer and labelled fallback terrain. Resolves PARTIAL. |
| Open in some nations only | Two tiers of service | Decision 0006 is narrowed to those nations. |

The result was the third row. Raw elevation was open in all four nations, with holes in two of them.

## Findings

### Coverage

Computed on 2026-11-10 from published footprints, clipped to the ONS Countries December 2025 polygons. Evidence: the footprint and catalogue addresses in the per-nation entries below.

| Nation | Open raw elevation | Resolution | Notes |
|---|---|---|---|
| England | 99.73% (130,107 of 130,459 km2) | 1 m composite, 2022 | Source patches were 1 m, 0.5 m or 0.25 m, all resampled to 1 m. |
| Wales | 100.00% (0.1 km2 uncovered of 20,782 km2) | 1 m, 2020-23 | 22,473 tiles of 1 km. |
| Scotland | 39.4% (31,059 of 78,794 km2) | 0.5 m or 1 m, with 0.25 m for some sites | 60.6% (47,736 km2) uncovered. 29.6% is at 50 cm or better, 9.8% at 1 m only. |
| Northern Ireland | 16.6% (2,373 of 14,312 km2) | 1 m river-basin, 0.125 to 0.5 m archaeology sites | 83.4% uncovered. The DAERA coastal strip was not in the figure. A geometric estimate put it at about 110 km2 of land, taking the total to roughly 17%. |

- 2026-11-10: 34.4% of Scotland's scheduled monuments (2,781 of 8,076) lay outside all open LIDAR. By council, Shetland was 317 of 391 (81.1%), Highland 904 of 1,280 (70.6%), Argyll and Bute 483 of 810 (59.6%), Na h-Eileanan Siar 133 of 220 (60.5%), Dumfries and Galloway 2.2% and Orkney 0.8%. The test used one point per monument. Evidence: https://inspire.hes.scot/arcgis/rest/services/HES/HES_Designations/MapServer/5
- 2026-11-10: 75.3% of Northern Ireland's scheduled or state-care records (1,708 of 2,268) and 79.3% of its other records (12,894 of 16,251) lay outside the river-basin and Historic Environment Division LIDAR. Evidence: https://admin.opendatani.gov.uk/dataset/46240fa5-db15-469e-b1c8-0460504b951c
- 2026-11-10: the follow-up named ten well-known Scottish sites with no open LIDAR, among them Calanais Standing Stones (7.0 km from coverage), Dun Telve and Dun Troddan (38.9 km), Dunsinane Hill (4.0 km) and Urquhart Castle (7.8 km). It named ten in Northern Ireland, among them Beaghmore stone circles (11.4 km) and Slieve Gullion passage tomb (6.4 km). Navan Fort, Giant's Ring, Tullaghoge and Dunseverick were covered.
- 2026-11-10: Burnswark was reported as uncovered by the earlier report and as partly covered by the follow-up. The follow-up wins. The Phase 3 50 cm footprint contains the scheduled-monument point. A 1 km window was 65.1% valid. Both Roman camps were clear, but the summit sat 103 m inside a NoData hole at the survey edge. Evidence: https://srsp-open-data.s3.eu-west-2.amazonaws.com/lidar/phase-3/dtm/27700/gridded/NY17NE_50CM_DTM_PHASE3.tif
- 2026-11-10: the earlier Scottish report gave 41-44% coverage and the follow-up gave 39.4%. The follow-up clipped to country polygons and used the 2025 footprints, so it wins. The Northern Ireland river-basin share also moved, from about 14% to 15.7%.
- 2026-11-10: the Scottish footprint WFS (`scotland:dsm-footprint-aggregate`, 19 features) lagged the bucket. It lacked the coastal 2025-26 survey and most National LiDAR Programme blocks. Coverage had to be derived from bucket tile names as well.
- 2026-11-10: fallback terrain showed landform and no monument-scale features. OS Terrain 50 gave 10 by 10 pixels over a 500 m box. Copernicus GLO-30 gave 17 by 19 pixels of a surface model, not bare earth. The OSNI 10 m DTM at Beaghmore showed drumlins and stream channels but not the stone circles.

### England

- 2026-11-10: the 2022 composite was reachable three ways, all under Open Government Licence v3.0 with no key. These were the Defra ArcGIS ImageServer proxy (2025 edition), the Data Services Platform WCS 2.0.1 (2022 edition) and 5 km tile zips (2022 edition). Evidence: https://environment.data.gov.uk/dataset/13787b9a-26a4-4775-8523-806d13af58fc
- 2026-11-10: a newer 2025 composite existed only as an ArcGIS image service. The item said it was produced in 2025 from surveys of the 2016/17 to 2024/25 seasons, with vertical accuracy of +/-10 cm RMSE. The tile search returned `lidar_composite_dtm` for 2022 only. The ImageServer's download operation was unsupported and `exportTilesAllowed` was false. Evidence: https://www.arcgis.com/sharing/rest/content/items/f9c4694d7d5140638536c4afe4119e6d?f=json
- 2026-11-10: the two editions differed. Over a 500 m box at Avebury, ImageServer minus WCS had mean -0.041 m, median -0.045 m and standard deviation 0.054 m, with a range of -0.82 to +0.97 m. Only 0.3% of pixels were identical and 8% differed by more than 10 cm. The report advised against mixing them in one layer.
- 2026-11-10: the 2025 service was valid over 100.00% of England on a 400 m sample grid. 351 km2 existed in 2025 and not in 2022, all on the North York Moors at E 470-500 km, N 480-500 km. No area existed in 2022 and not in 2025.
- 2026-11-10: the ImageServer's catalogue listed 5,779 tiles of 5 km, all with `CompYear` 2025-06-01. The 2022 download catalogue listed 5,876. 5,769 were shared. Evidence: https://environment.data.gov.uk/backend/catalog/api/tiles/collections/survey/search
- 2026-11-10: a 2025-equivalent could be built from the 2022 composite plus 3,168 DTM tiles flown after it: `national_lidar_programme_dtm` 2022 (529) and 2023 (538), and `lidar_tiles_dtm` 2022 (1,034), 2023 (676) and 2024 (391). The size of those patch tiles was not measured.
- 2026-11-10: ImageServer timings differed between reports. The earlier report measured about 0.9 s at any extent, with 29 of 30 requests succeeding. The follow-up measured a median of 1.94 s and a p90 of 2.36 s per 256 px request in a burst of 24 at concurrency 6, with an uncompressed response of 263,352 bytes. The follow-up also noted several 30-45 s timeouts and one 502 in about 128 requests. The follow-up's figures are the later ones. No rate limit was published. Evidence: https://utility.arcgis.com/usrsvcs/servers/f9c4694d7d5140638536c4afe4119e6d/rest/services/LIDAR/LIDAR_Composite_1m_DTM/ImageServer
- 2026-11-10: ImageServer size limits were 3072 by 3072 px accepted (27.8 MB, 4.75 s), 4096 by 4096 HTTP 500 and 5000 by 5000 HTTP 400. The follow-up recorded a 2880 by 3272 whole-England export returning 500 and 1440 by 1636 working.
- 2026-11-10: the ImageServer returned voids as +3.4028235e38 with no nodata tag. The WCS returned nodata -3.4028234663852886e+38 with the tag set in the earlier report. The follow-up found that inside the North York Moors gap the WCS returned 256 by 256 pixels of 0.0 with no NoData tag, in 0.79 s, while the ImageServer returned 249.98 m at the same point. The follow-up wins on voids. Evidence: https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs
- 2026-11-10: the WCS was bit-identical to the downloadable tile SU16nw_DTM_1m.tif over a 500 by 300 px overlap. It took about 1 s for 300 m boxes and 3.2-5.0 s for 20 km at 256 px. A 100 km box gave no response in 90 s. Between 2.5% and 11% of small requests never returned in one period, and 0 of 20 in a later clean sample. The earlier report suspected that part of the higher figure came from its own abandoned requests.
- 2026-11-10: the 5 km tile zips returned HTTP 405 to HEAD and no Content-Length, and ignored Range. Five full downloads measured 38.7 to 84.0 MB per tile at about 8.5 MB/s. The follow-up estimated about 321 GB for the whole 1 m DTM, with a range of 214 to 465 GB, on a weak basis of five samples. The earlier report had given an upper bound of about 278 GB. A non-existent tile or year returned HTTP 200 with a 22-byte empty zip.
- 2026-11-10: the Environment Agency's survey FAQ, updated 14 March 2022, said "There's no option of bulk download for the whole country or for a large area. This would need to be supplied offline." It pointed to the Large Data Download request form at https://environment.data.gov.uk/support/datadownload. The form was not submitted and its fields, cost and turnaround were not read. The website capped a selection at fewer than 48 tiles, but the search API returned 2,449 results for a 50 km box. Evidence: https://environment.data.gov.uk/support/faqs/275879146
- 2026-11-10: no numeric rate limit or anti-caching clause was found in the Data Services Platform terms, updated 5 September 2023. They said "You must also use it in a way that doesn't infringe the rights of, or restrict or inhibit the use and enjoyment of, the site by anyone else". No terms were found for the ArcGIS proxy beyond the item's OGL statement.
- 2026-11-10: the ArcGIS proxy was found through ArcGIS Online search, not through the Data Services Platform dataset page. The item carried the keyword "Service Proxy". Its source server needed a token, and `serviceProxyParams` was null in the public JSON.
- 2026-11-10: the 2022 survey index (`LIDAR_Composite_1m_DTM_2022_extents`, 21,380 polygons) gave flown dates per location. Source patch resolution by count was 1 m 15,094, 0.5 m 4,803 and 0.25 m 1,483. Patch area by flown year was 2018 22.6%, 2019 21.7%, 2020 20.4%, 2021 22.4%, and 4.0% for 2022. No 2025 survey index was found.
- 2026-11-10: the CORS findings were these. The WCS, WMS, WMTS and OGC API Features sent `access-control-allow-origin: *`. The ImageServer reflected the Origin. The tile search API and tile zips sent no allow-origin header on the actual response, so they were server-side only.
- 2026-11-10: the one old endpoint `environment.data.gov.uk/image/rest/services` returned HTTP 200 with a 72-byte error body for every path.

### Scotland

- 2026-11-10: raw float32 DTMs were open GeoTIFFs in the listable S3 bucket `srsp-open-data` (eu-west-2), with CORS `*` and Range preflight allowed. The bucket held 76,996 objects and 3,381.65 GB, of which DTM GeoTIFF was 625.4 GB. Evidence: https://srsp-open-data.s3.eu-west-2.amazonaws.com/?list-type=2&delimiter=/&prefix=lidar/
- 2026-11-10: the WCS was switched off. The GeoServer WMS and WMTS offered colour ramps only (`lidar-dem-viridis`, `lidar-dem`, `lidar-presence`). The WMS honoured a user `sld_body` with a ShadedRelief symbolizer, but ignored it for 256 px requests aligned to the EPSG:3857 grid and for the aggregate group.
- 2026-11-10: collections differed in structure. Phases 1 and 2 were 1 m in 10 km tiles with no overviews. A 10 km phase 1 tile read at 20 m pixels took 34 s. Phases 3 to 6 were 0.5 m in 5 km tiles of 10000 by 10000 px, up to 470 MB each. The National LiDAR Programme was 0.5 m in 1 km cloud-optimised tiles. Nodata was -9999, except for the programme at -32767.
- 2026-11-10: DTM object counts were phase 1 382, phase 2 232, phase 3 674, phase 4 420, phase 5 250, phase 6 77, programme 5,933, coastal 1,169, Orkney 1,655, Hebrides 327 and HES 801. Phase 1 pixel size was 1.0000026 by 0.9999934 m.
- 2026-11-10: the National LiDAR Programme was live. The Scottish Government blog of 29 January 2026 said it ran "from May 2025 - July 2027" with releases "at approximately 6 month intervals through the programme to provide full national coverage above high tide". 5,933 DTM tiles had been released by 2026-09-25, covering 5,081 km2 on land (6.4%), about 1,490 km2 of it new ground. That commitment was a blog statement and not a dated schedule. Evidence: https://blogs.gov.scot/digital/wp-json/wp/v2/posts/5809
- 2026-11-10: licences were not uniform. The portal's per-collection metadata gave Open Government Licence v3 for phases 1 to 6, Outer Hebrides 2019, Orkney 2023, HES 2016, HES 2017, HES 2017sp3, coastal 2025-26 and the programme. Four HES collections (`hes_2010`, `hes-2010s10`, `hes-2016-2017`, `luing`) and the Phase 2 LAZ files were under the Non-Commercial Government Licence v2. The required wording was "HES licence this data for non-commercial use only as permitted by Fugro, the owners of the data." The AWS registry page named only Phase 2 LAZ as an exception, so it was out of date. These sets held 6.17 GB of DTM and included the 25 cm Antonine Wall survey. Evidence: https://api.remotesensing.data.gov.scot/search/collection/scotland-gov/*
- 2026-11-10: attribution strings, as recorded, were these. Phase 1: "Crown copyright Scottish Government, SEPA and Scottish Water (2012)". Phases 2 and 3: "Copyright Scottish Government and SEPA (2014). Fugro retain the commercial copyright." Hebrides: "(c) SEPA (2019)". National programme: "Crown copyright Scottish Government (c) Crown copyright and database right (2025)". Coastal: "Crown copyright Scottish Government". Phases 4 to 6 and Orkney gave a licence and no attribution statement.
- 2026-11-10: Rough Castle on the Antonine Wall was used for the Scottish read test, 500 m box 284100,679450 to 284600,679950. Phase 4 returned 1000 by 1000 float32 pixels at 0.5 m, all valid, 51.73 to 101.60 m, in 0.30 s to open and 0.66 s to read.
- 2026-11-10: the old host `srsp-ows.jncc.gov.uk` returned a 302 redirect to `ows.remotesensing.data.gov.scot`, and `eo.jncc.gov.uk` timed out. The portal's catalogue API was found in the portal's JavaScript bundle and was undocumented.
- 2026-11-10: two searches found no other open Scottish LIDAR holder outside the portal. The follow-up marked this as absence of evidence from two searches, not a catalogue audit. Nobody was contacted.

### Wales

- 2026-11-10: the DataMapWales GeoServer had no LIDAR raster WMS or WCS layers. The national 1 m DTM was one cloud-optimised GeoTIFF on Azure Blob, `wales_dtm_32bit_cog.tif`, 48,611,310,928 bytes, float32 with DEFLATE and overviews 2 to 64, quantised to 0.01 m. Evidence: https://dmwproductionblob.blob.core.windows.net/cogs/lidar/wales_dtm_32bit_cog.tif
- 2026-11-10: the 16-bit COG held whole metres and the report rated it useless for earthworks. The tinted hillshade COG made the Tre'r Ceiri ramparts and hut circles barely visible.
- 2026-11-10: a Tre'r Ceiri 500 m box read 500 by 500 pixels at 1 m, all valid, 304.38 to 486.50 m, in 0.25 s to open and 0.54 s to read. The per-kilometre tile carried the flight date 2021-03-02.
- 2026-11-10: the follow-up counted 22,473 1 km tiles in the WFS catalogue, by year 2020 3,679, 2021 8,548, 2022 10,201 and 2023 45. HEAD requests on 50 random links gave a mean of 2.18 MB, so about 49.1 GB (plus or minus 2.3 GB at 95%). The tiles were float32 DEFLATE and striped, not cloud-optimised.
- 2026-11-10: the Welsh licence was recorded inconsistently. The two map pages that published the COG URLs said "Open Government Licence for Public Sector Information (OGL)". The tile-catalogue layer and its CSW record said "Not Specified". No publisher attribution string was given anywhere. The follow-up did not re-read the licence.
- 2026-11-10: the Azure blobs sent no CORS headers for third-party origins. The preflight returned 403 "CORS not enabled" and allowed only `https://datamap.gov.wales`. DataMapWales had announced a beta site on 2026-06-23, so paths might change.
- 2026-11-10: the Natural Resources Wales archive (1998-2015) held 14,942 tiles, covering 73.2% at 2 m, 60.4% at 1 m, 5.8% at 0.5 m and 0.4% at 0.25 m. Its attribution was "Contains Natural Resources Wales information (c) Natural Resources Wales and Database Right. All rights Reserved."

### Northern Ireland

- 2026-11-10: there was no national LIDAR. The open sets, all under UK Open Government Licence v3, were the OSNI river-basin surveys 2004-2014 (77 blocks, 1 m, 2,240 km2, Belfast excluded), the Historic Environment Division archaeology surveys 2008-2014 (39 sites, 0.125 to 0.5 m, 172.5 km2), DfI Rivers Lough Neagh 2017 (1 m) and Belfast 2006 (0.5 m), and a DAERA 2021 coastal strip. Evidence: https://admin.opendatani.gov.uk/api/3/action/package_search?q=lidar&rows=200
- 2026-11-10: the files were zipped ESRI ASCII grids with no CRS embedded. Irish Grid (EPSG:29902) was assumed from the extents shapefile. The Historic Environment Division note said some surveys were in ITM, and later zips held both copies. Nodata was -9999 or -99. The follow-up counted 39 zips, 21.86 GB and 7,312 members for the Historic Environment Division sets, and 56.9 GB for all NI downloads.
- 2026-11-10: a 2012 river-basin tile (Burren_03_03_2012) held integer values such as 170790, which are millimetres, though the official note said metres. Only one tile was decoded, so the share of millimetre files was not known.
- 2026-11-10: the Historic Environment Division Tullaghoge tile read 1250 by 1250 cells at 0.2 m with NoData -99, and its hillshade showed the double-banked fort and plough ridges clearly. One member was extracted by range request, 4.2 MB fetched of a 227 MB zip. Evidence: https://opendatani.blob.core.windows.net/archaeologylidar/Tullaghoge.zip
- 2026-11-10: the DAERA coastal survey was an ArcGIS ImageServer tile cache of float32 LERC, source 0.25 m, covering the intertidal zone to about 200 m inland. Its footprint layer could not be queried. The follow-up did not re-test the elevation cache.
- 2026-11-10: DAERA news of 2022-02-09 said "A LiDAR survey covering all of Northern Ireland, has recently been announced" for the Soil Nutrient Health Scheme. AFBI on 2024-08-20 described a "specially commissioned LiDAR survey" over 6,927 km2 of Zones 1 and 2, 48% of NI. A search of OpenDataNI for the scheme returned 0 datasets. No licence or release plan was found.
- 2026-11-10: DAERA peatland and special-area-of-conservation hillshade services carried the item licence "Internal use only." They were publicly reachable and not licensed for reuse.
- 2026-11-10: Azure Blob, Cloudflare R2 and the OS Downloads redirect honoured Range. A zip's central directory could be listed and single members extracted without downloading the archive. OpenDataNI links redirected to presigned R2 URLs that expired after 7 days and rejected HEAD.

### Mirror size

- 2026-11-10: the follow-up estimated DTM-only source bytes at England about 320 GB, Scotland 625 GB, Wales 49 GB and Northern Ireland about 25 GB as cloud-optimised GeoTIFF, which is about 1.02 TB. As lossless COG with overviews it came to about 1.1 TB. With LERC_ZSTD at 1 cm it came to about 0.5 TB. Adding surface models roughly doubled it.
- 2026-11-10: one England tile (SU16nw, 48.20 MB source) re-encoded as COG with 512 px blocks came to 52.95 MB with DEFLATE and predictor 3, 51.92 MB with ZSTD, 36.43 MB with LERC_ZSTD at 1 mm, 27.87 MB with LERC at 1 cm, 23.54 MB with LERC_ZSTD at 1 cm and 10.54 MB with LERC_ZSTD at 5 cm. The factors came from one chalk-downland tile.
- 2026-11-10: full Scottish national coverage at 50 cm would add about 1.2 TB of LZW DTM. At about $0.023 per GB-month, a price that was not re-checked, 1.1 TB was about $25 a month in Standard storage. Egress and CDN costs were not estimated.

### Sources and suggested use

Reuse class and access mode follow Decision 0004 and Decision 0007. "Bulk" here means copied into a mirror or a cache. Decision 0007 defines "live" as a query by the user's browser with nothing stored. A server-side fetch on demand stores a copy, so it is marked bulk here, and whether Decision 0007 allows it is not settled. The suggestions come from the research reports and are not built.

| Source | Reuse class | Suggested access mode | Required wording, as recorded |
|---|---|---|---|
| England composite DTM tiles, 2022 | open, Open Government Licence v3.0 | bulk | "© Environment Agency copyright and/or database right 2022. All rights reserved." |
| England 2025 ArcGIS ImageServer | open, "Open Government License (OGL)" | bulk, fetched on demand behind a cache as the interim source | "© Environment Agency copyright and/or database right 2025. All rights reserved." |
| England WCS | open | bulk, fetched on demand with a coverage mask, never alone | as the 2022 tiles |
| Scotland phases 1-6, Hebrides, Orkney, coastal, programme, HES 2016, 2017 and 2017sp3 | open, Open Government Licence v3 | bulk | per collection, as listed above |
| Scotland HES 2010, 2010 S10, 2016-2017, Luing and Phase 2 LAZ | non_commercial, Non-Commercial Government Licence v2 | bulk, in a separate prefix with a licence flag | "HES licence this data for non-commercial use only as permitted by Fugro, the owners of the data." |
| Wales national 1 m COG and tiles | open, "Open Government Licence for Public Sector Information (OGL)", with the catalogue saying "Not Specified" | bulk | none given by the publisher |
| Wales NRW archive | open, Open Government Licence v3 | bulk, 0.25 m and 0.5 m tiles only | "Contains Natural Resources Wales information (c) Natural Resources Wales and Database Right. All rights Reserved." |
| Northern Ireland river-basin, Historic Environment Division, Lough Neagh, Belfast | open, UK Open Government Licence v3 | bulk | no statement found; Belfast 2006 needed a Cyient Europe Ltd acknowledgement, not read |
| DAERA 2021 coastal tile cache | open, Open Government Licence v3.0 | live | "Department of Agriculture, Environment and Rural Affairs (DAERA), Bluesky" |
| DAERA peatland hillshade services | link_only, "Internal use only." | deeplink | "(c) NIEA 2026" as recorded. Not tested |
| OS Terrain 50, OSNI 10 m DTM | open, Open Government Licence v3 | bulk, context only | "Contains OS data (c) Crown copyright [and database right] [year]." for Terrain 50 |
| Copernicus GLO-30 | open, free under the Copernicus DEM licence, annex wording not read | bulk, context only | AWS page asks: "Copernicus Digital Elevation Model (DEM) was accessed on DATE from https://registry.opendata.aws/copernicus-dem." |
| National Library of Scotland rendered tiles | open underlying data; hosting terms not found | deeplink | "Crown copyright Scottish Government, SEPA, Fugro and Scottish Water (2012-2021)" and "With thanks to Richard Pearson for processing using RVT" |

Suggested use, from the research reports:

- Mirror each nation to cloud storage and convert to one cloud-optimised mosaic per nation with per-survey provenance. Mirror, do not proxy, England. Ask the Environment Agency through its Large Data Download form first, and ask for the 2025 composite by name. If that fails, crawl one stream at a time, which the follow-up put at about 11 hours for 320 GB.
- Until a nation is mirrored, read it from the publisher on demand: the ImageServer for England, a range request on the national file for Wales, the open bucket for Scotland.
- Ask the Defra Data Sharing & Access Team whether third-party applications may call the ArcGIS proxy at tile-serving volume.
- Keep the four non-commercial Scottish collections out of the default mosaic and show them as a separate labelled layer.
- Show a coverage layer from day one, built from footprints and tile names, with capture year and resolution. Label OS Terrain 50, the OSNI 10 m DTM and Copernicus GLO-30 as context only.
- Write a normalising ingester for Northern Ireland that sets the CRS explicitly, handles both nodata values, and detects millimetre files by value range.
- Treat any monument within about 200 m of a footprint edge as needing a pixel-level check.
- Write to DAERA and AFBI to ask for release of the Soil Nutrient Health Scheme survey. It was the only route found to whole-nation coverage in Northern Ireland.

### Not tested

- The `?subscription-key=public` variant of the England tile download URL appeared in the site's JavaScript. It was not requested.
- The 10 m England zip was identified by its header only. A 64 KB range probe was ignored and streamed 616 MB before the timeout. The partial file stayed on disk.
- The sibling 2025 ImageServers (2 m DTM and the surface models) and the per-survey National LIDAR Programme and time-stamped tiles were not requested.
- No point cloud was sized or fetched in Scotland or England.
- The Belfast 2006 attribution note was not read.

## Outcome

Raw 1 m LIDAR elevation was open for 99.73% of England and all of Wales, under the Open Government Licence, with no key. It was open for only 39.4% of Scotland and 16.6% of Northern Ireland, so the answer for the whole UK is PARTIAL. England had one catch: its 2025 composite could be reached only as a live image service, and the downloadable edition was 2022. Scotland's four non-commercial collections were usable only by a non-commercial service. Rendering from raw elevation worked in every nation that had coverage, and a coverage layer was needed to show the rest.
