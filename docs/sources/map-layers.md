# Map layer sources

This page covers basemaps and overlays, historic maps, aerial imagery, geology and land layers. The research pass of 2026-11-10 found a key-free, legally clean stack: OpenFreeMap for roads and labels, National Library of Scotland (NLS) historic maps under CC-BY, British Geological Survey (BGS) geology under open terms, and Environment Agency aerial photography under the Open Government Licence. Esri World Imagery and Wayback, the best cropmark imagery, load without a key but their terms expect an ArcGIS account. Google, Bing and Mapbox imagery cannot be used. The Historic England, Cambridge and Britain from Above photo archives are open to look up but not to copy.

Every observation was made on 2026-11-10 and is written in the past tense. Nothing here has been built. The research recorded status codes and content types but not sizes or timings, so "Tested" rows give status and type only. Reuse classes and modes follow [Decision 0004](../architecture/decisions/0004-field-club-is-non-commercial.md) and [Decision 0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md). A mode of `live` means the browser fetches the layer from the publisher at view time. A layer's facts table has a "Key needed" row only where a key was required. Where the row is absent, the research used the layer with no key. In CORS rows, Wildcard means `Access-Control-Allow-Origin: *`, and Origin reflected means the server echoed the request's Origin.

## Summary

| Source | Publisher | Coverage | Licence | Reuse | Mode | Records |
|---|---|---|---|---|---|---|
| OpenFreeMap vector tiles | OpenFreeMap | Global | MIT service, ODbL data | share_alike | live | z0-14 |
| NLS six-inch 2nd edition | NLS | GB | CC-BY 4.0 | open | live | z1-17 |
| NLS 25-inch | NLS | GB by county | CC-BY | open | live | About 56 tilesets |
| NLS six-inch 1st edition | NLS | Eng, Wales by county; Scotland | CC-BY | open | live | n/a |
| NLS 1:25,000 outline | NLS | GB | CC-BY | open | live | z1-16 |
| NLS small scales | NLS | GB | CC-BY | open | live | z1-14 |
| NLS Bartholomew half-inch | NLS | GB | CC-BY | open | live | Two editions |
| NLS air photo mosaics | NLS | Selected areas | CC-BY | open | live | z16 max |
| NLS ten-mile maps | NLS | GB | CC-BY | open | live | z1-12 |
| NLS RVT hillshade, England | NLS | England | OGL data | open | live | z1-18 |
| NLS RVT hillshade, Wales | NLS | Wales | OGL v3.0 | open | live | z1-18 |
| NLS RVT hillshade, Scotland | NLS | Scotland, partial | Per phase | open, unchecked | live | 7 tilesets |
| BGS Geology 50k WMS | BGS | GB | OGL | open | live | n/a |
| BGS Geology 625k WMS | BGS | UK | Open, no resale | open | live | n/a |
| BGS OGC API Features 625k | BGS | UK | As 625k WMS | open | bulk | 4 collections |
| Historic England AIM | HE | England, part | OGL | open | bulk | 498,295 polygons |
| EA Vertical Aerial Photography | EA | England, patchy | OGL | open | bulk | 79,607 polygons |
| Natural England CRoW access | Natural England | England | OGL v3 | open | bulk | 42,054 polygons |
| Council rights of way | Councils | Eng, Wales, partial | Mostly OGL | open | bulk | 149 authorities |
| OS Open Zoomstack | OS | GB | OGL | open | bulk | Version 2026-06 |
| Protomaps planet build | Protomaps | Global | ODbL | share_alike | bulk | 62 builds |
| Historic England oblique photos | HE | England | None stated | link_only | live | 468,176 points |
| Historic England vertical photos | HE | England | None stated | link_only | live | 103,185 footprints |
| CUCAP | Cambridge | UK, Ireland | None open | link_only | live | Not counted |
| Esri World Imagery | Esri | Global | Esri MLA | link_only | live, account | z0-23 |
| Esri World Imagery Wayback | Esri | Global | Esri terms | link_only | live, account | 198 releases |
| Esri capture-date lookup | Esri | Global | Esri terms | link_only | live | JSON identify |
| Soilscapes | Cranfield, Defra | England, Wales | Unconfirmed | link_only, tentative | live | n/a |
| EOX Sentinel-2, 2016 and 2017 | EOX | Global | CC BY 4.0 | open | live | z14 max |
| EOX Sentinel-2, 2018 onward | EOX | Global | CC BY-NC-SA 4.0 | non_commercial | live | z14 max |
| EOX transparent OSM overlay | EOX | Global | Attribution | share_alike | live | n/a |
| OS Maps API OpenData styles | OS | GB | OGL data | open | live, key | z7-16 open |
| NLS Combined VAT | NLS | England | OGL data | open | deeplink | z1-16 |
| NLS terrarium elevation | NLS | England, Wales | OGL data | open | deeplink | z4-16 |
| NLS Historic Maps API on MapTiler | NLS, MapTiler | GB | CC BY 3.0 | non_commercial | live, key | 8 layers |
| OpenStreetMap standard tiles | OSMF | Global | ODbL, tile usage policy | share_alike | live, dev only | z0-19 |

Sources that can only be opened by a link are in "Deep link only". Sources the research judged unusable are in "Layers to avoid".

## Layers the research judged clean without a key

OpenFreeMap; the NLS historic maps, all CC-BY, though NLS had not confirmed in writing that a public app may hot-link its S3 tilesets; BGS Geology 50k and 625k; Environment Agency vertical aerial photography, which is download only; Historic England AIM and Natural England CRoW access, both OGL; OS Open Zoomstack as a wholly OGL fallback basemap; and the NLS RVT multi-hillshade tiles for England and Wales, which NLS listed as offered for reuse. The research judged Esri imagery, Soilscapes, EOX mosaics from 2018 and every Google, Bing and Mapbox layer not clean.

## OpenFreeMap vector tiles

OpenStreetMap vector tiles in the OpenMapTiles schema with hosted styles, glyphs and sprites. The research judged it the best default overlay over LIDAR.

| | |
|---|---|
| Address | TileJSON https://tiles.openfreemap.org/planet. Styles https://tiles.openfreemap.org/styles/{liberty, bright, positron, dark or fiord} |
| Tested on 2026-11-10 | 200 application/json for TileJSON and styles. 200 application/vnd.mapbox-vector-tile for a tile |
| Format and CRS | MVT .pbf, z0-14, EPSG:3857 |
| Licence | Homepage: "Is commercial usage allowed? Yes" and "The license of this project is MIT". Data is OpenStreetMap under ODbL |
| Attribution | "OpenFreeMap © OpenMapTiles Data from OpenStreetMap", from the TileJSON. The homepage said "Attribution is required" |
| Reuse class | share_alike |
| Suggested mode | live, with a self-hosted fallback |
| Paging and limits | "there are no limits on the number of map views or requests". Terms: offline downloads at most 3,000 tiles or 50 MB, at most 4 parallel requests, a unique User-Agent. No SLA: "may discontinue it at any time without notice" |
| CORS | Wildcard |

```json
{
  "type": "vector",
  "url": "https://tiles.openfreemap.org/planet",
  "attribution": "OpenFreeMap © OpenMapTiles Data from OpenStreetMap"
}
```

```
https://tiles.openfreemap.org/planet/20261101_080013_pt/14/8107/5453.pbf
```

### Notes

- The tile path carried a dated build id, 20261101_080013_pt, so the TileJSON `url` is the stable address. Glyphs: `https://tiles.openfreemap.org/fonts/{fontstack}/{range}.pbf`. Sprite: `https://tiles.openfreemap.org/sprites/ofm_f384/ofm`.
- The Avebury z14 tile held transportation subclass footway 22 and bridleway 3, and the poi layer had gate 50 and stile 8. The source was donation funded.
- Suggested use: draw only line and symbol layers on transportation, transportation_name, place, boundary, waterway and water_name, with no fill, above the LIDAR. Keep the style JSON in the repository. MapLibre overzooms the z14 tiles cleanly to z20.

