from datetime import UTC, datetime, time, timedelta

from sqlalchemy.orm import Session

from ..models import AttendanceSession
from ..timeutils import VIETNAM_TZ

AUTO_CHECKOUT_TIME = time(23, 58)


def _naive_utc_from_vietnam(value: datetime) -> datetime:
    return value.replace(tzinfo=VIETNAM_TZ).astimezone(UTC).replace(tzinfo=None)


def _session_checkin_vietnam(row: AttendanceSession) -> datetime:
    if row.source == "dah":
        return row.checked_in_at
    return row.checked_in_at.replace(tzinfo=UTC).astimezone(VIETNAM_TZ).replace(tzinfo=None)


def _session_checkout_value(row: AttendanceSession, checkout_vietnam: datetime) -> datetime:
    if row.source == "dah":
        return checkout_vietnam
    return _naive_utc_from_vietnam(checkout_vietnam)


def _checkout_deadline_for(row: AttendanceSession) -> datetime:
    checked_in_vietnam = _session_checkin_vietnam(row)
    checkout_vietnam = datetime.combine(checked_in_vietnam.date(), AUTO_CHECKOUT_TIME)
    if checked_in_vietnam > checkout_vietnam:
        checkout_vietnam += timedelta(days=1)
    return checkout_vietnam


def current_auto_checkout_deadline(now_vietnam: datetime | None = None) -> datetime:
    now_vietnam = now_vietnam or datetime.now(VIETNAM_TZ).replace(tzinfo=None)
    if now_vietnam.tzinfo:
        now_vietnam = now_vietnam.astimezone(VIETNAM_TZ).replace(tzinfo=None)
    today_deadline = datetime.combine(now_vietnam.date(), AUTO_CHECKOUT_TIME)
    if now_vietnam >= today_deadline:
        return today_deadline
    return today_deadline - timedelta(days=1)


def auto_checkout_open_sessions(db: Session, now_vietnam: datetime | None = None) -> dict:
    deadline = current_auto_checkout_deadline(now_vietnam)
    rows = (
        db.query(AttendanceSession)
        .filter(AttendanceSession.status == "open", AttendanceSession.checked_out_at.is_(None))
        .order_by(AttendanceSession.checked_in_at.asc(), AttendanceSession.id.asc())
        .all()
    )
    closed = 0
    members = 0
    employees = 0
    for row in rows:
        checkout_vietnam = _checkout_deadline_for(row)
        if checkout_vietnam > deadline:
            continue
        row.checked_out_at = _session_checkout_value(row, checkout_vietnam)
        row.status = "closed"
        suffix = f"Tự động check-out lúc {AUTO_CHECKOUT_TIME.strftime('%H:%M')}."
        note = (row.note or "").strip()
        row.note = f"{note} {suffix}".strip() if suffix not in note else note
        closed += 1
        if row.customer_id:
            members += 1
        if row.employee_id:
            employees += 1
    db.commit()
    return {
        "closed": closed,
        "members": members,
        "employees": employees,
        "deadline": deadline.isoformat(),
    }
