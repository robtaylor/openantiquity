"""`fieldclub-jobs`: the scheduled jobs, for a scheduler to run.

    fieldclub-jobs scan-channels [--max-channels N] [--delay SECONDS]
    fieldclub-jobs refresh-sources
    fieldclub-jobs add-channel <UC... channel id> [--title TEXT] [--disable]

Each job logs a one-line summary and exits 0 when everything it tried
worked, or 1 when anything failed, so the scheduler can raise the alarm.
A failure doesn't stop the rest of the run.
"""

from __future__ import annotations

import argparse
import logging
import sys
from collections.abc import Sequence

from fieldclub.config import get_settings
from fieldclub.db import SessionLocal
from fieldclub.jobs import channels, sources

logger = logging.getLogger("fieldclub.jobs")


def _positive_int(text: str) -> int:
    try:
        value = int(text)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a whole number") from None
    if value < 1:
        raise argparse.ArgumentTypeError("must be at least 1")
    return value


def _seconds(text: str) -> float:
    try:
        value = float(text)
    except ValueError:
        raise argparse.ArgumentTypeError("expected a number of seconds") from None
    if not 0 <= value <= 600:
        raise argparse.ArgumentTypeError("must be between 0 and 600")
    return value


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="fieldclub-jobs", description="Open Antiquity's scheduled jobs.")
    commands = parser.add_subparsers(dest="command", required=True)

    scan = commands.add_parser("scan-channels", help="add mentions for links to findings in watched channels")
    defaults = channels.ScanLimits()
    scan.add_argument("--max-channels", type=_positive_int, default=defaults.max_channels, metavar="N")
    scan.add_argument("--delay", type=_seconds, default=defaults.delay_s, metavar="SECONDS")

    commands.add_parser("refresh-sources", help="run each bulk source whose data is older than it should be")

    add = commands.add_parser("add-channel", help="watch a YouTube channel, or change one already watched")
    add.add_argument("channel_id", help="the channel's id, which starts with UC")
    add.add_argument("--title", help="a name to know it by")
    add.add_argument("--disable", action="store_true", help="stop scanning it")
    return parser


def scan_channels(max_channels: int, delay_s: float) -> int:
    stats = channels.scan(limits=channels.ScanLimits(max_channels=max_channels, delay_s=delay_s))
    logger.info("%s", stats.summary())
    return 1 if stats.failed else 0


def refresh_sources() -> int:
    stats = sources.refresh()
    logger.info("%s", stats.summary())
    return 1 if stats.failed else 0


def add_channel(channel_id: str, title: str | None, disable: bool) -> int:
    with SessionLocal() as db:
        try:
            channel = channels.add_channel(db, channel_id, title=title, enabled=not disable)
        except channels.ChannelScanError as exc:
            logger.error("%s", exc)
            return 1
        db.commit()
        logger.info(
            "add-channel: %s is %s", channel.channel_id, "watched" if channel.enabled else "no longer scanned"
        )
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    args = build_parser().parse_args(sys.argv[1:] if argv is None else argv)
    logging.basicConfig(
        level=get_settings().log_level, format="%(asctime)s %(levelname)s %(name)s: %(message)s"
    )
    try:
        if args.command == "scan-channels":
            return scan_channels(args.max_channels, args.delay)
        if args.command == "refresh-sources":
            return refresh_sources()
        assert args.command == "add-channel", f"unhandled command {args.command!r}"
        return add_channel(args.channel_id, args.title, args.disable)
    except Exception:
        logger.exception("%s failed", args.command)
        return 1


if __name__ == "__main__":
    sys.exit(main())