## NLS tilesets: shared terms

The NLS tilesets below share a host, a licence and a credit line. This section states them once, and each series section gives only what differs.

| | |
|---|---|
| Host | https://mapseries-tilesets.s3.amazonaws.com, a public S3 bucket. No SLA and no usage limit stated |
| Format and CRS | PNG 256 px in EPSG:3857, unless a section says otherwise |
| Licence | CC-BY (NLS). Sheet pages showed "Re-use: CC-BY (NLS)". The copyright page allowed "commercial, non-commercial, educational and private purposes" under CC-BY |
| Attribution | "Reproduced with the permission of the National Library of Scotland", with a link to https://maps.nls.uk/ |
| Reuse class | open |
| Suggested mode | live |
| CORS | Wildcard. Missing tiles inside coverage returned 404 with CORS headers |

### Tested tile requests

```
https://mapseries-tilesets.s3.amazonaws.com/os/six-inch-wiltshire/15/16215/10907.png
https://mapseries-tilesets.s3.amazonaws.com/os/25000_outline/15/16215/10907.png
https://mapseries-tilesets.s3.amazonaws.com/api/nls/14/8107/5453.jpg
https://mapseries-tilesets.s3.amazonaws.com/bartholomew_great_britain/15/16215/10907.png
https://mapseries-tilesets.s3.amazonaws.com/air-photos-10560/16/32430/21815.png
https://mapseries-tilesets.s3.amazonaws.com/ten_mile/geological/12/2026/1363.png
```

### Notes

- NLS's copyright page once carried a "CC-BY-NC-SA (OS)" exception for OS six-inch and 25-inch England and Wales, 1:25,000 1937-61, the Seventh Series and the ten-mile maps. On 2026-11-10 that clause sat inside an HTML comment and was not displayed. A third-party MapTiler page still described commercial limits on some series. Other exceptions included British Library material such as Roy. The research recommended written confirmation from NLS.
- Several URLs come from NLS's own viewer script, `explore-layers-ol6.js`, and are not on NLS's published list of 32 layers. NLS moved its public API to MapTiler in March 2022. The old host `nls-0.tileserver.com` served a placeholder image reading "NLS maps upgraded: maptiler.com/nls" and must not be used. The viewer script path was dated `scripts/20251109/` and was expected to change.
- Suggested use: email NLS before launch to confirm hot-linking from a public app, and offer to mirror the tiles to Cloud Storage under CC-BY if they prefer. Set `maxzoom` per source from the observed values below, so MapLibre overzooms instead of requesting 404s. Each JSON gives the credit line without link markup, and MapLibre can carry the link as an HTML anchor.

## NLS six-inch 2nd edition, 1888-1913

Continuous georeferenced OS six-inch mapping at 1:10,560 for Great Britain. The research called it the standard layer for earthwork annotation.

| | |
|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/os/6inchsecond/{z}/{x}/{y}.png |
| Tested on 2026-11-10 | 200 image/png at z15, z16 and z17 over Avebury. 404 at z18 |
| Licence | CC-BY 4.0 (NLS) |

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/os/6inchsecond/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "minzoom": 1,
  "maxzoom": 17,
  "attribution": "Reproduced with the permission of the National Library of Scotland"
}
```

```
https://mapseries-tilesets.s3.amazonaws.com/os/6inchsecond/15/16215/10907.png
```

The sample tile showed "The Temple, Stone Circle" at Avebury. NLS stated a maximum zoom of 16. Its published brief layers list pointed to MapTiler layer uk-osgb10k1888 for this series.

## NLS 25-inch, 1841-1952

OS 25-inch mapping at 1:2,500, the most detailed historic mapping the research found, as one tileset per county and edition.

| | |
|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/25_inch/{county}/{z}/{x}/{y}.png |
| Tested on 2026-11-10 | `25_inch/wiltshire`: 200 at z15, z16 and z18, 404 at z19. `25_inch/wiltshire2nd`: 200 at z15, 404 at z16 to z18 at that spot |
| Licence | CC-BY (NLS), shown on the sheet page for Wiltshire II.11. Undocumented for reuse beyond that |
| Records | About 56 tileset names under `25_inch/` in the viewer script |

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/25_inch/wiltshire/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "maxzoom": 18,
  "bounds": [-2.37245, 50.90840, -1.47408, 51.69208],
  "attribution": "Reproduced with the permission of the National Library of Scotland"
}
```

```
https://mapseries-tilesets.s3.amazonaws.com/25_inch/wiltshire/18/129721/87261.png
```

Each county needs its own source with `bounds` from the NLS script. Only the Wiltshire bounds were recorded. Generate the rest from https://maps.nls.uk/geo/scripts/20251109/explore-layers-ol6.js. The script listed about 56 names, including wiltshire, wiltshire2nd, wales, scotland_1 and scotland_2. The single-layer alternative, MapTiler `uk-osgb1888`, needs a key.

## NLS six-inch 1st edition, 1840s-1880s

The earliest large-scale OS survey, as one tileset per county for England and Wales and one mosaic for Scotland.

| | |
|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/os/six-inch-{county}/{z}/{x}/{y}.png. Scotland: https://mapseries-tilesets.s3.amazonaws.com/os/6inchfirst/{z}/{x}/{y}.png |
| Tested on 2026-11-10 | `os/six-inch-wiltshire`: 200 at z15 and z17. `os/6inchfirst`: 200 over Edinburgh, 404 over Avebury |

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/os/six-inch-wiltshire/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "maxzoom": 17,
  "attribution": "Reproduced with the permission of the National Library of Scotland"
}
```

Wiltshire's maxzoom 17 was observed. The Scotland mosaic uses the `os/6inchfirst` address with `"maxzoom": 16`, the published value. Only the Scotland layer was on NLS's published list. County names came from the viewer script. Bounds were not recorded.

## NLS 1:25,000 outline, 1945-1965

The post-war 1:25,000 Provisional outline edition, continuous for Great Britain.

| | |
|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/os/25000_outline/{z}/{x}/{y}.png |
| Tested on 2026-11-10 | 200 at z15 and z16, 404 at z17 |
| Format | z1-16. On the published layers list |

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/os/25000_outline/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "minzoom": 1,
  "maxzoom": 16,
  "attribution": "Reproduced with the permission of the National Library of Scotland"
}
```

The coloured 1:25,000 1937-61 series was available only through MapTiler as `uk-osgb25k1937`.

## NLS small scales, 1920s-1940s

Continuous one-inch and smaller OS mapping of Great Britain. The research named it the free one-inch option for England.

| | |
|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/api/nls/{z}/{x}/{y}.jpg |
| Tested on 2026-11-10 | 200 image/jpeg at z14, 404 at z15 |
| Format and CRS | JPEG 256 px, z1-14, EPSG:3857 |
| Format | On the published layers list |

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/api/nls/{z}/{x}/{y}.jpg"],
  "tileSize": 256,
  "minzoom": 1,
  "maxzoom": 14,
  "attribution": "Reproduced with the permission of the National Library of Scotland"
}
```

Other Scotland-only layers tested 200: `os/1inch_pop_nat_grid` and `popular_outline`.

## NLS Bartholomew half-inch

Bartholomew layer-coloured half-inch maps of Great Britain, in editions 1897-1907 and 1940-1947.

| | |
|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/bartholomew_great_britain/{z}/{x}/{y}.png and https://mapseries-tilesets.s3.amazonaws.com/bartholomew/great_britain_1940s/{z}/{x}/{y}.png |
| Tested on 2026-11-10 | 1897-1907: 200 at z15. 1940s: 200 at z14, 404 at z15 |
| Format | On the published layers list |

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/bartholomew_great_britain/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "maxzoom": 15,
  "attribution": "Reproduced with the permission of the National Library of Scotland"
}
```

