# Spike — Can the browser render archaeological LIDAR visualisations without server-side processing?

**Status:** Resolved (2026-11-10) — NO; MapLibre GL JS 6.17.0 had no raster blend modes, so the standard blend needed server-side rendering. Its hillshade slope quantisation to 8 bits was read from source and not tested in a browser

## Question

Can MapLibre GL JS, with elevation tiles sent to the browser, render the visualisations that archaeologists use to spot earthworks, without a server computing them?

## Why this is in question

Decision 0006 renders terrain tiles on the server from raw elevation. That choice costs storage, an ingest job per nation and a render service. If the browser could do the job from plain elevation tiles, most of that cost would not be needed. The question was whether MapLibre's own hillshade and layer compositing were good enough for features a few centimetres high, and what the reference recipes asked for.

## Approach

The research pass of 2026-11-10 read the source and specifications. It did not run the reference implementation and it did not test in a browser. The single input was one report on LIDAR visualisation.

- **Q1.** What recipe do archaeologists use as the standard visualisation, and what exactly are its parameters?
  - Step 1: Read the `rvt_py` source and preset files (Apache-2.0, version 2.2.3 on PyPI).
  - Step 2: Read the papers and guidance that define the recipe: Kokalj and Somrak 2019, Kokalj and Hesse 2017, Historic England 2018 and the European Archaeological Council Guidelines 10 (2025).
- **Q2.** Can MapLibre GL JS compute and composite that recipe in the browser?
  - Step 1: Read the style specification (26.6.0) and the shader and renderer source at tag v6.17.0 for hillshade, raster-dem encodings and blending.
  - Step 2: Simulate the 8-bit slope buffer and the elevation encodings in numpy on a synthetic earthwork of 0.10 m ridge and furrow at 8 m wavelength with 2 cm noise on a 1 m grid.
- **Q3.** If not, can a server render the recipe cheaply enough to serve on demand?
  - Step 1: Write a numpy implementation of the same algorithms and time it per tile on an Apple M4 Pro, single thread.
  - Step 2: Test tiled computation against whole-array computation for seams.

## Decision matrix

| Outcome | Means | Action |
|---|---|---|
| Q2 passes | The browser can blend and relight from plain elevation tiles | Decision 0006 would have been replaced by one that serves elevation only. |
| Q2 fails, Q3 passes | Server rendering is needed, and is cheap per tile | Decision 0006 accepted. The server renders the blend. Resolves NO. |
| Q2 fails, Q3 fails | Neither side can do it | A pre-rendering decision would have replaced Decision 0006. |
| Q2 partly passes | The browser can do relighting and colour ramps but not blends | The server renders the blend and the browser does the rest. |

The result was the second row, with a note from the fourth. The browser could relight and colour a single elevation channel, and the server was needed for the blend.

## Findings

All observations were made on 2026-11-10. The MapLibre statements come from source and specification, not from a browser. The hillshade quantisation is marked "likely" by the report for that reason.

### The recipe

- The Visualization for Archaeological Topography (VAT) general preset was read from `settings/blender_VAT.json` and the `general` block of `default_terrains_settings.json`. The table lists its layers from the base up.

| Order | Layer | Parameters | Blend | Opacity |
|---|---|---|---|---|
| Base | Hillshade | azimuth 315, sun elevation 35, stretch 0-1 | Normal | 100% |
| 2 | Slope gradient | degrees, stretch 0-50, inverted (1-x) | Luminosity | 50% |
| 3 | Openness, positive | stretch 68-93 degrees | Overlay | 50% |
| Top | Sky-view factor | stretch 0.7-1.0 | Multiply | 25% |

The general preset's sky-view factor and openness shared `svf_n_dir` 16, `svf_r_max` 10 px and `svf_noise` 0. Normalisation clipped to [min, max] and scaled to 0-1. Evidence: https://raw.githubusercontent.com/EarthObservation/RVT_py/master/settings/blender_VAT.json

