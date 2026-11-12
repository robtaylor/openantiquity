# LIDAR sources

This page lists every route to LIDAR elevation, and to ready-made LIDAR tiles, that the research pass of 2026-11-10 found for the four UK nations. Raw 1 m elevation was open for 99.73% of England, all of Wales, 39.4% of Scotland and 16.6% of Northern Ireland. Every elevation source below is under the Open Government Licence except four Historic Environment Scotland collections, which are non-commercial. England's two coverage services had traps, Scotland's was switched off and Wales had none. Nothing here is built: each statement records what someone else's service did on 2026-11-10, and "Suggested use" lines are suggestions. DSP means the Defra Data Services Platform. Reuse classes and modes come from Decisions [0004](../architecture/decisions/0004-field-club-is-non-commercial.md) and [0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md), and Decision [0006](../architecture/decisions/0006-terrain-tiles-are-rendered-from-raw-elevation.md) says why raw elevation matters.

Later the same day Defra supplied England's 2022 composite in bulk. See [England LIDAR bulk supply](lidar-england-bulk-supply.md). Decision 0006 was then revised so that England is read only from a mirror of those files, and none of the web services below sits on the path of a map tile.

## Coverage by nation

Percentages come from the follow-up report, which clipped each publisher's footprints to the ONS Countries December 2025 polygons.

| Nation | Covered by open LIDAR | Resolution | Capture years | Raw-elevation route | Size to mirror |
|---|---|---|---|---|---|
| England | 99.73% (130,107 of 130,459 km2) in the 2022 composite. The 2025 composite also fills 351 km2 of the North York Moors. | 1 m composite, resampled from 1 m, 0.5 m and 0.25 m patches. | 2000 to 2022, mostly 2018 to 2021, for the 2022 edition. 2016/17 to 2024/25 for the 2025 edition. | ArcGIS image service (2025). WCS (2022). 5 km zips (2022). | About 320 GB for the 2022 zips, range 214 to 465, from five sample tiles. The 3,168 newer patch tiles were not measured. |
| Scotland | 39.4% (31,059 of 78,794 km2). | 1 m only: 9.8%. 50 cm or better: 29.6%. Some sets at 25 cm. | Phases 1 and 2 credited 2012 and 2014, phases 3 to 6 2020 to 2022, Hebrides 2019, Orkney 2023, coastal 2025-26, programme 2025 to 2027. | Open S3 bucket of GeoTIFFs. The WCS is disabled. | 625.4 GB of DTM, of which 6.17 GB is non-commercial. About 1.2 TB more at 50 cm if the programme reaches full coverage. |
| Wales | 100.00% of 20,782 km2. | 1 m. | 2020 to 2023, mostly 2021 and 2022. | One national float32 cloud-optimised GeoTIFF, or 22,473 per-km tiles. | 48.6 GB as one file, about 49.1 GB as tiles. |
| Northern Ireland | 16.6% (2,373 of 14,312 km2), about 17% with the coast. | 1 m river-basin surveys, 0.5 m for 2007 and Belfast, 12.5 to 50 cm for heritage sites. | 2004 to 2014, Lough Neagh 2017, heritage sites 2008 to 2014, coast 2021. | Zipped ESRI ASCII grids. No national set. | About 25 GB as cloud-optimised GeoTIFF, estimated. Raw downloads total 56.9 GB. |

A four-nation DTM mirror was estimated at about 1.0 TB of source files, 1.1 TB as lossless cloud-optimised GeoTIFF and 0.5 TB with 1 cm LERC compression. Surface models roughly double each figure.

The earlier England report said "about 99%" and counted 5,779 tiles, the 2025 catalogue. The earlier Scotland report gave 40.9% to 43.8% from unclipped footprints.

34.4% of Scotland's 8,076 scheduled monuments lay outside all open LIDAR, as did 75.3% of 2,268 scheduled or state-care records in Northern Ireland, by one test point per monument. Burnswark was partly covered, not uncovered as the earlier Scotland report said. Phase 3 showed both Roman camps, and the summit sat in a nodata hole. Scotland's programme runs from May 2025 to July 2027, and a blog of 29 January 2026 promised "full national coverage above high tide" with releases about every six months. 6.4% of Scotland was published by 2026-11-10. A whole-NI survey made for the Soil Nutrient Health Scheme was unpublished.

## Which England edition each route serves

England had two editions of the 1 m composite DTM. The two must not be mixed in one layer. Over a 500 m box at Avebury, the 2025 edition minus the 2022 edition had mean -0.041 m and range -0.82 to +0.97 m. Only 0.3% of pixels were identical and 8% differed by more than 10 cm. A mixed layer would show seams.

| Route | Edition |
|---|---|
| ArcGIS image service, raw and rendered | 2025, CompYear 2025-06-01 |
| DSP WCS | 2022, bit-identical to the 5 km tiles |
| DSP 5 km tile zips | 2022 only. Years 2023 to 2025 return empty zips. |
| DSP WMS and WMTS hillshade, 10 m zip, survey indexes | 2022. No 2025 index was found. |
| NLS England tiles | Credited to 2022 |
| Mapterhorn | Not stated |

The 2025 composite was not downloadable: the tile search listed 2022 only, the image service refused downloads, and data.gov.uk listed nothing newer. The follow-up noted that the 2022 composite plus 3,168 DTM tiles flown after it, from the national_lidar_programme_dtm and lidar_tiles_dtm products, could stand in. Nobody compared that build with the 2025 composite. Stated vertical accuracy is +/-10 cm RMSE for 2025 and +/-15 cm for 2022.

## Nodata traps

Normalise every void to NaN and keep a coverage mask.

| Source | Void value | Trap |
|---|---|---|
| DSP WCS | 0.0 | Inside the North York Moors gap, GetCoverage returned 256 by 256 pixels of 0.0 with no nodata tag, which reads as sea level. The Avebury sample showed -3.4028234663852886e+38 with the tag set. |
| ArcGIS image service | +3.4028235e38 | No nodata tag in the GeoTIFF. Mask values above 1e38. |
| DSP 5 km tiles | -3.4028235e38 | Tag set. A missing tile returns HTTP 200 and a 22-byte empty zip. |
| Scotland | -9999 | Programme tiles use -32767. |
| Wales | -9999 | Values quantised to 0.01 m. |
| Northern Ireland | -9999 or -99 | Heritage grids use -99. At least one river-basin tile held millimetres, not metres. |

## England tile naming for the 5 km downloads

The address is `https://environment.data.gov.uk/tiles/collections/survey/{product}/{year}/{resolution}/{tileId}`. The tileId is the 100 km square letters, then two digits of easting and two of northing, giving the south-west corner as kilometre offsets in 5 km steps.

| Item | Value |
|---|---|
| Example tileId | SU1065: square SU, easting 410000, northing 165000 |
| Label | The 10 km square plus quadrant: SU16nw |
| Zip name | `lidar_composite_dtm-2022-1-SU16nw.zip` |
| Zip contents | `SU16nw_DTM_1m.tif`, `.tfw`, `.tif.xml`, `.tif.aux.xml`, `SU16nw_DTM_1m_Metadata.gpkg` |
| Tile | 5000 by 5000 pixels, float32, LZW, 128 pixel blocks, no overviews, 38.7 to 84.0 MB |

## Summary

EA is the Environment Agency, SG the Scottish Government, NLS the National Library of Scotland, HES Historic Environment Scotland. Reuse is the Decision 0004 class and Mode the Decision 0007 access mode. Decision 0007 defines live as a query by the user's browser with nothing stored on our servers. Elevation that OpenAntiquity's server would fetch on demand and keep in a cache stores a copy, so this table gives it `bulk` and the open question is in the last section. Sources to read about but not use carry `deeplink`.