The 1940s edition uses the second address with `"maxzoom": 14`.

## NLS air photo mosaics, 1944-1950

Georeferenced OS air photo mosaics at 1:10,560 from RAF photography, with place names overprinted, for selected areas of England, Wales and Scotland. The research judged them useful for features since ploughed out.

| | |
|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/air-photos-10560/{z}/{x}/{y}.png for England and Wales. https://mapseries-tilesets.s3.amazonaws.com/air-photo/{z}/{x}/{y}.png for Scotland, from the viewer script |
| Tested on 2026-11-10 | `air-photos-10560`: 200 at z12, z15 and z16 over Avebury, 404 at z17. The published https://geo.nls.uk/maps/air-photos/ URL returned 404 at Avebury and Edinburgh |
| Format | On the layers list |

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/air-photos-10560/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "maxzoom": 16,
  "attribution": "Reproduced with the permission of the National Library of Scotland"
}
```

The Avebury tile showed the henge with an "AVEBURY" overprint. The Scotland name `air-photo` was not tested. `air-photos-1250`, for towns, returned 404 at Avebury.

## NLS ten-mile planning maps, 1944-1957

Thematic 1:633,600 national maps. The research judged them low value at site scale and possible as an overview layer.

| | |
|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/ten_mile/{general, geological, land_utilisation, land_classification, physical, farming, limestone, admin, coal_iron, iron_steel, railway, rainfall, roads_46 or roads_56}/{z}/{x}/{y}.png |
| Tested on 2026-11-10 | 200 for general and geological at z12. 404 at z13 |
| Format | z1-12. On the published layers list |

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/ten_mile/geological/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "minzoom": 1,
  "maxzoom": 12,
  "attribution": "Reproduced with the permission of the National Library of Scotland"
}
```

## NLS RVT multi-direction hillshade

Three-band RGB hillshades made with the Relief Visualization Toolbox from public sector LIDAR, lit from 315, 15 and 75 degrees at 35 degrees elevation for England. NLS listed the England and Wales URLs as offered for reuse. Decision 0006 renders Field Club's own visualisations, so these serve as comparison layers.

| | England | Wales | Scotland |
|---|---|---|---|
| Address | .../lidar/england/{z}/{x}/{y}.png | .../lidar/wales/{z}/{x}/{y}.png | .../lidar/rgb/phase{1..6}/{z}/{x}/{y}.png, .../lidar/rgb/hebrides/ |
| Tested on 2026-11-10 | 200 image/png | 200 image/png | 200 for phases 1, 3, 4, 5. 404 outside coverage |
| Format | Paletted, z1-18 | Paletted, z1-18 | RGBA. Maxzoom 16, or 17 for phases 5 and 6 |
| Licence | Environment Agency data under OGL | "Contains public sector information licensed under the Open Government Licence v3.0." | Per-phase Crown copyright, phase licences not checked |
| Attribution | "(c) Environment Agency copyright and/or database right 2022. All rights reserved." Also credit NLS and RVT | As the licence line | Phase 1: "Crown copyright Scottish Government, SEPA and Scottish Water (2012)". Hebrides: "Copyright SEPA (2019)". Other phases per the NLS guide |

All three use the host and CORS terms above, with reuse class open and suggested mode live. The research reports disagreed on whether the LIDAR tiles answer a third-party origin. A recheck on 2026-11-11 of an England tile at z14, sent with `Origin: https://fieldclub.example`, got 200 with `Access-Control-Allow-Origin: *` and `Vary: Origin`. For Scotland the class holds only if each phase's own licence is open. The addresses are relative to the NLS host.

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/lidar/england/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "minzoom": 1,
  "maxzoom": 18,
  "bounds": [-6.4665, 49.8506, 1.7782, 55.8782],
  "attribution": "(c) Environment Agency copyright and/or database right 2022. All rights reserved. National Library of Scotland, processed with RVT"
}
```

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/lidar/wales/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "minzoom": 1,
  "maxzoom": 18,
  "bounds": [-5.3026, 51.3662, -2.6361, 53.4469],
  "attribution": "Contains public sector information licensed under the Open Government Licence v3.0"
}
```

```json
{
  "type": "raster",
  "tiles": ["https://mapseries-tilesets.s3.amazonaws.com/lidar/rgb/phase1/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "maxzoom": 16,
  "attribution": "Crown copyright Scottish Government, SEPA and Scottish Water (2012)"
}
```

```
curl -L -H 'Origin: https://example.org' https://mapseries-tilesets.s3.amazonaws.com/lidar/england/16/32318/22028.png
curl -L https://mapseries-tilesets.s3.amazonaws.com/lidar/wales/15/15981/10678.png
curl -L https://mapseries-tilesets.s3.amazonaws.com/lidar/rgb/phase1/15/16044/10229.png
```

### Notes

Richard Pearson processed England, and tiles were last modified between November 2024 and January 2025. The England and Wales bounds came from `metadata.json`. Scotland bounds were not recorded. The England attribution string is composed from the credits the research recorded and is not an NLS-approved form.

## BGS Geology 50k WMS

The BGS Detailed Geology service at 1:50,000: bedrock, superficial deposits, artificial ground, mass movement and linear features.

| | |
|---|---|
| Address | https://map.bgs.ac.uk/arcgis/services/BGS_Detailed_Geology/MapServer/WMSServer |
| Tested on 2026-11-10 | GetCapabilities 200 text/xml. GetMap 200 image/png. GetFeatureInfo 200 application/geo+json |
| Format and CRS | PNG, jpeg, svg. Maximum 4096 px. Native EPSG:27700, also 3857, 4326 and 4258 |
| Licence | Capabilities: "These data are delivered under the terms of the Open Government Licence ..., subject to the following acknowledgement accompanying the reproduced BGS materials: Contains British Geological Survey materials copyright UKRI [year]." Fees: none |
| Attribution | "Contains British Geological Survey materials © UKRI 2026" |
| Reuse class | open |
| Suggested mode | live, with GetFeatureInfo on click |
| Paging and limits | MaxScaleDenominator 94,495. A z12 tile came back blank and z14 rendered |
| CORS | Origin reflected |

```json
{
  "type": "raster",
  "tiles": ["https://map.bgs.ac.uk/arcgis/services/BGS_Detailed_Geology/MapServer/WMSServer?service=WMS&version=1.3.0&request=GetMap&layers=BGS.50k.Superficial.deposits&styles=&format=image/png&transparent=true&crs=EPSG:3857&width=256&height=256&bbox={bbox-epsg-3857}"],
  "tileSize": 256,
  "minzoom": 13,
  "attribution": "Contains British Geological Survey materials © UKRI 2026"
}
```

```
https://map.bgs.ac.uk/arcgis/services/BGS_Detailed_Geology/MapServer/WMSServer?service=WMS&version=1.3.0&request=GetFeatureInfo&layers=BGS.50k.Bedrock,BGS.50k.Superficial.deposits&query_layers=BGS.50k.Bedrock,BGS.50k.Superficial.deposits&styles=&info_format=application/geo%2Bjson&crs=EPSG:3857&width=256&height=256&bbox=-207908.716935,6696942.671643,-205462.732030,6699388.656549&i=128&j=128
```

### Notes

