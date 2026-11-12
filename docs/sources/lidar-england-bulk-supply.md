# England LIDAR bulk supply from Defra

On 2026-11-10 the Defra Data Services Platform service desk gave OpenAntiquity's owner access to its LIDAR archive over SFTP, in answer to a Large Dataset request with ticket reference DSP3-11967. The reply came seven minutes after the request was acknowledged. This page records what was found on the supply that day.

The connection details are in the owner's email under that ticket. Scripts read them from the untracked `.env` file as `DEFRA_SFTP_HOST`, `DEFRA_SFTP_USER` and `DEFRA_SFTP_PASSWORD`. They aren't written anywhere in this repository.

## Summary

| Source | Publisher | Coverage | Licence | Reuse | Mode | Records |
|---|---|---|---|---|---|---|
| LIDAR Composite DTM 2022, 1 m, bulk supply | Environment Agency through the Defra Data Services Platform | England | Open Government Licence v3.0 | open | bulk | 5,877 tiles, 353.6 GB |

## What Defra said

The service desk answered the request's three questions by email on 2026-11-10.

- The 2022 composite, together with the 1 m DTM tiles, was the latest data available. There was no newer edition to supply.
- Access to the SFTP supply had no time limit, and it could be used to download whatever data was needed.
- The WMS and WCS services could be built into third-party applications. They were tuned for live map viewing, not for bulk harvesting. A use that cached responses and asked only for missing areas was expected to fit. For the core dataset Defra said it would "highly recommend using the bulk supply".

The owner replied the same day to confirm that access worked.

## Layout

The request named the composite. The account could also list the rest of the archive. Only the composite folder was read.

| Folder | Observed on 2026-11-10 |
|---|---|
| `composite/2022/GeoTiffs/1m/DTM` | 5,877 `.tif` files, 353.6 GB. Each had a `.tfw`, two `.xml` files and a `.tif.ovr` overview file. The overviews came to a further 153.0 GB |
| `composite/2022/Zip_Files/1m/DTM` | 5,877 zips, 349.5 GB, named `LIDAR-DTM-1m-2022-<tile>.zip` |
| `composite/2022/GeoTiffs/2m/DTM` | 28,242 files, 149.8 GB with sidecar files included |
| `composite/2022/GeoTiffs/1m/FZ_DSM` and `LZ_DSM`, and the same under `2m` | Surface models. Not opened |
| `national-lidar-program/processed` | 42 folders named by product and year from 2016 to 2022, among them DTM, DSM and VOM. Not opened |
| `national-lidar-program/raw` | 333 folders named by survey polygon, `P_10585` to `P_13024`. Not opened |
| `timestamped-archive/processed` | 159 folders named by product, resolution and year. The 1 m DTM folders ran from 2000 to 2022. Not opened |
| `point-cloud` | `processed` and `raw`. Not opened |
| `national-lidar-program-cog/raw` | Empty |

The folder is lower-case `composite`. Defra's email called it "Composite", and that spelling returned a directory-not-found error.

A tile file is named `<tile>_DTM_1m.tif`. The tile name is the 10 km grid square followed by its 5 km quadrant, so `SU16nw` covers eastings 410000 to 415000 and northings 165000 to 170000. The research found 5,876 tiles in the public catalogue. The supply held 5,877.

## One tile opened

`SU16nw`, which covers the eastern half of Avebury, was downloaded and decoded.

| Property | Value |
|---|---|
| Size | 5,000 by 5,000 pixels, one band, 48.2 MB |
| Data type | 32-bit float, metres |
| Coordinate system | EPSG:27700, 1 m pixels |
| Bounds | 410000, 165000 to 415000, 170000 |
| No-data value | -3.4028234663852886e+38, with the tag set |
| Internal layout | 128-pixel blocks, LZW compression, no internal overviews |
| Valid pixels | 25,000,000 of 25,000,000 |
| Minimum, maximum, mean | 132.52 m, 260.20 m, 181.98 m |

Those three statistics are the same as the research recorded for this tile from the public download, so the supply holds the same files.

Every `.tif` in the folder carried a modification date of 2026-05-28.

## Transfer behaviour

| Test | Result |
|---|---|
| Speed on one connection from a UK home line | 84.0 MB in 10.5 s including sign-in, about 8 MB/s |
| Whole-file read with the client's default read-ahead | The server dropped the connection at 54,493,184 bytes. Two files failed this way, three attempts each |
| Read in windows of 8 MiB, reopening the file handle for each | Completed, and resumed a partial file correctly |
| Read in windows of 32 MiB | Completed at the same speed |
| Tiles larger than 52 MiB | 4,054 of 5,877 |
| Host key | `ecdsa-sha2-nistp256`, fingerprint `SHA256:vp1YdDYlFLMB/r/5jb86NNGUn1HWEiZ5z1CdB1mT7No` |
| Two connections at once, three tiles, the same evening at about 21:45 | 184.7 MB in 96 s, 1.9 MB/s in all. One tile alone took 51.0 MB in 32.3 s, 1.6 MB/s. Both connections worked |

At the speed observed first, one connection would take about twelve hours for the 1 m DTM. At the evening's 1.9 MB/s over two it would take about 52 hours.

## Suggested use

Take the 1 m DTM GeoTIFFs. Leave the zips, which hold the same data, and the `.ovr` files, which a conversion to cloud-optimised GeoTIFF replaces. Read every file in windows and resume on failure, because most tiles are over the size at which a whole-file read was cut off. Pin the host key.

The 2 m DTM could serve middle zoom levels without building overviews. That wasn't tested.

Defra's wording covers the data the project needs. The folders beyond the composite weren't asked for by name, so take from them only what the product uses, such as surveys flown after the composite was built.

## Open questions

- Whether Defra refreshes this supply as new surveys are published. The year folders seen ended at 2022, while the research found DTM tiles dated up to 2024 in the public catalogue.
- The size of the surface-model folders.
- Whether more than two connections at once are tolerated. Two worked.
- Why the evening's transfers ran at a quarter of the first speed: the line, the time of day or the server.
