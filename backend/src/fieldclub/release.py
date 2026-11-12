# ruff: noqa: T201 - a command-line tool: what it prints is its output
"""What a deploy runs once, before any machine is replaced: `release_command` in `fly.toml`.

    fieldclub-release

First `fieldclub-terrain check`: the mirror holds the tiles this code expects,
and GDAL reads one on a thread of its own. Then `python -m fieldclub.db`: the
schema. The check comes first, so a release it stops has changed nothing, and
the machines keep the image they have.
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Sequence

from fieldclub import db
from fieldclub.terrain import cli as terrain_cli


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        prog="fieldclub-release",
        description="Check the elevation mirror, then create what the schema lacks. A deploy runs it first.",
    )
    parser.parse_args(argv)
    status = terrain_cli.main(["check"])
    if status != 0:
        print("error: the release stops here. The schema wasn't touched.", file=sys.stderr)
        return status
    db.main([])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