Layers: BGS.50k.Bedrock, BGS.50k.Superficial.deposits, BGS.50k.Artificial.ground, BGS.50k.Mass.movement and BGS.50k.Linear.features. GetFeatureInfo at Avebury returned LEX_RCS_D "Zig Zag Chalk Formation-Chalk" and BROAD_D "chalk". The 50k vector data was not an open download. The OGL statement covered this view service.

## BGS Geology 625k WMS

1:625,000 bedrock and superficial geology of the UK, on a different host from the 50k service.

| | |
|---|---|
| Address | https://ogc.bgs.ac.uk/cgi-bin/BGS_Bedrock_and_Superficial_Geology/wms |
| Tested on 2026-11-10 | GetCapabilities 200 text/xml. GetMap 200 image/png |
| Format and CRS | PNG, jpeg and MVT listed. Maximum 3072 px. Native EPSG:27700, also 3857, 4326 and 4258 |
| Licence | Capabilities: "The 1:625k DiGMap data is made available for all uses - including commercial use, however the British Geological Survey (BGS) at all times retains the copyright in this material and you are not permitted, without an appropriate licence, to set up a service selling on this material." Fees: none |
| Attribution | "Contains British Geological Survey materials © UKRI 2026" |
| Reuse class | open |
| Suggested mode | live, below z13 |
| CORS | Wildcard |

```json
{
  "type": "raster",
  "tiles": ["https://ogc.bgs.ac.uk/cgi-bin/BGS_Bedrock_and_Superficial_Geology/wms?service=WMS&version=1.3.0&request=GetMap&layers=GBR_BGS_625k_BLS&styles=&format=image/png&transparent=true&crs=EPSG:3857&width=256&height=256&bbox={bbox-epsg-3857}"],
  "tileSize": 256,
  "maxzoom": 12,
  "attribution": "Contains British Geological Survey materials © UKRI 2026"
}
```

```
https://ogc.bgs.ac.uk/cgi-bin/BGS_Bedrock_and_Superficial_Geology/wms?service=WMS&version=1.3.0&request=GetMap&layers=GBR_BGS_625k_BLS&styles=&format=image/png&transparent=true&crs=EPSG:3857&width=256&height=256&bbox=-234814.550892,6692356.699946,-195678.792410,6731492.458428
```

Layers: GBR_BGS_625k_BLT, GBR_BGS_625k_BLS and GBR_BGS_625k_BA for bedrock, and GBR_BGS_625k_SLT and GBR_BGS_625k_SLS for superficial deposits.

## BGS OGC API Features, geology 625k

The 625k bedrock, superficial, dykes and faults as queryable vector features.

| | |
|---|---|
| Address | https://ogcapi.bgs.ac.uk/collections/{bgsgeology625kbedrock, bgsgeology625ksuperficial, bgsgeology625kdykes or bgsgeology625kfaults}/items |
| Tested on 2026-11-10 | 200 application/json |
| Format and CRS | GeoJSON, EPSG:4326 output |
| Licence | The 625k WMS statement: "made available for all uses - including commercial use". The OGC API licence page was not read separately |
| Attribution | "Contains British Geological Survey materials © UKRI 2026" |
| Reuse class | open |
| Suggested mode | bulk |
| Records | The sample bbox returned numberMatched 3. Geometries were large, 474 KB for 2 features |
| CORS | Origin reflected |

```
https://ogcapi.bgs.ac.uk/collections/bgsgeology625kbedrock/items?f=json&limit=2&bbox=-1.9,51.4,-1.8,51.45
```

The same dataset was a 12 MB shapefile from the OS Downloads API, product BGS_Geology_625k. Suggested use: ingest once rather than query per view. This is not a tile source, so no MapLibre definition applies.

## Historic England Aerial Investigation and Mapping

Archaeological features mapped by Historic England and partners from aerial photographs and LIDAR, with period, monument type, evidence and source photo references.

| | |
|---|---|
| Address | https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/HE_AIM_data/FeatureServer |
| Tested on 2026-11-10 | 200 application/json |
| Format and CRS | JSON, GeoJSON. EPSG:27700. `outSR=4326` worked |
| Licence | Service copyrightText: "© Historic England 2026. Released under OGL." |
| Attribution | "© Historic England 2026. Released under OGL." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | Layer 0 Detailed_Mapping 498,295. Layer 1 Monument_Extents 197,372. Layer 2 Project_Area 163 |
| Paging and limits | maxRecordCount 2000. Capabilities Query and Extract |
| CORS | Wildcard |

```
https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/HE_AIM_data/FeatureServer/0/query?where=1%3D1&geometry=-1.862,51.424,-1.846,51.433&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=2&f=geojson
```

Fields included LAYER, PERIOD, MONUMENT_TYPE, EVIDENCE_1, SOURCE_1, HE_UID and HE_URL1, a Heritage Gateway link. SOURCE_1 cited photos, for example "CUCAP RC8KnBB 222-3 25-APR-1988".

## Environment Agency Vertical Aerial Photography

EA orthophotography at 10 to 50 cm in RGB, near infra-red and RGBN, flown project by project since 2006. It was the only high-resolution imagery the research found that can be self-hosted and traced from under the OGL.

| | |
|---|---|
| Address | Index WFS https://environment.data.gov.uk/spatialdata/survey-index-files/wfs, typeName `dataset-9f0fa3fc-a860-4729-adc9-47fe53f658d0:Vertical_photography_index_catalogue`. Downloads at https://environment.data.gov.uk/DefraDataDownload/?Mode=survey, as ECW in 5 km zips. No imagery WMS or WMTS |
| Tested on 2026-11-10 | WFS GetCapabilities 200 application/xml. GetFeature 200 application/json. WMS GetCapabilities 200 text/xml. Guessed imagery WMS paths returned 404 |
| Format and CRS | Index in GeoJSON or GML. Imagery in ECW. EPSG:27700 |
| Licence | Open Government Licence. The data.gov.uk record: "There are no public access constraints to this data. Use of this data is subject to the licence identified." |
| Attribution | "© Environment Agency copyright and/or database right [year]. All rights reserved." |
| Reuse class | open |
| Suggested mode | bulk, where the index shows coverage |
| Records | 79,607 index polygons. 0 at Avebury. 47 in a 2 km box at Oxford |
| CORS | Wildcard on the WFS and WMS |

```
https://environment.data.gov.uk/spatialdata/survey-index-files/wfs?service=WFS&version=2.0.0&request=GetFeature&typeNames=dataset-9f0fa3fc-a860-4729-adc9-47fe53f658d0:Vertical_photography_index_catalogue&outputFormat=application/json&count=3&bbox=450000,205000,452000,207000,urn:ogc:def:crs:EPSG::27700
```

Index fields included filename, sd_flown, ed_flown, type such as IRRGB, resolution and bands. A bbox in EPSG:4326 axis order returned nothing, so use EPSG:27700. Coverage was patchy: river corridors, coasts and incident response. Suggested use: query the index by bbox, convert the ECW downloads to cloud-optimised GeoTIFF and tile them to Cloud Storage, if coverage justifies it. Coverage of the user base was not measured.

## Natural England CRoW access layer

Open access land in England: open country, registered common land and Section 16 dedicated land. It tells users where they may legally walk to check a feature.

| | |
|---|---|
| Address | https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/CRoW_Act_2000_Access_Layer/FeatureServer/0 |
| Tested on 2026-11-10 | 200 application/json |
| Format and CRS | JSON, GeoJSON, PBF. EPSG:27700 |
| Licence | Item licenceInfo: "There are no public access constraints to this data. Use of this data is subject to the Open Government Licence" version 3 |
| Attribution | "© Natural England copyright. Contains Ordnance Survey data © Crown copyright and database right 2024." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 42,054 polygons, data version v52 |
| Paging and limits | maxRecordCount 2000 |
| CORS | Wildcard |

