"""Time range parsing and timestamp helpers. All results are timezone-aware (local tz)."""

from __future__ import annotations

import re
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, Union


def local_tz():
    return datetime.now().astimezone().tzinfo


def now() -> datetime:
    return datetime.now().astimezone()


def _start_of_day(d: datetime) -> datetime:
    return d.replace(hour=0, minute=0, second=0, microsecond=0)


def parse_point(value: str, *, end: bool = False) -> datetime:
    """Parse a single point in time.

    Accepts: now, today, yesterday, ISO date (2026-11-06), ISO datetime,
    relative durations (90m, 24h, 7d, 2w). With end=True a bare date means end of that day.
    """
    v = value.strip().lower()
    n = now()
    if v == "now":
        return n
    if v == "today":
        return _start_of_day(n) + (timedelta(days=1) if end else timedelta())
    if v == "yesterday":
        return _start_of_day(n) - timedelta(days=1) + (timedelta(days=1) if end else timedelta())
    m = re.fullmatch(r"(\d+)\s*(m|min|h|d|w)", v)
    if m:
        amount, unit = int(m.group(1)), m.group(2)
        delta = {"m": timedelta(minutes=amount), "min": timedelta(minutes=amount),
                 "h": timedelta(hours=amount), "d": timedelta(days=amount),
                 "w": timedelta(weeks=amount)}[unit]
        return n - delta
    if re.fullmatch(r"\d{4}-\d{2}-\d{2}", v):
        d = datetime.strptime(v, "%Y-%m-%d").replace(tzinfo=local_tz())
        return d + timedelta(days=1) if end else d
    d = to_dt(value)
    if d is None:
        raise ValueError(f"unrecognized time: {value!r}")
    return d


def parse_range(spec: Optional[str] = None, since: Optional[str] = None,
                until: Optional[str] = None) -> Tuple[datetime, datetime]:
    """Resolve a named range or explicit since/until into (start, end)."""
    n = now()
    if spec:
        s = spec.strip().lower()
        today = _start_of_day(n)
        monday = today - timedelta(days=today.weekday())
        named = {
            "today": (today, n),
            "yesterday": (today - timedelta(days=1), today),
            "this-week": (monday, n),
            "last-week": (monday - timedelta(days=7), monday),
            "this-month": (today.replace(day=1), n),
        }
        if s in named:
            return named[s]
        if s == "last-month":
            first = today.replace(day=1)
            prev = (first - timedelta(days=1)).replace(day=1)
            return prev, first
        if ".." in s:
            a, b = s.split("..", 1)
            return parse_point(a), parse_point(b, end=True)
        # relative like 7d / 24h means "the last N"
        return parse_point(s), n
    start = parse_point(since) if since else _start_of_day(n)
    stop = parse_point(until, end=True) if until else n
    if stop <= start:
        raise ValueError("range end must be after range start")
    return start, stop


def to_dt(value: Union[str, int, float, None]) -> Optional[datetime]:
    """Convert ISO strings or epoch (s/ms) to an aware datetime in local tz."""
    if value is None or value == "":
        return None
    try:
        if isinstance(value, (int, float)):
            ts = float(value)
            if ts > 1e11:   # milliseconds
                ts /= 1000.0
            return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone()
        s = str(value).strip()
        if s.isdigit():
            return to_dt(int(s))
        if s.endswith("Z"):
            s = s[:-1] + "+00:00"
        # normalize fractional seconds to 6 digits (Codex writes ns; py<3.11 needs 3 or 6)
        s = re.sub(r"\.(\d+)", lambda m: "." + (m.group(1) + "000000")[:6], s, count=1)
        d = datetime.fromisoformat(s)
        if d.tzinfo is None:
            d = d.replace(tzinfo=timezone.utc)
        return d.astimezone()
    except (ValueError, OverflowError, OSError):
        return None


def in_range(d: Optional[datetime], start: datetime, end: datetime) -> bool:
    return d is not None and start <= d < end
