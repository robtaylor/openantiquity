"""`fieldclub-terrain`: fill the elevation mirror, build the national overview, warm the tile cache, report.

    fieldclub-terrain mirror SU16nw SU16ne          named tiles
    fieldclub-terrain mirror --bbox=-1.9,51.4,-1.8,51.45
    fieldclub-terrain mirror --all --concurrency 2  all of England, resumable
    fieldclub-terrain national build                the overview for zooms below 13
    fieldclub-terrain warm --bbox=-1.9,51.4,-1.8,51.45 --zooms 13-16 [--styles composite,slope]
    fieldclub-terrain years build                   capture years from Defra's survey index
    fieldclub-terrain sources                       the LIDAR rows in the sources table
    fieldclub-terrain info

Mirroring lists the mirror once, skips the tiles it already holds and resumes
partial downloads, so an interrupted run is simply started again. Each tile
is read back as a COG before it is published, and its stored size (and, in a
bucket, its CRC32C) is checked after. `--concurrency` is how many tiles are in
hand at once. At most `FIELDCLUB_TERRAIN_FETCH_CONCURRENCY` of them are being
downloaded, each over its own SFTP connection, kept open from tile to tile.

The commands that store or show elevation write its `sources` rows first,
which needs the database. `--skip-sources` leaves that to a later
`fieldclub-terrain sources` where the database can be reached.
"""

from __future__ import annotations

import argparse
import logging
import sys
import threading
import time
from collections.abc import Callable, Iterable
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import TextIO

from sqlalchemy.exc import OperationalError

from fieldclub.config import get_settings
from fieldclub.errors import AppError
from fieldclub.gridref import transformer
from fieldclub.terrain import years
from fieldclub.terrain.attribution import register_sources
from fieldclub.terrain.catalogue import SourceTile
from fieldclub.terrain.errors import CredentialsMissingError, SupplyRefusedError
from fieldclub.terrain.grid import tiles_in
from fieldclub.terrain.national import Builder
from fieldclub.terrain.service import Terrain, build_terrain
from fieldclub.terrain.styles import DEFAULT_STYLE, FINE_MINZOOM, MAXZOOM, MINZOOM, STYLES

logger = logging.getLogger(__name__)

# How often a long run writes a progress line to the log, for a machine nobody is watching.
LOG_EVERY_S = 60.0


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


def _duration(seconds: float) -> str:
    seconds = max(0, round(seconds))
    hours, rest = divmod(seconds, 3600)
    return f"{hours}h{rest // 60:02d}m" if hours else f"{rest // 60}m{rest % 60:02d}s"


