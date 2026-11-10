# Decision 0012 — The national overview is built from our own mirror

**Status:** Proposed.

**TL;DR.** In the context of drawing map tiles below zoom 13 for all of England, facing a 10 m national composite that Defra's server wouldn't deliver, we chose to mosaic the 8 m overviews already inside our own mirrored 5 km tiles into one cloud-optimised file per build, versioned by the tiles it holds, to get cacheable low-zoom tiles from the same edition as the 1 m data, accepting that the overview only covers what has been mirrored and must be rebuilt as the mirror grows.

## Context

When this was written, the code read low zooms from the overviews of whichever 1 m tiles happened to be mirrored, uncached, while it waited for Defra's 10 m composite.

Decision 0006 had planned the national 10 m composite for zooms 7 to 12. It was one zip of 5,301,314,401 bytes. On 2026-11-10 the server closed every transfer after about 1.08 GB, at any speed, over HTTP/1.1 and HTTP/2, and answered every Range request with the whole file, so the download could neither finish nor resume. The partial file was deleted.

Every tile the mirror adds is a COG with internal overviews at 2, 4 and 8 m. Reading a tile's 8 m overview took 13 ms on a laptop. Measured on the eleven local tiles, a 5 km tile at 8 m came to 0.58 MB with the mirror's LERC encoding at 1 cm.

A 512-pixel tile at zoom 12 spans about 6 km and touches up to nine 5 km tiles, and at zoom 7 a few hundred. Reading those from the mirror for each tile was too slow to serve and couldn't be cached, because the answer changed as the mirror filled.

## Decision

1. Zooms below 13 read one national COG at 8 m with overviews at 16 to 512 m, on a grid whose edges are multiples of 512 m from the British National Grid origin, so every level lands on the same global grid in every build.
2. The COG is built by `fieldclub-terrain national build` from the 8 m overviews of the mirrored tiles, through 50 km chunks kept in the work directory. A build reads only the tiles no chunk holds yet, and an interrupted build resumes at the next unfinished chunk.
3. Each build is a new file named by a hash of the tiles it holds. `national.json` in the same folder names the current one, and the previous build is kept for servers that haven't looked again yet.
4. The build is part of the edition that tile cache keys and URL tokens carry, so a rebuild changes the token `/meta` hands out and nothing cached under the old one is reused for it.
5. A low-zoom tile that touches a 5 km tile the build doesn't hold draws what the mirror has there and is sent as uncacheable, so an area mirrored since the last build still draws.

## Alternatives considered

- **Keep trying Defra's 10 m download** was rejected because nothing on our side could get past the 1.08 GB cut, and the file was resampled from the 2 m composite, so it would have been a second edition beside the 1 m one.
- **Read the 2 m DTM folder of the bulk supply** was rejected because it is 149.8 GB and would have been a third copy of the same survey data to fetch and convert.
- **Update one COG in place** was rejected because the COG layout puts overviews first and can't be appended to. A whole new file per build is simpler and makes the switch atomic.
- **Pre-render low-zoom map tiles instead of an elevation overview** was rejected because every style and the elevation tiles need the elevation, and a style change would mean rendering the country again.
- **Read the mirror at low zooms, cached by tile** was rejected because a cached tile would hide every tile mirrored after it was drawn, and an uncached one costs hundreds of reads at zoom 7.

## Consequences

- Low-zoom tiles are cacheable and immutable under their token once the overview holds every tile they touch.
- The overview comes from the same files as the 1 m tiles. Over Avebury, zoom 12 from the overview meets zoom 13 from the mirror without a visible step.
- England in full is estimated at 3.5 GB: 81,344 by 87,552 pixels. On a 14-core laptop the COG write took 56 s and the chunks 106 s from tile data already in memory.
- Coverage below zoom 13 is only as complete as the mirror. Until a build holds a tile, low zooms draw it from the mirror uncached, and past 64 such tiles in view they don't draw it at all.
- Old builds' cached tiles stay in the tile cache until something removes them.
- A fresh machine has no chunks, so its first build reads every mirrored tile again.

## Walk-back options

- **If Defra publishes a downloadable national composite of the same edition**, a build can read it in place of the chunks. The grid, the manifest and the versioning stay.
- **If builds grow too slow for one machine**, the chunks can be built in parallel jobs, because each chunk is independent until the final VRT.

## Links

- Decision 0006 — renders terrain from raw elevation and planned the 10 m composite this replaces.
- `../../sources/lidar-england-bulk-supply.md` — the bulk supply the mirror is filled from.
