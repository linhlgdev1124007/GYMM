from datetime import UTC, date, datetime, timedelta, timezone

VIETNAM_TZ = timezone(timedelta(hours=7))


def utc_now() -> datetime:
    """Return naive UTC for compatibility with SQLAlchemy DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)


def vietnam_today() -> date:
    return datetime.now(VIETNAM_TZ).date()
