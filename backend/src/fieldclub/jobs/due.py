"""Which scheduled jobs are due, for a scheduler that can only start something every hour.

Fly starts a scheduled machine hourly, daily, weekly or monthly, at a time of
its own choosing within the interval. The channel scan runs every six hours
and the source refresh nightly, so one machine is started hourly and runs
`fieldclub-jobs due`, which asks this module what to run. Nothing is kept
between runs: the answer comes from the database and the clock.

- The scan is due when some channel is watched and none has been checked in
  the last six hours less an hour. The hour is the room Fly takes in starting
  the machine, so scans come between five and seven hours apart and six on
  average. Every channel a scan reaches is stamped (`channels.scan`), so the
  most recent stamp is when the last scan ran.
- The refresh is due in one hour of the night, `REFRESH_HOUR_UTC`. A second
  start in that hour does no harm: the refresh runs only sources whose data
  is older than their `max_age` (`sources.refresh`), so it finds them current.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from fieldclub.models import WatchChannel

SCAN_EVERY = timedelta(hours=6)
# Fly starts an hourly machine somewhere within each hour.
SCAN_SLACK = timedelta(hours=1)
# 03:00 to 03:59 UTC: 03:00 in winter and 04:00 in summer in London, when the site is quietest.
REFRESH_HOUR_UTC = 3


@dataclass(frozen=True)
class Due:
    scan_channels: bool
    refresh_sources: bool

    def names(self) -> list[str]:
        return [
            name
            for name, wanted in (
                ("scan-channels", self.scan_channels),
                ("refresh-sources", self.refresh_sources),
            )
            if wanted
        ]


def utc_now() -> datetime:
    return datetime.now(UTC)


def what_is_due(db: Session, now: datetime) -> Due:
    """What an hourly run started at `now` should run."""
    assert now.tzinfo is not None, "the time must carry its zone"
    enabled = WatchChannel.enabled.is_(True)
    watched = db.scalar(select(func.count()).select_from(WatchChannel).where(enabled))
    last_checked = db.scalar(select(func.max(WatchChannel.last_checked_at)).where(enabled))
    scan = bool(watched) and (last_checked is None or now - last_checked >= SCAN_EVERY - SCAN_SLACK)
    return Due(scan_channels=scan, refresh_sources=now.astimezone(UTC).hour == REFRESH_HOUR_UTC)