| Source | Publisher | Coverage | Licence | Reuse | Mode | Records |
|---|---|---|---|---|---|---|
| Defra 5 km tile zips, 2022 | EA | England | OGL | open | bulk | 5,876 tiles |
| Defra tile search API | EA | England | OGL | open | bulk | 173,160 rows |
| Defra image service, 2025 | EA | England | OGL | open | bulk | 5,779 tiles |
| Defra WCS, 2022 | EA | England | OGL | open | bulk | 2 coverages |
| Defra survey index catalogues | EA | England | OGL | open | bulk | 21,380 polygons |
| Defra WMTS hillshade, 2022 | EA | England | OGL | open | live | 3 layers |
| Defra WMS, 2022 | EA | England | OGL | open | live | 3 layers |
| Defra raster functions, 2025 | EA | England | OGL | open | live | 9 functions |
| Defra 10 m DTM zip, 2022 | EA | England | OGL | open | bulk | 5.3 GB |
| Defra sibling composites, 2022 and 2025 | EA | England | OGL | open | deeplink | Capabilities only |
| Defra per-survey tiles | EA | England | OGL | open | deeplink | Not tested |
| Old EA image endpoint | EA | England | Not applicable | link_only | deeplink | 0 |
| Scotland open S3 bucket | SG, JNCC | Scotland | OGL v3 per collection | open | bulk | 76,996 objects |
| Scotland catalogue API and programme metadata | SG, JNCC | Scotland | OGL v3 | open | bulk | 54 collections |
| Scotland footprint WFS | SG, JNCC | Scotland | OGL v3 | open | bulk | 19 features |
| Scotland WMS | SG, JNCC | Scotland | OGL v3 | open | live | 56 layers |
| Scotland WMTS | SG, JNCC | Scotland | OGL v3 | open | deeplink | 51 layers |
| Scotland WCS | SG, JNCC | Scotland | Not applicable | link_only | deeplink | Disabled |
| HES non-commercial collections | HES | Scotland, small sites | Non-Commercial Government Licence v2 | non_commercial | bulk | 508 DTM files |
| Wales national 1 m COG | Welsh Government | Wales | OGL | open | bulk | 1 file, 48.6 GB |
| Wales per-km DTM tiles | Welsh Government | Wales | OGL | open | bulk | 22,473 tiles |
| Wales tile catalogue 2020-23 | Welsh Government | Wales | "Not Specified" on the layer | open | bulk | 22,473 |
| Wales 16-bit COG | Welsh Government | Wales | OGL | open | deeplink | 1 file |
| Wales hillshade COG | Welsh Government | Wales | OGL | open | deeplink | 1 file |
| NRW archive catalogue | Natural Resources Wales | Wales, about 70% | OGL v3 | open | bulk | 14,942 |
| DataMapWales archive tiles | Welsh Government, NRW | Wales | OGL | open | deeplink | z0 to z17 |
| DataMapWales GeoServer | Welsh Government | Wales | Per layer | link_only | deeplink | No LIDAR layers |
| OSNI river-basin LIDAR | LPS, OSNI | NI, about 14% | OGL v3 | open | bulk | 86 zips |
| HED archaeology LIDAR | HED | NI, 39 sites | OGL v3 | open | bulk | 39 zips |
| DfI Rivers LIDAR | DfI Rivers | NI | OGL v3 | open | bulk | Lough Neagh, Belfast |
| DAERA coastal elevation | DAERA | NI coast | OGL v3 | open | live | LOD 0 to 23 |
| OSNI 10 m DTM | LPS, OSNI | NI | OGL v3 | open | bulk | 293 sheets |
| OpenDataNI CKAN API | Open Data NI | NI | OGL v3 | open | bulk | 87 packages |
| DAERA peatland hillshade | DAERA, NIEA | NI, about 20 sites | "Internal use only." | link_only | deeplink | Not tested |
| OS Terrain 50 | Ordnance Survey | GB | OGL v3 | open | bulk | 2,858 tiles |
| Copernicus GLO-30 | ESA | Global | Copernicus DEM licence, annex not read | open | bulk | 30.5 MB per tile |
| AWS Terrain Tiles | Mapzen, AWS | Global | Not checked | link_only | deeplink | z0 to z15 |
| Mapterhorn | Mapterhorn | Global, UK 1 m partial | OGL for UK entries | open | live | Not counted |
| NLS multi-direction, England and Wales | NLS | England, Wales | Derived from OGL | open | live | Zoom 1 to 18 |
| NLS multi-direction, Scotland | NLS | Scotland, partial | Per phase, not checked | open | live | 6 phases, Hebrides |
| NLS Combined VAT | NLS | England | Derived from OGL | open | deeplink | Zoom 1 to 16 |
| NLS terrarium DTM | NLS | England, Wales | Derived from OGL | open | deeplink | Zoom 4 to 16 |
| NLS Sherwood Forest | NLS, Miner2Major | Sherwood Forest | None stated | link_only | deeplink | Zoom 1 to 19 |
| Boundary and monument sources | ONS, HES, DfC | UK | OGL | open | bulk | See section |

## Defra 5 km tile zips, 2022

The only English download of the 1 m composite DTM: one zip per 5 km OS grid tile, 2022 edition only.

| Row | Value |
|---|---|
| Access | Plain GET, one zip per tile. No key. |
| Address | `https://environment.data.gov.uk/tiles/collections/survey/{product}/{year}/{resolution}/{tileId}` |
| Tested on 2026-11-10 | HTTP 200 application/zip, 48,128,660 B in 5.8 s. HEAD returned 405. |
| Format and CRS | Zip holding a 5000 by 5000 float32 LZW GeoTIFF. EPSG:27700, heights above Ordnance Datum Newlyn. 1 m pixels. |
| Licence, attribution | Open Government Licence v3.0. "© Environment Agency copyright and/or database right 2022. All rights reserved." |
| Reuse class, mode | open, bulk, after asking the Environment Agency |
| Limits and CORS | The website refused selections of 48 or more tiles. The terms forbid use that would "restrict or inhibit the use and enjoyment of the site by anyone else". No CORS header. |

```
curl -L -o SU1065.zip https://environment.data.gov.uk/tiles/collections/survey/lidar_composite_dtm/2022/1/SU1065
```

Notes:
- The FAQ says "There's no option of bulk download for the whole country or for a large area. This would need to be supplied offline."
- GET used chunked transfer with no Content-Length and ignored Range. It ran at about 8.5 MB/s, roughly 11 hours for 320 GB. Sizes ran 1.55 to 3.36 MB per covered km2.
- A missing tile or year returned HTTP 200 and a 22-byte zip. Check the size.

Suggested use: ask for an offline supply through the Large Data Download form, naming the 2025 edition. If refused, crawl one stream at a time and reject empty zips.

## Defra tile search API

Returns every survey product, year, resolution and 5 km tile intersecting a posted polygon, with download addresses.

| Row | Value |
|---|---|
| Access | POST of a GeoJSON polygon. No key. |
| Address | `https://environment.data.gov.uk/backend/catalog/api/tiles/collections/survey/search` |
| Tested on 2026-11-10 | HTTP 200 application/json, 74 results in 0.44 s for a small box. An all-England polygon returned 173,160 rows, 60 MB, in 23 s. |
| Format and CRS | JSON: count and results with product, year, resolution, tile, label, uri. Input in WGS84. |
| Licence, attribution | Open Government Licence v3.0. "© Environment Agency copyright and/or database right 2022. All rights reserved." |
| Reuse class, mode | open, bulk, as the tile index for the zips |
| Records | 173,160 rows. lidar_composite_dtm 2022: 5,876 at 1 m, 5,876 at 2 m. |
| Limits and CORS | No paging. No CORS header on the response. |

```
curl -X POST -H 'Content-Type: application/geo+json' --data '{"type":"Polygon","coordinates":[[[-1.8580,51.4265],[-1.8500,51.4265],[-1.8500,51.4305],[-1.8580,51.4305],[-1.8580,51.4265]]]}' https://environment.data.gov.uk/backend/catalog/api/tiles/collections/survey/search
```

Composites exist for 2022 only. Programme tiles are named `P_XXXXX_OSOSOS_SDFLOWN_EDFLOWN`.

## Defra image service, 2025

An ArcGIS image service that returned raw float32 metres at any extent and scale from the 2025 composite. It was the only open route to the 2025 edition.

| Row | Value |
|---|---|
| Access | ArcGIS ImageServer: exportImage, getSamples, identify, query. No key. |
| Address | `https://utility.arcgis.com/usrsvcs/servers/f9c4694d7d5140638536c4afe4119e6d/rest/services/LIDAR/LIDAR_Composite_1m_DTM/ImageServer` |
| Tested on 2026-11-10 | HTTP 200 image/tiff, 780,433 B, 1.09 s for a 500 m box. 29 of 30 small requests succeeded. One returned an instant 502. |
| Format and CRS | GeoTIFF float32 LZW, or LERC2 with `format=lerc&compressionTolerance=0.01`. Native EPSG:27700. imageSR=3857 snapped exactly to the requested box. 1 m pixels. |
| Licence, attribution | The item says "Open Government License (OGL)", linking to OGL v3. "© Environment Agency copyright and/or database right 2025. All rights reserved." |
| Reuse class, mode | open, bulk. The research suggested server-side use behind a cache until England is mirrored |
| Limits and CORS | No rate limit published. max-age=30. Advertised maxImageWidth 15000, maxImageHeight 4100. Reflects the Origin. |

