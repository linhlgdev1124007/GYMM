import os
from pathlib import Path
import tempfile
from datetime import timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault(
    "GYM_DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="pulsefit-insights-tests-")) / "bootstrap.sqlite3"),
)


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'insights.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_expired_member(db, code="CUS0001295"):
    from server.models import Customer, Membership, Person, ServicePackage
    from server.timeutils import vietnam_today

    today = vietnam_today()
    person = Person(display_name="Expired Yesterday", phone="0900001295", status="active")
    db.add(person)
    db.flush()
    customer = Customer(person_id=person.id, customer_code=code, status="active")
    package = ServicePackage(
        code=f"FIT-{code}",
        name="Fitness Expired",
        category="Fitness",
        duration_days=30,
        price=100000,
        is_pt=False,
        is_active=True,
    )
    db.add_all([customer, package])
    db.flush()
    membership = Membership(
        customer_id=customer.id,
        package_id=package.id,
        code=f"MS-{code}",
        registered_at=today - timedelta(days=31),
        starts_at=today - timedelta(days=31),
        expires_at=today - timedelta(days=1),
        status="active",
    )
    db.add(membership)
    db.commit()
    return customer


def test_expired_yesterday_membership_appears_in_alerts_and_dashboard_attention(tmp_path):
    from server.services.alerts_service import alerts
    from server.services.dashboard_service import dashboard

    db = make_session(tmp_path)
    try:
        customer = seed_expired_member(db)

        alert_data = alerts(db)
        dashboard_data = dashboard(db)

        expired_alert = next(
            item for item in alert_data["items"]
            if item["type"] == "membership_expired"
        )
        assert expired_alert["memberId"] == customer.id
        assert alert_data["counts"]["expired"] == 1
        assert dashboard_data["attention"][0]["code"] == "CUS0001295"
        assert dashboard_data["attention"][0]["issue"] == "Gói vừa hết hạn"
        assert dashboard_data["attention"][0]["priority"] == "critical"
        assert dashboard_data["membershipHealth"]["expiredRecent"] == 1
        assert dashboard_data["membershipHealth"]["totalContracts"] == 1
    finally:
        db.close()


def test_alert_read_state_is_per_user_and_resets_for_a_new_expiry(tmp_path):
    from server.models import Membership, User
    from server.services.alerts_service import alerts, mark_all_read, mark_read

    db = make_session(tmp_path)
    try:
        seed_expired_member(db)
        first_user = User(username="manager-one", display_name="Manager One", password_hash="x", role="manager")
        second_user = User(username="manager-two", display_name="Manager Two", password_hash="x", role="manager")
        db.add_all([first_user, second_user])
        db.commit()

        first_alert = alerts(db, first_user.id)["items"][0]
        assert first_alert["isRead"] is False
        assert mark_read(db, first_user.id, first_alert["id"]) is True
        assert alerts(db, first_user.id)["counts"]["unread"] == 0
        assert alerts(db, first_user.id)["items"][0]["isRead"] is True
        assert alerts(db, second_user.id)["counts"]["unread"] == 1

        membership = db.query(Membership).one()
        membership.expires_at = membership.expires_at - timedelta(days=1)
        db.commit()
        refreshed = alerts(db, first_user.id)
        assert refreshed["counts"]["unread"] == 1
        assert refreshed["items"][0]["id"] != first_alert["id"]
        assert mark_all_read(db, first_user.id) == 1
        assert alerts(db, first_user.id)["counts"]["unread"] == 0
    finally:
        db.close()


def test_dashboard_context_metrics_and_debt_aging(tmp_path):
    from datetime import datetime

    from server.models import AttendanceSession, Membership, Payment
    from server.services.dashboard_service import dashboard
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        customer = seed_expired_member(db, code="CUS-CONTEXT")
        membership = db.query(Membership).one()
        membership.debt_amount = 350000
        membership.debt_due_date = vietnam_today() - timedelta(days=10)
        db.add_all([
            AttendanceSession(customer_id=customer.id, checked_in_at=datetime.combine(vietnam_today(), datetime.min.time()), status="open"),
            Payment(customer_id=customer.id, membership_id=membership.id, payment_no="PAY-CONTEXT", paid_at=datetime.combine(vietnam_today(), datetime.min.time()), amount=500000),
            Payment(customer_id=customer.id, membership_id=membership.id, payment_no="PAY-FUTURE", paid_at=datetime.combine(vietnam_today() + timedelta(days=1), datetime.min.time()), amount=250000),
        ])
        db.commit()

        data = dashboard(db)

        assert data["metrics"]["checkinsToday"] == 1
        assert data["metrics"]["openVisits"] == 1
        assert data["metrics"]["revenueToday"] == 500000
        assert data["metrics"]["revenueMonth"] == 500000
        assert data["metrics"]["overdueDebt"] == 350000
        assert data["financialHealth"]["debtAging"]["days8To30"] == {"count": 1, "amount": 350000.0}
        assert data["attention"][0]["issue"] == "Nợ quá hạn"
        assert data["attention"][0]["actionLabel"] == "Thu tiền"
        assert data["generatedAt"].endswith("Z")
    finally:
        db.close()


