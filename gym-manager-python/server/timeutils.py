from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return naive UTC for compatibility with the existing SQLite DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)
