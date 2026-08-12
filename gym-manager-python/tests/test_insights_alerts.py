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
