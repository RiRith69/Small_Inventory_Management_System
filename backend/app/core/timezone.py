"""Timezone helpers.

The warehouse operates in Cambodia.  All *calendar* values (delivery dates and
payment dates) are interpreted in ``Asia/Phnom_Penh``; all *timestamps* are
stored as timezone-aware UTC values in PostgreSQL (``timestamptz``).
"""

from __future__ import annotations

from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from app.core.config import settings

try:  # pragma: no cover - zoneinfo data is available on all supported platforms
    LOCAL_TZ = ZoneInfo(settings.timezone)
except Exception:  # pragma: no cover
    LOCAL_TZ = timezone.utc


def now_utc() -> datetime:
    """Current time as an aware UTC datetime."""
    return datetime.now(timezone.utc)


def as_utc(dt: datetime) -> datetime:
    """Normalize aware or database-returned naive timestamps to UTC."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def to_local(dt: datetime) -> datetime:
    return as_utc(dt).astimezone(LOCAL_TZ)


def local_today() -> date:
    """Today's calendar date in the warehouse timezone."""
    return datetime.now(LOCAL_TZ).date()


def utc_from_local_date(d: date) -> datetime:
    """Midnight of a local calendar date, expressed as an aware UTC datetime."""
    return datetime(d.year, d.month, d.day, tzinfo=LOCAL_TZ).astimezone(timezone.utc)


def format_local_date(dt: datetime | date, fmt: str = "%d-%m-%Y") -> str:
    if isinstance(dt, datetime):
        dt = to_local(dt).date()
    return dt.strftime(fmt)