- The VAT flat preset used the same four layers, blend modes and opacities, with these overrides from the `flat` block. Hillshade sun elevation 15. Slope stretch 0-15 degrees. Positive openness stretch 85-93 degrees. Sky-view factor stretch 0.9-1.0 with `svf_r_max` 20 px and `svf_noise` 3. Noise level 3 ignored the nearest 40% of the radius, so r_min was 8 px, and openness used the same radius and noise setting. The `steep` block read sun 55, slope 0-60, sky-view factor 0.55-1.0 at radius 10, positive openness 55-95 and negative openness 45-95. Evidence: https://raw.githubusercontent.com/EarthObservation/RVT_py/master/settings/default_terrains_settings.json
- Combined VAT was VAT general at Normal blend and 50% opacity over VAT flat at Normal and 100%, which is 0.5 times general plus 0.5 times flat. `VAT_combined.py` set `general_opacity` to 50 and the QGIS plugin hard-coded the same. Output was single-band float 0-1, byte-scaled to 0-255. The RVT documentation called it "our preferred choice". EAC Guidelines 10 (2025) said it "is emerging as a preferred choice for both interpretation and illustration". Evidence: https://raw.githubusercontent.com/EarthObservation/RVT_py/master/VAT_combined.py
- Blend mathematics in `rvt/blend_func.py`. Opacity: out = blend(top, base) x a + base x (1 - a). Multiply: top x base. Screen: 1 - (1 - top)(1 - base). Overlay, decided on the base: if base is above 0.5, 1 - (1 - 2(base - 0.5))(1 - top), otherwise 2 x base x top. Luminosity used lum = 0.3R + 0.59G + 0.11B and shifted base RGB by lum(top) - lum(base) with clipping. Over a greyscale base it returned the top layer, so slope at 50% was a plain average with the hillshade. Slope and negative openness were inverted after normalisation. Evidence: https://raw.githubusercontent.com/EarthObservation/RVT_py/master/rvt/blend_func.py
- Radius units differed between code and papers. RVT radii were pixel counts. Kokalj and Somrak 2019 described the VAT default as a 5 m search radius, and for flat terrain "from 5 m to 10 m while disregarding the first 4 m", with flat stretches of slope 0-35 degrees, openness 85-92 degrees and sky-view factor 0.95-1.00. EAC Table 6 listed "5 m radius in 16 directions". On a 1 m DTM the shipped defaults therefore meant 10 m for general and 20 m ignoring 8 m for flat. The National Library of Scotland built its England Combined VAT with the stock module on 1 m data. The pass did not settle which convention to adopt. Evidence: https://doi.org/10.3390/rs11070747
- `rvt_py` per-visualisation defaults, from `rvt/default.py`. `ve_factor` 1. Hillshade azimuth 315, elevation 35. Multi-hillshade 16 directions, elevation 35, with the three-band version using azimuths 315 (R), 22.5 (G) and 90 (B). SLRM `slrm_rad_cell` 20 px, allowed 10-50 only. Sky-view factor 16 directions, `r_max` 10 px, noise 0. Anisotropic sky-view factor direction 315, level 1. Local dominance minimum radius 10, maximum 20, increment 1 px, angular step 15 degrees, observer height 1.7. MSRM feature 0-20 m, scaling factor 2. MSTP local (1, 5, 1), meso (5, 50, 5), broad (50, 500, 50) px, lightness 0.9. The 8-bit stretches were slope 0-51 degrees, hillshade 0-1, SLRM -2 to 2 m, sky-view factor 0.6375-1, anisotropic sky-view factor 0.7-0.9, both opennesses 60-95 degrees, local dominance 0.5-1.8 and MSRM -2.5 to 2.5. Evidence: https://raw.githubusercontent.com/EarthObservation/RVT_py/master/rvt/default.py
- Algorithms, from `rvt/vis.py`. Slope by central differences, dz/dx = (z[x+1] - z[x-1]) / (2 x res). Hillshade as cos(zenith) cos(slope) + sin(zenith) sin(slope) cos(aspect - azimuth), clipped at 0. Sky-view factor and openness: divide the DEM by resolution, sample integer offsets along each of n rays at radii from r_min to r_max in steps of a third of a pixel, rounded and de-duplicated, take the maximum of (z_offset - z) / distance and convert to angle g. Sky-view factor was the mean of 1 - sin(max(g, 0)). Positive openness was 90 - mean(g) in degrees. Negative openness was positive openness of the negated DEM, shown inverted. Noise levels 0 to 3 set r_min to 0%, 10%, 20% and 40% of r_max, minimum 1 px. SLRM was the DEM minus a (2r+1)^2 box mean by integral image. MSTP took the maximum absolute DEV = (z - mean) / std over each radius range and mapped it as 1 - exp(-lightness x |DEV|) to R for broad, G for meso and B for local. Evidence: https://raw.githubusercontent.com/EarthObservation/RVT_py/master/rvt/vis.py
- Kokalj and Hesse 2017 gave typical settings by terrain, as general, very flat and steep or complex. Hillshade azimuth 315 and sun elevation 35, 5 and over 45. Slope 0-50, 0-15 and 0-60 degrees. Local relief model filter radius 10, 5 and 25 m. Sky-view factor radius 10 m in 16 directions with stretch 0.65-1.0, 0.9-1.0 and 0.55-1.0. Positive openness 65-95, 85-91 and 55-95 degrees. Their licence is CC BY-NC-ND 4.0, so the tables may be cited and not republished. Evidence: https://omp.zrc-sazu.si/zalozba/catalog/download/824/3485/287?inline=1
- Historic England 2018, citing Bennett and others 2012, said no single technique recorded more than 77% of features, any two recorded more than 80% and any three more than 90%. Single-direction hillshade was shown vanishing when lit along ridges. Evidence: https://historicengland.org.uk/images-books/publications/using-airborne-lidar-in-archaeological-survey/
- Kokalj and Hesse Table 15 rated shaded relief as not suitable for ridge and furrow, former field boundaries and mining pits. Local dominance was very suitable for burial mounds, former field boundaries and mining pits. Sky-view factor was very suitable for hollow ways and terraces. The report's mapping of these onto UK feature types was marked "likely", as its own synthesis.

