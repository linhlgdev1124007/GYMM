from datetime import UTC, date, datetime, timedelta, timezone
import os

VIETNAM_TZ = timezone(timedelta(hours=7))
_TEST_TODAY: date | None = None


def utc_now() -> datetime:
    """Return naive UTC for compatibility with SQLAlchemy DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def vietnam_today() -> date:
    if os.getenv("GYM_ENV", "").strip().lower() == "test" and _TEST_TODAY:
        return _TEST_TODAY
    return datetime.now(VIETNAM_TZ).date()


def set_test_today(value: date | None) -> None:
    global _TEST_TODAY
    if os.getenv("GYM_ENV", "").strip().lower() != "test":
        raise RuntimeError("Test clock can only be changed when GYM_ENV=test")
    _TEST_TODAY = value


def utc_iso(value: datetime | None) -> str | None:
    if not value:
        return None
    if value.tzinfo:
        value = value.astimezone(UTC)
    else:
        value = value.replace(tzinfo=UTC)
    return value.isoformat().replace("+00:00", "Z")


def vietnam_day_utc_bounds(start: date, end: date | None = None) -> tuple[datetime, datetime]:
    """Return naive UTC bounds for an inclusive Vietnam calendar date range."""
    end = end or start
    local_start = datetime.combine(start, datetime.min.time(), tzinfo=VIETNAM_TZ)
    local_end = datetime.combine(end + timedelta(days=1), datetime.min.time(), tzinfo=VIETNAM_TZ)
    return (
        local_start.astimezone(UTC).replace(tzinfo=None),
        local_end.astimezone(UTC).replace(tzinfo=None),
    )


def attendance_vietnam_datetime(value: datetime | None, source: str | None) -> datetime | None:
    """Normalize a stored attendance timestamp to naive Vietnam local time."""
    if not value:
        return None
    if source == "dah":
        return value.replace(tzinfo=None)
    if value.tzinfo:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(tzinfo=UTC).astimezone(VIETNAM_TZ).replace(tzinfo=None)


def utc_vietnam_date(value: datetime | None) -> date | None:
    """Return the Vietnam calendar date for a UTC DateTime database value."""
    if not value:
        return None
    if value.tzinfo:
        value = value.astimezone(UTC).replace(tzinfo=None)
    return value.replace(tzinfo=UTC).astimezone(VIETNAM_TZ).date()
