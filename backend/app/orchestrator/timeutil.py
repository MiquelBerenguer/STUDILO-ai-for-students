from __future__ import annotations

from datetime import UTC, date, datetime, time
from zoneinfo import ZoneInfo


def local_dt(d: date, hhmm: str, tz: str) -> datetime:
    h, m = (int(x) for x in hhmm.split(":"))
    return datetime.combine(d, time(h, m), tzinfo=ZoneInfo(tz)).astimezone(UTC)


def local_today(now: datetime, tz: str) -> date:
    return now.astimezone(ZoneInfo(tz)).date()