```
https://utility.arcgis.com/usrsvcs/servers/f9c4694d7d5140638536c4afe4119e6d/rest/services/LIDAR/LIDAR_Composite_1m_DTM/ImageServer/exportImage?bbox=410000,169700,410500,170200&bboxSR=27700&imageSR=27700&size=500,500&format=tiff&pixelType=F32&noData=&noDataInterpretation=esriNoDataMatchAny&interpolation=RSP_NearestNeighbor&compression=LZ77&renderingRule=%7B%22rasterFunction%22%3A%22None%22%7D&f=image
```

Notes:
- Voids came back as +3.4028235e38 with no nodata tag.
- The first report measured about 0.9 s at any scale. The follow-up measured a median of 1.94 s for 256 by 256 pixel requests, and found "several 30-45 s timeouts and one 502 in about 128 requests" in an earlier agent's logs. The later figure is the safer one.
- 4096 by 4096 returned HTTP 500.
- The proxy forwards to `di-defra-open.img.arcgis.com`, which needs a token. Any limit is invisible. Downloads are unsupported.
- copyrightText still says 2022. The DSP dataset page does not link to the service.
- The item record, `https://www.arcgis.com/sharing/rest/content/items/f9c4694d7d5140638536c4afe4119e6d?f=json`, was fetched on 2026-11-10. It reads "Open Government License (OGL)", was created 2024-04-30, modified 2026-02-12, and says the data covers "all of England".

Suggested use: on-demand elevation behind a cache, with the edition year stored per tile. Ask the Defra Data Sharing and Access Team whether the proxy is meant for third-party applications.

## Defra WCS, 2022

A GeoServer WCS 2.0.1 over the 2022 composite, returning raw float32 bit-identical to the downloadable tiles. The follow-up marked it "avoid" for coverage logic.

| Row | Value |
|---|---|
| Access | WCS 2.0.1, also 1.1.1 and 1.1.0. No key. |
| Address | `https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs` |
| Tested on 2026-11-10 | HTTP 200 image/tiff, 3,936,707 B in 2.6 s. 357,219 B with `&geotiff:compression=DEFLATE`. |
| Format and CRS | GeoTIFF float32. Native EPSG:27700. Also 4326, 4258, 3857, 900913. 1 m pixels. |
| Licence, attribution | Open Government Licence v3.0. "© Environment Agency copyright and/or database right 2022. All rights reserved." |
| Reuse class, mode | open, bulk. Fallback only, at zoom 12 and above, with a coverage mask |
| Limits and CORS | GeoServer control-flow was active. CORS *. |

```
https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wcs?service=WCS&version=2.0.1&request=GetCoverage&coverageId=13787b9a-26a4-4775-8523-806d13af58fc__Lidar_Composite_Elevation_DTM_1m&format=image/tiff&subset=E(410000,410500)&subset=N(169700,170200)
```

Notes:
- In the North York Moors gap, E 489000 to 489256, N 495000 to 495256 returned every pixel as 0.0 with no nodata tag. The 2025 service gave 249.98 m there.
- 100 km at 256 pixels gave no response in 60 to 90 s. Scaling axes must be i and j. EPSG:3857 output was not snapped to the requested box.

## Defra survey index catalogues

Polygons giving the survey id, resolution, year and flown dates behind the 2022 composites and the time-stamped archives.

| Row | Value |
|---|---|
| Address | `https://environment.data.gov.uk/spatialdata/survey-index-files/ogc/features/v1/collections/{collection}/items` |
| Tested on 2026-11-10 | HTTP 200 application/geo+json, 0.33 s. A 72.5 MB GeoPackage of the 1 m extents took 12 s. |
| Format and CRS | GeoJSON, GeoPackage or CSV. CRS84 output, EPSG:27700 storage. |
| Licence, attribution | Open Government Licence v3.0. "© Environment Agency copyright and/or database right 2022. All rights reserved." |
| Reuse class, mode | open, bulk |
| Records | LIDAR_Composite_1m_DTM_2022_extents 21,380. 2m 22,597. National_LIDAR_Programme_Index_Catalogue 7,139. LIDAR_DTM_Time_Stamped_Extents 167,584. 15 collections. |
| Limits and CORS | `limit=30000` returned a whole collection. CORS: access-control-allow-origin: * in the first report. Undetermined in the follow-up. |

Notes: Fields include year, resolution, sd_flown and ed_flown. Avebury was flown 2018-12-10 to 2019-01-09. There is no 2025 collection.

## Defra WMTS hillshade, 2022

Cached greyscale hillshade, colour elevation and blended tiles of the 2022 DTM on a Web Mercator grid.

| Row | Value |
|---|---|
| Address | `https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wmts` with `layer=Lidar_Composite_Hillshade_DTM_1m`, `style=hillshade`, `tilematrixset=WebMercatorQuad`, `tilematrix={z}`, `tilerow={y}`, `tilecol={x}` |
| Tested on 2026-11-10 | HTTP 200 image/png, 37,296 B, 0.19 s, cache HIT, for tilematrix 15, tilerow 10907, tilecol 16215. z6 to z19 all HIT. z20 was a MISS at 2.2 s. |
| Format and CRS | 256 px PNG. WebMercatorQuad, British National Grid, EPSG:4326. |
| Licence, attribution | OGL. "© Environment Agency copyright and/or database right 2022. All rights reserved." |
| Reuse class, mode | open, live, as a low-zoom preview |
| Records | 3 layers: Lidar_Composite_Hillshade_DTM_1m, Lidar_Composite_Elevation_DTM_1m, Lidar_Composite_DTM_1m |
| Limits and CORS | One of 20 requests hung for 20 s. CORS *. |

The hillshade is single-direction. Avebury henge was clearly legible at z15. The REST form returned 400 on the `/spatialdata/` alias.

## Defra WMS, 2022

WMS 1.3.0 rendering hillshade, a colour ramp or a blended group, with GetFeatureInfo returning raw elevation at a pixel.

| Row | Value |
|---|---|
| Address | `https://environment.data.gov.uk/spatialdata/lidar-composite-digital-terrain-model-dtm-1m/wms`. The visualisation report used `...-dtm-1m-2022/wms`, which also answered. |
| Tested on 2026-11-10 | HTTP 200 image/png, 37,296 B, 0.59 s. The visualisation report measured 0.38 s. |
| Format and CRS | 25 GetMap formats. Native EPSG:27700. Also 3857, 900913, 4326, 4258, CRS:84. |
| Licence, attribution | Open Government Licence v3.0. "© Environment Agency copyright and/or database right 2022. All rights reserved." |
| Reuse class, mode | open, live |
| Records | 3 layers |
| Limits and CORS | 4096 square took 4.6 s. 8192 square gave no response in 60 s. CORS: access-control-allow-origin: * |

Notes: The elevation layer is a colour ramp over -12 to 1400 m. GetFeatureInfo with `info_format=application/json` on it returned `{"Elevation":157.33999633789062}` in 0.77 s.

## Defra raster functions, 2025

Server-side rendered hillshade, slope, aspect, classified elevation and a detrended view of the 2025 DTM, through the image service.

| Row | Value |
|---|---|
| Address | The image service address above, `exportImage` with a `renderingRule` |
| Tested on 2026-11-10 | HTTP 200 image/png, 19,910 B, 0.47 s. At z15 standard hillshade took 0.73 s, detrended 1.6 s, slope 0.78 s. |
| Licence, attribution | OGL v3.0. "© Environment Agency copyright and/or database right 2025. All rights reserved." |
| Reuse class, mode | open, live for comparison only |
| Limits and CORS | None published, max-age=30. Reflects Origin. |

Notes: The nine function names include 'Hillshade - Multidirectional', 'Slope - Classified' and 'Elevation - Detrended - 1m DTM', spelled exactly so. The multidirectional hillshade was clean but low-contrast. The detrended view was noisy at z15 and its method was undocumented.

## Defra 10 m DTM zip, 2022

An all-England 10 m DTM, resampled bilinearly from the 2 m composite, as one zipped GeoTIFF.