def test_audit_logs_filter_and_optional_actor_options(tmp_path):
    from datetime import UTC, datetime, time

    from server.models import AuditLog, Customer, Person, User
    from server.services.audit_service import list_audit_logs
    from server.timeutils import VIETNAM_TZ, vietnam_today

    db = make_session(tmp_path)
    try:
        admin = User(username="admin-audit", display_name="Admin Audit", password_hash="x", role="admin")
        manager = User(username="manager-audit", display_name="Manager Audit", password_hash="x", role="manager")
        person = Person(display_name="Audit Member", phone="0900000000", status="active")
        db.add_all([admin, manager, person])
        db.flush()
        customer = Customer(person_id=person.id, customer_code="AUD001", status="active")
        db.add(customer)
        db.flush()

        today_start = datetime.combine(vietnam_today(), time(hour=9), tzinfo=VIETNAM_TZ).astimezone(UTC).replace(tzinfo=None)
        old_time = today_start - timedelta(days=1)
        db.add_all(
            [
                AuditLog(
                    actor_user_id=admin.id,
                    action="update",
                    entity_type="member",
                    entity_id=customer.id,
                    customer_id=customer.id,
                    summary="Cập nhật hội viên Audit Member",
                    details_json='{"fields":["name"]}',
                    created_at=today_start,
                ),
                AuditLog(
                    actor_user_id=manager.id,
                    action="create",
                    entity_type="plan",
                    entity_id=10,
                    summary="Tạo gói test",
                    created_at=old_time,
                ),
            ]
        )
        db.commit()

        without_actors = list_audit_logs(db, scope="today", page=1, page_size=5, include_actors=False)
        assert without_actors["actors"] == []
        assert without_actors["pagination"]["total"] == 1
        assert without_actors["items"][0]["customer"]["code"] == "AUD001"

        by_actor = list_audit_logs(db, actor_id=manager.id, page=1, page_size=5)
        assert by_actor["pagination"]["total"] == 1
        assert by_actor["items"][0]["actor"]["username"] == "manager-audit"
        assert {row["username"] for row in by_actor["actors"]} == {"admin-audit", "manager-audit"}

        by_search = list_audit_logs(db, q="Admin Audit", page=1, page_size=5)
        assert by_search["pagination"]["total"] == 1
        assert by_search["items"][0]["actor"]["username"] == "admin-audit"
    finally:
        db.close()


def test_reports_include_revenue_by_sale_and_detail_rows(tmp_path):
    from datetime import datetime

    from server.models import Employee, Membership, Payment, Person
    from server.services.dashboard_service import reports
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        customer = seed_expired_member(db, code="CUS-REPORT")
        membership = db.query(Membership).one()
        person = Person(display_name="Sale Report", phone="0900002000", status="active")
        db.add(person)
        db.flush()
        sale = Employee(person_id=person.id, employee_code="EMP-REPORT", job_title="Sale", status="active")
        db.add(sale)
        db.flush()
        membership.direct_sales_employee_id = sale.id
        paid_at = datetime.combine(vietnam_today(), datetime.min.time())
        db.add(Payment(customer_id=customer.id, membership_id=membership.id, payment_no="PAY-REPORT", paid_at=paid_at, amount=700000, method="cash"))
        db.commit()

        data = reports(db, vietnam_today().isoformat(), vietnam_today().isoformat())

        assert data["summary"]["revenue"] == 700000
        assert data["summary"]["previousRevenue"] == 0
        assert data["summary"]["collectionRate"] == 100
        assert data["summary"]["previousCheckins"] == 0
        assert data["daily"] == [{
            "date": vietnam_today().isoformat(),
            "amount": 700000.0,
            "membershipAmount": 700000.0,
            "ptAmount": 0,
            "dayPassAmount": 0,
            "discountAmount": 0,
            "surchargeAmount": 0,
            "payments": 1,
            "checkins": 0,
        }]
        assert data["comparisonPeriod"]["to"] < data["period"]["from"]
        assert data["generatedAt"].endswith("Z")
        assert data["revenueBySale"] == [{"saleEmployeeId": sale.id, "saleName": "Sale Report", "saleTitle": "Sale", "amount": 700000.0, "payments": 1}]
        assert data["revenueByMethod"] == [{"method": "cash", "amount": 700000.0, "share": 100.0}]
        assert data["revenueItems"][0]["paymentNo"] == "PAY-REPORT"
        assert data["revenueItems"][0]["saleName"] == "Sale Report"
        assert data["revenueItems"][0]["memberCode"] == "CUS-REPORT"
    finally:
        db.close()


