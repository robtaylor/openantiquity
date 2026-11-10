"""`fieldclub-terrain`: fill the elevation mirror, warm the tile cache, and say what the mirror holds.

    fieldclub-terrain mirror SU16nw SU16ne          named tiles
    fieldclub-terrain mirror --bbox=-1.9,51.4,-1.8,51.45
    fieldclub-terrain mirror --all --concurrency 2  all of England, resumable
    fieldclub-terrain warm --bbox=-1.9,51.4,-1.8,51.45 --zooms 13-16 [--styles composite,slope]
    fieldclub-terrain national download|convert     the 10 m composite for low zooms
    fieldclub-terrain info

Mirroring skips tiles already in the mirror and resumes partial downloads,
so an interrupted run can simply be started again.
"""

from __future__ import annotations

import argparse
import logging
import sys
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from fieldclub.config import get_settings
from fieldclub.errors import AppError
from fieldclub.gridref import transformer
from fieldclub.terrain import national
from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.grid import tiles_in
from fieldclub.terrain.service import Terrain, build_terrain, national_location
from fieldclub.terrain.styles import FINE_MINZOOM, MAXZOOM, MINZOOM, STYLES

logger = logging.getLogger(__name__)


def parse_bbox(text: str) -> tuple[float, float, float, float]:
    parts = [float(part) for part in text.split(",")]
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("a box is west,south,east,north in degrees")
    west, south, east, north = parts
    if not (west < east and south < north):
        raise argparse.ArgumentTypeError("a box needs west < east and south < north")
    return west, south, east, north


def parse_zooms(text: str) -> range:
    low, _, high = text.partition("-")
    first, last = int(low), int(high or low)
    if not MINZOOM <= first <= last <= MAXZOOM:
        raise argparse.ArgumentTypeError(f"zooms run from {MINZOOM} to {MAXZOOM}")
    return range(first, last + 1)


def tiles_for_bbox(terrain: Terrain, bbox: tuple[float, float, float, float]) -> list[SourceTile]:
    west, south, east, north = bbox
    eastings, northings = transformer(4326, 27700).transform(
        [west, east, east, west], [south, south, north, north]
    )
    return terrain.catalogue.covering((min(eastings), min(northings), max(eastings), max(northings)))


class Progress:
    """One line on stderr, rewritten in place."""

    def __init__(self, total: int, label: str) -> None:
        self.total, self.label, self.done, self.failed = total, label, 0, 0
        self.started = time.monotonic()

    def step(self, note: str, *, failed: bool = False) -> None:
        self.done += 1
        self.failed += failed
        elapsed = time.monotonic() - self.started
        eta = elapsed / self.done * (self.total - self.done)
        sys.stderr.write(
            f"\r{self.label} {self.done}/{self.total}  failed {self.failed}  "
            f"{elapsed:.0f}s elapsed, ~{eta:.0f}s left  {note:<24}"
        )
        sys.stderr.flush()

    def finish(self) -> None:
        sys.stderr.write("\n")


def run_parallel[T](
    items: Iterable[T],
    work: Callable[[T], object],
    concurrency: int,
    label: str,
    name: Callable[[T], str] = str,
) -> int:
    """Run `work` on each item with a pool, showing progress by `name`. Returns how many failed."""
    jobs = list(items)
    progress = Progress(len(jobs), label)
    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(work, job): name(job) for job in jobs}
        for future in as_completed(futures):
            job_name = futures[future]
            try:
                future.result()
                progress.step(job_name)
            except (AppError, OSError) as exc:
                progress.step(job_name, failed=True)
                logger.error("%s failed: %s", job_name, exc)
    progress.finish()
    return progress.failed


def cmd_mirror(terrain: Terrain, args: argparse.Namespace) -> int:
    if args.all:
        tiles = list(terrain.catalogue)
    elif args.bbox:
        tiles = tiles_for_bbox(terrain, args.bbox)
    else:
        tiles = []
        for name in args.tiles:
            tile = terrain.catalogue.get(name)
            if tile is None:
                print(f"{name}: not in the {terrain.catalogue.edition} catalogue, skipped")
            else:
                tiles.append(tile)
    missing = [tile for tile in tiles if not terrain.mirror.has(tile.name)]
    size = sum(tile.size for tile in missing)
    print(f"{len(tiles)} tiles asked for, {len(missing)} to add ({size / 1e9:.1f} GB of source)")
    failed = run_parallel((t.name for t in missing), terrain.mirror.ensure, args.concurrency, "mirror")
    return 1 if failed else 0