| Row | Value |
|---|---|
| Address | `https://environment.data.gov.uk/file-management-open/data-sets/ac3682a1-1ead-4478-8a2d-d8402ef9ead0/files/LIDAR_Composite_10m_DTM_2022.zip` |
| Tested on 2026-11-10 | HEAD 200 application/octet-stream, 5,301,314,401 B. Only the zip header was read. The GeoTIFF was not decoded. A Range request was ignored and the server streamed the whole body at about 10 MB/s. |
| Format and CRS | Zip, first entry `.tfw`. EPSG:27700, 10 m pixels. |
| Licence, attribution | OGL v3.0, dataset ce8fe7e7-bed0-4889-8825-19b042e128d2. "© Environment Agency copyright and/or database right 2022. All rights reserved." |
| Reuse class, mode | open, bulk for low-zoom context only |

## Defra sibling composites, 2022 and 2025

Sibling services for the 2 m DTM and the first-return and last-return surface models, in the 2022 family on the DSP and the 2025 family on ArcGIS.

| Row | Value |
|---|---|
| Address, 2022 | `https://environment.data.gov.uk/spatialdata/{slug}/wcs`, slug `lidar-composite-digital-terrain-model-dtm-2m`, `lidar-composite-digital-surface-model-first-return-dsm-1m`, `-last-return-dsm-1m` or a `-2m` variant |
| Address, 2025 | `https://utility.arcgis.com/usrsvcs/servers/{itemId}/rest/services/LIDAR/{name}/ImageServer`. Items: f8f6301f80714700b68d79e7b2bc5b86 LIDAR_Composite_2m_DTM, 5b0eefaf165d46699a2e844c4d074971 1m_FZ_DSM, 9db6977fa1c0439a9e4dffb39b82528d 2m_FZ_DSM, 5a412eedf4604138aeb82a0fced552ce 1m_LZ_DSM, 90c92707669e4b1c903e054d3662f528 2m_LZ_DSM |
| Tested on 2026-11-10 | 2022 family: GetCapabilities only, HTTP 200, no GetCoverage. 2025 family: not tested. The addresses came from an ArcGIS Online search of 82 items modified 2026-02-12. |
| Licence, attribution | OGL. "© Environment Agency copyright and/or database right 2022. All rights reserved." for 2022 and "© Environment Agency copyright and/or database right 2025. All rights reserved." for 2025. |
| Reuse class, mode | open, deeplink |

Surface models include trees and buildings.

## Defra per-survey tiles

Per-survey 5 km tiles beneath the composite: National LIDAR Programme DTM, DSM, intensity, VOM and LAZ, time-stamped DTM and DSM, and point clouds. Not tested.

| Row | Value |
|---|---|
| Address | The tile address used for the composite zips, with another product id |
| Tested on 2026-11-10 | Not tested. No tile was downloaded. The products appeared in tested search results at resolutions such as 0.5 and 0.15. |
| Licence, attribution | OGL v3.0. "© Environment Agency copyright and/or database right 2022. All rights reserved." The time-stamped datasets state 2019 or 2020. |
| Reuse class, mode | open, deeplink for now |
| Records | National LIDAR Programme: 302 blocks covering England, Phase 1 flown January 2017 to February 2023. Time-stamped tiles ran 1996-12-01 to 2024-04-18. |

The 3,168 post-2022 DTM tiles come from these products. Point clouds exist from 2006.

## Old EA image endpoint

A former ArcGIS image services root, now a stub. Avoid it.

| Row | Value |
|---|---|
| Address | `https://environment.data.gov.uk/image/rest/services?f=json` |
| Tested on 2026-11-10 | HTTP 200, 72 B: `{"error":{"code":400,"message":"Invalid URL","details":["Invalid URL"]}}`. Every path under it did the same. |
| Reuse class, mode | link_only, deeplink |

The source server `di-defra-open.img.arcgis.com` returned error 499 "Token Required".

## Scotland open S3 bucket

The Scottish Remote Sensing Portal's open bucket holds raw float32 DTM, DSM and LAZ for every public-sector survey as per-tile GeoTIFFs. It is the route to Scottish elevation.

| Row | Value |
|---|---|
| Access | Open S3. Anonymous ListObjectsV2 and HTTP range reads. |
| Address | `https://srsp-open-data.s3.eu-west-2.amazonaws.com/lidar/{dataset}/dtm/27700/gridded/{TILE}_{RES}_DTM_{SUFFIX}.tif`. Listing: `https://srsp-open-data.s3.eu-west-2.amazonaws.com/?list-type=2&prefix=lidar/phase-4/dtm/` |
| Tested on 2026-11-10 | HTTP 200 listing, 206 range GET. A 500 m window of 1000 by 1000 pixels opened in 0.30 s and read in 0.66 s. |
| Format and CRS | GeoTIFF float32 LZW, EPSG:27700. 1 m for phases 1 and 2, 0.5 m for phases 3 to 6, programme, coastal, Orkney and most of Hebrides, 0.25 m for part of Hebrides and HES 2016. |
| Licence | Open Government Licence v3 unless stated. Four HES collections differ. |
| Attribution | Phase 1: "Crown copyright Scottish Government, SEPA and Scottish Water (2012)". Phases 2 to 3: "Copyright Scottish Government and SEPA (2014). Fugro retain the commercial copyright." Hebrides: "(c) SEPA (2019)". Programme: "Crown copyright Scottish Government (c) Crown copyright and database right (2025)". Coastal: "Crown copyright Scottish Government". Phases 4 to 6 and Orkney: licence only. |
| Reuse class, mode | open, bulk. The four HES collections are non_commercial. |
| Records | DTM files: phase 1 382, phase 2 232, phase 3 674, phase 4 420, phase 5 250, phase 6 77, programme 5,933, coastal 1,169, Orkney 1,655, Hebrides 327, HES 801. 76,996 objects and 3,381.65 GB in all, DTM 625.4 GB. |
| Limits and CORS | CORS *, methods HEAD and GET, preflight allows Range. |

```
curl -H 'Range: bytes=0-1023' https://srsp-open-data.s3.eu-west-2.amazonaws.com/lidar/phase-4/dtm/27700/gridded/NS87NW_50CM_DTM_PHASE4.tif
```

Notes:
- Tile names look like `NS87NW_50CM_DTM_PHASE4`. Phase 1 and 2 tiles are 10 km. Phases 3 to 6 are 5 km, 10000 by 10000 pixels, up to 470 MB. Others are 1 km.
- Phases 1 and 2 and Orkney have no overviews.
- Phase 1 pixels are 1.0000026 by 0.9999934 m and Orkney 2023 is AREA_OR_POINT=Point. Resample to a common grid before mosaicking.
- Programme objects were last modified 2026-04-14 (1,590 tiles) and 2026-09-25 (4,343). The AWS registry names only the phase 2 LAZ as non-commercial, which the follow-up found out of date.

Suggested use: list the bucket monthly, keyed on LastModified, and keep per-collection licence from the catalogue API.

## Scotland catalogue API and programme metadata

JSON catalogue of collections, with licence and attribution, and per-tile products with S3 keys and bounding boxes.

| Row | Value |
|---|---|
| Address | `https://api.remotesensing.data.gov.scot/search/collection/scotland-gov/*` and POST `https://api.remotesensing.data.gov.scot/search/product` |
| Tested on 2026-11-10 | HTTP 200 application/json. A POST with collection `scotland-gov/lidar/phase-4/dtm`, a WKT footprint, `spatialop` intersects, limit and offset worked. |
| Format and CRS | JSON. Footprints EPSG:4326, data EPSG:27700. |
| Licence, attribution | OGL v3, per-collection useConstraints, the authoritative licence field. Attribution as each collection states. |
| Reuse class, mode | open, bulk, to read licences into a datasets table |
| Records | 54 collections |
| Limits and CORS | None observed. access-control-allow-origin: * |

The endpoints came from the portal's script bundle and are undocumented. Some metadata is copied, so phase 3's temporal extent repeats phase 2's. The programme collection says Bluesky captured it via APGB at 10 points per m2, 50 cm DTM and DSM, 2025 to 2027.

The programme metadata zip `https://maps.data.gov.scot/shapefiles/LiDAR/SG_NLP_Metadata.zip` was OGL v3, 39.0 MB, dated 2026-09-29, EPSG:27700. It holds shapefiles and lasinfo reports for 8 blocks and 7,183 LAZ tiles, such as NR_50, NX_05_South and NX50_NX55_East. The shapefiles were not opened. Reuse open, mode bulk.

## Scotland footprint WFS

Multipolygon data-presence footprints per survey, the only vector coverage layer.

