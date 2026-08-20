import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault(
    "GYM_DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="pulsefit-day-pass-tests-")) / "bootstrap.sqlite3"),
)


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'day-passes.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_plan(db):
    from server.models import ServicePackage

    plan = ServicePackage(
        code="MONTHLY",
        name="Gói tháng",
        category="Gym",
        duration_days=30,
        price=600000,
        is_pt=False,
        is_active=True,
    )
    db.add(plan)
    db.commit()
    return plan


def test_day_pass_allows_missing_phone_and_reports_separate_revenue(tmp_path):
    from server.services.dashboard_service import reports
    from server.services.day_passes_service import create_day_pass
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        row = create_day_pass(db, {
            "guestName": "Khach vang lai",
            "visitDate": today.isoformat(),
            "chargedAmount": 79000,
            "paymentMethod": "cash",
        }, None)

        assert row["guestPhone"] is None
        assert row["chargedAmount"] == 79000

        data = reports(db, today.isoformat(), today.isoformat())
        assert data["summary"]["revenue"] == 79000
        assert data["summary"]["membershipRevenue"] == 0
        assert data["summary"]["dayPassRevenue"] == 79000
        assert data["revenueByType"] == [
            {"type": "membership", "label": "Gói hội viên", "amount": 0.0, "payments": 0, "share": 0.0},
            {"type": "pt", "label": "PT/BT", "amount": 0.0, "payments": 0, "share": 0.0},
            {"type": "day_pass", "label": "Khách tập ngày", "amount": 79000.0, "payments": 1, "share": 100.0},
        ]
        assert data["revenueByMethod"] == [{"method": "cash", "amount": 79000.0, "share": 100.0}]
        assert data["revenueItems"][0]["revenueType"] == "Khách tập ngày"
        assert data["revenueItems"][0]["package"] == "Khách tập ngày"
    finally:
        db.close()


def test_day_pass_conversion_refunds_day_pass_and_prevents_double_counting(tmp_path):
    from server.models import DayPassVisit
    from server.services.dashboard_service import reports
    from server.services.day_passes_service import create_day_pass
    from server.services.members_service import create_member
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        plan = seed_plan(db)
        day_pass = create_day_pass(db, {
            "guestName": "Convert Guest",
            "guestPhone": "",
            "visitDate": today.isoformat(),
            "chargedAmount": 79000,
            "paymentMethod": "cash",
        }, None)

        member = create_member(db, {
            "name": "Convert Guest",
            "phone": "0900007001",
            "source": "Khách tập ngày",
            "sourceDayPassId": day_pass["id"],
            "membership": {
                "planId": plan.id,
                "startsAt": today.isoformat(),
                "expiresAt": today.isoformat(),
                "finalPrice": 600000,
                "paidAmount": 600000,
                "paymentMethod": "cash",
            },
        })

        converted = db.get(DayPassVisit, day_pass["id"])
        assert converted.status == "converted"
        assert converted.conversion_policy == "refunded"
        assert converted.conversion_amount == 79000
        assert converted.converted_customer_id == member["id"]

        data = reports(db, today.isoformat(), today.isoformat())
        assert data["summary"]["revenue"] == 600000
        assert data["summary"]["membershipRevenue"] == 600000
        assert data["summary"]["dayPassRevenue"] == 0
        assert [item["revenueType"] for item in data["revenueItems"]] == ["Gói hội viên"]
    finally:
        db.close()


def test_day_pass_conversion_can_record_deduction_policy(tmp_path):
    from server.models import DayPassVisit
    from server.services.dashboard_service import reports
    from server.services.day_passes_service import create_day_pass
    from server.services.members_service import create_member
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        plan = seed_plan(db)
        day_pass = create_day_pass(db, {
            "guestName": "Deduct Guest",
            "visitDate": today.isoformat(),
            "chargedAmount": 79000,
            "paymentMethod": "cash",
        }, None)

        create_member(db, {
            "name": "Deduct Guest",
            "phone": "0900007002",
            "source": "Khách tập ngày",
            "sourceDayPassId": day_pass["id"],
            "sourceDayPassConversionPolicy": "deducted",
            "membership": {
                "planId": plan.id,
                "startsAt": today.isoformat(),
                "expiresAt": today.isoformat(),
                "finalPrice": 600000,
                "paidAmount": 521000,
                "paymentMethod": "cash",
                "debtDueDate": today.isoformat(),
            },
        })

        converted = db.get(DayPassVisit, day_pass["id"])
        assert converted.status == "converted"
        assert converted.conversion_policy == "deducted"
        assert converted.conversion_amount == 79000

        data = reports(db, today.isoformat(), today.isoformat())
        assert data["summary"]["revenue"] == 600000
        assert data["summary"]["membershipRevenue"] == 521000
        assert data["summary"]["dayPassRevenue"] == 79000
        assert sorted(item["revenueType"] for item in data["revenueItems"]) == ["Gói hội viên", "Khách tập ngày"]
    finally:
        db.close()