```
https://services.arcgis.com/JJzESW51TqeY9uat/arcgis/rest/services/CRoW_Act_2000_Access_Layer/FeatureServer/0/query?where=1%3D1&geometry=-2.0,51.3,-1.6,51.6&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=2&f=geojson
```

Fields: Descrip, OC, RCL, S16, Map_Area and Version. Sibling services on the same host cover the CRoW sections. Wales and Scotland equivalents were not tested.

## Public rights of way from councils

Rights of way are published authority by authority, and no national dataset exists. The rowmaps site indexes open releases.

| | |
|---|---|
| Address | Index https://www.rowmaps.com/datasets/. Example https://maps.wiltshire.gov.uk/arcgis/rest/services/OpenData/PublicRightsofWay/FeatureServer/0 |
| Tested on 2026-11-10 | rowmaps 200 text/html. Wiltshire FeatureServer 200 application/json. Query 200 application/geo+json |
| Format and CRS | Shapefile, KML, GPX, GeoJSON via rowmaps. GeoJSON from the FeatureServer. EPSG:27700 |
| Licence | Varies by authority, mostly OGL with an OS acknowledgement. rowmaps: "Rights of way data for 149 authorities in England and Wales have been released with an open licence." The Wiltshire service stated no licence |
| Attribution | Per authority, typically "© [Council]. Contains OS data © Crown copyright and database right [year]" |
| Reuse class | open, per authority. Wiltshire unconfirmed |
| Suggested mode | bulk, one authority at a time, with the licence recorded per dataset |
| Records | 149 authorities released. Coverage incomplete |
| Paging and limits | Wiltshire maxRecordCount 11000 |
| CORS | Origin reflected on the Wiltshire server |

```
https://maps.wiltshire.gov.uk/arcgis/rest/services/OpenData/PublicRightsofWay/FeatureServer/0/query?where=1%3D1&geometry=-1.87,51.42,-1.84,51.44&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=2&f=geojson
```

The research called OSM transportation, with subclass footway and bridleway in the OpenFreeMap tiles, the practical national layer. It warned that showing a path as a legal right of way from OSM or stale council data could mislead users about access.

## OS Open Zoomstack

The Ordnance Survey open vector basemap of Great Britain, downloadable without a key. The research suggested it as a wholly OGL fallback basemap with no OSM share-alike.

| | |
|---|---|
| Address | https://api.os.uk/downloads/v1/products/OpenZoomstack/downloads?area=GB&format=Vector+Tiles&subformat=%28MBTiles%29&redirect |
| Tested on 2026-11-10 | 307, then 206 application/octet-stream on a range request. The file header was SQLite 3 |
| Format and CRS | MBTiles vector tiles, 2,852,712,448 bytes. GeoPackage zip 4,301 MB, EPSG:27700. The MBTiles projection was not confirmed, and Web Mercator was believed |
| Licence | Open Government Licence. The OS page was not directly readable. Confirmed through a search of the OS support page |
| Attribution | "Contains OS data © Crown copyright and database right 2026" |
| Reuse class | open |
| Suggested mode | bulk |
| Records | Product version 2026-06. Updated June and December |
| CORS | Origin reflected on the API JSON |

```
curl -L -r 0-4095 'https://api.os.uk/downloads/v1/products/OpenZoomstack/downloads?area=GB&format=Vector+Tiles&subformat=%28MBTiles%29&redirect'
```

Suggested use: convert with `pmtiles convert` and host on Cloud Storage. The same API listed 25 open products without a key.

## Protomaps planet build

A daily single-file planet vector basemap built from OpenStreetMap, which can be cut by bounding box for self-hosting.

| | |
|---|---|
| Address | https://build.protomaps.com/{YYYYMMDD}.pmtiles. Index https://build-metadata.protomaps.dev/builds.json |
| Tested on 2026-11-10 | 206 application/octet-stream on range 0-16383. builds.json 200 |
| Format and CRS | PMTiles v3, gzip MVT, z0-15, EPSG:3857 |
| Licence | Data © OpenStreetMap contributors under ODbL. The Protomaps licence page was not re-read |
| Attribution | "© OpenStreetMap contributors", plus a Protomaps credit per their documentation, which was not re-read |
| Reuse class | share_alike |
| Suggested mode | bulk |
| Records | 62 builds. The latest, 20261110.pmtiles, was 139,416,504,818 bytes with 1,431,655,765 addressed tiles |
| CORS | No `Access-Control-Allow-Origin` header. A download host, not for hot-linking |

```
curl -r 0-16383 https://build.protomaps.com/20261110.pmtiles
```

A Great Britain extract would load through the pmtiles protocol with a source of `type` vector and `url` `pmtiles://https://{our-bucket}/gb.pmtiles`. The bucket does not exist yet, so no definition is recorded.

Suggested workflow: `pmtiles extract <build url> gb.pmtiles --bbox=-8.7,49.8,1.8,60.9`, upload to Cloud Storage with a CORS policy allowing GET and the Range header, and load through the pmtiles protocol. A public Cloud Storage object returned 206 with `accept-ranges: bytes`. Protomaps uses its own schema, not OpenMapTiles.

## Historic England aerial photo indexes

Two public ArcGIS services list Historic England Archive photographs: oblique photographs as points and vertical photographs, including 1940s RAF sorties, as footprint polygons.

| | Oblique | Vertical |
|---|---|---|
| Address | https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/Obliques_update_20250304_view/FeatureServer/0 | The same host, `New_Verticals_20250304_view` |
| Key needed | No | No |
| Tested on 2026-11-10 | 200 application/json | 200 application/json |
| Format and CRS | JSON, GeoJSON. EPSG:27700, `outSR=4326` worked | JSON, GeoJSON. EPSG:27700 |
| Licence | None on the service, as copyrightText was empty. Per-record copyright, for example "© Historic England". Not stated as OGL | None on the service. Per-record copyright, for example "Source Historic England Archive (RAF photography)" or "© Historic England" |
| Attribution | "© Historic England Archive" | "Source Historic England Archive" |
| Reuse class | link_only | link_only |
| Suggested mode | live | live |
| Records | 468,176 in the current `Obliques_20260529_Full_view`. The service tested held 453,090. 257 within about 1 km of Avebury | 103,185 in the current `Verticals_20260529_poly_Full_view`. The service tested held 96,190. 102 at Avebury |
| Paging and limits | maxRecordCount 15, Query only | maxRecordCount 15 |
| CORS | Wildcard | Same |

```
https://services-eu1.arcgis.com/ZOdPfBS3aqqDYPUQ/arcgis/rest/services/Obliques_update_20250304_view/FeatureServer/0/query?where=1%3D1&geometry=-1.862,51.424,-1.846,51.433&geometryType=esriGeometryEnvelope&inSR=4326&spatialRel=esriSpatialRelIntersects&outFields=*&outSR=4326&resultRecordCount=2&f=geojson
```

The vertical query uses `New_Verticals_20250304_view` in place of the oblique service name.

### Notes

- Two reports disagreed on the counts. The completeness review settled it: they were two date-stamped services, the 20260529 pair current and the 20250304 pair stale. The layer path under the current names was not recorded.
- The 15-record limit looked like a deliberate anti-harvest setting. Suggested use: query per viewport, cache briefly, link out and do not bulk copy. Service names carry dates and will be replaced.

## Cambridge University Collection of Aerial Photography

CUCAP is a catalogue of Cambridge air photos, heavily used in archaeology, with a public GeoJSON points-of-interest API.