| Row | Value |
|---|---|
| Address | `https://ows.remotesensing.data.gov.scot/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=scotland:dsm-footprint-aggregate&outputFormat=application/json&srsName=EPSG:27700` |
| Tested on 2026-11-10 | HTTP 200 application/json, 13.3 MB in 2.9 s. EPSG:27700, about 0.5 m vertex precision. |
| Licence, attribution | Open Government Licence v3. "Scottish Government" |
| Reuse class, mode | open, bulk |
| Records | 19 features. Union 31,861 km2 before clipping to land. CountDefault 1,000,000. CORS *. |

It is stale. It lacks coastal 2025-26 and HES 2016, and holds programme squares NR, NS and NX only. Build the mask from it plus 1 km tile names from the bucket. Using 5 and 10 km tile names for phases 1 to 6 would overstate coverage at 64%.

## Scotland WMS

WMS 1.3.0 over every DTM and DSM collection with colour-ramp styles only. It also accepts a user SLD for server-side shaded relief.

| Row | Value |
|---|---|
| Address | `https://ows.remotesensing.data.gov.scot/geoserver/ows?service=WMS&version=1.3.0&request=GetMap&layers=scotland:{layer}&crs=EPSG:3857&bbox={bbox-epsg-3857}&width=512&height=512&format=image/png&sld_body={urlencoded SLD}`. The old host `srsp-ows.jncc.gov.uk` now redirects here. |
| Tested on 2026-11-10 | HTTP 200 image/png, 500 by 500 pixel hillshade in 0.57 s. 4096 by 4096 in 4.0 s. |
| Format and CRS | PNG or JPEG. image/geotiff output is an 8-bit palette, not raw values. EPSG:27700, 3857, 4326, 900913. |
| Licence, attribution | OGL v3. As the underlying collection. |
| Reuse class, mode | open, live as a zero-ingest preview only |
| Records | 56 named layers |
| Limits and CORS | access-control-allow-origin: * |

```
GetMap layers=scotland:scotland-lidar-4-dtm crs=EPSG:27700 bbox=284100,679450,284600,679950 width=500 height=500 format=image/png with sld_body containing <RasterSymbolizer><ShadedRelief><BrightnessOnly>true</BrightnessOnly><ReliefFactor>55</ReliefFactor></ShadedRelief></RasterSymbolizer>
```

Notes:
- The SLD gave a real hillshade of Rough Castle. A 256 by 256 request aligned to the 3857 grid ignored it and returned the cached colour tile, so use 512. It did not apply to `scotland:lidar-aggregate`, so each phase needs its own request.

## Scotland WMTS

Cached colour-ramp tiles of each DTM and DSM layer. Earthworks are invisible in them.

| Row | Value |
|---|---|
| Address | `https://ows.remotesensing.data.gov.scot/geoserver/gwc/service/wmts/rest/{layer}/{style}/WebMercatorQuad/{z}/{y}/{x}?format=image/png`, for example layer `scotland:scotland-lidar-4-dtm-s3`, style `scotland:lidar-dem`, tile 16/20408/32066 |
| Tested on 2026-11-10 | HTTP 200 image/png, 1.45 s miss, 0.13 s hit. 51 layers. |
| Licence, reuse, mode | OGL v3. open, deeplink. CORS *. |

## Scotland WCS

A coverage service that would give raw values. It was switched off. Avoid it.

| Row | Value |
|---|---|
| Address | `https://ows.remotesensing.data.gov.scot/geoserver/ows?service=WCS&request=GetCapabilities` |
| Tested on 2026-11-10 | HTTP 200 carrying an ExceptionReport, "Service WCS version 2.0.1 is disabled". The same 528 B reply came for 1.0.0, 1.1.1 and other paths. |
| Reuse class, mode | link_only, deeplink |

## HES non-commercial collections

Archaeology-targeted 25 to 50 cm DTM and DSM for Stirling 2010, Scottish Ten 2010, 2016-2017 sub project 4, which includes the Antonine Wall, and the Isle of Luing. They sit in the same bucket as OGL data.

| Row | Value |
|---|---|
| Address | `https://srsp-open-data.s3.eu-west-2.amazonaws.com/lidar/hes/{hes_2010|hes-2010s10|hes-2016-2017|luing}/dtm/27700/gridded/` |
| Tested on 2026-11-10 | HTTP 206. A window of `NS8479_25CM_DTM_HES2016_2017.tif` read in 1.8 s at 0.25 m. |
| Format and CRS | GeoTIFF float32 LZW COG, nodata -9999, EPSG:27700 |
| Licence, attribution | Non-Commercial Government Licence v2. Fugro owns the data. "HES licence this data for non-commercial use only as permitted by Fugro, the owners of the data." |
| Reuse class, mode | non_commercial, bulk, under a separate prefix with a licence flag |
| Records | DTM files: hes_2010 49, hes-2010s10 359, hes-2016-2017 56, luing 44. Footprints 34, 196, 22 and 29 km2. 6.17 GB. |
| CORS | access-control-allow-origin: * |

Notes: The first report marked these "avoid" until the commercial question was settled, which Decision 0004 did. The Phase 2 LAZ is also non-commercial. The other HES sets are OGL: hes-2016, hes-2017 and hes-2017sp3. Whether the restriction reaches derived hillshades in a free public tool was open.

## Wales national 1 m COG and siblings

A single national mosaic of the 2020-23 1 m DTM as float32 metres. It is the route to Welsh elevation.

| Row | Value |
|---|---|
| Access | Bulk download. Azure Blob cloud-optimised GeoTIFF with range reads. |
| Address | `https://dmwproductionblob.blob.core.windows.net/cogs/lidar/wales_dtm_32bit_cog.tif` |
| Tested on 2026-11-10 | HEAD 200 image/tiff, 48,611,310,928 B. A 500 by 500 window opened in 0.25 s and read in 0.54 s. All Wales at 382 m pixels took 4.3 s. |
| Format and CRS | Float32 COG, DEFLATE, 256 blocks, 191007 by 233000 pixels, overviews 2 to 64, nodata -9999, quantised to 0.01 m. EPSG:27700. |
| Licence, attribution | "Open Government Licence for Public Sector Information (OGL)" on the LiDAR viewer and LiDAR Data download map pages. The tile catalogue layer says "Not Specified". None given by the publisher. NLS uses "Contains public sector information licensed under the Open Government Licence v3.0." |
| Reuse class, mode | open, bulk |
| Records | 1 file, 48.6 GB. The surface model equivalent is 52.1 GB. |
| CORS | None for third parties. The preflight returned 403 "CORS not enabled" and only `https://datamap.gov.wales` is allowed. |

Notes: Last-Modified was 2024-10-04. It is one unversioned object, so a republish would change everything silently. DataMapWales announced a move to a beta site on 2026-06-23, so paths may change.

Two siblings sit in the same container. `https://dmwproductionblob.blob.core.windows.net/cogs/lidar/wales_dtm_16bit_cog.tif` is the same mosaic rounded to whole metres. It returned HTTP 200 and 3,601,904,014 B, with 184 distinct values at Tre'r Ceiri. One metre steps destroy micro-relief, so avoid it. `https://dmwproductionblob.blob.core.windows.net/cogs/dtm_1m_wales_hillshade_2020_23_cubic_cog.tif` is a rendered hillshade, OGL, an RGB JPEG COG of 1,052,625,840 B with no CORS. It returned HTTP 200. It was a green-yellow tint with weak shading, and the ramparts at Tre'r Ceiri were barely visible. Reuse open for both, mode deeplink.

## Wales per-km DTM tiles

The 2020-23 DTM as 22,473 one-kilometre GeoTIFFs on Azure Blob.

| Row | Value |
|---|---|
| Address | `https://dmwproductionblob.blob.core.windows.net/lidar-zips/2020-22/dtm/{file}.tif`, for example `wg_del_1_222381_20200322dtm.tif` |
| Tested on 2026-11-10 | HTTP 200 image/tiff, range supported. The Tre'r Ceiri tile, 2.65 MB, decoded identical to the national COG. |
| Format and CRS | 1000 by 1000 float32, DEFLATE, striped, not cloud-optimised, nodata -9999. EPSG:27700. |
| Licence, reuse, mode | OGL v3 per the earlier report, not re-read by the follow-up. open, bulk as an alternative to the single file. |
| Records, CORS | 22,473 tiles, about 49.1 GB from 50 random HEADs averaging 2.18 MB. No CORS header seen. |

