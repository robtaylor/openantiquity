# Thematic, gazetteer and vocabulary sources

This page covers the community and thematic datasets, OpenStreetMap heritage tags, place-name gazetteers, geocoders, georeferenced photographs, grid-reference libraries and the controlled vocabularies that a research pass tested on 2026-11-10. Open Antiquity was not built when this was written,. Every observation below is about someone else's service on that date, in the past tense. Open and usable in bulk were the Atlas of Hillforts, GB1900, OS Open Names, Itiner-e, Pleiades, XRONOS, the Geograph index, Wikidata and the FISH thesauri. OpenStreetMap was open, but Decision 0007 keeps it out of the index. Not open were Beresford's Lost Villages, Open Domesday and Gatehouse, which are non-commercial only, and the ADS thematic archives, the Megalithic Portal, NMRS, KEPN and Vision of Britain, which are links at best.

Reuse classes and access modes follow [Decision 0004](../architecture/decisions/0004-field-club-is-non-commercial.md) and [Decision 0007](../architecture/decisions/0007-the-record-index-stores-only-what-licences-allow.md). A source licensed for non-commercial use counts as usable. A publisher that blocks scripts or forbids harvesting is a deep link whatever its licence. Anything untested is marked "not tested".

## Summary

| Source | Publisher | Coverage | Licence | Reuse | Mode | Records |
|---|---|---|---|---|---|---|
| [Atlas of Hillforts](#atlas-of-hillforts-of-britain-and-ireland) | Oxford and Edinburgh | UK, IoM, Ireland | CC BY-SA 4.0 | share_alike | bulk | 4,147 points |
| [GB1900 gazetteer](#gb1900-gazetteer) | Portsmouth and partners | Great Britain | CC BY-SA 4.0 | share_alike | bulk | 2,552,459 labels |
| [OS Open Names](#os-open-names) | Ordnance Survey | Great Britain | Open Government Licence | open | bulk | 3,050,396 rows |
| [OpenStreetMap, Geofabrik extract](#openstreetmap-geofabrik-extract) | Geofabrik GmbH | UK | ODbL 1.0 | share_alike | live | 104,564 objects |
| [OpenStreetMap, public Overpass](#openstreetmap-public-overpass) | OSM / FOSSGIS | UK, worldwide | ODbL 1.0 | share_alike | live | as above |
| [taginfo, Great Britain](#taginfo-great-britain) | Geofabrik | Great Britain | statistics from ODbL data | share_alike | live | 101,390 objects |
| [Itiner-e nightly export](#itiner-e-nightly-export) | Aarhus and UAB | Roman Empire | CC BY 4.0 | open | bulk | 17,184 segments |
| [Itiner-e static version 2024](#itiner-e-static-version-2024) | Zenodo | Roman Empire | CC BY 4.0 | open | bulk | same dataset, frozen |
| [Pleiades GIS CSV](#pleiades-gis-csv-bundle) | ISAW (NYU) | Ancient world | CC BY 3.0 | open | bulk | 42,422 places |
| [Pleiades place JSON](#pleiades-place-json) | ISAW (NYU) | Ancient world | CC BY 3.0 | open | live | one place per call |
| [DARE](#digital-atlas-of-the-roman-empire-dare) | Johan Åhlfeldt | Roman Empire | not stated | link_only | deeplink | 24 in a Britain bbox |
| [DARMC Roman roads](#darmc-roman-road-network) | Harvard University | Roman Empire | none set | link_only | deeplink | not counted |
| [Beresford's Lost Villages](#beresfords-lost-villages) | University of Hull | England | CC BY-NC-SA 4.0 | non_commercial | bulk | 2,222 points |
| [Gatehouse Gazetteer](#gatehouse-gazetteer) | Philip Davis | England, Wales, Islands | non-commercial only | non_commercial | deeplink | 5,113 England records |
| [Open Domesday JSON API](#open-domesday-json-api) | Anna Powell-Smith | England | CC BY-NC-SA data | non_commercial | deeplink | endpoint gone |
| [XRONOS](#xronos-radiocarbon-database) | University of Bern | Worldwide | CC BY 4.0 | open | bulk | 23,190 GB dates |
| [p3k14c](#p3k14c-radiocarbon-database) | PEOPLE 3000 | Worldwide | data licence not stated | link_only | deeplink | not counted |
| [BGS mine plans catalogue](#bgs-mine-plans-catalogue) | BGS | UK | BGS terms, OGL unconfirmed | link_only | deeplink | 131,768 records |
| [Coal mine entries](#coal-mine-entries) | Mining Remediation Authority | GB coalfields | Open Government Licence | open | live | tile layer |
| [Wikidata](#wikidata-query-service) | Wikimedia Foundation | Worldwide | CC0 1.0 | open | bulk | 7,880 UK sites |
| [OSNI gazetteer and NI historic settlements](#osni-gazetteer-and-historic-settlements) | OSNI / DfC NI | Northern Ireland | Open Government Licence | open | bulk | 336 names, 672 settlements |
| [Nominatim, public](#nominatim-public-instance) | OSMF | Worldwide | ODbL 1.0 | share_alike | live | n/a |
| [Photon, public](#photon-public-instance) | komoot | Worldwide | ODbL 1.0 | share_alike | live | n/a |
| [Photon British Islands dump](#photon-british-islands-dump) | GraphHopper / komoot | GB, IM, GG, JE | ODbL 1.0 | share_alike | bulk | 1.03 GB dump |
| [OS Names API](#os-names-api) | Ordnance Survey | Great Britain | OS Data Hub terms | link_only | deeplink | not used |
| [postcodes.io](#postcodesio) | Ideal Postcodes | UK | MIT, OS and ONS data | open | live | n/a |
| [Geograph API](#geograph-api) | Geograph Project | Great Britain and Ireland | CC BY-SA 2.0 per image | share_alike | live | over 11,000 near Avebury |
| [Geograph dumps](#geograph-database-dumps) | Geograph Project | Great Britain and Ireland | CC BY-SA 2.0 | share_alike | bulk | over 7 million images |
| [Wikimedia Commons geosearch](#wikimedia-commons-geosearch) | Wikimedia Foundation | Worldwide | per file | share_alike | live | per query |
| [FISH thesauri on heritagedata.org](#heritagedataorg-skos-linked-data) | FISH, HES, RCAHMW | UK | OGL v3 or CC BY 3.0 | open | bulk | 57 schemes |
| [SENESCHAL web services](#heritagedataorg-seneschal-web-services) | FISH / University of South Wales | UK | as per scheme | open | live | n/a |
| [heritagedata.org SPARQL](#heritagedataorg-sparql-endpoint) | FISH / University of South Wales | UK | as per scheme | open | live | n/a |
| [FISH bulk downloads](#fish-terminologies-bulk-downloads) | FISH | England-led, UK-wide use | free to use, OGL v3 | open | bulk | Monument Types version 29 |

## Atlas of Hillforts of Britain and Ireland

A point record for every confirmed or possible hillfort, with morphology, dating, HER, NMR and scheduling identifiers and four related tables.

| Row | Value |
|---|---|
| Access | ArcGIS FeatureServer, no key |
| Address | `https://services1.arcgis.com/PTDJItLzolyiewT6/arcgis/rest/services/Atlas_of_Hillforts/FeatureServer/0` |
| Tested on 2026-11-10 | HTTP 200. One-record GeoJSON request returned EN0001 Aconbury Camp, Herefordshire. Size and time not recorded. |
| Format and CRS | JSON, GeoJSON, PBF. Native EPSG:3857, with X/Y national grid, NGR and Longitude/Latitude fields. |
| Licence | CC BY-SA 4.0 |
| Attribution | "Lock, Gary and Ralston, Ian. 2024. Atlas of Hillforts of Britain and Ireland. Available at: https://hillforts.arch.ox.ac.uk" |
| Reuse class | share_alike |
| Suggested mode | bulk |
| Records | 4,147 hillforts: Scotland 1,695, England 1,225, Wales 690, Republic of Ireland 475, Northern Ireland 32, Isle of Man 30. That is 3,642 in the UK. Tables: Investigations 17,322, References 10,236, Entrances 4,656, Dating Evidence 1,064. |
| Positional precision | Points. The research recorded no accuracy figure. |
| Paging and limits | maxRecordCount 2,000, pagination supported |
| CORS | yes, `*` |

```
https://services1.arcgis.com/PTDJItLzolyiewT6/arcgis/rest/services/Atlas_of_Hillforts/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=1&outSR=4326&f=geojson
```

Notes:

- 253 fields, including Atlas_Number, HER_Primary_Record_Number, NMR_Monument_Number, Scheduled_Monument_Number and Dating_Evidence__*.
- The data is a snapshot from 2012 to October 2016, so it will disagree with current HER records.
- The service sits on a university ArcGIS Online account, found through hillforts.arch.ox.ac.uk. The site had already moved once.
- The HER, NMR and scheduling numbers allow links to official records without spatial matching.

Suggested use: snapshot the service, and keep the layer in its own table with the licence on each row.

## GB1900 gazetteer

Every text label on the Ordnance Survey six-inch County Series maps of about 1900, transcribed by volunteers, with coordinates.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://www.visionofbritain.org.uk/downloads/GB1900_gazetteer_complete_july_2018.zip` |
| Tested on 2026-11-10 | HTTP 200 application/zip, 146 MB. The first attempt dropped the connection and the retry succeeded. Time not recorded. |
| Format and CRS | ZIP containing a 703 MB UTF-16 CSV. EPSG:27700 and WGS84 columns. |
| Licence | CC BY-SA 4.0 for the complete and abridged files. The raw dump is CC0 1.0. |
| Attribution | Acknowledge "the Great Britain Historical GIS Project at the University of Portsmouth, the GB1900 partners and volunteers". Derived works must not be named "GB1900". |
| Reuse class | share_alike |
| Suggested mode | bulk |
| Records | 2,552,459 rows, 692,647 distinct strings. The abridged file had 1,174,449 rows. |
| Positional precision | Point at the label position, not at the feature. |

```
curl -L -o complete.zip https://www.visionofbritain.org.uk/downloads/GB1900_gazetteer_complete_july_2018.zip
```

Notes:

- Fields: pin_id, final_text, nation, parish, osgb_east, osgb_north, latitude, longitude.
- The file covers Great Britain and not Northern Ireland. It stops at July 2018.
- The abridged file removes every string that occurs 300 or more times, with a short list of exceptions. That removes the generic antiquity labels, so the complete file is the one to use. The abridged file is at `https://www.visionofbritain.org.uk/downloads/GB1900_gazetteer_abridged_july_2018.zip` and was 72.7 MB.
- Exact-label counts in the complete file:

Old Quarry 24,673; Stone 13,625; Old Shaft 6,436; Tumulus 3,674; Moat 3,351; Tumuli 1,606; Cairn 1,459; Old Level 1,368; Old Limekiln 1,245; Camp 867; Mound 814; Fort 626; Standing Stone 497; Intrenchment 261; Hut Circles 246.

About 35,773 rows matched an antiquity keyword pattern.

Suggested use: a "what the 1900 six-inch map labelled here" layer built from the antiquity rows, which lines up directly with LIDAR. It doubles as a name source for the search box.

## OS Open Names

Ordnance Survey's open gazetteer of settlements, roads, postcodes and named natural features.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://api.os.uk/downloads/v1/products/OpenNames/downloads?area=GB&format=CSV&redirect` |
| Tested on 2026-11-10 | HTTP 200. Version 2026-10. CSV zip 103 MB. Time not recorded. |
| Format and CRS | CSV zip 103 MB, about 820 files. GeoPackage zip 210 MB. GML. EPSG:27700. |
| Licence | Open Government Licence (OS OpenData licence) |
| Attribution | "Contains OS data © Crown Copyright and database rights 2026. Contains Royal Mail data © Royal Mail copyright and database right 2026. Contains National Statistics data © Crown copyright and database right 2026." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 3,050,396 rows: Postcode 1,743,934, Named Road 884,116, landcover 121,153, landform 76,443, populatedPlace 43,274, hydrography 26,874. |

```
https://api.os.uk/downloads/v1/products/OpenNames/downloads
```

Notes:

- The download needed no API key. The hosted API for the same data does, see [OS Names API](#os-names-api).
- 34 columns, including NAME1, NAME2 (Welsh or Gaelic), TYPE, LOCAL_TYPE, GEOMETRY_X, GEOMETRY_Y and COUNTY_UNITARY.
- Great Britain only. Northern Ireland is the gap, see [OSNI gazetteer](#osni-gazetteer-and-historic-settlements).

Suggested use: the base of a self-hosted gazetteer for the search box, joined with GB1900 and OSM names.

## OpenStreetMap Geofabrik extract

Daily OSM PBF extracts for the UK and its nations.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf` |
| Tested on 2026-11-10 | HEAD only: HTTP 200 via a 307 redirect. Last-modified 9 to 10 November 2026. Files were not downloaded. |
| Format and CRS | OSM PBF, EPSG:4326 |
| Licence | ODbL 1.0 |
| Attribution | "© OpenStreetMap contributors". |
| Reuse class | share_alike |
| Suggested mode | live, as an overlay that is not indexed, following Decision 0007. The research suggested bulk. See Open questions |
| Records | Extract sizes: united-kingdom 2.28 GB, great-britain 2.20 GB, england 1.71 GB, scotland 330 MB, wales 151 MB, ireland-and-northern-ireland 418 MB. |
| Positional precision | Point, line and polygon geometry. No accuracy figure recorded. |

```
curl -sIL https://download.geofabrik.de/europe/united-kingdom-latest.osm.pbf
```

Notes:

- Counts from the public Overpass service for the whole UK, area 3600062149:

historic=* 104,564 (52,226 nodes, 50,890 ways, 1,448 relations); historic=ruins 26,835; historic=archaeological_site 15,757; historic=castle 1,349; archaeological_site=fortification 2,729; archaeological_site=tumulus 2,200; archaeological_site=megalith 1,267; fortification_type=hill_fort 391; site_type key 45; historic=tumulus 0.

- Overpass counts the UK and [taginfo](#taginfo-great-britain) counts Great Britain, so their totals differ.
- OSM held 391 hill forts UK-wide against 3,642 UK entries in the Atlas of Hillforts, about 11%. The research called OSM a crosswalk and not a complete inventory. In Great Britain, 214,317 objects carried a wikidata tag, 11,410 carried HE_ref and 4,160 carried ref:GB:nhle.
- Overpass queries for roman_road, mine_shaft, bunker and pillbox did not complete (502). See taginfo for those counts.
- Under the OSMF Collective Database Guideline, mixing OSM and non-OSM records of the same feature type in one table moves towards a Derivative Database, which must be offered under ODbL if used publicly. That was the research's reading and not legal advice.

Why an extract beats Overpass: the public service rejected generic User-Agents, failed on 10 of 23 attempts and took 27 to 137 seconds for a UK-wide count. A dated PBF file has none of those problems.

Suggested use: Decision 0007 says OSM is drawn as an overlay and isn't indexed. The research suggested filtering the extract with `osmium tags-filter` for historic=*, archaeological_site=*, military=bunker and man_made=adit, then loading it with osm2pgsql into its own schema. Both routes start from the extract. Keep OSM features out of tables of other sources' records.

## OpenStreetMap public Overpass

Live queries over OSM historic=*, archaeological_site=* and related tags. The research recommended avoiding it on any production path.

| Row | Value |
|---|---|
| Access | REST, Overpass QL, no key |
| Address | `https://overpass-api.de/api/interpreter` |
| Tested on 2026-11-10 | HTTP 200 with a descriptive User-Agent. HTTP 406 with `Mozilla/5.0 (research)` and with curl's default. HTTP 502 or 504 "at capacity" on 10 of 23 attempts. UK-wide count queries took 27 to 137 s. A three-feature bbox query took 38 s. |
| Format and CRS | JSON, CSV, XML. EPSG:4326. |
| Licence | ODbL 1.0 |
| Attribution | "© OpenStreetMap contributors, linked to https://www.openstreetmap.org/copyright" |
| Reuse class | share_alike |
| Suggested mode | live, for development queries only |
| Records | See the Geofabrik entry for counts. |
| Paging and limits | 2 slots per IP at the status endpoint. |
| CORS | yes, `*` |

```
curl -A 'landscape-research-tool/0.1' --data-urlencode 'data=[out:json][timeout:25];nwr["historic"="archaeological_site"](51.40,-1.90,51.45,-1.80);out tags center 3;' https://overpass-api.de/api/interpreter
```

Notes:

- The sample returned West Kennet Long Barrow, node 370206805.
- A group-by query over all UK historic values failed on overpass-api.de, overpass.private.coffee and maps.mail.ru.
- The server text says the public endpoint is for "browser-based and human-operated tools".

## taginfo Great Britain

Per-tag usage counts for the Great Britain extract, useful for planning tag filters.

| Row | Value |
|---|---|
| Access | REST JSON, no key |
| Address | `https://taginfo.geofabrik.de/europe:great-britain/api/4/key/values?key=historic&sortname=count&sortorder=desc` |
| Tested on 2026-11-10 | HTTP 200 application/json. Data until 2026-11-09. |
| Format and CRS | JSON, no geometry |
| Licence | Statistics derived from OSM, ODbL 1.0 |
| Attribution | Not recorded. Use "© OpenStreetMap contributors". |
| Reuse class | share_alike |
| Suggested mode | live |
| Records | historic key: 101,390 objects, 804 distinct values |
| CORS | yes, `*` |

```
https://taginfo.geofabrik.de/europe:great-britain/api/4/tag/stats?key=bunker_type&value=pillbox
```

Notes: Northern Ireland sits in the europe:ireland-and-northern-ireland extract. The counts for Great Britain were:

- historic: ruins 26,489; memorial 19,783; archaeological_site 14,413; mine_shaft 9,235; monument 2,941; roman_road 2,257; castle 1,251; crop_mark 903.
- archaeological_site: tumulus 2,194; mineral_extraction 2,117; fortification 2,076; megalith 1,183; settlement 528; hut_circle 474; crannog 303; broch 301.
- fortification_type: dun 630; hill_fort 384; broch 239; motte 181.
- megalith_type: menhir 416; stone_circle 370; long_barrow 67.
- bunker_type: pillbox 1,953.
- water: moat 231.

The site_type key was effectively dead at 45 uses. archaeological_site=* is the live sub-key, at 10,716 uses.

## Itiner-e nightly export

An open digital atlas of Roman roads. Each line is a GeoJSON LineString segment with certainty, dates, bibliography and nearby Pleiades places.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://itiner-e.org/route-segments/download` |
| Tested on 2026-11-10 | HTTP 200 application/octet-stream, 57.8 MB. Time not recorded. |
| Format and CRS | NDJSON of GeoJSON features, EPSG:4326 |
| Licence | CC BY 4.0 |
| Attribution | "Itiner-e: the digital atlas of ancient roads © 2024 by Brughmans, Pažout, de Soto and Bjerregaard Vahlstrup is licensed under CC BY 4.0" |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 17,184 segments. About 1,465 fell in a Britain bounding box, about 18,260 km: Secondary Road 829, Main Road 598, Sea Lane 32, River 6. |
| Positional precision | Mostly conjectured alignment, not survey grade. |
| CORS | no access-control header |

```
curl -L -A 'Mozilla/5.0 (research)' -o export.ndjson https://itiner-e.org/route-segments/download
```

Notes:

- Properties include name, type, lowerDate, upperDate, segmentCertainty and bibliography.
- Across the export, segmentCertainty was Conjectured 15,112, Certain 1,082 and Hypothetical 990. In the Britain bounding box it was Conjectured 1,136 and Hypothetical 329, with no Certain segments at all. Lines will often sit off the agger visible in LIDAR.

Suggested use: draw segments styled by segmentCertainty so that a conjectured line isn't read as a surveyed one. Prefer this nightly file for ingest and cite the Zenodo DOI. The research gave Itiner-e as superseding DARMC, which has no clear licence.

## Itiner-e static version 2024

A citable frozen copy of the Itiner-e dataset, described in Scientific Data in 2025.

| Row | Value |
|---|---|
| Access | Bulk download from Zenodo, no key |
| Address | `https://zenodo.org/records/17122148` |
| Tested on 2026-11-10 | HTTP 200 for the Zenodo API metadata. Files were not downloaded. |
| Format and CRS | GeoPackage 33.6 MB, GeoJSON 78 MB, Shapefile 138 MB |
| Licence | CC BY 4.0 |
| Attribution | "de Soto, P. et al. (2025) A High-Resolution Dataset of Roads of the Roman Empire: Itiner-e static version 2024. Zenodo. https://doi.org/10.5281/zenodo.17122148" |
| Reuse class | open |
| Suggested mode | bulk, as a citation copy |

```
https://zenodo.org/api/records/17122148
```

Notes: metadata and file list only were checked. The research marked it reference-only and preferred the nightly export for ingest.

## Pleiades GIS CSV bundle

A gazetteer of ancient places with representative points, names, place types and precision flags.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://atlantides.org/downloads/pleiades/gis/pleiades_gis_data.zip` |
| Tested on 2026-11-10 | HTTP 200 application/zip, 35.7 MB. Time not recorded. |
| Format and CRS | ZIP of CSV, EPSG:4326. Location points, lines and polygons as WKT. |
| Licence | CC BY 3.0 |
| Attribution | "Copyright © The Contributors. Sharing and remixing permitted under terms of the Creative Commons Attribution 3.0 License (cc-by)." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 42,422 places. About 1,445 fell in a crude British Isles bounding box: 1,390 "precise" and 55 "rough". |
| Positional precision | Representative point, with a location_precision flag. |

```
curl -L -o pleiades_gis_data.zip https://atlantides.org/downloads/pleiades/gis/pleiades_gis_data.zip
```

Notes:

- places.csv fields include title, uri, id, representative_latitude, representative_longitude, bounding_box_wkt and location_precision.
- Itiner-e segments embed nearby Pleiades place IDs, which gives a cross-reference without spatial matching.

Suggested use: flag location_precision=rough on the map so a centroid isn't read as a site position.

## Pleiades place JSON

The full JSON record for one Pleiades place.

| Row | Value |
|---|---|
| Access | REST JSON, no key |
| Address | `https://pleiades.stoa.org/places/{id}/json` |
| Tested on 2026-11-10 | HTTP 200. Londinium/Augusta returned reprPoint [-0.088949, 51.513335]. |
| Format and CRS | JSON, point |
| Licence | CC BY 3.0 |
| Attribution | "Copyright © The Creators. Sharing and remixing permitted under terms of the Creative Commons Attribution 3.0 License (cc-by)." |
| Reuse class | open |
| Suggested mode | live |
| Records | One place per call. |
| CORS | yes, `*` |

```
https://pleiades.stoa.org/places/79574/json
```

Notes: the bulk CSV suits a list of British places. This endpoint suits a click-through to one place.

## Digital Atlas of the Roman Empire (DARE)

Roman-period places with a rendered Roman Empire basemap.

| Row | Value |
|---|---|
| Access | REST GeoJSON and XYZ tiles, no key |
| Address | `https://imperium.ahlfeldt.se/api/geojson.php?bbox={w},{s},{e},{n}` |
| Tested on 2026-11-10 | HTTP 200. A tile at `https://dh.gu.se/tiles/imperium/{z}/{x}/{y}.png` returned a 256 px PNG for 7/63/42. |
| Format and CRS | GeoJSON and PNG tiles, EPSG:4326 |
| Licence | "Not stated on any page I could fetch". The 2017 GitHub snapshot (johaahlf/dare) is Apache-2.0. |
| Reuse class | link_only, until a licence is found |
| Suggested mode | deeplink |
| Records | A whole-Britain bbox returned only 24 features: 20 cities and 4 fortresses. |
| Positional precision | Point, with a precision field in metres. |
| CORS | yes, `*` |

```
https://imperium.ahlfeldt.se/api/geojson.php?bbox=-0.3,51.4,0.1,51.6
```

Notes:

- The sample returned London / Londinium, id 1888.
- The old host dare.ht.lu.se no longer connected. The GitHub snapshot has places2.geojson (8.3 MB) and roads_low.geojson (4.1 MB).
- No licence for the API or the tiles was found. This is an open question below.

## DARMC Roman Road Network

A Barrington Atlas-derived Roman road shapefile from Harvard's DARMC. The research recorded it as a source to avoid.

| Row | Value |
|---|---|
| Access | Dataverse download, no key |
| Address | `https://dataverse.harvard.edu/dataset.xhtml?persistentId=doi:10.7910/DVN/TI0KAU` |
| Tested on 2026-11-10 | HTTP 200 through the Dataverse API. darmc.harvard.edu returned 403. |
| Format and CRS | Shapefile, 1.5 MB. CRS not recorded. |
| Licence | None set. The Dataverse terms read: "This dataset is made available with limited information on how it can be used." |
| Reuse class | link_only |
| Suggested mode | deeplink. Avoid |
| Records | Not counted. Version 2008, small-scale lines. |
| Positional precision | Small scale, so coarser than Itiner-e. |

```
https://dataverse.harvard.edu/api/datasets/:persistentId/?persistentId=doi:10.7910/DVN/TI0KAU
```

Notes: Itiner-e supersedes it and has a clear licence.

## Beresford's Lost Villages

Deserted medieval villages from Beresford and Hurst's 1971 list, with tax, Domesday and investigation history. The research called it the only national dataset of deserted medieval villages.

| Row | Value |
|---|---|
| Access | ArcGIS FeatureServer, no key |
| Address | `https://services2.arcgis.com/GTEgXeL0m6EyJsOO/arcgis/rest/services/Lost_Villages/FeatureServer/0` |
| Tested on 2026-11-10 | HTTP 200. One-record GeoJSON request returned Astwick, TL 213385. Size and time not recorded. |
| Format and CRS | JSON, GeoJSON, PBF. Native EPSG:3857, with x_coord and y_coord in OSGB and Latitude/Longitude fields. |
| Licence | CC BY-NC-SA 4.0, stated in the website footer. The ArcGIS item's licence field was empty. |
| Attribution | "(c) 2009-2024 The University of Hull. This work is licensed under a Creative Commons Attribution-NonCommercial-ShareAlike 4.0 International License." |
| Reuse class | non_commercial |
| Suggested mode | bulk, as a separate layer |
| Positional precision | Grid references mostly 6-figure, so about 100 m. |
| CORS | yes, `*` |

```
https://services2.arcgis.com/GTEgXeL0m6EyJsOO/arcgis/rest/services/Lost_Villages/FeatureServer/0/query?where=1%3D1&outFields=*&resultRecordCount=1&outSR=4326&f=geojson
```

Notes:

- 45 fields, including Site_name, Grid_reference, NMR_no, HER_no, Site_status, Domesday_reference and Site_type.
- NMR_no, HER_no and Site_status, which carries scheduling numbers, link to official records.
- The old dmv.hull.ac.uk site is now WordPress plus an ArcGIS Experience. The service is on a university ArcGIS Online account.
- Under Decision 0004, any later monetisation would first require removing this layer.

## Gatehouse Gazetteer

A gazetteer and bibliography of medieval castles, fortified houses and palaces in England, Wales and the Islands.

| Row | Value |
|---|---|
| Access | Bulk download of tab-delimited files, no key |
| Address | `https://www.gatehouse-gazetteer.info/downlf/England.tab.zip` |
| Tested on 2026-11-10 | HTTP 200 application/zip, 7.4 MB. A record page at `https://www.gatehouse-gazetteer.info/English%20sites/3079.html` also returned 200. |
| Format and CRS | Tab-delimited text (UTF-8, CR line endings) and FileMaker Pro. EPSG:27700 and WGS84 columns. |
| Licence | No open licence. "Please feel free to download these for your own, non-commerical use." Commercial use "may breach copyright restrictions". The spelling "non-commerical" is the publisher's. |
| Reuse class | non_commercial |
| Suggested mode | deeplink |
| Records | England 5,113 records with 69 columns. Licences to crenellate: 610. |
| Paging and limits | maxRecordCount 2,000 |
| Positional precision | Point from OS grid reference, easting and northing, lat/lon. |

```
https://www.gatehouse-gazetteer.info/English%20sites/3079.html
```

Notes:

- Last updated 13 July 2017. Columns include grid ref, site type, confidence, PastScape, HER and NHLE numbers. Other files: Wales, Islands and LOC.
- The research recommended a deep link either way unless permission is obtained. The wording invites a personal non-commercial download and is silent on republishing.

## Open Domesday JSON API

A documented REST API for Domesday places, manors and hundreds with WGS84 coordinates. It was gone on 2026-11-10.

| Row | Value |
|---|---|
| Access | REST JSON, documented as keyless |
| Address | `https://opendomesday.org/api/1.0/placesnear?lat=52.5&lng=1.0&radius=10` |
| Tested on 2026-11-10 | HTTP 404 on every documented route: place, placesnear, manor, hundred, area, county and image. Tested over http and https. |
| Format and CRS | none |
| Licence | Underlying data CC BY-NC-SA, per the site's about page |
| Attribution | See the place-pages entry under Deep link only. |
| Reuse class | non_commercial |
| Suggested mode | deeplink. Avoid the API |

```
https://opendomesday.org/api/1.0/place/20086
```

Notes: that request returned 404 text/html. The `/api/` documentation page still loaded with 200 and said no key was needed, but the endpoints were gone. The API vanished without its documentation changing.

## XRONOS radiocarbon database

An open aggregation of archaeological radiocarbon dates with site coordinates.

| Row | Value |
|---|---|
| Access | REST JSON, no key |
| Address | `https://xronos.ch/api/v1/data?query_country=GB` |
| Tested on 2026-11-10 | HTTP 200 application/json, 35 MB for the GB query. Time not recorded. |
| Format and CRS | JSON, EPSG:4326 |
| Licence | CC BY 4.0 |
| Attribution | XRONOS: "This work is licensed under a Creative Commons Attribution 4.0 International License." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 23,190 measurements. 22,956 had coordinates. 4,940 site names and 4,628 distinct coordinate pairs. |
| Positional precision | Site-level point. 16,939 of 22,956 latitudes had 4 decimal places, about 10 m, though the real precision is whatever the source recorded. |
| CORS | no access-control header |

```
https://xronos.ch/api/v1/data?query_site=Stonehenge
```

Notes:

- Fields include labnr, bp, std, material, site, country, lat, lng and reference.
- Most GB records cite p3k14c (19,386) and Bevan2017 (15,958), so expect duplicate lab numbers across references.
- Country labels were inconsistent. The Stonehenge record carried "England/Wales", so `query_country=GB` may undercount. A bounding-box filter on the full dump is safer.

## p3k14c radiocarbon database

A global archaeological radiocarbon dataset and an upstream source of XRONOS.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://www.p3k14c.org/data/p3k14c_2022.06.csv` |
| Tested on 2026-11-10 | HEAD only: HTTP 200 text/csv, 25.9 MB |
| Format and CRS | CSV, point |
| Licence | The data licence was not stated on the download page. The R package repository is MIT. |
| Reuse class | link_only, until a licence is stated |
| Suggested mode | deeplink |
| Positional precision | Coordinates are obfuscated to county centroids only for the United States, Canada and one named database, not for the UK. |

```
https://www.p3k14c.org/data/p3k14c_2022.06.csv
```

Notes: XRONOS, under CC BY 4.0, is the safer route to the same dates.

## BGS mine plans catalogue

A catalogue of mine plans held by the British Geological Survey, with links to scans where public.

| Row | Value |
|---|---|
| Access | OGC API Features, no key |
| Address | `https://ogcapi.bgs.ac.uk/collections/mine_plans/items?f=json&limit=3` |
| Tested on 2026-11-10 | HTTP 200. The sample returned a Pant-y-Mwyn tunnel, lead, SJ26NW. |
| Format and CRS | GeoJSON, CRS84 |
| Licence | BGS terms of use. Each record points to `https://www.bgs.ac.uk/legal-and-policy/terms-of-use/`. The research did not confirm OGL and did not read that page. |
| Reuse class | link_only until the terms are read |
| Suggested mode | deeplink. Bulk only once the terms are confirmed |
| Records | 131,768. 5,510 had publicly visible scans. |
| Positional precision | None in practice. Every feature had an empty Polygon. Location is an OS quarter-sheet code such as SJ26NW, a 5 km square. |
| Paging and limits | `limit` parameter. No cap recorded. |
| CORS | yes, echoes the request origin |

```
https://ogcapi.bgs.ac.uk/collections/mine_plans/items?f=json&limit=3&has_public_visible_scans_yn=Y
```

Notes:

- bbox filters returned 0 matches over three mining districts, and bbox-crs 27700 was rejected. Plans must be attached to 5 km cells and not drawn as points.
- Fields include plan_title, mine_name, mineral_trans_comma_list, year_abandoned, qs_comma_list and scan_url_comma_list.
- Many records were borehole plans, not mines.

## Coal mine entries

Recorded coal mine shafts and adits, served as a cached tile layer.

| Row | Value |
|---|---|
| Access | WMTS and XYZ tiles, no key |
| Address | `https://services-eu1.arcgis.com/Qn4lKcPDVHNivEyr/arcgis/rest/services/Mine_Entries/MapServer/WMTS/1.0.0/WMTSCapabilities.xml` |
| Tested on 2026-11-10 | HTTP 200 for the capabilities and one tile. The tile was a 256 px PNG of 384 bytes. |
| Format and CRS | PNG tiles, EPSG:3857, 23 zoom levels |
| Licence | UK Open Government Licence, as listed on data.gov.uk |
| Attribution | Not recorded. The OGL statement is "Contains public sector information licensed under the Open Government Licence v3.0." |
| Reuse class | open |
| Suggested mode | live |

```
https://services-eu1.arcgis.com/Qn4lKcPDVHNivEyr/arcgis/rest/services/Mine_Entries/MapServer/tile/10/328/505
```

Notes:

- The one tile fetched was 384 bytes, so probably blank.
- The vector service at `.../MineEntries/FeatureServer` returned HTTP 499 Token Required.
- Publisher: Mining Remediation Authority, formerly the Coal Authority. Coverage is the Great Britain coalfields.

## Wikidata Query Service

CC0 knowledge base with typed, georeferenced heritage items and external identifiers.

| Row | Value |
|---|---|
| Access | SPARQL, no key |
| Address | `https://query.wikidata.org/sparql` |
| Tested on 2026-11-10 | HTTP 200 for small GET queries. HTTP 429 on POST: "Aggressively rate-limiting to 1 req / min - this rule was created during active wdqs outage". HTTP 504 for a broad subclass query that timed out at 65 s. |
| Format and CRS | SPARQL JSON or CSV, WGS84 |
| Licence | CC0 1.0 |
| Reuse class | open |
| Suggested mode | bulk, by per-class queries or the dumps |
| Paging and limits | A rate rule of 1 request per minute was observed that day. |
| CORS | yes, `*` |

```
curl -G -A 'landscape-research-tool/0.1' -H 'Accept: text/csv' --data-urlencode 'query=SELECT (COUNT(*) AS ?n) WHERE { ?i wdt:P31 wd:Q1935728 ; wdt:P17 wd:Q145 . }' https://query.wikidata.org/sparql
```

That query returned 343 stone circles. UK items with coordinates, by class label:

archaeological site 7,880; cairn 3,606; castle 2,457; round barrow 2,445; moated site 812; motte-and-bailey castle 654; standing stone 633; Roman villa 372; menhir 371; stone circle 338; hillfort 322; broch 317; chambered cairn 312; tumulus 292; long barrow 262; deserted medieval village 217; pillbox 136; henge 79.

Notes:

- A generic and a descriptive User-Agent both got 429 on POST. GET with a descriptive one worked. The research advised per-class queries with long pauses, or the dumps.
- Medieval and military coverage from open sources was thin. Moated sites: 812 in Wikidata, 231 water=moat in OSM and 3,351 "Moat" labels in GB1900. Pillboxes: 1,953 in OSM for Great Britain and 136 in Wikidata. The full Defence of Britain set is under ADS terms. Castles: 1,349 in OSM, 2,457 in Wikidata and 5,113 Gatehouse records for England.

## OSNI gazetteer and historic settlements

A Northern Ireland place-name gazetteer, plus a gazetteer of historic nucleated and urban settlements with SMR references.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://admin.opendatani.gov.uk/dataset/d27903f1-15e6-4c07-8564-ddc655e9c549/resource/411c6ea5-c079-43aa-bd62-438423d070cc/download/osni_open_data_-_gazetteer_-_place_names.csv` |
| Tested on 2026-11-10 | HTTP 200. Size and time not recorded. |
| Format and CRS | CSV and GeoJSON. Irish Grid, EPSG:29902 declared in the GeoJSON. |
| Licence | UK Open Government Licence |
| Reuse class | open |
| Suggested mode | bulk |
| Records | Place names: 336 rows only. Historic settlements: 672 features. |

```
https://admin.opendatani.gov.uk/dataset/cc308891-4639-4dde-ac72-d75a750add93/resource/85640193-221a-4893-9cb1-e1237a8decf5/download/ghnus_05112026.geojson
```

Notes:

- The place-name file is far too small for a search box. Northern Ireland search needs OSM names or another OSNI product.
- A later check listed "OSNI Open Data - Largescale Boundaries - Townlands (2013)" under OGL on OpenDataNI's CKAN API. The listing was seen and the file was not downloaded.
- The research did not test the terms for BT postcodes.

## Nominatim public instance

A free-text geocoder over OSM.

| Row | Value |
|---|---|
| Access | REST JSON, no key |
| Address | `https://nominatim.openstreetmap.org/search?q={query}&format=jsonv2&countrycodes=gb` |
| Tested on 2026-11-10 | HTTP 200 |
| Format and CRS | JSON, point plus bounding box |
| Licence | ODbL 1.0 data, under the OSMF Nominatim Usage Policy |
| Attribution | "Data © OpenStreetMap contributors, ODbL 1.0. http://osm.org/copyright" |
| Reuse class | share_alike |
| Suggested mode | live, submit-on-enter only |
| Paging and limits | "Absolute maximum 1 request per second across the whole application". Auto-complete is forbidden. No systematic queries. A Referer or User-Agent identifying the application is required. |
| CORS | yes, `*` |

```
https://nominatim.openstreetmap.org/search?q=Maiden+Castle+Dorset&format=jsonv2&limit=2&countrycodes=gb
```

Notes: suitable only at low volume, and not for type-ahead.

## Photon public instance

A search-as-you-type geocoder over OSM, run by komoot.

| Row | Value |
|---|---|
| Access | REST GeoJSON, no key |
| Address | `https://photon.komoot.io/api/?q={query}&bbox=-8.7,49.8,1.9,60.9` |
| Tested on 2026-11-10 | HTTP 200 |
| Format and CRS | GeoJSON, point plus extent |
| Licence | ODbL 1.0 data. Terms: "please be fair - extensive usage will be throttled. We do not guarantee for the availability". |
| Attribution | "© OpenStreetMap contributors" |
| Reuse class | share_alike |
| Suggested mode | live |
| Paging and limits | No number published. Throttled on extensive use. |
| CORS | yes, `*` |

```
https://photon.komoot.io/api/?q=Maiden+Castle&limit=2&bbox=-8.7,49.8,1.9,60.9
```

Notes: it is designed for type-ahead but offers no availability guarantee. Self-hosting from the dump below removes that dependency.

## Photon British Islands dump

A pre-built weekly Photon data dump for Great Britain, the Isle of Man and the Channel Islands.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://download1.graphhopper.com/public/europe/british-islands/photon-dump-british-islands-master-latest.jsonl.zst` |
| Tested on 2026-11-10 | HEAD only: HTTP 200, last-modified 5 November 2026. Not downloaded. |
| Format and CRS | JSONL, zstd, 1.03 GB |
| Licence | ODbL 1.0 |
| Attribution | "© OpenStreetMap contributors" |
| Reuse class | share_alike |
| Suggested mode | bulk, to self-host as the geocoder fallback |

```
curl -sIL https://download1.graphhopper.com/public/europe/british-islands/photon-dump-british-islands-master-latest.jsonl.zst
```

Notes: Ireland is a separate extract. The older path `/public/extracts/by-country-code/gb/` still existed but was stale, at July 2025 and 3 GB.

## OS Names API

Hosted search over OS Open Names. The research recorded it as a source to avoid.

| Row | Value |
|---|---|
| Access | REST JSON, key required |
| Address | `https://api.os.uk/search/names/v1/find?query={query}&key={key}` |
| Tested on 2026-11-10 | HTTP 401 without a key: "Failed to resolve API Key variable request.queryparam.key" |
| Format and CRS | JSON |
| Licence | OS Data Hub terms |
| Reuse class | link_only |
| Suggested mode | deeplink. Not used. Open Names covers it |

```
https://api.os.uk/search/names/v1/find?query={query}&key={key}
```

Notes: the same data is in the keyless [OS Open Names](#os-open-names) download. The research sent the request without a key.

## postcodes.io

An open-source UK postcode and place lookup API.

| Row | Value |
|---|---|
| Access | REST JSON, no key |
| Address | `https://api.postcodes.io/postcodes/{postcode}` |
| Tested on 2026-11-10 | HTTP 200 |
| Format and CRS | JSON. WGS84, plus BNG eastings and northings. Irish Grid for Northern Ireland. |
| Licence | MIT for the software. OS and ONS open data underneath. |
| Reuse class | open |
| Suggested mode | live |
| CORS | yes, `*` |

```
https://api.postcodes.io/postcodes/SN81RF
```

Notes: the sample returned parish Avebury, E 410014 N 169888. A place search, `https://api.postcodes.io/places?q=Avebury&limit=2`, also worked. The service is self-hostable.

## Geograph API

Georeferenced photographs searchable by grid square or location.

| Row | Value |
|---|---|
| Access | REST JSON, also RSS and KML. A personal API key is required by the documentation. |
| Address | `https://api.geograph.org.uk/syndicator.php?key={apikey}&format=JSON&q={gridref}` |
| Tested on 2026-11-10 | HTTP 200. A request with an empty key still returned data, which is undocumented. |
| Format and CRS | JSON |
| Licence | CC BY-SA 2.0 per image |
| Attribution | Show the photographer's credit, state that the image is Creative Commons licensed, and link to `https://www.geograph.org.uk/photo/{id}`. |
| Reuse class | share_alike |
| Suggested mode | live |
| Records | The sample, grid square SU1069, returned 15 items. 11,609 images lay within 10 km of Avebury. |
| Positional precision | Point at the photo subject position. |
| Paging and limits | Searches reach only the first 1,000 matching images. Feeds are "not for bulk download". |
| CORS | yes, `*` |

```
https://api.geograph.org.uk/syndicator.php?key=&format=JSON&q=SU1069
```

Notes:

- A key is requested at `https://www.geograph.org.uk/get-api-key.php`. Don't rely on the empty-key behaviour.
- Adapted images must also be CC licensed.

## Geograph database dumps

Daily dumps of the full Geograph image index: titles, credits, coordinates, tags and descriptions.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://data.geograph.org.uk/dumps/` |
| Tested on 2026-11-10 | HTTP 200. Only the sample file was downloaded. |
| Format and CRS | TSV and mysqldump, gzip. National grid eastings and northings plus WGS84. |
| Licence | CC BY-SA 2.0 |
| Attribution | "© Copyright Geograph Project and individual contributors; see https://www.geograph.org.uk/credits/" |
| Reuse class | share_alike |
| Suggested mode | bulk |
| Records | The listing page said "over 7 million images as of Dec 2021". |
| Positional precision | 4 to 10 figure grid reference. Viewpoint and view direction are in gridimage_geo. |

```
https://data.geograph.org.uk/dumps/gridimage_base_sample.tsv.gz
```

Notes:

- The sample held 10,000 rows. Full files, all dated 2026-11-10: gridimage_base.tsv.gz 248 MB, gridimage_geo.tsv.gz 114 MB and gridimage_text.tsv.gz 367 MB.
- Base fields include gridimage_id, realname, title, imagetaken, grid_reference, wgs84_lat and wgs84_long.
- Image files need a separate request form.

Suggested use: a local "photos near here" index linking to the Geograph photo page with the photographer's credit and the CC BY-SA 2.0 notice.

## Wikimedia Commons geosearch

Geotagged media files near a point, with licence and credit metadata.

| Row | Value |
|---|---|
| Access | MediaWiki REST JSON, no key |
| Address | `https://commons.wikimedia.org/w/api.php?action=query&generator=geosearch&ggscoord={lat}%7C{lon}&ggsradius=500&ggsnamespace=6&prop=imageinfo&iiprop=url%7Cextmetadata&iiurlwidth=320&format=json&origin=*` |
| Tested on 2026-11-10 | HTTP 200 |
| Format and CRS | JSON, point |
| Licence | Per file. The two sampled were CC BY-SA 2.0. |
| Attribution | Per file, from the extmetadata Artist, Attribution and LicenseShortName fields |
| Reuse class | share_alike, to be checked per file |
| Suggested mode | live |
| Records | Per query. |
| CORS | yes, `*`, with `origin=*` |

```
https://commons.wikimedia.org/w/api.php?action=query&list=geosearch&gscoord=51.4288%7C-1.8544&gsradius=1000&gsnamespace=6&gslimit=3&format=json&origin=*
```

Notes: all three Avebury results were Geograph imports, so expect duplicates with Geograph.

## heritagedata.org SKOS linked data

The monument type, period, evidence, event, object and related thesauri of FISH, HES and RCAHMW, as SKOS concept schemes with dereferenceable URIs.

| Row | Value |
|---|---|
| Access | REST linked data, content chosen by suffix .ttl, .json, .rdf or .n3 |
| Address | `http://purl.org/heritagedata/schemes/{scheme}[/concepts/{id}].{ttl, json, rdf or n3}` |
| Tested on 2026-11-10 | HTTP 200, after a redirect from the purl.org address to `https://heritagedata.org/live/...` |
| Format and CRS | text/turtle, RDF/JSON, RDF/XML, N-Triples. No geometry. |
| Licence | Per scheme. OGL v3 for the main Historic England and FISH schemes: eh_tmt2, eh_period, eh_evd, eh_com, mda_obj, agl_et. CC BY 3.0 for some: Defence of Britain, Farmsteads, Heritage Crime and the OASIS lists. Open Government Licence for the HES and RCAHMW schemes. |
| Attribution | cc:attributionName "Historic England", or HES or RCAHMW per scheme, plus "Contains public sector information licensed under the Open Government Licence v3.0." |
| Reuse class | open |
| Suggested mode | bulk |
| Records | 57 schemes. eh_tmt2 5,111 concepts, eh_period 152, eh_evd 59, eh_com 1,403, Scotland monument types (scheme 1) 2,735, Wales monument types (scheme 10) 2,113, Wales events (scheme 17) 66. |
| CORS | no Access-Control-Allow-Origin header observed |

```
curl -L 'http://purl.org/heritagedata/schemes/eh_tmt2/concepts/70204.json'
```

Notes:

- The per-scheme licences above came from getSchemes. Scheme numbers 560, 571 and 547 are OGL v3 with attributionName "Historic England". Defence of Britain is 365, Farmsteads 573 and Heritage Crime 596, all CC BY 3.0. The HES schemes (1, 2, 3, scapa) and RCAHMW schemes (10 to 25) use `http://reference.data.gov.uk/id/open-government-licence`. The site footer default is CC BY 3.0 "except where otherwise noted".
- Canonical URIs are the `http://purl.org/...` form, and the research advised storing those as identifiers.
- dct:issued on eh_tmt2 showed releases in January, June and July 2026.
- Heneb's guidance for submitting data to Welsh HERs, version 4, requires terms from schemes 10, 11, 19, 17, 13 and 18: Monument Type (Wales), Period (Wales), Evidence, Event, Survival Condition and Condition Rating.

Suggested use: ingest once and make monument type, period and evidence controlled pick-lists that store the purl.org URI. Use schemes 10, 11 and 19 for Wales and 1 and scapa for Scotland. Don't depend on the live services at request time.

## heritagedata.org SENESCHAL web services

JSON lookup services over the same thesauri: label search, scheme lists, top concepts, relations and an existence check.

| Row | Value |
|---|---|
| Access | REST JSON, JSONP supported, no key |
| Address | `https://www.heritagedata.org/live/services/{service}`, where service is one of getSchemes, getTopConceptsForScheme, getConceptsForScheme, getConceptRelations, getConceptLabels, getConceptLabelMatch or getConceptExists |
| Tested on 2026-11-10 | HTTP 200. The JSON body was served as text/html; charset=UTF-8. |
| Format and CRS | JSON, no geometry |
| Licence | As per scheme, OGL v3 or CC BY 3.0. The service source code is CC BY. |
| Attribution | "Historic England / FISH" |
| Reuse class | open |
| Suggested mode | live |
| Records | A "barrow" search returned an 11.9 KB array beginning Barrow, Bank Barrow. |
| Paging and limits | None published. `limit` and `offset` parameters page results. |
| CORS | no header. Use the `callback` parameter for JSONP or call it from the server. |

```
curl 'https://www.heritagedata.org/live/services/getConceptLabelMatch?schemeURI=http://purl.org/heritagedata/schemes/eh_tmt2&contains=barrow'
```

Notes: parameters are schemeURI, conceptURI, contains, limit, offset, alias, verbose and pretty. The research preferred to ingest once and serve type-ahead from PostGIS.

## heritagedata.org SPARQL endpoint

SPARQL query access to all hosted concept schemes.

| Row | Value |
|---|---|
| Access | SPARQL, no key |
| Address | `https://heritagedata.org/live/sparql.php?query={sparql}&output=json` |
| Tested on 2026-11-10 | HTTP 200 for simple queries. HTTP 500 for queries with OPTIONAL. |
| Format and CRS | application/sparql-results+json, no geometry |
| Licence | As per scheme |
| Reuse class | open |
| Suggested mode | live, not on a request path |
| Records | A count query returned 5,111 for eh_tmt2. |
| CORS | no header. The form offers a jsonp parameter. |

```
curl -G 'https://heritagedata.org/live/sparql.php' --data-urlencode 'query=PREFIX skos: <http://www.w3.org/2004/02/skos/core#> SELECT (COUNT(?c) AS ?n) WHERE { ?c skos:inScheme <http://purl.org/heritagedata/schemes/eh_tmt2> }' --data-urlencode 'output=json'
```

Notes: the store was ARC2 with a SPARQL+ dialect, so keep queries simple.

## FISH Terminologies bulk downloads

The current FISH thesauri as CSV zips, RDF/SKOS files and PDFs, with table structure documentation.

| Row | Value |
|---|---|
| Access | Bulk download, no key |
| Address | `https://heritage-standards.org.uk/fish-vocabularies/` |
| Tested on 2026-11-10 | HTTP 200 application/x-zip-compressed, 383,971 bytes, for MonumentTypeV29.zip |
| Format and CRS | ZIP of CSV, also RDF/XML and CSV for periods. No geometry. |
| Licence | The page said the files were "free to use and do not require FISH membership". The scheme-level licence on heritagedata.org is OGL v3 for the main thesauri. |
| Attribution | "Historic England / FISH" |
| Reuse class | open |
| Suggested mode | bulk |
| Records | Version 29, April 2026. The Historic England Periods CSV had 149 rows with MIN_DATE and MAX_DATE. |

```
curl -L -O 'https://heritage-standards.org.uk/2026/zip_files/MonumentTypeV29.zip'
```

Notes:

- The zip held ThesaurusTerms.csv, ThesaurusTermRelations.csv, ThesaurusTermUses.csv, ThesaurusTermPreferences.csv, ClassificationGroups.csv and ThesaurusVersion.csv.
- The periods CSV was at `https://heritage-standards.org.uk/2026/csv_files/HE_Periods1_20260408.csv`, with columns NAME, PERIOD_UID, CHRON_ORDER, PARENT_UID, MIN_DATE, MAX_DATE, DESCRIPTION, VALID_FLAG, SHORT_NAME and altLabel.

## Grid-reference libraries

These are software, so they have no reuse class. The research tested them against the OS Caister Water Tower test point, where the OSTN15 value was E 651409.804, N 313177.450, quoted from memory in the report.

| Library | Version | Licence | Result on 2026-11-10 |
|---|---|---|---|
| pyproj (Python) | 3.8.0, PROJ 9.8.1 | not recorded | With PROJ_NETWORK=ON it selected the OSTN15 operation, accuracy 0.03 m, and returned E 651409.805, N 313177.452. |
| osbng (Python) | 0.5.1 | MIT, Ordnance Survey | Parsed and built grid references correctly. |
| convertbng (Python) | 2.0.0 | not recorded | Implements OSTN15. Not run. |
| geodesy (JavaScript) | 2.4.0 | MIT | Parsed "SU 102 699" to 410200, 169900. Helmert transform. 1.4 m east and 3.1 m north of the OSTN15 value. |
| proj4 (JavaScript) | 2.22.0 | MIT | Same result as geodesy with the standard EPSG:27700 towgs84 definition. It exposes nadgrid() for loading OSTN15, which was not tested. |

Notes:

- The only other ETRS89 to BNG operation pyproj offered was a "ballpark" transform that put the point at E 651282.5, about 127 m off. If the OSTN15 grid is missing, PROJ can fall back to it.
- pyproj resolved EPSG:29901 (OSNI 1952), 29902 (TM65), 29903 (TM75) and EPSG:2157 (ITM). The three Irish Grid codes agreed within 0.7 m for Belfast. NI open data seen that day declared EPSG:29902. proj4 with an EPSG:29903 definition matched pyproj for Belfast at 333835.8, 374054.3.
- The research found no maintained npm or PyPI library for Irish Grid letter references, and geodesy does not cover them.

Suggested use: bake the OSTN15 grid into the backend image and assert at startup that the operation is sub-metre. Use geodesy for BNG parsing and display on the client, where a Helmert error of about 3.5 m is acceptable, and proj4 for Irish Grid. Parse grid references, lat/lon pairs and postcodes locally before any text search.

## Deep link only

These sources either block scripts, forbid reproduction or have no usable interface. Each is a link to the publisher's page. Nothing from them is stored.

| Source | Reuse | Link pattern |
|---|---|---|
| Open Domesday place pages | non_commercial | `https://opendomesday.org/place/{1km-grid-ref}/{slug}/` |
| Hull Domesday dataset | non_commercial | `https://digitalcollections.hull.ac.uk/collections/3t945r28b` |
| England's Rock Art | non_commercial | `https://archaeologydataservice.ac.uk/archives/view/era_eh_2009/` |
| Defence of Britain Archive | non_commercial | `https://archaeologydataservice.ac.uk/archives/view/dob/` |
| Megalithic Portal | link_only | `https://www.megalithic.co.uk/article.php?sid={id}` |
| Roman Roads Research Association | link_only | `https://www.romanroads.org/gazetteer/gazetteer_home.html` |
| Northern Mine Research Society | link_only | `https://nmrs.org.uk/mines-map/index/` |
| Key to English Place-Names | link_only | `https://kepn.nottingham.ac.uk/` |
| A Vision of Britain through Time | link_only | `https://www.visionofbritain.org.uk/place/place_page.jsp?p_id={id}` |

### Open Domesday place pages and vector tiles

- Tested: place pages and vector tiles returned HTTP 200. Sample page `https://opendomesday.org/place/NZ2011/aldbrough/`. A tile at `https://tiles.opendomesday.org/services/domesday/mytiles-65536/tiles/8/127/84.pbf` was 167 KB. Tiles were z5 to 14, 512 px, one layer with 31 attributes, CORS `*`.
- Licence: "The raw Domesday data is hosted by Hull University, under a CC-NC-BY-SA licence". Folio images are CC BY-SA.
- Attribution: "Maps and site by Anna Powell-Smith. Domesday data created by Professor J.J.N. Palmer and team. Images: credit Professor John Palmer, George Slater and opendomesday.org."
- The research advised against hotlinking the tiles without asking, because they are on a private server and the data is non-commercial.

### Hull Domesday dataset

- Palmer's Domesday databases and notes at Hull. Nine items, last updated 2025-04-01.
- Only the collection page was fetched. The files were not downloaded, so coordinate content is not tested. Open Domesday describes the licence as CC BY-NC-SA. The Hull page said the licence was detailed with each item.

### England's Rock Art at ADS

- A database of prehistoric rock art panels, mainly Northumberland and County Durham. One search result said locations were accurate to 100 m.
- Tested: the archive page returned HTTP 403, a Cloudflare "Just a moment..." challenge, for curl and WebFetch. The ADS follow-up, written later, reached the per-record page `https://archaeologydataservice.ac.uk/archives/collections/view/era_eh_2009/fullrecord.cfm?id=2880` with 200. It also found 2,103 to 2,106 panel records in the ADS catalogue API, each with a geopoint, such as "Green Grag 09 (ERA ID: 2880)" at 53.909332,-1.802103. Decision 0007 treats the catalogue as a live source.
- Licence: ADS Terms of Use and Access. DataCite: "ADS Terms and Conditions apply to reuse". Cite depositors and ADS with DOI 10.5284/1138794.

### Defence of Britain Archive at ADS

- A Council for British Archaeology survey of twentieth-century anti-invasion defences, including pillboxes.
- Tested: HTTP 403 behind a Cloudflare challenge, including through doi.org. The ADS terms page, `https://archaeologydataservice.ac.uk/about/policies/use-access-to-data/ads-terms-of-use-and-access/`, returned 200. The later follow-up found 20,173 site-level records in the catalogue API, each with a geopoint, such as "Army Barracks" at 59.88505,-1.306351.
- Licence: "The data must not be sold or supplied to a third party. The data should only be used for teaching, learning, and research purposes." The terms also say that if you build on the material "you must distribute your contributions in the public domain". The CBA radiocarbon index, doi:10.5284/1017767, is under the same terms.
- Attribution: "Council for British Archaeology (2007) Defence of Britain Archive. York: Archaeology Data Service. doi:10.5284/1000327"
- The follow-up read the terms as allowing browser-direct live queries with no server cache for a free non-commercial tool. That was its interpretation and not an ADS statement. Its draft permission letter to ADS had not been sent.
- Rural Settlement of Roman Britain, DOI 10.5284/1030449, is under the same terms. The catalogue held one collection-level record for it. Its roughly 3,600 site records were in no API found, and its archive page returned 403.

### Megalithic Portal

- A community database of megalithic and other ancient sites. Tested: HTTP 200. Sample `https://www.megalithic.co.uk/article.php?sid=132`, Pobull Fhinn Stone Circle, North Uist.
- Licence: all rights reserved. Terms 6.1(d): "no part of this site may be reproduced or stored in any other website or included in any public or private electronic retrieval system or service without the prior written permission of megalithic.co.uk." Use is "personal use only".
- robots.txt disallowed asb_kml.php, asb_gpx.php, georss.php and le_ajaxmapdata.php.

### Roman Roads Research Association

- Road-by-road gazetteer pages for parts of Britain: Yorkshire, Cumbria, Cheshire and Lancashire. Licence: "All content © Roman Roads Research Association 2024, all rights reserved; unless otherwise stated."
- The home page, last modified 27 September 2026, said a new digital map of Roman Britain "will be made freely available before the end of the year, as a geopackage for use in GIS, and as KMZ files". No download link existed on 2026-11-10.

### Northern Mine Research Society

- Online maps and databases of collieries, metal mines, quarries and smelt mills. Tested: HTTP 200. Licence: "© Northern Mine Research Society; 'Please contact us also if you wish to reproduce any of the content on this site.'"

### Key to English Place-Names

- Etymologies of English place-names, as a JavaScript app. The home page returned 200. `/api/*` and a guessed place URL returned 404, so the link is to the home page only. Licence: "© 2026 University of Nottingham. All Rights Reserved."

### A Vision of Britain through Time

- Historical gazetteer, statistics and travel writing. HTTP 200 for the sample page. One earlier request timed out, and the GB1900 download dropped one connection. `/api` returned 404.
- The site content isn't openly licensed. Statistical and boundary data come through the UK Data Service and are "mostly deposited under open licenses but limiting commercial use". Historic parish boundaries are not open.

## Open questions

- Should Gatehouse be ingested under Decision 0004? The research recommended a deep link and did not settle it.
- Will ADS and the CBA allow Defence of Britain and England's Rock Art points to be indexed? The follow-up drafted a permission request and did not send it. The browser-direct live reading of the terms is the follow-up's interpretation.
- What are the download formats for the ADS thematic archives? Someone needs to check them in a browser, since scripts are blocked.
- When will the RRRA release its promised Roman Britain GeoPackage, and under what licence? It could supersede Itiner-e for Britain.
- Are the BGS mine plan records under OGL? The research didn't read the BGS terms page.
- Does the Hull Domesday dataset hold place coordinates, and what licence is on each item?
- What licence covers the DARE data and tiles? No page fetched stated one.
- What licence covers the p3k14c data file? Only the R package is MIT. XRONOS, under CC BY 4.0, is the safer route.
- Which open source should supply Northern Ireland place names and postcodes? The OSNI gazetteer had 336 rows, the townlands listing under OGL was not downloaded, and BT postcode terms were not tested.
- Does the Coal Mine Entries tile layer draw points at working zoom levels?
- Does proj4's nadgrid() with the OSTN15 file give centimetre accuracy in the browser, and is the file small enough to ship? Not tested.
- Geograph answered an empty key on 2026-11-10. That is undocumented, so a key should be requested.
- Decision 0007 says OSM is an overlay and is not indexed, while the research recommended loading an extract into its own schema. The Photon British Islands dump is OSM-derived and was suggested as bulk. The owner has to settle which applies.