| | |
|---|---|
| Address | https://www.cambridgeairphotos.com/api/v2/pois?limit=250&size=200&bbox={w},{s},{e},{n} |
| Tested on 2026-11-10 | 200 application/json. The record page also returned 200 |
| Format and CRS | GeoJSON, EPSG:4326, with eastings and northings in properties |
| Licence | No open licence. The per-record copyright field read "Subject to confirmation" |
| Attribution | "Cambridge University Collection of Aerial Photography" |
| Reuse class | link_only |
| Suggested mode | live |
| Paging and limits | `limit=250`, which the site's own map used |
| CORS | Wildcard |

```
https://www.cambridgeairphotos.com/api/v2/pois?limit=5&size=200&bbox=-1.87,51.42,-1.84,51.44
```

Properties included id such as RC8knBB223, photoDate, type, eastings, northings and copyright. AIM SOURCE_1 strings cite CUCAP frame ids, so links can be cross-built. The record page pattern is on the deep links page.

## Esri World Imagery and Wayback

World Imagery is a global mosaic, 0.3 to 0.5 m over England. Wayback archives every release since 2014 so older vintages can be chosen. The research judged them among the best cropmark tools.

| | World Imagery | Wayback |
|---|---|---|
| Address | https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x} | https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/{releaseNum}/{z}/{y}/{x} |
| Key needed | No technically. Terms require an ArcGIS account or Esri software | Same |
| Tested on 2026-11-10 | 200 image/jpeg at z17 and z19 over Avebury | 200 image/jpeg for releases 10 and 43291. Config 200 application/json |
| Format and CRS | JPEG 256 px, z0-23, EPSG:3857 | JPEG 256 px, EPSG:3857 |
| Records | Not counted | 198 releases, 2014-02-20 to 2026-10-29 |
| CORS | Wildcard | Wildcard |

Both share one licence, the Esri Master License Agreement. The terms summary, last updated April 21, 2025, said "Use with Esri software and comply with its terms of use. If you do not have Esri software, you must purchase an ArcGIS Online subscription." It prohibited "Systematically harvest basemap tiles", "Redistribute basemap tiles" and "Download, redistribute or self-host any content hosted by Esri". Attribution: "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community". Reuse class link_only. Suggested mode live, only if an ArcGIS Location Platform account is registered, with no proxy or cache. With an account, basemap tiles cost "2M free then $0.15 per 1,000 tiles".

```json
{
  "type": "raster",
  "tiles": ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
  "tileSize": 256,
  "maxzoom": 19,
  "attribution": "Source: Esri, Vantor, Earthstar Geographics, and the GIS User Community"
}
```

For Wayback, use the Wayback address in `tiles` with `tileSize` 256 and the same attribution. A maximum zoom was not recorded.

```
https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/17/43630/64860
https://wayback.maptiles.arcgis.com/arcgis/rest/services/World_Imagery/WMTS/1.0.0/default028mm/MapServer/tile/10/17/43630/64860
```

### Notes

- The tiles loaded with no key. Use from a non-Esri app without an account was outside the stated terms, and Esri could block the referrer. Esri's "Uses Permitted" document gave ArcGIS app users tracing rights for vector data, with public sharing allowed. It did not clearly extend to users of a third-party app, so tracing findings from it was unresolved.
- The tile path takes row before column, so the placeholders read `{z}/{y}/{x}`.
- Wayback needs one source per chosen release. The config at https://s3-us-west-2.amazonaws.com/config.maptiles.arcgis.com/waybackconfig.json mapped releaseNum to itemTitle, itemURL and metadataLayerUrl. Release numbers were not in date order, so sort by the date in itemTitle.
- A separate Esri metadata service gave the capture date at a point. It returned 200 application/json with a wildcard CORS header, under Esri terms and reuse class link_only. Fields: SRC_DATE2, SRC_DATE, NICE_DESC, SRC_DESC, SRC_RES, SRC_ACC and NICE_NAME. At Avebury the 2014-02 and 2016-06 releases showed 2011-09-28 and 2024-06 onward showed 2023-06-04. Tested request:

```
https://metadata.maptiles.arcgis.com/arcgis/rest/services/World_Imagery_Metadata_2026_r10/MapServer/identify?f=json&geometry=-1.8542,51.4286&geometryType=esriGeometryPoint&sr=4326&tolerance=1&mapExtent=-1.86,51.42,-1.85,51.43&imageDisplay=400,400,96&layers=all&returnGeometry=false
```

## Soilscapes

A 1:250,000 simplified soil map of England and Wales with 27 classes, served by Cranfield University through the UK Soil Observatory.

| | |
|---|---|
| Address | Tiles https://www.landis.org.uk/arcgis/rest/services/UKSoilObservatory/Soilscapes_Cranfield/MapServer/tile/{z}/{y}/{x}. WMS https://www.landis.org.uk/arcgis/services/UKSoilObservatory/Soilscapes_Cranfield/MapServer/WmsServer, layer 0 |
| Tested on 2026-11-10 | Tile 200 image/png at z12 and z14. WMS GetMap 200 image/png. Identify 200 JSON |
| Format and CRS | PNG 256 px, cache levels 0-19, EPSG:3857 |
| Licence | Unclear for this endpoint. Service copyrightText: "Copyright © Cranfield University, 2018". landis.org.uk said Soilscapes "is now available for free via the LandIS Portal", whose EULA, dated 1 March 2026, let Public Data be copied, adapted and exploited "commercially and non-commercially". Whether Soilscapes was Public Data was not confirmed |
| Attribution | "Data originated from the Cranfield University, Land Information System LandIS® Portal [source data file name or report including publication date] as Public Data [year of data access], subject to the Open Licence", if Soilscapes is Public Data |
| Reuse class | link_only, provisional until confirmed |
| Suggested mode | live |
| CORS | Origin reflected |

```json
{
  "type": "raster",
  "tiles": ["https://www.landis.org.uk/arcgis/rest/services/UKSoilObservatory/Soilscapes_Cranfield/MapServer/tile/{z}/{y}/{x}"],
  "tileSize": 256,
  "maxzoom": 14,
  "attribution": "Copyright © Cranfield University, 2018"
}
```

```
https://www.landis.org.uk/arcgis/rest/services/UKSoilObservatory/Soilscapes_Cranfield/MapServer/identify?f=json&geometry=-1.8542,51.4286&geometryType=esriGeometryPoint&sr=4326&tolerance=1&mapExtent=-1.86,51.42,-1.85,51.43&imageDisplay=400,400,96&layers=all&returnGeometry=false
```

Identify at Avebury returned SOILSCAPE "Shallow lime-rich soils over chalk or limestone". Cranfield and Defra opened the LandIS portal on 28 April 2026. Its Open Licence is not the OGL and is accepted by click-through.

## EOX Sentinel-2 cloudless and OSM overlay

Annual global cloud-free Sentinel-2 mosaics at 10 m. At that scale they resolve field patterns only, not cropmarks or earthworks, so they serve as a small-scale backdrop.

| | 2016 and 2017 | 2018 onward |
|---|---|---|
| Address | https://tiles.maps.eox.at/wmts/1.0.0/{layer}/default/g/{z}/{y}/{x}.jpg, layer `s2cloudless_3857` for 2016 and `s2cloudless-2017_3857` for 2017 | Same pattern, layers `s2cloudless-2018_3857` to `s2cloudless-2025_3857` |
| Key needed | No | No |
| Tested on 2026-11-10 | 200 image/jpeg for the 2016, 2020, 2024 and 2025 layers. Capabilities 200 application/xml | Covered by the same tests |
| Format and CRS | JPEG 256 px, EPSG:3857, also WGS84 layers | Same |
| Licence | Creative Commons Attribution 4.0 International | Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International. "For commercial usage please see" EOX |
| Attribution | "Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016)" | The 2018 onward wording was not recorded |
| Reuse class | open | non_commercial |
| Suggested mode | live | live |
| CORS | Origin reflected | Same |