Names carry a delivery number, the south-west corner and the flight date. HEAD returns Content-Length and Content-MD5.

## Wales tile catalogue 2020-23

A 1 km tile index with capture date and direct links to each DTM and DSM tile.

| Row | Value |
|---|---|
| Address | `https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:welsh_government_lidar_tile_catalogue_2020_2023&outputFormat=application/json&srsName=EPSG:27700&bbox={minx},{miny},{maxx},{maxy},EPSG:27700` |
| Tested on 2026-11-10 | HTTP 200 in 0.26 s. GeoJSON with british_gr, dtm_link, dsm_link, delivery, date, start_time, end_time, year. EPSG:27700. CORS *. |
| Licence | "Not Specified" on the layer page and CSW record c00a927d-2705-4396-b9b3-3029c44ae367. OGL on the parent map pages. |
| Reuse class, mode | open, provisional until Welsh Government confirms. Bulk, for survey-date provenance. |
| Records | 22,473 |

Links lack the `https://` scheme. The layers `wg_lidar_tile_index` and `nrw_lidar_tile_index` returned 400.

## NRW archive catalogue

An index of 1998 to 2015 Natural Resources Wales surveys at 0.25, 0.5, 1 and 2 m, with links to zipped DTM and DSM.

| Row | Value |
|---|---|
| Address | `https://datamap.gov.wales/geoserver/ows?service=WFS&version=2.0.0&request=GetFeature&typeNames=geonode:nrw_lidar_tile_catalogue_archive&outputFormat=application/json&srsName=EPSG:27700` |
| Tested on 2026-11-10 | HTTP 200 application/json. A zip HEAD at `lle.blob.core.windows.net/lidar/1m_res_SH34_2014_dtm.zip` returned 200, 27.4 MB. Zip contents were not opened. |
| Format and CRS | GeoJSON: lidar_name, gb_ng, date_flown, resolution, dsm_url, dtm_url, year. 2 km polygons, zips per 10 km square. EPSG:27700. |
| Licence, attribution | Open Government Licence v3, CSW record 2e6ee51a-a3de-4370-a991-e89e7e7f9ce4. "Contains Natural Resources Wales information (c) Natural Resources Wales and Database Right. All rights Reserved." |
| Reuse class, mode | open, bulk for the 0.25 m and 0.5 m tiles only |
| Records | 14,942: 2 m 5,979, 1 m 5,345, 0.5 m 2,148, 0.25 m 1,470. Coverage 73.2% at 2 m, 60.4% at 1 m, 5.8% at 0.5 m, 0.4% at 0.25 m. |
| CORS | access-control-allow-origin: * on the WFS |

Notes: The 1 to 2 m archive is superseded by the 2020-23 model.

## DataMapWales archive tiles

Colour shaded-relief XYZ tiles of the historic NRW archive, used by the DataMapWales LiDAR viewer.

| Row | Value |
|---|---|
| Address | `https://datamapwales.azureedge.net/imagery/lidar/{dtm1m|dtm2m|dsm1m|dsm2m}/{z}/{x}/{y}.png`, tested at `dtm1m/17/63925/42712.png` |
| Tested on 2026-11-10 | HTTP 200 image/png, 256 px palette, z0 to z17, EPSG:3857, about 70% of Wales. Hut circles were visible. `dtm50cm` and `dtm25cm` returned 404. No CORS header. |
| Licence, attribution | OGL for the NRW archive. "Contains Natural Resources Wales information (c) Natural Resources Wales and Database Right. All rights Reserved." |
| Reuse class, mode | open, deeplink. The two reports said reference only and avoid. |

## DataMapWales GeoServer

The general Welsh Government OWS endpoint. It holds no LIDAR raster layers. Avoid it for elevation.

| Row | Value |
|---|---|
| Address | `https://datamap.gov.wales/geoserver/ows` |
| Tested on 2026-11-10 | HTTP 200. WCS GetCapabilities listed 9 noise-map coverages. WMS GetCapabilities took 83 s for 14.3 MB. LIDAR matches were tile-index vectors only. The beta site showed the same. |
| Reuse class, mode | link_only, deeplink |

## OSNI river-basin LIDAR

1 m DTM and DSM, 0.5 m for 2007, for 69 flood-study areas, 2004 to 2014.

| Row | Value |
|---|---|
| Access | Bulk download. Zip of ESRI ASCII grids through CKAN. |
| Address | `https://admin.opendatani.gov.uk/api/3/action/package_search?q=river+basin+lidar`, slugs `osni-open-data-river-basin-lidar-{2004,2007,2008,2009,2010,2012,2013,2014}-dtms-and-dsms` |
| Tested on 2026-11-10 | HTTP 302 to a presigned Cloudflare R2 URL, then 206. A range read of `burren_03_03_2012.zip` listed 16 members. |
| Format and CRS | ESRI ASCII grid in zip, some GRD, CSV or XYZ for 2009 to 2010. TM65 Irish Grid, EPSG:29902 per the extents file, not embedded. |
| Licence, attribution | UK Open Government Licence (OGL) v3. None recorded. The report suggested the standard OGL v3 line naming LPS and OSNI. |
| Reuse class, mode | open, bulk |
| Records | 86 zips, 18.5 GB with DSM and point clouds. About 14% of NI. Belfast excluded for copyright. 1 to 2 km tiles. |

Notes:
- `DTM_1m/V0900848.asc` was 2000 by 2000, NODATA -9999, with values such as 104500 to 228430. Those are millimetres, although the official note says metres. Only one tile was decoded.
- Presigned URLs expire after 7 days and reject HEAD with 403. Store the CKAN resource URL and use GET with Range.

The extents file `https://opendatani.blob.core.windows.net/dfiriverslidar/RiverBasin_LIDAR_Extents.zip` was OGL, a shapefile in EPSG:29902 with 77 blocks, 2,240 km2 or 15.7% of NI, and no CORS header. Its grid index `RiverBasin_LIDAR_Grid_Index.zip` held 3,722 1 km tiles. Both were fetched with HTTP 200. Reuse open, mode bulk.

## HED archaeology LIDAR

DTM and DSM for 39 monument sites surveyed from 2008 to 2014. It was the best archaeological LIDAR found in the three smaller nations.

| Row | Value |
|---|---|
| Access | Bulk download. Zip of ESRI ASCII grids on Azure Blob. Range requests work. |
| Address | `https://opendatani.blob.core.windows.net/archaeologylidar/{Site}.zip` |
| Tested on 2026-11-10 | HTTP 200 and 206. A tile of `Navan.zip` (1.70 GB, 518 .asc) came out by range. A Tullaghoge tile of 10.9 MB cost 4.2 MB of a 227 MB zip. |
| Format and CRS | ESRI ASCII grid, 250 m tiles. Irish Grid or ITM by survey. Folder names end `_ING` or `ITM`. Not embedded. Later zips hold both. |
| Licence, attribution | UK Open Government Licence (OGL) v3. None in the dataset note. The report suggested the standard OGL v3 line naming DfC Historic Environment Division. |
| Reuse class, mode | open, bulk |
| Records | 39 zips, 21.86 GB, 7,312 members. Dunluce 190 MB, Tullaghoge 227 MB, Navan 1.7 GB. |
| CORS | No header observed |

Notes: Hillshades showed the Navan Fort enclosure and the plough ridges at Tullaghoge. No extent shapefile is published. Footprints can be derived from tile names for 38 of 39 zips.

## DfI Rivers LIDAR

1 m DTM and DSM around Lough Neagh (April 2017) and 0.5 m of Belfast (March 2006).

| Row | Value |
|---|---|
| Address | `https://opendatani.blob.core.windows.net/dfiriverslidar/`, CKAN slugs `lidar-lough-neagh-environs-2017` and `lidar-belfast-city-2006` |
| Tested on 2026-11-10 | Listing only. `Lough Neagh North East_DSM_DTM.zip` was 93.5 MB with 186 .asc. The grids were not decoded. |
| Format and CRS | ESRI ASCII grid in zip. LAS also for Lough Neagh. Irish Grid, assumed. No CORS header. |
| Licence, attribution | UK Open Government Licence (OGL) v3. Belfast 2006 requires the Cyient Europe Ltd acknowledgement in 'River Basin LIDAR - Belfast City- Note.pdf', which was not read. |
| Reuse class, mode | open, bulk |
| Records | Lough Neagh 478 tiles, 0.73 GB plus 14.37 GB of LAS. Belfast 1.42 GB. |

## DAERA coastal elevation