def cmd_warm(terrain: Terrain, args: argparse.Namespace) -> int:
    styles = args.styles.split(",") if args.styles else list(STYLES)
    unknown = [style for style in styles if style not in STYLES]
    if unknown:
        print(f"unknown styles: {', '.join(unknown)}")
        return 2
    jobs = [(z, x, y) for z in args.zooms for x, y in tiles_in(args.bbox, z)]
    print(f"{len(jobs)} map tiles in {len(styles)} styles plus elevation")

    def warm(tile: tuple[int, int, int]) -> None:
        terrain.renderer.dem_png(*tile)
        for style in styles:
            terrain.renderer.lidar_png(style, *tile)

    failed = run_parallel(jobs, warm, args.concurrency, "warm", name=lambda tile: "/".join(map(str, tile)))
    return 1 if failed else 0


def cmd_national(terrain: Terrain, args: argparse.Namespace) -> int:
    path, exists = national_location(get_settings())
    if "://" in path or path.startswith("/vsi"):
        print(
            "The national composite is built locally and then uploaded. "
            "Point FIELDCLUB_TERRAIN_NATIONAL at a local file."
        )
        return 2
    dest = Path(path)
    zip_path = dest.parent / national.ZIP_NAME
    if args.action == "download":

        def show(have: int, total: int) -> None:
            sys.stderr.write(f"\rdownload {have / 1e9:.2f}/{total / 1e9:.2f} GB")

        national.download(zip_path, on_progress=show)
        sys.stderr.write("\n")
        print(f"downloaded {zip_path}")
        return 0
    if not zip_path.is_file():
        print(f"{zip_path} isn't there yet: run `fieldclub-terrain national download` first")
        return 1
    started = time.monotonic()
    national.convert(zip_path, dest)
    print(
        f"wrote {dest} ({dest.stat().st_size / 1e9:.2f} GB) in {time.monotonic() - started:.0f}s; "
        f"in use: {exists()}"
    )
    return 0


def cmd_info(terrain: Terrain, args: argparse.Namespace) -> int:
    catalogue = terrain.catalogue
    held = [name for name in terrain.mirror.store.names() if name in catalogue]
    held_names = set(held)
    held_bytes = sum(tile.size for tile in catalogue if tile.name in held_names)
    print(f"edition      {terrain.mirror.edition}")
    print(f"mirror       {terrain.mirror.store!r}")
    print(f"catalogue    {len(catalogue)} tiles, {catalogue.total_bytes / 1e9:.1f} GB of source")
    print(
        f"mirrored     {len(held)} tiles ({100 * len(held) / len(catalogue):.2f}%), "
        f"{held_bytes / 1e9:.2f} GB of source"
    )
    print(f"national     {'built' if terrain.national_available() else 'not built'}")
    print(
        f"zooms        {MINZOOM}-{FINE_MINZOOM - 1} from the national 10 m, "
        f"{FINE_MINZOOM}-{MAXZOOM} from the 1 m mirror"
    )
    if held:
        print(f"tiles        {' '.join(held[:40])}{' ...' if len(held) > 40 else ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fieldclub-terrain",
        description="Fill the elevation mirror, warm the tile cache, and report on both.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    mirror = sub.add_parser("mirror", help="add source tiles to the mirror")
    mirror.add_argument("tiles", nargs="*", default=[], help="tile names such as SU16nw")
    mirror.add_argument("--bbox", type=parse_bbox, help="west,south,east,north in degrees")
    mirror.add_argument("--all", action="store_true", help="every tile in the catalogue")
    mirror.add_argument("--concurrency", type=int, default=2, choices=range(1, 9), metavar="1-8")
    warm = sub.add_parser("warm", help="render and cache tiles for a box")
    warm.add_argument("--bbox", type=parse_bbox, required=True)
    warm.add_argument("--zooms", type=parse_zooms, default=parse_zooms(f"{FINE_MINZOOM}-{MAXZOOM}"))
    warm.add_argument("--styles", help="comma-separated style ids; all by default")
    warm.add_argument("--concurrency", type=int, default=4, choices=range(1, 17), metavar="1-16")
    nat = sub.add_parser("national", help="the national 10 m composite")
    nat.add_argument("action", choices=["download", "convert"])
    sub.add_parser("info", help="what the mirror holds")
    return parser


COMMANDS = {"mirror": cmd_mirror, "warm": cmd_warm, "national": cmd_national, "info": cmd_info}


def main(argv: list[str] | None = None, *, terrain: Terrain | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    if args.command == "mirror" and sum(map(bool, (args.tiles, args.bbox, args.all))) != 1:
        build_parser().error("mirror takes tile names, or --bbox, or --all")
    try:
        return COMMANDS[args.command](terrain or build_terrain(), args)
    except AppError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
