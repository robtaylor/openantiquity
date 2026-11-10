"""`fieldclub-ingest`: list the connectors, or run one.

    fieldclub-ingest list
    fieldclub-ingest run <key> [--bbox west,south,east,north] [--limit N] [--allow-shrink]

A run with `--bbox` or `--limit` is partial: it adds and updates records but
never deletes any. A full run deletes what the source no longer has, and
refuses when that is a large share of what is stored unless `--allow-shrink`
says the loss is real.

The same commands run the reference loaders in `ingest/reference/`, which
fill the gazetteer and the admin areas instead of the record index. A loader
replaces its rows: those in the box with `--bbox`, and all of them otherwise.
It refuses `--limit`, because a run that kept only N rows would delete the rest.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from fieldclub.config import get_settings
from fieldclub.errors import AppError
from fieldclub.ingest import reference, registry, runner
from fieldclub.ingest.base import BBox
from fieldclub.ingest.reference.base import run_loader


def parse_bbox(text: str) -> BBox:
    parts = text.split(",")
    if len(parts) != 4:
        raise argparse.ArgumentTypeError("expected west,south,east,north")
    try:
        west, south, east, north = (float(part) for part in parts)
        return runner.check_bbox((west, south, east, north))
    except (ValueError, AppError) as exc:
        raise argparse.ArgumentTypeError(str(exc)) from None


def positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="fieldclub-ingest", description="Ingest heritage records from external sources."
    )
    commands = parser.add_subparsers(dest="command", required=True)

    commands.add_parser("list", help="show every connector")

    run = commands.add_parser("run", help="run one connector")
    run.add_argument("key", help="the source key, as shown by 'list'")
    run.add_argument(
        "--bbox", type=parse_bbox, metavar="W,S,E,N", help="only records in this box, in degrees"
    )
    run.add_argument(
        "--limit",
        type=positive_int,
        metavar="N",
        help="stop after N records; connectors only, since a reference loader replaces all its rows",
    )
    run.add_argument(
        "--allow-shrink",
        action="store_true",
        help="let a full run delete a large share of the stored records, when the source really lost them",
    )
    return parser


def list_connectors() -> int:
    connectors = registry.all_connectors()
    if not connectors:
        print("No connectors are registered yet.")
        return 0
    settings = get_settings()
    rows = [("KEY", "CATEGORY", "ACCESS", "READY", "NAME")]
    for cls in [*connectors, *reference.all_loaders()]:
        info = cls.source
        ready = "yes" if cls(settings).is_configured() else "no"
        rows.append((info.key, str(info.category), str(info.access), ready, info.name))
    widths = [max(len(row[column]) for row in rows) for column in range(4)]
    for row in rows:
        print(
            "  ".join(cell.ljust(width) for cell, width in zip(row[:4], widths, strict=True)) + "  " + row[4]
        )
    return 0


def load_one(key: str, bbox: BBox | None, limit: int | None, allow_shrink: bool = False) -> int:
    """Run the reference loader for `key`. A limit is refused before anything is touched."""
    loader_cls = reference.get(key)
    assert loader_cls is not None, f"{key} is not a loader"
    if limit is not None:
        print(
            f"{key} replaces all its rows, so it takes no --limit: a run that kept {limit} would delete "
            "the rest. Run it whole, or with --bbox where it allows one.",
            file=sys.stderr,
        )
        return 1
    try:
        run = run_loader(loader_cls(get_settings()), bbox=bbox, allow_shrink=allow_shrink)
    except AppError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    assert run.stats is not None, "a finished run stores its stats"
    stats = run.stats
    print(
        f"{key}: {stats['inserted']} rows from {stats['read']} read upstream "
        f"(replacing {stats['deleted']}) in {stats['seconds']} s"
    )
    return 0


def run_one(key: str, bbox: BBox | None, limit: int | None, allow_shrink: bool = False) -> int:
    if reference.get(key) is not None:
        return load_one(key, bbox, limit, allow_shrink)
    try:
        connector = registry.get(key)(get_settings())
    except registry.UnknownConnectorError as exc:
        print(exc.message, file=sys.stderr)
        return 1
    try:
        run = runner.run_connector(connector, bbox=bbox, limit=limit, allow_shrink=allow_shrink)
    except runner.ConnectorNotConfiguredError as exc:
        # Not a failure: a source without its key is simply left out.
        print(exc.message)
        return 0
    except (runner.IngestFailedError, runner.IngestBusyError) as exc:
        print(exc.message, file=sys.stderr)
        return 1
    assert run.stats is not None, "a finished run stores its stats"
    stats = runner.RunStats(**run.stats)
    print(
        f"{key}: {stats.seen} records ({stats.inserted} new, {stats.updated} updated, "
        f"{stats.deleted} removed) in {stats.seconds} s"
    )
    return 0


def _join_bbox(argv: Sequence[str]) -> list[str]:
    """Turn `--bbox -2,51,-1,52` into `--bbox=-2,51,-1,52`.

    Most British longitudes are negative, and argparse takes a value that
    starts with a minus sign for another option.
    """
    joined: list[str] = []
    arguments = iter(argv)
    for argument in arguments:
        value = next(arguments, None) if argument == "--bbox" else None
        joined.append(argument if value is None else f"--bbox={value}")
    return joined


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(_join_bbox(sys.argv[1:] if argv is None else argv))
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    if args.command == "list":
        return list_connectors()
    assert args.command == "run", f"unhandled command {args.command!r}"
    return run_one(args.key, args.bbox, args.limit, args.allow_shrink)


if __name__ == "__main__":
    sys.exit(main())
