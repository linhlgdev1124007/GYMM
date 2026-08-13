from datetime import date, timedelta
import os
from pathlib import Path
import tempfile

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
import pytest

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


def seed_member_with_plan(db, status="pending", starts_at=date(2026, 8, 1), activated_at=None, code="CUS0000001"):
    from server.models import Customer, Membership, Person, ServicePackage

    person = Person(display_name="Lifecycle Member", phone="0900000001", status="active")
    db.add(person)
    db.flush()
    customer = Customer(person_id=person.id, customer_code=code, status="lead")
    package = ServicePackage(
        code=f"FIT-LIFE-{code[-1]}",
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
        code=f"MS-LIFE-{code[-1]}",
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
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        reactivated_at = today + timedelta(days=5)
        customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=today - timedelta(days=10),
            activated_at=today - timedelta(days=10),
        )
        membership.expires_at = today + timedelta(days=20)
        customer.status = "active"
        db.commit()

        membership_action(db, membership.id, {
            "action": "suspend",
            "suspendedAt": today.isoformat(),
            "reason": "Kích hoạt nhầm",
        }, actor=None)
        db.refresh(membership)
        assert membership.status == "suspended"

        membership_action(db, membership.id, {
            "action": "activate",
            "activatedAt": reactivated_at.isoformat(),
            "reason": "Khách bắt đầu tập lại",
        }, actor=None)
        db.refresh(membership)
        db.refresh(customer)

        assert membership.status == "active"
        assert membership.starts_at == reactivated_at
        assert membership.expires_at == reactivated_at + timedelta(days=20)
        assert customer.status == "active"
    finally:
        db.close()


def test_freeze_does_not_extend_until_reactivated_and_counts_actual_days(tmp_path):
    from server.models import MembershipFreeze
    from server.services.members_service import freeze_membership, membership_action
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=today - timedelta(days=10),
            activated_at=today - timedelta(days=10),
        )
        original_start = membership.starts_at
        original_activation = membership.activated_at
        membership.expires_at = today + timedelta(days=20)
        customer.status = "active"
        db.commit()

        freeze_membership(db, membership.id, {
            "startsAt": today.isoformat(),
            "endsAt": (today + timedelta(days=9)).isoformat(),
            "reason": "Khách xin bảo lưu",
        }, actor=None)
        db.refresh(membership)
        freeze = db.query(MembershipFreeze).filter_by(membership_id=membership.id).one()
        assert membership.status == "frozen"
        assert membership.expires_at == today + timedelta(days=20)
        assert freeze.compensated_days == 0

        membership_action(db, membership.id, {
            "action": "activate",
            "activatedAt": (today + timedelta(days=4)).isoformat(),
            "reason": "Khách quay lại sớm",
        }, actor=None)
        db.refresh(membership)
        db.refresh(freeze)

        assert membership.status == "active"
        assert membership.starts_at == original_start
        assert membership.activated_at == original_activation
        assert membership.expires_at == today + timedelta(days=24)
        assert freeze.ends_at == today + timedelta(days=4)
        assert freeze.compensated_days == 4
    finally:
        db.close()


def test_same_day_suspend_or_freeze_reactivation_does_not_add_day(tmp_path):
    from server.services.members_service import freeze_membership, membership_action
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        _customer, suspended_membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=today - timedelta(days=10),
            activated_at=today - timedelta(days=10),
        )
        suspended_membership.expires_at = today + timedelta(days=20)
        db.commit()

        membership_action(db, suspended_membership.id, {
            "action": "suspend",
            "suspendedAt": today.isoformat(),
            "reason": "Bấm nhầm",
        }, actor=None)
        membership_action(db, suspended_membership.id, {
            "action": "activate",
            "activatedAt": today.isoformat(),
            "reason": "Kích hoạt lại ngay",
        }, actor=None)
        db.refresh(suspended_membership)
        assert suspended_membership.expires_at == today + timedelta(days=20)

        _customer, frozen_membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=today - timedelta(days=10),
            activated_at=today - timedelta(days=10),
            code="CUS0000002",
        )
        frozen_membership.expires_at = today + timedelta(days=20)
        db.commit()

        freeze_membership(db, frozen_membership.id, {
            "startsAt": today.isoformat(),
            "endsAt": (today + timedelta(days=5)).isoformat(),
            "reason": "Bấm nhầm",
        }, actor=None)
        membership_action(db, frozen_membership.id, {
            "action": "activate",
            "activatedAt": today.isoformat(),
            "reason": "Kích hoạt lại ngay",
        }, actor=None)
        db.refresh(frozen_membership)
        assert frozen_membership.expires_at == today + timedelta(days=20)
    finally:
        db.close()


