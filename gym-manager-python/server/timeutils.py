from datetime import UTC, datetime


def utc_now() -> datetime:
    """Return naive UTC for compatibility with SQLAlchemy DateTime columns."""
    return datetime.now(UTC).replace(tzinfo=None)