def test_reports_filter_debts_by_due_date_period(tmp_path):
    from server.models import Membership
    from server.services.dashboard_service import reports
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        seed_expired_member(db, code="CUS-DEBT-PERIOD")
        membership = db.query(Membership).one()
        today = vietnam_today()
        membership.debt_amount = 300000
        membership.debt_due_date = today
        db.commit()

        current = reports(db, today.isoformat(), today.isoformat())
        outside = reports(db, (today + timedelta(days=10)).isoformat(), (today + timedelta(days=10)).isoformat())

        assert current["summary"]["debt"] == 300000
        assert len(current["debts"]) == 1
        assert current["debts"][0]["memberCode"] == "CUS-DEBT-PERIOD"
        assert current["debts"][0]["membershipCode"] == membership.code
        assert current["debts"][0]["saleName"] == "Chưa phân công"
        assert "phone" in current["debts"][0]
        assert outside["summary"]["debt"] == 0
        assert outside["debts"] == []
    finally:
        db.close()


def test_vietnam_day_boundaries_and_non_financial_payload(tmp_path):
    from datetime import datetime

    from server.models import AttendanceSession, Membership, Payment
    from server.services.alerts_service import alerts
    from server.services.dashboard_service import dashboard, reports
    from server.timeutils import vietnam_day_utc_bounds, vietnam_today

    db = make_session(tmp_path)
    try:
        customer = seed_expired_member(db, code="CUS-TIMEZONE")
        membership = db.query(Membership).one()
        today = vietnam_today()
        membership.debt_amount = 120000
        membership.debt_due_date = today - timedelta(days=1)
        utc_start, _ = vietnam_day_utc_bounds(today)
        db.add_all([
            Payment(customer_id=customer.id, membership_id=membership.id, payment_no="PAY-VN-DAY", paid_at=utc_start + timedelta(minutes=5), amount=900000),
            Payment(customer_id=customer.id, membership_id=membership.id, payment_no="PAY-PREVIOUS-VN-DAY", paid_at=utc_start - timedelta(minutes=5), amount=100000),
            AttendanceSession(customer_id=customer.id, checked_in_at=utc_start + timedelta(minutes=10), source="manual", status="closed"),
            AttendanceSession(customer_id=customer.id, checked_in_at=datetime.combine(today, datetime.min.time()) + timedelta(minutes=15), source="dah", status="closed"),
        ])
        db.commit()

        report = reports(db, today.isoformat(), today.isoformat())
        restricted_dashboard = dashboard(db, include_financial=False)
        restricted_alerts = alerts(db, include_financial=False)

        assert report["summary"]["revenue"] == 900000
        assert report["summary"]["checkins"] == 2
        assert report["daily"][0]["amount"] == 900000
        assert report["daily"][0]["checkins"] == 2
        assert "revenueMonth" not in restricted_dashboard["metrics"]
        assert "overdueDebt" not in restricted_dashboard["metrics"]
        assert "financialHealth" not in restricted_dashboard
        assert all(item["issueType"] not in {"debt", "overdue_debt"} for item in restricted_dashboard["attention"])
        assert "overdueDebt" not in restricted_alerts["counts"]
        assert all(item["type"] != "overdue_debt" for item in restricted_alerts["items"])
    finally:
        db.close()


def test_reports_reject_malformed_dates_with_422(tmp_path):
    import pytest
    from fastapi import HTTPException
    from server.services.dashboard_service import reports

    db = make_session(tmp_path)
    try:
        with pytest.raises(HTTPException) as error:
            reports(db, "17-08-2026", "not-a-date")
        assert error.value.status_code == 422
    finally:
        db.close()