class Progress:
    """One line on stderr, rewritten in place, and a line in the log every `log_every_s`.

    With `total_bytes`, the time left comes from the bytes done, because tiles
    differ in size by a factor of a hundred.
    """

    def __init__(
        self,
        total: int,
        label: str,
        *,
        total_bytes: int | None = None,
        out: TextIO | None = None,
        log_every_s: float = LOG_EVERY_S,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.total, self.label, self.done, self.failed = total, label, 0, 0
        self.total_bytes, self.done_bytes = total_bytes, 0
        self.out = out or sys.stderr
        self.log_every_s = log_every_s
        self.clock = clock
        self.started = self._logged = clock()

    def line(self) -> str:
        elapsed = self.clock() - self.started
        if self.total_bytes:
            share = self.done_bytes / self.total_bytes
            amount = f"{self.done_bytes / 1e9:.1f}/{self.total_bytes / 1e9:.1f} GB"
            rate = f", {self.done_bytes / 1e6 / elapsed:.1f} MB/s" if elapsed > 0 else ""
        else:
            share, amount, rate = (self.done / self.total if self.total else 1.0), "", ""
        left = elapsed / share * (1 - share) if share > 0 else float("nan")
        eta = _duration(left) if share > 0 else "?"
        return (
            f"{self.label} {self.done}/{self.total} {amount}  failed {self.failed}  "
            f"{_duration(elapsed)} elapsed{rate}, about {eta} left"
        )

    def step(self, note: str, *, failed: bool = False, size: int = 0) -> None:
        self.done += 1
        self.failed += failed
        self.done_bytes += size
        line = self.line()
        self.out.write(f"\r{line}  {note:<12}")
        self.out.flush()
        if self.clock() - self._logged >= self.log_every_s:
            self._logged = self.clock()
            logger.info("%s", line)

    def finish(self) -> None:
        self.out.write("\n")
        logger.info("%s", self.line())


def run_parallel[T](
    items: Iterable[T],
    work: Callable[[T], object],
    concurrency: int,
    label: str,
    name: Callable[[T], str] = str,
    size: Callable[[T], int] | None = None,
    *,
    stop_on: tuple[type[BaseException], ...] = (),
    max_failures_in_a_row: int | None = None,
) -> list[str]:
    """Run `work` on each item with a pool, showing progress by `name`.

    Stops starting new items after an error of a type in `stop_on`, or after
    `max_failures_in_a_row` failures with no success between them. Returns the
    names that failed or were never started.
    """
    assert max_failures_in_a_row is None or max_failures_in_a_row >= 1, "the limit must be at least one"
    jobs = list(items)
    total_bytes = sum(size(job) for job in jobs) if size is not None else None
    progress = Progress(len(jobs), label, total_bytes=total_bytes)
    failed: list[str] = []
    never_started: list[str] = []
    stop = threading.Event()
    counted = threading.Lock()
    in_a_row = 0

    def guarded(job: T) -> bool:
        """Run `job` unless the run has been told to stop. Whether it was started.

        The decision to stop is taken here, in the worker, so that no further
        item starts while the main thread is still catching up.
        """
        nonlocal in_a_row
        if stop.is_set():
            return False
        try:
            work(job)
        except (AppError, OSError) as exc:
            with counted:
                in_a_row += 1
                limit_reached = max_failures_in_a_row is not None and in_a_row >= max_failures_in_a_row
                if (isinstance(exc, stop_on) or limit_reached) and not stop.is_set():
                    logger.error("Stopping %s after %s: no further items will be started", label, name(job))
                    stop.set()
            raise
        with counted:
            in_a_row = 0
        return True

    with ThreadPoolExecutor(max_workers=concurrency) as pool:
        futures = {pool.submit(guarded, job): job for job in jobs}
        for future in as_completed(futures):
            job = futures[future]
            job_size = size(job) if size is not None else 0
            try:
                if not future.result():
                    never_started.append(name(job))
                    continue
                progress.step(name(job), size=job_size)
            except (AppError, OSError) as exc:
                progress.step(name(job), failed=True, size=job_size)
                failed.append(name(job))
                logger.error("%s failed: %s", name(job), exc)
    progress.finish()
    if never_started:
        logger.error("%s: %d of %d items were never started", label, len(never_started), len(jobs))
    return sorted(failed + never_started)


# A mirror run gives up after this many tiles fail in a row: the supply is
# down or refusing us, and asking about every remaining tile won't help.
MIRROR_FAILURES_IN_A_ROW = 5


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
    # One listing, not one request per tile.
    held = set(terrain.mirror.store.names())
    missing = [tile for tile in tiles if tile.name not in held]
    size = sum(tile.size for tile in missing)
    print(f"{len(tiles)} tiles asked for, {len(missing)} to add ({size / 1e9:.1f} GB of source)")
    failed = run_parallel(
        missing,
        lambda tile: terrain.mirror.ensure(tile.name),
        args.concurrency,
        "mirror",
        name=lambda tile: tile.name,
        size=lambda tile: tile.size,
        stop_on=(SupplyRefusedError, CredentialsMissingError),
        max_failures_in_a_row=MIRROR_FAILURES_IN_A_ROW,
    )
    if failed:
        shown = ", ".join(failed[:20]) + (" ..." if len(failed) > 20 else "")
        print(f"{len(failed)} tiles failed or weren't tried: {shown}. Run the same command again to retry them.")
        return 1
    print(f"added {len(missing)} tiles, each read back and checked before it was published")
    return 0


def cmd_national(terrain: Terrain, args: argparse.Namespace) -> int:
    def show(done: int, total: int, note: str) -> None:
        sys.stderr.write(f"\roverview {done}/{total} chunks  {note:<16}")
        sys.stderr.flush()

    builder = Builder(
        terrain.mirror,
        terrain.overview.store,
        terrain.mirror.work_dir,
        workers=args.workers,
        on_progress=show,
    )
    report = builder.build()
    sys.stderr.write("\n")
    if report.up_to_date:
        print(f"overview {report.build} already holds all {report.tiles} mirrored tiles")
        return 0
    print(
        f"built overview {report.build} from {report.tiles} tiles ({report.read} read from the mirror), "
        f"{report.bytes / 1e6:.1f} MB, in {_duration(report.seconds)}"
    )
    return 0


def cmd_warm(terrain: Terrain, args: argparse.Namespace) -> int:
    styles = args.styles.split(",") if args.styles else [DEFAULT_STYLE]
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


def cmd_years(terrain: Terrain, args: argparse.Namespace) -> int:
    from fieldclub.http import get_client

    dest = Path(args.out) if args.out else years.packaged_path()
    index = years.IndexClient(get_client())
    started = time.monotonic()
    found = years.build(terrain.catalogue, index, dest)
    print(
        f"wrote {dest}: {len(found)} of {len(terrain.catalogue)} tiles have capture years, "
        f"from {index.requests} requests, {index.bytes / 1e6:.1f} MB, "
        f"in {_duration(time.monotonic() - started)}"
    )
    return 0


def cmd_sources(terrain: Terrain, args: argparse.Namespace) -> int:
    # `_register` has already written them.
    return 0


def cmd_info(terrain: Terrain, args: argparse.Namespace) -> int:
    catalogue = terrain.catalogue
    held = [name for name in terrain.mirror.store.names() if name in catalogue]
    held_names = set(held)
    held_bytes = sum(tile.size for tile in catalogue if tile.name in held_names)
    snapshot = terrain.overview.snapshot()
    print(f"edition      {terrain.mirror.edition}")
    print(f"mirror       {terrain.mirror.store!r}")
    print(f"catalogue    {len(catalogue)} tiles, {catalogue.total_bytes / 1e9:.1f} GB of source")
    print(
        f"mirrored     {len(held)} tiles ({100 * len(held) / len(catalogue):.2f}%), "
        f"{held_bytes / 1e9:.2f} GB of source"
    )
    if snapshot.manifest is None:
        print("overview     not built")
    else:
        behind = len(held_names - snapshot.built)
        print(
            f"overview     {snapshot.manifest.build}, {len(snapshot.built)} tiles, "
            f"built {snapshot.manifest.created}" + (f", {behind} mirrored since" if behind else "")
        )
    print(
        f"zooms        {MINZOOM}-{FINE_MINZOOM - 1} from the overview, "
        f"{FINE_MINZOOM}-{MAXZOOM} from the 1 m mirror"
    )
    if held:
        print(f"tiles        {' '.join(held[:40])}{' ...' if len(held) > 40 else ''}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fieldclub-terrain",
        description="Fill the elevation mirror, build the national overview, warm the tile cache, report.",
    )
    sub = parser.add_subparsers(dest="command", required=True)
    mirror = sub.add_parser("mirror", help="add source tiles to the mirror")
    mirror.add_argument("tiles", nargs="*", default=[], help="tile names such as SU16nw")
    mirror.add_argument("--bbox", type=parse_bbox, help="west,south,east,north in degrees")
    mirror.add_argument("--all", action="store_true", help="every tile in the catalogue")
    mirror.add_argument("--concurrency", type=int, default=2, choices=range(1, 5), metavar="1-4")
    national = sub.add_parser("national", help="the national overview for zooms below 13")
    national.add_argument("action", choices=["build"])
    national.add_argument("--workers", type=int, default=4, choices=range(1, 17), metavar="1-16")
    warm = sub.add_parser("warm", help="render and cache tiles for a box")
    warm.add_argument("--bbox", type=parse_bbox, required=True)
    warm.add_argument("--zooms", type=parse_zooms, default=parse_zooms(f"{FINE_MINZOOM}-{MAXZOOM}"))
    warm.add_argument("--styles", help=f"comma-separated style ids; {DEFAULT_STYLE} by default")
    warm.add_argument("--concurrency", type=int, default=4, choices=range(1, 17), metavar="1-16")
    year = sub.add_parser("years", help="capture years from Defra's survey index")
    year.add_argument("action", choices=["build"])
    year.add_argument("--out", help="where to write them; the packaged file by default")
    sub.add_parser("sources", help="write the LIDAR rows of the sources table")
    sub.add_parser("info", help="what the mirror and the overview hold")
    for command in (mirror, national, year):
        command.add_argument(
            "--skip-sources", action="store_true", help="don't write the sources rows (no database here)"
        )
    return parser


COMMANDS = {
    "mirror": cmd_mirror,
    "national": cmd_national,
    "warm": cmd_warm,
    "years": cmd_years,
    "sources": cmd_sources,
    "info": cmd_info,
}
# The commands that store or show elevation, so need its `sources` rows first.
STORING = frozenset({"mirror", "national", "years", "sources"})


def _register() -> list[str]:
    from fieldclub.db import SessionLocal

    with SessionLocal() as db:
        keys = register_sources(db)
        db.commit()
    return keys


def main(argv: list[str] | None = None, *, terrain: Terrain | None = None) -> int:
    args = build_parser().parse_args(argv)
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    logging.getLogger("paramiko").setLevel(logging.WARNING)
    if args.command == "mirror" and sum(map(bool, (args.tiles, args.bbox, args.all))) != 1:
        build_parser().error("mirror takes tile names, or --bbox, or --all")
    if args.command in STORING and not getattr(args, "skip_sources", False):
        try:
            keys = _register()
        except OperationalError:
            logger.exception("Couldn't write the sources rows")
            print(
                "error: the database can't be reached to write the LIDAR sources rows. Run "
                "`fieldclub-terrain sources` where it can, or pass --skip-sources.",
                file=sys.stderr,
            )
            return 1
        print(f"sources rows written: {', '.join(keys)}")
    try:
        return COMMANDS[args.command](terrain or build_terrain(), args)
    except AppError as exc:
        print(f"error: {exc.message}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
