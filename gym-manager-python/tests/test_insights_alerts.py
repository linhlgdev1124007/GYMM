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
        assert dashboard_data["attention"][0]["issue"] == "Gói đã hết hạn"
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