```json
{
  "type": "raster",
  "tiles": ["https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/{z}/{y}/{x}.jpg"],
  "tileSize": 256,
  "maxzoom": 14,
  "attribution": "Sentinel-2 cloudless - https://s2maps.eu by EOX IT Services GmbH (Contains modified Copernicus Sentinel data 2016)"
}
```

```
https://tiles.maps.eox.at/wmts/1.0.0/s2cloudless_3857/default/g/14/5453/8107.jpg
```

EOX also served a transparent OSM overlay, https://tiles.maps.eox.at/wmts/1.0.0/overlay_3857/default/g/{z}/{y}/{x}.png and `overlay_bright_3857`, which returned 200 image/png RGBA at 256 px. Its capabilities said "Proper attribution is required for any usage." The attribution is "Overlay { Data © OpenStreetMap contributors, Rendering © EOX and MapServer }", the reuse class is share_alike, the mode is live as a fallback only, and CORS was Origin reflected. The tile was sparse at z14 with no footpaths, so the research judged the vector overlay far better. The tested request was https://tiles.maps.eox.at/wmts/1.0.0/overlay_3857/default/g/14/5453/8107.png.

The research advised using only the 2016 and 2017 layers if the app might be commercial. Decision 0004 proposes that Field Club is non-commercial, which would admit the later layers, though they also carry share-alike terms.

## OS Maps API OpenData styles

OS-hosted raster basemap tiles, Outdoor, Road and Light, with open data at z7 to z16 in Web Mercator.

| | |
|---|---|
| Address | https://api.os.uk/maps/raster/v1/zxy/{Outdoor_3857, Road_3857 or Light_3857}/{z}/{x}/{y}.png?key=KEY |
| Key needed | Yes |
| Tested on 2026-11-10 | 401 text/xml. No key was used, by instruction. CORS could not be observed |
| Format and CRS | PNG 256 px. EPSG:3857 and EPSG:27700 |
| Licence | OS OpenData plan: "free and unlimited usage" for open data zoom levels, z7 to z16 in 3857. z17 to z20 are premium, using MasterMap |
| Attribution | "Contains OS data © Crown copyright and database right 2026" |
| Reuse class | open |
| Suggested mode | live, with a key |
| Paging and limits | 600 transactions per minute per API per project live. 50 in development. HTTP 429 when exceeded |

```json
{
  "type": "raster",
  "tiles": ["https://api.os.uk/maps/raster/v1/zxy/Outdoor_3857/{z}/{x}/{y}.png?key=KEY"],
  "tileSize": 256,
  "minzoom": 7,
  "maxzoom": 16,
  "attribution": "Contains OS data © Crown copyright and database right 2026"
}
```

```
https://api.os.uk/maps/raster/v1/zxy/Outdoor_3857/14/8107/5453.png
```

The key shows in the browser, so it needs a referrer restriction or a proxy. Capping maxzoom at 16 avoids premium charges.

## NLS Combined VAT and terrarium tiles

Two NLS tilesets NLS did not list as offered for reuse. Combined VAT is a greyscale Combined Visualization for Archaeological Topography, rendered with `rvt_py` from the Environment Agency 1 m DTM in 5 km tiles with a 50 m buffer. The terrarium set holds Terrarium-encoded DTM tiles behind the NLS "Live computed LiDAR / SLRM" layer.

| | Combined VAT, England | Terrarium, England and Wales |
|---|---|---|
| Address | https://mapseries-tilesets.s3.amazonaws.com/CVAT/{z}/{x}/{y}.png | https://mapseries-tilesets.s3.amazonaws.com/slrm_england_wales/{z}/{x}/{y}.png |
| Tested on 2026-11-10 | 200 image/png at z10, z14 and z16. 404 at z17 | 200 image/png at z8, z12, z14, z15 and z16. 404 at z17 |
| Format and CRS | Paletted greyscale PNG, 256 px, z1-16, about 1.5 m per pixel in southern England, EPSG:3857 | PNG RGBA, 512 px, full 1/256 m precision, z4-16, about 0.76 m per pixel at z16 in Dorset, EPSG:3857 |
| Licence | Underlying data OGL. Tileset not offered for reuse | Underlying data OGL, from the Environment Agency and DataMapWales. Tileset not offered for reuse |
| Attribution | Viewer credit: "(c) Environment Agency copyright 2022. With thanks to Richard Pearson for processing using RVT" | Viewer credit: "LiDAR DTM: Environment Agency, DataMapWales, Open Government Licence" |
| Reuse class | open for the data | open for the data |
| Suggested mode | deeplink until NLS agrees | deeplink until NLS agrees |

```
curl -L https://mapseries-tilesets.s3.amazonaws.com/CVAT/16/32318/22028.png
curl -L https://mapseries-tilesets.s3.amazonaws.com/slrm_england_wales/16/32318/22028.png
```

### Notes

No source definition is given until NLS replies. CVAT bounds were -6.5277, 49.8120, 1.8364, 55.9231, and its tiles were last modified 2026-09-21. The viewer titled it "Eng, Wales" but the methodology text described England only. A terrarium definition would be a `raster-dem` source with `encoding` set to `terrarium` and `tileSize` 512, and none was loaded during the research. Decoded elevation at Maiden Castle ran from 73.8 to 132.7 m with all 256 blue values present. Terrarium tiles were last modified 2026-10-26, were about 260 KB at z16 and carried alpha-0 no-data at low zoom. The NLS viewer code for this layer is proprietary and a UX reference only.

## NLS Historic Maps API on MapTiler

Eight continuous NLS layers hosted by MapTiler, including the coloured 1:25,000 1937-61 and the one-inch 7th series.

| | |
|---|---|
| Address | https://api.maptiler.com/tiles/{uk-osgb10k1888, uk-osgb1888, uk-osgb63k1885, uk-osgb25k1937, uk-osgb63k1955, uk-osgb1919, uk-oslondon1k1893 or uk-baire250k1940}/{z}/{x}/{y}.jpg?key=KEY. TileJSON at `.../tiles.json?key=` |
| Key needed | Yes |
| Tested on 2026-11-10 | 403 text/plain without a key: "Missing key - Get your FREE key at https://cloud.maptiler.com/account/keys/". Not tested with a key |
| Format and CRS | JPEG or PNG, EPSG:3857 |
| Licence | NLS API page: "Creative Commons Attribution 3.0 Unported Licence", plus MapTiler Cloud terms |
| Attribution | National Library of Scotland with a link to its website, plus the MapTiler attribution |
| Reuse class | non_commercial |
| Suggested mode | live, with a key, only if the two layers with no free equivalent are needed |
| Paging and limits | "There is a free tier for all non-commercial subscribers using 100,000 tile requests per month or less" |
| CORS | Wildcard |

```json
{
  "type": "raster",
  "tiles": ["https://api.maptiler.com/tiles/uk-osgb25k1937/{z}/{x}/{y}.jpg?key=KEY"],
  "tileSize": 256,
  "attribution": "National Library of Scotland, MapTiler"
}
```

Only `uk-osgb25k1937`, the coloured 1:25,000 1937-61, and `uk-osgb63k1955`, the one-inch 7th series 1955-61, had no free S3 equivalent. `uk-baire250k1940` covered Ireland and `uk-oslondon1k1893` covered London. The NLS viewer embedded NLS's own MapTiler key, which the research said must not be reused. The JSON is composed from the address and has no recorded zoom limits.

## OpenStreetMap standard tiles

Raster tiles of the default OSM Carto style, run by the OpenStreetMap Foundation. The research judged them fine for development or as a low-volume optional layer, and not a production dependency.