Raw float32 elevation tiles for the whole NI coast, from the intertidal zone to about 200 m inland, from a 0.25 m source.

| Row | Value |
|---|---|
| Address | `https://tiles-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/Full_NI_Elevation/ImageServer/tile/{z}/{y}/{x}`, tested at 16/20661/31570 (Dunluce) |
| Tested on 2026-11-10 | HTTP 200 image/lerc, 35 KB, 0.33 s. Decoded to 257 by 257 float32, -0.62 to 59.61 m. The follow-up did not re-test it. |
| Format and CRS | LERC, LOD 0 to 23, EPSG:3857 scheme, cached to about 0.15 m pixels |
| Licence, attribution | "Contains public sector information licensed under the Open Government Licence v3.0". "Department of Agriculture, Environment and Rural Affairs (DAERA), Bluesky" |
| Reuse class, mode | open, live as a separate coastal layer once re-tested |
| Limits and CORS | max-age=3600. Reflects Origin. |

It suits coastal promontory forts and eroding sites.

The rendered equivalent is `https://tiles-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/Topographic_LiDAR_DTM_TPK/MapServer/tile/{z}/{y}/{x}`, colour-relief PNG8 under the same OGL. The follow-up could not query its footprint layer, so the coast is missing from the 16.6% figure, at about 110 km2 of land by estimate.

## OSNI 10 m DTM

An NI-wide interpolated 10 m bare-earth DTM, the best open national elevation for NI.

| Row | Value |
|---|---|
| Address | `https://admin.opendatani.gov.uk/api/3/action/package_show?id=osni-open-data-10m-dtm-sheets-251-293`, and five sibling datasets for sheets 1 to 250 |
| Tested on 2026-11-10 | HTTP 302 then 206. A range read of `osni_10m_dtm_sheets_251-293.zip` listed 41 sheets. Whitespace-separated "E N Z" text. Irish Grid, EPSG:29902 assumed. |
| Licence, attribution | UK Open Government Licence (OGL) v3. None recorded. |
| Reuse class, mode | open, bulk as fallback context only |
| Records | 293 sheets in six zips of 92 to 188 MB |

At Beaghmore it showed drumlins and stream channels. The stone circles, cairns and alignments were invisible. The "Enhanced Digital Terrain Model" on nidirect is a paid product.

## OpenDataNI CKAN API

The catalogue API for NI open datasets, listing every LIDAR resource address.

| Row | Value |
|---|---|
| Address | `https://admin.opendatani.gov.uk/api/3/action/package_search?q=lidar&rows=100` |
| Tested on 2026-11-10 | HTTP 200 application/json, 87 packages, all license_id `uk-ogl`. CORS *. |
| Reuse class, mode | open, bulk, to resolve current resource addresses |

Use the `admin.` host, because `/api/3` returned 404 on the public site. File names embed dates, so fixed addresses break.

## DAERA peatland hillshade

Rendered hillshade map services for about 20 bog and fen sites. Avoid them.

| Row | Value |
|---|---|
| Address | `https://tiles-eu1.arcgis.com/kswen6BYexuc1SUk/arcgis/rest/services/{Site}_Hillshade_WGS84/MapServer` |
| Tested on 2026-11-10 | Not tested. Only the organisation search listing was read. |
| Licence, attribution | "Internal use only." "(c) NIEA 2026" |
| Reuse class, mode | link_only, deeplink. Publicly reachable but not licensed for reuse. |

## OS Terrain 50

A GB-wide 50 m DTM grid. A fallback terrain that shows no earthworks.

| Row | Value |
|---|---|
| Address | `https://api.os.uk/downloads/v1/products/Terrain50/downloads?area=GB&format=ASCII+Grid+and+GML+%28Grid%29&redirect` |
| Tested on 2026-11-10 | HTTP 200 (API JSON), 302, 206. A 161.7 MB zip of 2,858 tile zips, version 2026-07. ESRI ASCII, 10 km tiles, 0.1 m vertical step, EPSG:27700. GB only. API reflects Origin. |
| Licence, attribution | OGL v3 (OS OpenData), page not re-read. "Contains OS data (c) Crown copyright [and database right] [year]." |
| Reuse class, mode | open, bulk for low-zoom context in uncovered Scotland only |

A Burnswark 500 m box was 10 by 10 pixels. At Glenelg it showed the glen but not Dun Telve or Dun Troddan, about 18 m across.

## Copernicus GLO-30

A global 1 arc-second surface model covering the whole UK. A fallback terrain that shows no earthworks.

| Row | Value |
|---|---|
| Address | `https://copernicus-dem-30m.s3.amazonaws.com/Copernicus_DSM_COG_10_N{lat}_00_W{lon}_00_DEM/Copernicus_DSM_COG_10_N{lat}_00_W{lon}_00_DEM.tif` |
| Tested on 2026-11-10 | HTTP 200, 30.5 MB per tile. A 17 by 19 pixel window at Burnswark read in 0.81 s. Float32 COG, EPSG:4326, about 27 by 31 m at 55 N. No CORS header. |
| Licence, attribution | "Free under the Copernicus DEM licence (CSCDA ESA mission-specific annex)" per the registry page. The annex was not read. The AWS page asks: "Copernicus Digital Elevation Model (DEM) was accessed on DATE from https://registry.opendata.aws/copernicus-dem." |
| Reuse class, mode | open, provisional until the annex is read. Bulk, below about z12, because there is no CORS header. |

It is a surface model, so forestry reads as terrain. At Glenelg it showed landform but no monument. In Northern Ireland the bare-earth OSNI 10 m DTM is preferable.

## AWS Terrain Tiles

Global elevation tiles in terrarium RGB encoding. A fallback terrain.

| Row | Value |
|---|---|
| Address | `https://s3.amazonaws.com/elevation-tiles-prod/terrarium/{z}/{x}/{y}.png`, tested at 14/8042/5174 |
| Tested on 2026-11-10 | HTTP 200 at z14 and z15, 404 at z16. 256 px, height = R*256 + G + B/256 - 32768. About 3 m per pixel at z15. CORS *. Last-Modified 2017. |
| Licence, reuse, mode | Not checked. link_only, deeplink until the licence and source mix are checked. |

## Mapterhorn

Global open terrarium tiles that include the England, Wales and Scotland Phase 1 1 m DTMs.

| Row | Value |
|---|---|
| Address | `https://tiles.mapterhorn.com/{z}/{x}/{y}.webp` |
| Tested on 2026-11-10 | HTTP 200 image/webp at z12 to z16. 404 at z17. |
| Format and CRS | 512 px WebP, terrarium, EPSG:3857. Vertical step 1/32 m at z16, 1/16 m at z15, 1/2 m at z12. |
| Licence, attribution | Code BSD-3. Data from "various open-data sources". UK entries in attribution.json are Open Government Licence. The TileJSON says "(c) Mapterhorn", linking to `https://mapterhorn.com/attribution`. |
| Reuse class, mode | open, live as a 3D terrain filler only |
| Records | Global 30 m base. UK: England 1 m, Wales 1 m, Scotland Phase 1 only. |
| Limits and CORS | None stated, max-age 7 days. CORS yes. |

Notes: The step is too coarse for 10 cm earthworks. The England edition was not stated.

## NLS multi-direction hillshade, England and Wales

A three-band RGB hillshade of the Environment Agency 1 m DTM, lit from 315, 15 and 75 degrees at 35 degrees elevation, made with the Relief Visualization Toolbox.

| Row | Value |
|---|---|
| Address | `https://mapseries-tilesets.s3.amazonaws.com/lidar/england/{z}/{x}/{y}.png`, tested at 16/32318/22028 |
| Tested on 2026-11-10 | HTTP 200 image/png. 256 px paletted, EPSG:3857, zoom 1 to 18. CORS *. Modified November 2024 to January 2025. No SLA. |
| Licence, attribution | Derived from Environment Agency data under the OGL. The NLS guide says: "If you re-use or re-publish these LiDAR layers, please ensure that you credit and appropriately acknowledge the creators of these specific layers." Upstream "© Environment Agency copyright and/or database right 2022. All rights reserved." Also credit NLS and the RVT processing, by Richard Pearson. |
| Reuse class, mode | open, live as a comparison layer. The NLS guide lists this URL for reuse. |

The Welsh set, `https://mapseries-tilesets.s3.amazonaws.com/lidar/wales/{z}/{x}/{y}.png`, is the same hillshade for the 2020-22 DTM. Tested at 15/15981/10678: HTTP 200, zoom 1 to 18, CORS yes. It is derived from DataMapWales data and credits "Contains public sector information licensed under the Open Government Licence v3.0." Reuse open, mode live as a comparison layer.

