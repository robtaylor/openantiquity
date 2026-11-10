"""One task's share of the whole-country elevation copy, for a Cloud Run job.

    python /app/jobs/mirror_shard.py [--concurrency 1]

Cloud Run starts every task of a job with the same command and tells each one
which it is through CLOUD_RUN_TASK_INDEX and CLOUD_RUN_TASK_COUNT. This splits
the England catalogue into that many shares of about equal size, the same way
in every task, and runs `fieldclub-terrain mirror` on this task's share. Each
task holds one connection to Defra's server unless told otherwise, so the
job's parallelism is the number of connections the server sees.

A tile already in the mirror is skipped, so a failed or interrupted task can be
run again and only fetches what is still missing.
"""

from __future__ import annotations

import argparse
import logging
import os
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
    parser = argparse.ArgumentParser(description="One task's share of the whole-country elevation copy.")
    parser.add_argument("--concurrency", type=int, default=1, choices=range(1, 9), metavar="1-8")
    args = parser.parse_args(argv)
    index = int(os.environ.get("CLOUD_RUN_TASK_INDEX", "0"))
    count = int(os.environ.get("CLOUD_RUN_TASK_COUNT", "1"))
    assert 0 <= index < count, f"task {index} of {count} is out of range"
    share = shares(list(england_catalogue()), count)[index]
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    logger.info("Task %d of %d: %d tiles", index + 1, count, len(share))
    if not share:
        return 0
    return cli.main(["mirror", *share, "--concurrency", str(args.concurrency)])


if __name__ == "__main__":
    sys.exit(main())