| | |
|---|---|
| Address | https://tile.openstreetmap.org/{z}/{x}/{y}.png |
| Tested on 2026-11-10 | 200 image/png |
| Format and CRS | PNG 256 px, z0-19, EPSG:3857 |
| Licence | Data ODbL. Use governed by the OSMF Tile Usage Policy |
| Attribution | "© OpenStreetMap contributors", visible on the map. The policy said "Do not hide attribution beneath UI, behind toggles, or off-screen" |
| Reuse class | share_alike |
| Suggested mode | live, for development only |
| Paging and limits | "Availability is best-effort: there is no SLA or guarantee". "We may block access, without notice". Bulk and offline fetching prohibited. Browsers must send a valid Referer |
| CORS | Wildcard |

```json
{
  "type": "raster",
  "tiles": ["https://tile.openstreetmap.org/{z}/{x}/{y}.png"],
  "tileSize": 256,
  "maxzoom": 19,
  "attribution": "© OpenStreetMap contributors"
}
```

```
https://tile.openstreetmap.org/15/16215/10907.png
```

The tiles are opaque, so they cannot serve as a transparent overlay. The policy advised "Avoid hard-coding the tile URL".

## Deep link only

These sources were not read by script, or must not be fetched or copied. The deep links page gives each pattern with its verification status.

| Source | Publisher | Licence | Reuse | Link pattern |
|---|---|---|---|---|
| NLS Georeferenced Maps viewer | NLS | n/a | link_only | https://maps.nls.uk/geo/explore/#zoom={zoom}&lat={lat}&lon={lon}&layers={mosaic_id}&b=1 |
| NLS Roy Military Survey, 1747-55 | NLS, British Library | "CC-BY (BL)": "This map is owned by the British Library, and their permission must be sought for any reproduction." | link_only | NLS viewer link |
| NLS Sherwood Forest 16 cm LIDAR | NLS, Miner2Major | "(c) 2021 Miner2Major Veiled Landscape Project", no open licence | link_only | NLS viewer link |
| Historic England Aerial Photo Explorer | Historic England | n/a | link_only | https://historicengland.maps.arcgis.com/apps/webappviewer/index.html?id=2626ed0c37484d96b8954dd33187084e&center={lon},{lat}&level={zoom} |
| Britain from Above | Historic England, RCAHMW, HES | Free use "is limited to personal, individual and educational use" | link_only | https://www.britainfromabove.org.uk/en/map?country=global&view=map#{zoom_index},{easting},{northing} |
| NCAP Air Photo Finder | HES | Commercial archive. Terms at https://www.ncap.org/licence-terms | link_only | https://airphotofinder.ncap.org/map?c={northing_3857}:{easting_3857}&z={zoom} |
| Google Earth web | Google | Terms forbid tracing | link_only | https://earth.google.com/web/@{lat},{lon},{alt}a,{distance}d,35y,0h,0t,0r |
| Know Your Place | Bristol City Council and partners | Mixed third-party rights | link_only | https://maps.bristol.gov.uk/kyp/?edition={edition}&layer={layer}&x={easting}&y={northing}&extent={metres} |
| Old Maps Online | Klokan Technologies, MapTiler | n/a | link_only | https://www.oldmapsonline.org/en/#position={zoom}/{lat}/{lon} |
| David Rumsey Map Collection | David Rumsey, Stanford | Not checked | link_only | https://www.davidrumsey.com/ |
| Vision of Britain through Time | University of Portsmouth | Not confirmed | link_only | https://www.visionofbritain.org.uk/ |
| Places of Wales | National Library of Wales | Not checked | link_only | https://places.library.wales/ |

None of these patterns was run in a browser, so each is "not tested" in the sense of the deep links page. Roy tiles at .../roy/highlands/{z}/{x}/{y}.png and .../roy/lowlands/{z}/{x}/{y}.png on the NLS host returned 200 image/png at z13 near Stirling, but need British Library permission before a public app embeds them. Sherwood Forest tiles at .../lidar/sherwood/dtm/{z}/{x}/{y}.png also returned 200 and are not to be embedded. The NLS viewer carries LIDAR SLRM and RVT layers, so it overlaps Field Club's purpose. Britain from Above had a JSON spatial service that returned 18 records in a 2.5 by 2 km box at Avebury, but it is same-origin for its own site. The research advised linking out and not copying images. Old Maps Online returned 403 to scripts, and its pattern was from memory.

## Layers to avoid

| Source | Publisher | Reason |
|---|---|---|
| OS Maps API Leisure, 1:50k and 1:25k | Ordnance Survey | Needs a key and exists only in EPSG:27700, which MapLibre cannot add as a native source. Re-tiling would cache premium data, which the API terms probably forbid. z0-5 open, z6-9 premium. Mode: none |
| Google Map Tiles API | Google | Not tested, as it needs a key and billing. Terms: "don't trace or digitize features from satellite imagery" and "you must not pre-fetch, index, store, or cache any Content". That conflicts with marking findings from what users see. Link to Google Earth instead |
| Bing Maps imagery | Microsoft | The discontinued-APIs page redirected with 301 to Azure Maps, which needs a subscription key. rowmaps.com: "Microsoft withdrew free use of their Bing Maps API in July 2025." |
| Mapbox Satellite | Mapbox | Not tested. Needs a token. Tracing terms were not retrievable. A paid dependency with nothing over Esri for cropmarks |
| Aerial Photography for Great Britain | APGB | Not open. Data "is available to APGB members through a web delivery portal". It would be the best cropmark source but is not available to a public project |
| DataMapWales LiDAR tiles | Welsh Government, NRW | https://datamapwales.azureedge.net/imagery/lidar/dtm1m/{z}/{x}/{y}.png returned 200 image/png with no CORS header, so MapLibre cannot load it from another origin without a proxy. OGL v3.0 as credited by NLS, not checked on the publisher's page |

## Cross-cutting notes

- **Tracing.** Google forbids tracing outright, and Esri's grant is unclear for third-party apps. The research suggested a layer registry with licence, attribution text and a `tracing_allowed` flag, and recording which layers were visible when a finding was drawn. It also suggested building the attribution control from that registry. OSM policy requires attribution to be visible, not behind a toggle.
- **Proxying.** The research suggested a small proxy only where the licence permits caching: NLS, BGS and OSM-derived tiles. It would turn 404s into transparent tiles. It advised against proxying or caching Esri or Google tiles.
- **Datum.** EA LIDAR and most English datasets use EPSG:27700, while OSM, NLS tiles and imagery use Web Mercator. The research said that reprojecting without the OSTN15 grid falls back to a Helmert transform with errors of several metres. It was not measured. Suggested use: install the OSTN15 grid in the PostGIS and GDAL images.

## Open questions

- Will NLS confirm in writing that a public app may hot-link the `mapseries-tilesets` layers, including the 25-inch county sets, CVAT and terrarium, or would it prefer a mirror in Cloud Storage? Does British Library permission for Roy extend to NLS's tiles in a third-party app?
- Should an ArcGIS Location Platform account be registered, and do Esri's terms then let users trace findings from World Imagery and Wayback?
- Is Soilscapes Public Data under the LandIS Portal Open Licence, and is there a downloadable version on portal.landis.org.uk?
- Does the OS Open Zoomstack MBTiles use a Web Mercator grid? It was believed so and not read from the file's metadata table.
- Which licence applies to each Scottish LIDAR phase tileset? How much of the likely user area has EA vertical photography?
- Which Welsh and Scottish equivalents are needed for access land, rights of way and imagery? The completeness review found no historic map layer for Northern Ireland, and noted that OpenDataNI listed 12 OGL datasets of the Historical Six Inch to One Mile County Series, unassessed. The Historic England National Mapping Programme raster tiles are in the England heritage report, not here.
- Is the OpenFreeMap or the Protomaps schema the better long-term base for the overlay style, given that Field Club may switch between hosted and self-hosted sources?
