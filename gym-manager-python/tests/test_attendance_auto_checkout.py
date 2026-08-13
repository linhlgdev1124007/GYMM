from datetime import datetime
import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault(
    "GYM_DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="pulsefit-auto-checkout-tests-")) / "bootstrap.sqlite3"),
)


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'attendance.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def test_auto_checkout_closes_open_member_and_employee_sessions_at_2358(tmp_path):
    from server.models import AttendanceSession
    from server.services.attendance_auto_checkout import auto_checkout_open_sessions

    db = make_session(tmp_path)
    try:
        member_session = AttendanceSession(
            customer_id=1,
            checked_in_at=datetime(2026, 8, 13, 9, 0),
            source="dah",
            status="open",
        )
        employee_session = AttendanceSession(
            employee_id=1,
            checked_in_at=datetime(2026, 8, 13, 8, 30),
            source="dah",
            status="open",
        )
        db.add_all([member_session, employee_session])
        db.commit()

        result = auto_checkout_open_sessions(db, now_vietnam=datetime(2026, 8, 13, 23, 58))

        assert result["closed"] == 2
        assert result["members"] == 1
        assert result["employees"] == 1
        assert member_session.status == "closed"
        assert member_session.checked_out_at == datetime(2026, 8, 13, 23, 58)
        assert employee_session.status == "closed"
        assert employee_session.checked_out_at == datetime(2026, 8, 13, 23, 58)
    finally:
        db.close()


def test_auto_checkout_before_2358_only_catches_previous_deadline(tmp_path):
    from server.models import AttendanceSession
    from server.services.attendance_auto_checkout import auto_checkout_open_sessions

    db = make_session(tmp_path)
    try:
        yesterday = AttendanceSession(
            customer_id=1,
            checked_in_at=datetime(2026, 8, 12, 18, 0),
            source="dah",
            status="open",
        )
        today = AttendanceSession(
            employee_id=1,
            checked_in_at=datetime(2026, 8, 13, 9, 0),
            source="dah",
            status="open",
        )
        db.add_all([yesterday, today])
        db.commit()

        result = auto_checkout_open_sessions(db, now_vietnam=datetime(2026, 8, 13, 12, 0))

        assert result["closed"] == 1
        assert yesterday.status == "closed"
        assert yesterday.checked_out_at == datetime(2026, 8, 12, 23, 58)
        assert today.status == "open"
        assert today.checked_out_at is None
    finally:
        db.close()


def test_auto_checkout_late_checkin_closes_on_next_day_deadline(tmp_path):
    from server.models import AttendanceSession
    from server.services.attendance_auto_checkout import auto_checkout_open_sessions

    db = make_session(tmp_path)
    try:
        late_session = AttendanceSession(
            customer_id=1,
            checked_in_at=datetime(2026, 8, 13, 23, 59),
            source="dah",
            status="open",
        )
        db.add(late_session)
        db.commit()

        early_result = auto_checkout_open_sessions(db, now_vietnam=datetime(2026, 8, 14, 12, 0))

        assert early_result["closed"] == 0
        assert late_session.status == "open"

        final_result = auto_checkout_open_sessions(db, now_vietnam=datetime(2026, 8, 14, 23, 58))

        assert final_result["closed"] == 1
        assert late_session.status == "closed"
        assert late_session.checked_out_at == datetime(2026, 8, 14, 23, 58)
    finally:
        db.close()