## NLS multi-direction hillshade, Scotland

RVT hillshade of the Scottish public-sector DTM, one tileset per phase, plus the Hebrides.

| Row | Value |
|---|---|
| Address | `https://mapseries-tilesets.s3.amazonaws.com/lidar/rgb/phase{1..6}/{z}/{x}/{y}.png` and `/lidar/rgb/hebrides/` |
| Tested on 2026-11-10 | HTTP 200 image/png for phases 1, 3, 4 and 5 at the test tile. 404 outside coverage, and at z17 for phase 4. |
| Format and CRS | 256 px RGBA PNG, EPSG:3857. Maximum zoom 16 for phases 1 to 4 and Hebrides, 17 for phases 5 and 6. |
| Licence, attribution | Per-phase Crown copyright statements in the NLS guide. The licence of each phase was not checked. The Scotland report found no tile hosting terms. Phase 1 "Crown copyright Scottish Government, SEPA and Scottish Water (2012)". Hebrides "Copyright SEPA (2019)". NLS also credits "With thanks to Richard Pearson for processing using RVT". |
| Reuse class, mode | open, provisional. Live as a comparison layer, after asking NLS. |
| CORS | The reports disagreed. The Scotland report saw no header for a third-party Origin. The visualisation report saw yes. |

Notes: Rough Castle and the Antonine Wall were clear in `.../lidar/rgb/phase4/16/32066/20408.png`. This was the only well-processed render of the Scottish data.

## NLS Combined VAT

Greyscale Combined VAT rendered with `rvt_py` from the Environment Agency 1 m DTM, in 5 km tiles with a 50 m buffer.

| Row | Value |
|---|---|
| Address | `https://mapseries-tilesets.s3.amazonaws.com/CVAT/{z}/{x}/{y}.png`, tested at 16/32318/22028 |
| Tested on 2026-11-10 | HTTP 200 image/png at z10, z14, z16. 404 at z17. Zoom 1 to 16, about 1.5 m per pixel in southern England. Modified 2026-09-21. CORS yes. |
| Licence, attribution | Underlying data OGL. Not in the NLS guide's list of URLs offered for reuse. "(c) Environment Agency copyright 2022. With thanks to Richard Pearson for processing using RVT" |
| Reuse class, mode | open for the data. Deeplink: ask NLS before hot-linking. |

The viewer titles the layer "Eng, Wales" but the method text describes England only.

## NLS terrarium DTM

Terrarium-encoded DTM tiles behind the NLS "Live computed LiDAR / SLRM" layer, for England and Wales.

| Row | Value |
|---|---|
| Address | `https://mapseries-tilesets.s3.amazonaws.com/slrm_england_wales/{z}/{x}/{y}.png`, tested at 16/32318/22028 |
| Tested on 2026-11-10 | HTTP 200 at z8 to z16, 404 at z17. 512 px RGBA, terrarium at full 1/256 m precision, about 0.76 m per pixel at z16. A Maiden Castle tile decoded to 73.8 to 132.7 m. Modified 2026-10-26. CORS yes. |
| Licence, attribution | Underlying data OGL. Not listed by NLS as a tileset for reuse. "LiDAR DTM: Environment Agency, DataMapWales, Open Government Licence" |
| Reuse class, mode | open for the data. Deeplink: ask before hot-linking. |

The Environment Agency edition behind it was not stated.

## NLS Sherwood Forest tiles

Hillshade tiles of the Miner2Major Veiled Landscape 16 cm survey, about 220 km2. Avoid them.

| Row | Value |
|---|---|
| Address | `https://mapseries-tilesets.s3.amazonaws.com/lidar/sherwood/dtm/{z}/{x}/{y}.png` |
| Tested on 2026-11-10 | HTTP 200 at 17/65146/42575. Zoom 1 to 19, EPSG:3857. CORS yes. |
| Licence | "(c) 2021 Miner2Major Veiled Landscape Project". No open licence stated. |
| Reuse class, mode | link_only, deeplink to the NLS viewer. |

## Boundary and monument sources used to measure coverage

Three heritage-family sources supplied the polygons and points behind the coverage figures. All were OGL, reuse class open, mode bulk.

| Source | Address | Tested on 2026-11-10 |
|---|---|---|
| ONS Countries December 2025 (BGC) | `https://services1.arcgis.com/ESMARspQHYMw9BZ9/ArcGIS/rest/services/Countries_December_2025_Boundaries_UK_BGC/FeatureServer/0` | HTTP 200, 4 features. England 130,459, Scotland 78,794, Wales 20,782, NI 14,312 km2. |
| HES Scheduled Monuments | `https://inspire.hes.scot/arcgis/rest/services/HES/HES_Designations/MapServer/5` | HTTP 200, 8,076 features in one request. |
| NI Sites and Monuments Record | `https://admin.opendatani.gov.uk/dataset/46240fa5-db15-469e-b1c8-0460504b951c/resource/a2af36e6-d3f0-4abc-9314-b1b72d5a9e06/download/nismr_05112026.geojson` | HTTP 200, 18,521 points. The file name carries a date, so resolve it through CKAN. |

## Deep link only

These are pages and forms, not data a script should read.

| Source | Link | What it gives |
|---|---|---|
| Defra dataset record, 1 m composite DTM | `https://environment.data.gov.uk/dataset/13787b9a-26a4-4775-8523-806d13af58fc` | Licence, attribution and lineage. HTTP 200. It states about 99% coverage, update frequency "annually" and last modified 2023-12-15. |
| Environment Agency Large Data Download form | `https://environment.data.gov.uk/support/datadownload` | The route for offline supply of large areas, cited by the survey FAQ `https://environment.data.gov.uk/support/faqs/275879146`. The form was script-rendered. Its fields, cost and turnaround were not read. Nothing was submitted. Contact: Defra Data Sharing and Access Team, `dspcustomerforum@environment-agency.gov.uk`. |
| DAERA news | `https://www.daera-ni.gov.uk/news/birds-eye-view-calculate-carbon-storage` | 2022-02-09: "A LiDAR survey covering all of Northern Ireland, has recently been announced". |
| AFBI news | `https://www.afbini.gov.uk/news/soil-nutrient-health-scheme-research-maps-way-ahead` | 2024-08-20: a "specially commissioned LiDAR survey" over 6,927 km2, 48% of NI. No licence or release statement. |
| Scottish Government blog | `https://blogs.gov.scot/digital/wp-json/wp/v2/posts/5809` | 2026-01-29. Programme dates, release cadence and the coverage goal. |

## Open questions

- All nations: Decision 0007 defines live as a browser query with nothing stored. The research suggested that the server fetch and cache the Defra image service and WCS, Copernicus and the Scotland catalogue API until a nation is mirrored. Does that fit Decisions 0006 and 0007, or does it need a new mode?
- England: will the Environment Agency supply the 2025 1 m composite offline, in what format and at what cost? Will it join the download catalogue? Does it sanction third-party use of the `utility.arcgis.com` proxy, and is there a limit?
- England: how large are the 3,168 post-2022 patch tiles, and does a 2022 composite plus patches match the 2025 composite? Is there a 2025 survey provenance index?
- Scotland: which blocks will the next programme release cover, and will the footprint WFS follow? The full-coverage commitment is a blog statement.
- Scotland: what attribution does the Scottish Government want for phases 4 to 6 and Orkney 2023? Does the non-commercial restriction on the four HES collections reach derived hillshades in a free public tool?
- Scotland: do Forestry and Land Scotland, SEPA, the national parks or any council hold LIDAR outside the portal? Nobody was contacted.
- Scotland: should the serving copy of 50 cm data stay at 50 cm or drop to 1 m? That decides whether Scotland costs about 0.3 TB or about 1.8 TB by 2028.
- Scotland and Wales: would NLS permit reuse of its RVT tiles? Will the Welsh Government confirm OGL v3 and an attribution string for the 2020-23 LiDAR?
- Northern Ireland: will DAERA or AFBI release the Soil Nutrient Health Scheme LIDAR? Which EPSG code applies to each survey, Irish Grid or ITM? How many river-basin zips are in millimetres? Is the DAERA 2021 coastal DTM available as a raw GeoTIFF?
- All nations: the GCS price of about $0.023 per GB-month was not re-checked, and egress and CDN cost were not estimated.
