# Decision 0006 — Terrain tiles are rendered from raw elevation

**Status:** Proposed.

**TL;DR.** In the context of showing earthworks a few centimetres high across four nations with different LIDAR publishers, facing ready-made hillshades that hide faint features and a browser renderer that quantises slope, we chose to render our own archaeological visualisations on the server from raw elevation, to control exactly how the ground is shown, accepting that we must source, cache and eventually mirror about half a terabyte of elevation data.

## Context

Nothing was built when this was written.

The research pass on 2026-11-10 tested every route to UK LIDAR. Raw 1 m elevation was open for 99.7% of England, all of Wales, 39% of Scotland and 17% of Northern Ireland. Each nation published it differently. England had an on-demand image service and downloadable 5 km tiles. Wales had one national 48.6 GB cloud-optimised file. Scotland had an open bucket of GeoTIFFs. Northern Ireland had zipped ASCII grids.

The publishers' own renderings didn't suit earthwork spotting. England offered a single-direction hillshade, Scotland colour ramps and Wales a low-contrast tinted image. The National Library of Scotland served good archaeological tiles, but offered only its multi-direction hillshade sets for reuse.

MapLibre couldn't do the job in the browser. Its hillshade stored slope in an 8-bit texture, which gave steps of about 2.9 degrees at UK latitudes, and it had no raster blend modes. The standard archaeological blend needs multiply, overlay and luminosity.

The reference implementation, `rvt_py`, pinned Python below 3.12 and pulled in GDAL and Jupyter. A numpy version of the same algorithms rendered the combined blend for a 512 px tile in about 75 ms, and fetching each tile with a buffer equal to the search radius removed seams exactly.

England's on-demand image service had no published usage limit, took up to 2 s per tile and served an edition that couldn't be downloaded in bulk. Its coverage service hung on between 2.5% and 11% of requests in testing.

On 2026-11-10 Defra answered a bulk request within ten minutes. It gave access with no time limit to the 2022 composite as 5,877 GeoTIFF tiles, 353.6 GB at 1 m. It said its web services could be used by third-party applications but were tuned for live map viewing, and it recommended the bulk supply for the core dataset.

## Decision

1. Field Club renders its own visualisations from raw elevation on the server, using its own numpy implementations of the Relief Visualization Toolbox algorithms and presets. The default layer is the combined blend.
2. Tiles are rendered on demand, each from its own bounds plus a buffer, and cached without expiry under a key that includes the style version.
3. Stretches are fixed and linear. Nothing is stretched per tile.
4. Elevation is read through one interface, from our own mirror of cloud-optimised files: a bucket in production and a local folder in development, one mosaic per nation with per-survey provenance.
5. A source tile that isn't in the mirror yet is fetched from the publisher's bulk supply on first use, converted and added. No publisher's web service sits on the path of a map tile.
6. The same elevation is also served as Terrarium-encoded tiles, for 3D terrain, the height readout, profiles and a light the user can steer.
7. A coverage layer shows where LIDAR exists, its capture year and resolution. Coarse fallback terrain is labelled as context only.

## Alternatives considered

- **Hot-linking the National Library of Scotland's tiles** was rejected because only one of their sets is offered for reuse, we couldn't change a parameter, and none of the elevation features would work. Their multi-direction hillshade stays available as a comparison layer.
- **Rendering in the browser** was rejected because of the slope quantisation and missing blend modes above.
- **Depending on `rvt_py`** was rejected because of its Python pin and dependency weight. The algorithms are Apache-2.0 and are reimplemented with attribution.
- **Pre-rendering the country before launch** was rejected because it needs the full mirror and days of compute before anyone sees a tile. On-demand rendering with a cache reaches the same end state for the places people look at.
- **Reading a publisher's web service for each map tile**, even as a stopgap, was rejected. Defra advised against relying on its services for the core dataset, the coverage service hung too often, and the image service serves a different edition from the files, which would have left seams wherever the two met.

## Consequences

- We decide how the ground looks, and can add or tune a visualisation without asking anyone.
- The first visitor to an uncached area waits for an upstream fetch and a render. Later visitors don't.
- Mirroring costs storage of about 0.5 TB with 1 cm lossy compression, and an ingest job per nation that must be re-run as Scotland's national programme releases new blocks until 2027.
- Until an area's source tile is in the mirror, the first view of it waits for a download of 40 to 90 MB. A laptop holds only the areas someone has looked at.
- Findings must record which visualisation and parameters the finder used, because the picture is now ours to change.

## Walk-back options

- **If on-demand rendering costs too much or is too slow**, pre-render the combined blend for the zoom levels people use most and keep the other styles lazy.
- **If a bulk supply is withdrawn** before a nation's mirror is complete, fill the rest from the publisher's public tile download, which serves the same files one at a time.

## Links

- Decision 0001 keeps rendering off the event loop and names the split into a separate service as its own walk-back.
- Decision 0004 allows the non-commercial Scottish collections into the mirror, kept under a separate prefix.