def test_suspend_and_freeze_dates_cannot_be_invalid_or_past(tmp_path):
    from fastapi import HTTPException
    from server.services.members_service import freeze_membership, membership_action
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=today - timedelta(days=10),
            activated_at=today - timedelta(days=10),
        )
        membership.expires_at = today + timedelta(days=20)
        db.commit()

        with pytest.raises(HTTPException, match="Ngày tạm dừng"):
            membership_action(db, membership.id, {
                "action": "suspend",
                "suspendedAt": (today - timedelta(days=1)).isoformat(),
                "reason": "Ngày cũ",
            }, actor=None)

        with pytest.raises(HTTPException, match="quá khứ"):
            freeze_membership(db, membership.id, {
                "startsAt": (today - timedelta(days=1)).isoformat(),
                "endsAt": (today + timedelta(days=1)).isoformat(),
                "reason": "Ngày cũ",
            }, actor=None)

        with pytest.raises(HTTPException, match="sau ngày bắt đầu"):
            freeze_membership(db, membership.id, {
                "startsAt": today.isoformat(),
                "endsAt": today.isoformat(),
                "reason": "Không hợp lệ",
            }, actor=None)
    finally:
        db.close()


def test_freeze_auto_completes_after_end_and_counts_planned_days(tmp_path):
    from server.models import MembershipFreeze
    from server.services.members_service import freeze_membership
    from server.services.membership_lifecycle import refresh_membership_lifecycle
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=today - timedelta(days=10),
            activated_at=today - timedelta(days=10),
        )
        membership.expires_at = today + timedelta(days=20)
        customer.status = "active"
        db.commit()

        freeze_membership(db, membership.id, {
            "startsAt": today.isoformat(),
            "endsAt": (today + timedelta(days=2)).isoformat(),
            "reason": "Khách xin bảo lưu",
        }, actor=None)
        refresh_membership_lifecycle(db, today=today + timedelta(days=3))
        db.refresh(membership)
        freeze = db.query(MembershipFreeze).filter_by(membership_id=membership.id).one()

        assert membership.status == "active"
        assert membership.expires_at == today + timedelta(days=22)
        assert freeze.compensated_days == 2
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
        package = old_membership.package
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


def test_expiring_membership_still_serializes_as_active(tmp_path):
    from server.services.members_service import list_members
    from server.services.serializers import membership_data
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=today - timedelta(days=25),
            activated_at=today - timedelta(days=25),
        )
        membership.expires_at = today + timedelta(days=5)
        db.commit()

        assert membership_data(membership)["status"] == "active"
        rows = list_members(db, q="", member_status="expiring", page=1, page_size=20)
        assert rows["items"][0]["membership"]["status"] == "active"
    finally:
        db.close()


def test_pending_member_status_filter_returns_waiting_members(tmp_path):
    from server.services.members_service import list_members

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="pending",
            starts_at=date(2026, 8, 20),
            activated_at=None,
        )

        rows = list_members(db, q="", member_status="pending", page=1, page_size=20)

        assert rows["pagination"]["total"] == 1
        assert rows["items"][0]["id"] == customer.id
        assert rows["items"][0]["membership"]["status"] == "pending"
    finally:
        db.close()


def test_adjust_membership_days_updates_expiry_and_history(tmp_path):
    from server.models import MembershipEvent
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )

        membership_action(db, membership.id, {
            "action": "adjust_days",
            "days": 5,
            "reason": "Cộng ngày khuyến mãi",
        }, None)
        db.refresh(membership)
        assert membership.expires_at == date(2026, 9, 5)

        membership_action(db, membership.id, {
            "action": "adjust_days",
            "days": -3,
            "reason": "Trừ ngày nhập sai",
        }, None)
        db.refresh(membership)
        assert membership.expires_at == date(2026, 9, 2)
        assert db.query(MembershipEvent).filter_by(membership_id=membership.id, action="adjust_days").count() == 2

        with pytest.raises(Exception) as exc:
            membership_action(db, membership.id, {
                "action": "adjust_days",
                "days": -99,
                "reason": "Trừ quá hạn",
            }, None)
        assert "trước ngày bắt đầu" in str(exc.value)
    finally:
        db.close()


def test_same_category_memberships_are_queued_and_other_categories_overlap(tmp_path):
    import asyncio
    from server.models import Membership, ServicePackage
    from server.services.members_service import create_membership, get_member
    from server.services.membership_lifecycle import refresh_membership_lifecycle

    db = make_session(tmp_path)
    try:
        customer, current = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        current.expires_at = date(2026, 8, 31)
        customer.status = "active"
        dance = ServicePackage(
            code="DANCE-LIFE",
            name="Dance Lifecycle",
            category="Dance",
            duration_days=30,
            price=100000,
            is_pt=False,
            is_active=True,
        )
        db.add(dance)
        db.commit()

        queued = asyncio.run(create_membership(db, {
            "memberId": str(customer.id),
            "planId": str(current.package_id),
            "startsAt": "2026-08-12",
            "expiresAt": "2026-09-11",
            "activateNow": "true",
            "finalPrice": "100000",
            "paidAmount": "0",
            "debtDueDate": "2026-08-20",
            "paymentMethod": "cash",
        }, [], None))
        assert queued["status"] == "pending"
        assert queued["startsAt"] == "2026-09-01"
        assert queued["activatedAt"] == "2026-09-01"
        assert queued["expiresAt"] == "2026-10-01"

        overlapping = asyncio.run(create_membership(db, {
            "memberId": str(customer.id),
            "planId": str(dance.id),
            "startsAt": "2026-08-12",
            "activateNow": "true",
            "finalPrice": "100000",
            "paidAmount": "0",
            "debtDueDate": "2026-08-20",
            "paymentMethod": "cash",
        }, [], None))
        assert overlapping["status"] == "active"
        assert overlapping["startsAt"] == "2026-08-12"
        assert overlapping["expiresAt"] == "2026-09-11"

        refresh_membership_lifecycle(db, today=date(2026, 9, 1))
        queued_row = db.query(Membership).filter_by(id=queued["id"]).one()
        db.refresh(customer)
        assert queued_row.status == "active"
        assert customer.status == "active"

        member = get_member(db, customer.id)
        assert member["memberships"][0]["status"] == "active"
    finally:
        db.close()