### What MapLibre could and could not do

- MapLibre GL JS latest was 6.17.0, published 2026-11-07, BSD-3-Clause. Version 6.0.0 became ESM-only and required WebGL2. Evidence: https://registry.npmjs.org/maplibre-gl/latest
- The `raster-dem` source took three encodings. Mapbox gave 0.1 m steps. Terrarium gave 1/256 m (3.90625 mm). `custom` took the viewer's own factors, from JS 3.4.0. The decode formula was r x redFactor + g x greenFactor + b x blueFactor - baseShift. Evidence: https://raw.githubusercontent.com/maplibre/maplibre-gl-js/v6.17.0/src/data/dem_data.ts
- The England report said the style specification allowed interactive light direction with no server compute. The visualisation report read the shaders and found the limits below. The visualisation report examined the source, so this record follows it.
- Terrarium quantisation was fine for 10 cm earthworks. On the test surface, terrarium added slope RMSE of 0.045 degrees and SLRM error of 1.1 mm. A custom 1 mm encoding gave 0.012 degrees. A 1/32 m step gave 0.37 degrees, a 1/16 m step 0.75 degrees, and the Mapbox 0.1 m step 1.25 degrees with SLRM error of 2.9 cm, which the report called unusable.
- MapLibre's native hillshade stored slope in an 8-bit texture. `hillshade_prepare.fragment.glsl` wrote Sobel derivatives to an RGBA8 framebuffer as deriv/8 + 128/255. One level was a gradient of 8/255, about 2.9 degrees of true slope at 52 N. On the test surface only 8 distinct x-derivative levels were used, with hillshade RMSE 0.012. Declaring a custom encoding with factors multiplied by 8 gave 54 levels, RMSE 0.0015, with clamping at about 39 degrees of ground slope. This came from source and a numpy simulation and was not confirmed in a browser. Evidence: https://raw.githubusercontent.com/maplibre/maplibre-gl-js/v6.17.0/src/shaders/glsl/hillshade_prepare.fragment.glsl
- Raster blend modes were not implemented. The style specification 26.6.0 defined `raster-layer-blend` with normal, multiply, color, luminosity, plus-lighter, screen and overlay, but its JS support entry was an issue link (maplibre-gl-js#48). maplibre-gl 6.17.0 depended on specification ^26.5.1, which lacked the property, and `draw_raster.ts` had no blend code. The VAT blend needs multiply, overlay and luminosity, so it could not be composed from separate raster layers. Raster layers did have `raster-contrast`, `raster-brightness-min` and `-max` and `raster-saturation`. Evidence: https://cdn.jsdelivr.net/npm/@maplibre/maplibre-gl-style-spec@26.6.0/src/reference/v8.json
- Hillshade options. `hillshade-method` took standard, basic, combined, igor and multidirectional (JS 5.5.0 and later). Illumination direction and altitude defaulted to 335 and 45, and the anchor to viewport. A `color-relief` layer (JS 5.6.0 and later) mapped a decoded elevation through an interpolate ramp. 3D terrain was the root `terrain` property (JS 2.2.0 and later). The map-projection and globe options existed from 5.0.0.
- DEM details. Each tile was padded by 2 px and backfilled from its eight neighbours, so native hillshade had no seams, and nothing wider than a 3 by 3 kernel was possible natively. Fully transparent pixels were expected to decode as -32768 m for terrarium, which the report marked "likely". `addProtocol` handlers could return an ImageBitmap, which allowed a client-side compute pipeline in the style of maplibre-contour.
- The National Library of Scotland already ran an in-browser pipeline. Its explore viewer loaded `slrm-layer.js` ("Live computed LiDAR", v1.3, October 2026), which computed SLRM and a movable-sun hillshade from 512 px terrarium tiles. Its radius presets were Small 6 m, Medium 15 m and Broad 35 m, with a range of 1 m to 2.5 km. The code was proprietary, with reuse and reverse engineering forbidden, so it served only as a user-interface reference. Evidence: https://maps.nls.uk/guides/lidar/
- Native British National Grid rendering became possible in 6.15.0 through the experimental `addProjection`. Every source, including the basemap, would then have to be served in that grid. The report advised staying on Web Mercator.
- An idea, marked "uncertain" and untested: `color-relief` accepts any raster-dem source, so a precomputed scalar such as SLRM in metres could be coloured in the browser with an adjustable ramp. It needed a prototype.

### What a server could do

- Timings came from the report's own numpy implementation, on an Apple M4 Pro, single thread, tile plus 20 px buffer, in the table below. They exclude the COG read and the PNG encode. `rvt_py` itself was not executed.

| Visualisation | 256 px | 512 px |
|---|---|---|
| Slope and hillshade | 0.5 ms | 0.8 ms |
| 16-direction hillshade | 4 ms | 9 ms |
| SLRM, r = 20 | 1.2 ms | 2.8 ms |
| Sky-view factor plus openness, r = 10 | 9.7 ms | 31 ms |
| VAT general | 11 ms | 35 ms |
| VAT flat | 12.5 ms | 39 ms |
| Combined VAT | 24 ms | 75 ms |
| Local dominance, 10-20 px | 33 ms | 114 ms |
| MSTP, 500 px buffer | 441 ms | 672 ms |

- Kokalj and Somrak Table 2 reported 3 s for a 1000 by 1000 VAT with 2019 tooling. Scripts: `bench_vis.py` and `bench_mstp_ld.py` in the research scratchpad, folder `research/lidar-visualisation/scripts/`.
- Buffered fetches removed seams. On 4 by 4 tiles of 256 px, a buffer equal to the search radius matched the whole-array result exactly (maximum difference 0.00000). One pixel less left small seams. No buffer gave errors up to 4.7 degrees in openness, 0.46 m in SLRM and 0.11 to 0.33 of full range in VAT. `rvt/tile.py` gave the overlaps: 1 px for slope and hillshade, `svf_r_max` for sky-view factor and openness, `slrm_rad_cell` for SLRM, and 500 px for MSTP. NLS built its Combined VAT from 5 km tiles with a 50 m buffer.
- `rvt_py` was awkward to deploy. PyPI 2.2.3 (2025-07-04) required Python `>=3.6,<3.12` and installed gdal, geopandas, jupyter and rasterio. numpy 2.5.4 and xarray-spatial 0.10.20 required Python 3.12 or later, so they could not share an environment with it. `rvt.vis` imported only numpy and scipy. Evidence: https://pypi.org/pypi/rvt-py/json
- Alternatives shipped no VAT blend. xarray-spatial 0.10.20 (MIT) listed sky-view factor, hillshade and TPI. WhiteboxTools (MIT) had multidirectional hillshade and multiscale topographic position. TiTiler core 2.4.0 (MIT) had HillShade, Slope, Terrarium and TerrainRGB. richdem was GPLv3 and last released in 2018. The report put the VAT blend at about 20 lines of numpy.
- Resampling before derivatives. On the analytic 0.10 m ridge and furrow resampled from 1 m to 0.735 m, slope RMSE was nearest 0.94, bilinear 0.27, cubic 0.11 and compute-then-warp 0.40 degrees without noise. With 2 cm noise it was nearest 1.38, bilinear 0.72, cubic 0.99 and compute-then-warp 0.68 degrees.
- Ground pixel size at 256 px was 0.77 m at 50 N, 0.74 m at 52 N and 0.60 m at 60 N at z17. Great Britain was roughly 7.1 million z17 tiles. At about 27 KB per paletted PNG that was around 200 GB per pre-rendered layer. A terrarium set at z16 in lossless WebP was about 250 GB. A real 512 px z16 terrarium tile was 244 KB as PNG and 141 KB as lossless WebP at 1/256 m, 119 KB at 1/128 m, 96 KB at 1/64 m and 75 KB at 1/32 m.
- Mapterhorn's UK terrarium tiles rounded elevation by zoom: 1/32 m at z16, 1/16 m at z15 and 1/2 m at z12. The report judged them too coarse for analysis and suitable as a 3D fallback.
- The report found one existing product that overlapped: waystone-ai.org, described as a "Free LiDAR Map of England & Wales and 850,000 Historic Sites". Only its landing page was read.

### Sources and suggested use

Reuse class and access mode follow Decision 0004 and Decision 0007.

| Source | Reuse class | Suggested access mode | Required wording, as recorded |
|---|---|---|---|
| `rvt_py` algorithms and presets | open, Apache-2.0 | reimplement, no data stored | README asks users to cite Zaksek, Ostir, Kokalj 2011 (Remote Sensing 3: 398-415); Kokalj, Zaksek, Ostir 2011 (Antiquity 85: 263-273); Kokalj and Somrak 2019 (Remote Sensing 11(7): 747) |
| NLS RVT multi-direction hillshade, England | open, derived from Environment Agency data under the Open Government Licence | live | "(c) Environment Agency copyright and/or database right 2022. All rights reserved." plus credit to NLS and the RVT processing |
| NLS RVT multi-direction hillshade, Wales | open | live | "Contains public sector information licensed under the Open Government Licence v3.0." |
| NLS RVT multi-direction hillshade, Scotland phases 1-6 and Hebrides | open, per-phase Crown copyright; licence per phase not checked | live | per phase, for example Phase 1 "Crown copyright Scottish Government, SEPA and Scottish Water (2012)" |
| NLS Combined VAT, England | open underlying data; not on NLS's reuse list | deeplink | "(c) Environment Agency copyright 2022. With thanks to Richard Pearson for processing using RVT" |
| NLS terrarium tiles, England and Wales | open underlying data; not on NLS's reuse list | deeplink | "LiDAR DTM: Environment Agency, DataMapWales, Open Government Licence" |
| NLS Sherwood Forest 16 cm tiles | link_only, "(c) 2021 Miner2Major Veiled Landscape Project", no open licence | deeplink | as the licence line |
| Environment Agency 1 m WMS hillshade | open, Open Government Licence | live | "(c) Environment Agency copyright and/or database right 2022. All rights reserved." |
| DataMapWales LiDAR tiles | open as credited by NLS, not checked on the publisher's page; no CORS | deeplink | "Contains public sector information licensed under the Open Government Licence v3.0." |
| Mapterhorn terrarium tiles | open, UK entries Open Government Licence | live, as fallback terrain | "(c) Mapterhorn" linking to https://mapterhorn.com/attribution |
| AWS Terrain Tiles (Mapzen) | licence not checked | live, as low-zoom fallback only | none found |
| Kokalj and Hesse 2017 guide | non_commercial in effect, CC BY-NC-ND 4.0 | deeplink, cite only | none recorded |
| Kokalj and Somrak 2019, EAC Guidelines 10 | open, CC BY 4.0 | deeplink, cite | none recorded |
| MapLibre GL JS | open, BSD-3-Clause | library, no data | none recorded |

Suggested use, from the research report:

- Render Combined VAT on the server as the default layer, from the 1 m DTM in EPSG:27700, and tile to Web Mercator at z17 for 256 px tiles or z16 for 512 px.
- Write a small numpy module for hillshade, multi-hillshade, slope, SLRM, sky-view factor, openness, local dominance and the VAT blend. Take radii in metres and convert with r_px = round(r_m / ground_pixel_size). Cite the papers.
- Fetch each tile with a buffer of at least the largest search radius in pixels: 1 for slope and hillshade, 10 for VAT general, 20 for VAT flat, Combined VAT, SLRM r = 20 and local dominance. Crop after computing. Pre-render MSTP offline only.
- Use linear stretches only. RVT 2.1.0 switched its 8-bit defaults to value mode to avoid a tiling effect, and Kokalj and Somrak noted that percentile clipping breaks comparability between areas.
- Publish the DTM as a terrarium raster-dem set, 512 px, lossless WebP or PNG, maximum zoom 16, alpha 255 everywhere and a vertical step no coarser than 1/128 m. Use it for 3D terrain, the height readout, profiles and a steerable hillshade.
- Where MapLibre's own hillshade is used, set `hillshade-method` to `multidirectional` or `basic` and `hillshade-illumination-anchor` to `map`. Prototype the custom-encoding workaround.
- Warp with bilinear resampling and never nearest.
- Store the visualisation id and full parameter set with every finding, as the EAC guidelines ask for full documentation of visualisation parameters.
- Do not use Mapbox terrain-RGB or Mapterhorn as the analysis DEM.
- Review waystone-ai.org for overlap before building.

### Not tested

- No browser test was made of MapLibre's 8-bit slope quantisation or of the custom-encoding workaround.
- `rvt_py` was inspected and not executed, so its per-tile speed was unknown.
- Whether `color-relief` could usefully render scalar tiles such as SLRM was not tried.
- The licence of each Scottish LIDAR phase was recorded only as the copyright statements that NLS quoted.
- Whether NLS would allow hot-linking of its Combined VAT or terrarium tiles was not asked.

## Outcome

The browser could not render the standard archaeological blend on its own. MapLibre GL JS 6.17.0 had no raster blend modes, and the blend needs multiply, overlay and luminosity. The report also read from source that its hillshade quantised slope to about 2.9 degree steps. It rated that "likely" and did not test it in a browser. The server could render Combined VAT for a 512 px tile in about 75 ms in numpy, so server-side rendering was cheap per tile. The browser could still relight elevation and colour a single channel from terrarium tiles. The answer is NO for the blend, and the browser was left the elevation-driven layers.
