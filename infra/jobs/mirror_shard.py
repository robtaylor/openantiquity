"""Shares of the whole-country elevation copy, run one after another on one machine.

    python /app/jobs/mirror_shard.py --shares 4 --share 1 [--share 3] [--concurrency 1]

The England catalogue is split into `--shares` shares of about equal size, the
same way on every run, and `fieldclub-terrain mirror` is run on each `--share`
named, numbered from 1, in the order given. On Fly two machines run two shares
each (infra/README.md), so the copy holds two connections to Defra's server.
Each share holds one connection unless told otherwise. A share stops early if
the supply refuses the login or several tiles fail in a row (`fieldclub-terrain
mirror`), and then the run stops with that share's exit status, so a broken
supply isn't asked about every tile. The LIDAR `sources` rows are left to
`fieldclub-terrain sources` (`--skip-sources`; infra/README.md).

A tile already in the mirror is skipped, so a failed or interrupted share can be
run again and only fetches what is still missing.
"""

from __future__ import annotations

import argparse
import logging
import sys

from fieldclub.terrain import cli
from fieldclub.terrain.catalogue import SourceTile, england_catalogue

logger = logging.getLogger("mirror_shard")


def shares(tiles: list[SourceTile], count: int) -> list[list[str]]:
    """Tile names split into `count` shares of about equal bytes, the same on every run.

    Largest first, each to the share with the fewest bytes so far, ties to the
    lowest index.
    """
    assert count >= 1, "there must be at least one share"
    names: list[list[str]] = [[] for _ in range(count)]
    totals = [0] * count
    for tile in sorted(tiles, key=lambda t: (-t.size, t.name)):
        index = min(range(count), key=lambda i: (totals[i], i))
        names[index].append(tile.name)
        totals[index] += tile.size
    assert sum(map(len, names)) == len(tiles), "every tile is in exactly one share"
    return [sorted(share) for share in names]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Shares of the whole-country elevation copy.")
    parser.add_argument(
        "--shares", type=int, required=True, help="how many shares the catalogue is split into"
    )
    parser.add_argument(
        "--share", type=int, action="append", required=True, help="a share to run, from 1; may be repeated"
    )
    # The range `fieldclub-terrain mirror --concurrency` accepts.
    parser.add_argument("--concurrency", type=int, default=1, choices=range(1, 5), metavar="1-4")
    args = parser.parse_args(argv)
    if args.shares < 1:
        parser.error("--shares must be at least 1")
    if bad := [share for share in args.share if not 1 <= share <= args.shares]:
        parser.error(f"--share {bad[0]} isn't between 1 and {args.shares}")
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    split = shares(list(england_catalogue()), args.shares)
    for number in args.share:
        share = split[number - 1]
        logger.info("Share %d of %d: %d tiles", number, args.shares, len(share))
        if not share:
            continue
        status = cli.main(["mirror", *share, "--concurrency", str(args.concurrency), "--skip-sources"])
        if status != 0:
            logger.error("Share %d of %d stopped with status %d", number, args.shares, status)
            return status
    return 0


if __name__ == "__main__":
    sys.exit(main())
