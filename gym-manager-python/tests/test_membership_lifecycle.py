from datetime import date, timedelta
import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

os.environ.setdefault("GYM_ENV", "test")
os.environ.setdefault(
    "GYM_DATABASE_PATH",
    str(Path(tempfile.mkdtemp(prefix="pulsefit-lifecycle-tests-")) / "bootstrap.sqlite3"),
)


def make_session(tmp_path):
    from server.database import Base

    engine = create_engine(f"sqlite:///{tmp_path / 'membership-lifecycle.sqlite3'}")
    Base.metadata.create_all(bind=engine)
    return sessionmaker(bind=engine)()


def seed_member_with_plan(db, status="pending", starts_at=date(2026, 8, 1), activated_at=None):
    from server.models import Customer, Membership, Person, ServicePackage

    person = Person(display_name="Lifecycle Member", phone="0900000001", status="active")
    db.add(person)
    db.flush()
    customer = Customer(person_id=person.id, customer_code="CUS0000001", status="lead")
    package = ServicePackage(
        code="FIT-LIFE",
        name="Fitness Lifecycle",
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
        code="MS-LIFE",
        registered_at=date(2026, 8, 1),
        starts_at=starts_at,
        expires_at=starts_at + timedelta(days=30),
        activated_at=activated_at,
        status=status,
    )
    db.add(membership)
    db.commit()
    return customer, membership


def test_pending_membership_activates_on_scheduled_vietnam_day(tmp_path):
    from server.services.membership_lifecycle import refresh_membership_lifecycle

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="pending",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 5),
        )

        refresh_membership_lifecycle(db, today=date(2026, 8, 4))
        db.refresh(membership)
        db.refresh(customer)
        assert membership.status == "pending"
        assert customer.status == "lead"

        refresh_membership_lifecycle(db, today=date(2026, 8, 5))
        db.refresh(membership)
        db.refresh(customer)
        assert membership.status == "active"
        assert membership.starts_at == date(2026, 8, 5)
        assert membership.expires_at == date(2026, 9, 4)
        assert customer.status == "active"
    finally:
        db.close()


def test_first_checkin_activates_pending_membership_before_scheduled_date(tmp_path):
    from server.models import AttendanceSession
    from server.services.operations_service import create_checkin

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="pending",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 20),
        )

        create_checkin(db, {"memberId": customer.id})
        db.refresh(membership)
        db.refresh(customer)

        assert membership.status == "active"
        assert membership.starts_at <= membership.activated_at
        assert membership.expires_at == membership.activated_at + timedelta(days=30)
        assert customer.status == "active"
        assert db.query(AttendanceSession).filter_by(customer_id=customer.id).count() == 1
    finally:
        db.close()


def test_suspended_membership_gets_compensated_when_reactivated(tmp_path):
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        membership.expires_at = date(2026, 8, 31)
        customer.status = "active"
        db.commit()

        membership_action(db, membership.id, {
            "action": "suspend",
            "suspendedAt": "2026-08-10",
            "reason": "Kích hoạt nhầm",
        }, actor=None)
        db.refresh(membership)
        assert membership.status == "suspended"

        membership_action(db, membership.id, {
            "action": "activate",
            "activatedAt": "2026-08-15",
            "reason": "Khách bắt đầu tập lại",
        }, actor=None)
        db.refresh(membership)
        db.refresh(customer)

        assert membership.status == "active"
        assert membership.expires_at == date(2026, 9, 6)
        assert customer.status == "active"
    finally:
        db.close()


def test_active_membership_expires_after_expiry_date_and_member_becomes_inactive(tmp_path):
    from server.services.membership_lifecycle import refresh_membership_lifecycle

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        membership.expires_at = date(2026, 8, 31)
        customer.status = "active"
        db.commit()

        refresh_membership_lifecycle(db, today=date(2026, 8, 31))
        db.refresh(membership)
        db.refresh(customer)
        assert membership.status == "active"
        assert customer.status == "active"

        refresh_membership_lifecycle(db, today=date(2026, 9, 1))
        db.refresh(membership)
        db.refresh(customer)
        assert membership.status == "expired"
        assert customer.status == "inactive"
    finally:
        db.close()


def test_member_status_follows_current_regular_membership(tmp_path):
    from server.models import Membership, ServicePackage
    from server.services.membership_lifecycle import refresh_membership_lifecycle

    db = make_session(tmp_path)
    try:
        customer, old_membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 7, 1),
            activated_at=date(2026, 7, 1),
        )
        old_membership.expires_at = date(2026, 7, 31)
        customer.status = "active"
        package = db.query(ServicePackage).filter_by(code="FIT-LIFE").one()
        new_membership = Membership(
            customer_id=customer.id,
            package_id=package.id,
            code="MS-LIFE-2",
            registered_at=date(2026, 8, 1),
            starts_at=date(2026, 8, 5),
            expires_at=date(2026, 9, 4),
            activated_at=date(2026, 8, 5),
            status="pending",
        )
        db.add(new_membership)
        db.commit()

        refresh_membership_lifecycle(db, today=date(2026, 8, 1))
        db.refresh(old_membership)
        db.refresh(new_membership)
        db.refresh(customer)
        assert old_membership.status == "expired"
        assert new_membership.status == "pending"
        assert customer.status == "lead"

        refresh_membership_lifecycle(db, today=date(2026, 8, 5))
        db.refresh(new_membership)
        db.refresh(customer)
        assert new_membership.status == "active"
        assert customer.status == "active"
    finally:
        db.close()
