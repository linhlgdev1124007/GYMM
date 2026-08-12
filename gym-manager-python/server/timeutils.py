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