def test_membership_payment_validation_is_enforced_by_backend(tmp_path):
    import asyncio
    from fastapi import HTTPException
    from server.services.members_service import create_membership

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="expired",
            starts_at=date(2026, 7, 1),
            activated_at=date(2026, 7, 1),
        )
        membership.expires_at = date(2026, 7, 31)
        db.commit()

        with pytest.raises(HTTPException, match="lớn hơn tổng tiền"):
            asyncio.run(create_membership(db, {
                "memberId": str(customer.id),
                "planId": str(membership.package_id),
                "startsAt": "2026-08-12",
                "activateNow": "true",
                "finalPrice": "100000",
                "paidAmount": "150000",
                "paymentMethod": "cash",
            }, [], None))

        with pytest.raises(HTTPException, match="hạn thanh toán"):
            asyncio.run(create_membership(db, {
                "memberId": str(customer.id),
                "planId": str(membership.package_id),
                "startsAt": "2026-08-12",
                "activateNow": "true",
                "finalPrice": "100000",
                "paidAmount": "50000",
                "paymentMethod": "cash",
            }, [], None))
    finally:
        db.close()


def test_member_status_syncs_after_cancel_and_transfer(tmp_path):
    from server.models import Customer, Membership, Person, ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        membership.expires_at = date(2026, 9, 1)
        customer.status = "active"
        db.commit()

        membership_action(db, membership.id, {
            "action": "cancel",
            "effectiveAt": "2026-08-12",
            "reason": "Khách yêu cầu hủy",
        }, None)
        db.refresh(customer)
        assert customer.status == "inactive"

        customer.status = "active"
        membership.status = "active"
        db.add(Person(display_name="Transfer Target", phone="0900000099", status="active"))
        db.flush()
        target_person = db.query(Person).filter_by(phone="0900000099").one()
        target = Customer(person_id=target_person.id, customer_code="CUS0000099", status="lead")
        db.add(target)
        db.commit()

        membership_action(db, membership.id, {
            "action": "transfer",
            "targetMemberId": target.id,
            "effectiveAt": "2026-08-12",
            "reason": "Chuyển nhượng",
        }, None)
        db.refresh(customer)
        db.refresh(target)
        assert customer.status == "inactive"
        assert target.status == "active"
    finally:
        db.close()


def test_cancel_service_inactivates_member_even_with_other_active_membership(tmp_path):
    from server.models import Membership, ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        customer, gym_membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        gym_membership.expires_at = date(2026, 9, 1)
        lady = ServicePackage(
            code="LADY-LIFE",
            name="Lady Lifecycle",
            category="Lady",
            duration_days=30,
            price=100000,
            is_pt=False,
            is_active=True,
        )
        db.add(lady)
        db.flush()
        lady_membership = Membership(
            customer_id=customer.id,
            package_id=lady.id,
            code="MS-LADY-1",
            registered_at=date(2026, 8, 1),
            starts_at=date(2026, 8, 1),
            expires_at=date(2026, 9, 1),
            activated_at=date(2026, 8, 1),
            status="active",
        )
        customer.status = "active"
        db.add(lady_membership)
        db.commit()

        result = membership_action(db, gym_membership.id, {
            "action": "cancel",
            "effectiveAt": "2026-08-12",
            "reason": "Khách hủy dịch vụ",
        }, None)
        db.refresh(customer)
        db.refresh(gym_membership)
        db.refresh(lady_membership)

        assert result["summary"] == "Hủy dịch vụ Fitness Lifecycle và inactive Lifecycle Member"
        assert gym_membership.status == "cancelled"
        assert lady_membership.status == "active"
        assert customer.status == "inactive"
    finally:
        db.close()


def test_cancelled_membership_cannot_be_reactivated(tmp_path):
    import pytest
    from fastapi import HTTPException
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="cancelled",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        membership.expires_at = date(2026, 9, 1)
        db.commit()

        with pytest.raises(HTTPException, match="không thể kích hoạt lại"):
            membership_action(db, membership.id, {
                "action": "activate",
                "effectiveAt": "2026-08-12",
                "reason": "Thử mở lại gói đã hủy",
            }, None)
    finally:
        db.close()
