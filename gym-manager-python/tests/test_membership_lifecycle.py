from datetime import date, datetime, timedelta
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


def test_suspend_cannot_be_past_and_freeze_accepts_past_start(tmp_path):
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

        freeze_membership(db, membership.id, {
            "startsAt": (today - timedelta(days=1)).isoformat(),
            "endsAt": (today + timedelta(days=1)).isoformat(),
            "reason": "Bảo lưu nhập bù",
        }, actor=None)
        db.refresh(membership)
        assert membership.status == "frozen"

        with pytest.raises(HTTPException, match="sau ngày bắt đầu"):
            freeze_membership(db, membership.id, {
                "startsAt": today.isoformat(),
                "endsAt": today.isoformat(),
                "reason": "Không hợp lệ",
            }, actor=None)
    finally:
        db.close()


def test_freeze_compensation_uses_business_rule_without_period_limits(tmp_path):
    from server.models import MembershipFreeze
    from server.services.members_service import freeze_membership

    db = make_session(tmp_path)
    try:
        cases = [
            (date(2026, 6, 1), date(2026, 7, 1), 0),
            (date(2026, 7, 15), date(2026, 8, 15), 14),
            (date(2026, 8, 15), date(2026, 8, 20), 5),
            (date(2026, 8, 15), date(2026, 9, 15), 31),
            (date(2026, 9, 15), date(2026, 10, 15), 0),
        ]
        for index, (starts_at, ends_at, expected_days) in enumerate(cases, start=1):
            _customer, membership = seed_member_with_plan(
                db,
                status="active",
                starts_at=date(2026, 8, 1),
                activated_at=date(2026, 8, 1),
                code=f"CUS000010{index}",
            )
            membership.expires_at = date(2026, 9, 1)
            db.commit()
            freeze_membership(db, membership.id, {
                "startsAt": starts_at.isoformat(),
                "endsAt": ends_at.isoformat(),
                "reason": f"Bảo lưu {index}",
            }, actor=None)
            freeze = db.query(MembershipFreeze).filter_by(membership_id=membership.id).order_by(MembershipFreeze.id.desc()).first()
            assert freeze.starts_at == starts_at
            assert freeze.ends_at == ends_at
            assert (freeze.ends_at - freeze.starts_at).days == (ends_at - starts_at).days
            from server.services.membership_lifecycle import freeze_compensation_days
            assert freeze_compensation_days(membership, starts_at, ends_at) == expected_days
    finally:
        db.close()


def test_completed_freeze_beyond_expiry_adds_full_allowed_days(tmp_path):
    from server.models import MembershipFreeze
    from server.services.members_service import freeze_membership
    from server.services.membership_lifecycle import refresh_membership_lifecycle

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

        freeze_membership(db, membership.id, {
            "startsAt": "2026-08-15",
            "endsAt": "2026-09-15",
            "reason": "Bảo lưu vượt hạn",
        }, actor=None)
        refresh_membership_lifecycle(db, today=date(2026, 9, 16))
        db.refresh(membership)
        freeze = db.query(MembershipFreeze).filter_by(membership_id=membership.id).one()

        assert freeze.compensated_days == 31
        assert membership.expires_at == date(2026, 10, 2)
        assert membership.status == "active"
    finally:
        db.close()


def test_no_effect_freeze_after_expiry_does_not_reactivate_membership(tmp_path):
    from server.models import MembershipFreeze
    from server.services.members_service import freeze_membership
    from server.services.membership_lifecycle import refresh_membership_lifecycle

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="expired",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        membership.expires_at = date(2026, 9, 1)
        customer.status = "inactive"
        db.commit()

        freeze_membership(db, membership.id, {
            "startsAt": "2026-09-15",
            "endsAt": "2026-10-15",
            "reason": "Nhập lịch không tác động",
        }, actor=None)
        refresh_membership_lifecycle(db, today=date(2026, 10, 16))
        db.refresh(membership)
        db.refresh(customer)
        freeze = db.query(MembershipFreeze).filter_by(membership_id=membership.id).one()

        assert freeze.compensated_days == 0
        assert membership.expires_at == date(2026, 9, 1)
        assert membership.status == "expired"
        assert customer.status == "inactive"
    finally:
        db.close()


def test_update_and_delete_completed_freeze_recalculate_expiry(tmp_path):
    from server.models import MembershipFreeze
    from server.services.members_service import delete_membership_freeze, freeze_membership, update_membership_freeze
    from server.services.membership_lifecycle import refresh_membership_lifecycle

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        membership.expires_at = date(2026, 9, 1)
        db.commit()

        freeze_membership(db, membership.id, {
            "startsAt": "2026-08-01",
            "endsAt": "2026-08-06",
            "reason": "Bảo lưu ngắn",
        }, actor=None)
        refresh_membership_lifecycle(db, today=date(2026, 8, 7))
        db.refresh(membership)
        freeze = db.query(MembershipFreeze).filter_by(membership_id=membership.id).one()
        assert membership.expires_at == date(2026, 9, 6)
        assert freeze.compensated_days == 5

        update_membership_freeze(db, membership.id, freeze.id, {
            "startsAt": "2026-08-01",
            "endsAt": "2026-08-11",
            "reason": "Bảo lưu dài hơn",
        }, actor=None)
        db.refresh(membership)
        db.refresh(freeze)
        assert freeze.compensated_days == 10
        assert membership.expires_at == date(2026, 9, 11)

        delete_membership_freeze(db, membership.id, freeze.id, actor=None)
        db.refresh(membership)
        assert membership.expires_at == date(2026, 9, 1)
        assert db.query(MembershipFreeze).filter_by(membership_id=membership.id).count() == 0
    finally:
        db.close()


def test_membership_timeline_splits_active_and_freeze_segments(tmp_path):
    from server.services.members_service import freeze_membership
    from server.services.serializers import membership_data
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=today - timedelta(days=13),
            activated_at=today - timedelta(days=13),
        )
        membership.expires_at = today + timedelta(days=18)
        db.commit()

        freeze_membership(db, membership.id, {
            "startsAt": today.isoformat(),
            "endsAt": (today + timedelta(days=6)).isoformat(),
            "reason": "Hội viên đi công tác",
        }, actor=None)
        db.refresh(membership)

        timeline = membership_data(membership)["timeline"]
        assert timeline["totalDays"] == 31
        assert timeline["totalPlannedFreezeDays"] == 6
        assert [segment["type"] for segment in timeline["segments"]] == ["active", "freeze", "active"]
        assert [segment["days"] for segment in timeline["segments"]] == [13, 6, 12]
        assert timeline["activeFreeze"]["startsAt"] == today.isoformat()
        assert timeline["activeFreeze"]["endsAt"] == (today + timedelta(days=6)).isoformat()
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


def test_adjust_expired_membership_days_can_reactivate_when_new_expiry_is_current(tmp_path):
    from server.models import MembershipEvent
    from server.services.members_service import membership_action
    from server.timeutils import vietnam_today

    db = make_session(tmp_path)
    try:
        today = vietnam_today()
        customer, membership = seed_member_with_plan(
            db,
            status="expired",
            starts_at=today - timedelta(days=40),
            activated_at=today - timedelta(days=40),
        )
        membership.expires_at = today - timedelta(days=5)
        customer.status = "inactive"
        db.commit()

        membership_action(db, membership.id, {
            "action": "adjust_days",
            "days": 3,
            "reason": "Cộng ngày tặng bị sót",
        }, None)
        db.refresh(membership)
        db.refresh(customer)
        assert membership.expires_at == today - timedelta(days=2)
        assert membership.status == "expired"
        assert customer.status == "inactive"

        membership_action(db, membership.id, {
            "action": "adjust_days",
            "days": 10,
            "reason": "Cộng đủ ngày tặng bị sót",
        }, None)
        db.refresh(membership)
        db.refresh(customer)

        assert membership.expires_at == today + timedelta(days=8)
        assert membership.status == "active"
        assert customer.status == "active"
        assert db.query(MembershipEvent).filter_by(membership_id=membership.id, action="adjust_days").count() == 2
    finally:
        db.close()


def test_cancelled_membership_cannot_adjust_days(tmp_path):
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

        with pytest.raises(HTTPException, match="đã hủy"):
            membership_action(db, membership.id, {
                "action": "adjust_days",
                "days": 10,
                "reason": "Không được mở lại gói đã hủy",
            }, None)
    finally:
        db.close()


def test_change_membership_to_higher_plan_recalculates_debt_with_due_date(tmp_path):
    import json
    from server.models import MembershipEvent, ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        upgrade_plan = ServicePackage(code="FIT-HIGHER", name="Fitness Higher", category="Fitness", duration_days=30, price=1500000, is_pt=False, is_active=True)
        membership.final_price = 1000000
        membership.paid_amount = 500000
        membership.deposit_amount = 500000
        membership.debt_amount = 500000
        membership.debt_due_date = date(2026, 8, 20)
        db.add(upgrade_plan)
        db.commit()

        membership_action(db, membership.id, {
            "action": "change",
            "planId": upgrade_plan.id,
            "finalPrice": "1500000",
            "expiresAt": "2026-09-15",
            "debtDueDate": "2026-08-25",
            "reason": "Khách đổi lên gói cao hơn",
        }, None)
        db.refresh(membership)

        event = db.query(MembershipEvent).filter_by(membership_id=membership.id, action="change").one()
        details = json.loads(event.details_json)

        assert membership.package_id == upgrade_plan.id
        assert membership.final_price == 1500000
        assert membership.paid_amount == 500000
        assert membership.debt_amount == 1000000
        assert membership.debt_due_date == date(2026, 8, 25)
        assert membership.expires_at == date(2026, 9, 15)
        assert details["previousDebt"] == 500000
        assert details["newDebt"] == 1000000
        assert details["newDebtDueDate"] == "2026-08-25"
    finally:
        db.close()


def test_change_membership_to_higher_plan_requires_debt_due_date_when_missing(tmp_path):
    from fastapi import HTTPException
    from server.models import ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        upgrade_plan = ServicePackage(code="FIT-HIGHER-MISSING-DUE", name="Fitness Higher Missing Due", category="Fitness", duration_days=30, price=1500000, is_pt=False, is_active=True)
        membership.final_price = 1000000
        membership.paid_amount = 1000000
        membership.deposit_amount = 1000000
        membership.debt_amount = 0
        membership.debt_due_date = None
        db.add(upgrade_plan)
        db.commit()

        with pytest.raises(HTTPException, match="hạn thanh toán"):
            membership_action(db, membership.id, {
                "action": "upgrade",
                "planId": upgrade_plan.id,
                "finalPrice": "1500000",
                "reason": "Thiếu hạn công nợ",
            }, None)
    finally:
        db.close()


def test_change_membership_to_lower_plan_can_keep_overpayment_as_credit(tmp_path):
    import json
    from server.models import MembershipEvent, ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        lower_plan = ServicePackage(code="FIT-LOWER-CREDIT", name="Fitness Lower Credit", category="Fitness", duration_days=30, price=700000, is_pt=False, is_active=True)
        membership.final_price = 1000000
        membership.paid_amount = 1000000
        membership.deposit_amount = 1000000
        membership.debt_amount = 0
        db.add(lower_plan)
        db.commit()

        membership_action(db, membership.id, {
            "action": "change",
            "planId": lower_plan.id,
            "finalPrice": "700000",
            "overpaymentPolicy": "keep_credit",
            "reason": "Giữ phần dư để đối soát sau",
        }, None)
        db.refresh(membership)

        event = db.query(MembershipEvent).filter_by(membership_id=membership.id, action="change").one()
        details = json.loads(event.details_json)

        assert membership.package_id == lower_plan.id
        assert membership.final_price == 700000
        assert membership.paid_amount == 1000000
        assert membership.deposit_amount == 1000000
        assert membership.debt_amount == 0
        assert membership.debt_due_date is None
        assert details["overpaidAmount"] == 300000
        assert details["overpaymentPolicy"] == "keep_credit"
        assert details["creditAmount"] == 300000
    finally:
        db.close()


def test_change_membership_to_lower_plan_can_record_external_refund(tmp_path):
    import json
    from server.models import MembershipEvent, ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        lower_plan = ServicePackage(code="FIT-LOWER-REFUND", name="Fitness Lower Refund", category="Fitness", duration_days=30, price=700000, is_pt=False, is_active=True)
        membership.final_price = 1000000
        membership.paid_amount = 1000000
        membership.deposit_amount = 1000000
        membership.debt_amount = 0
        db.add(lower_plan)
        db.commit()

        membership_action(db, membership.id, {
            "action": "change",
            "planId": lower_plan.id,
            "finalPrice": "700000",
            "overpaymentPolicy": "external_refund",
            "reason": "Hoàn tiền ngoài hệ thống",
        }, None)
        db.refresh(membership)

        event = db.query(MembershipEvent).filter_by(membership_id=membership.id, action="change").one()
        details = json.loads(event.details_json)

        assert membership.package_id == lower_plan.id
        assert membership.final_price == 700000
        assert membership.paid_amount == 700000
        assert membership.deposit_amount == 700000
        assert membership.debt_amount == 0
        assert details["overpaidAmount"] == 300000
        assert details["overpaymentPolicy"] == "external_refund"
        assert details["externalRefundAmount"] == 300000
    finally:
        db.close()


def test_change_membership_to_lower_plan_can_reduce_recorded_paid_amount(tmp_path):
    import json
    from server.models import MembershipEvent, ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        lower_plan = ServicePackage(code="FIT-LOWER-ADJUST", name="Fitness Lower Adjust", category="Fitness", duration_days=30, price=700000, is_pt=False, is_active=True)
        membership.final_price = 1000000
        membership.paid_amount = 1000000
        membership.deposit_amount = 1000000
        membership.debt_amount = 0
        db.add(lower_plan)
        db.commit()

        membership_action(db, membership.id, {
            "action": "change",
            "planId": lower_plan.id,
            "finalPrice": "700000",
            "overpaymentPolicy": "reduce_paid",
            "reason": "Điều chỉnh lại số đã thu do nhập sai",
        }, None)
        db.refresh(membership)

        event = db.query(MembershipEvent).filter_by(membership_id=membership.id, action="change").one()
        details = json.loads(event.details_json)

        assert membership.package_id == lower_plan.id
        assert membership.final_price == 700000
        assert membership.paid_amount == 700000
        assert membership.deposit_amount == 700000
        assert membership.debt_amount == 0
        assert details["overpaidAmount"] == 300000
        assert details["overpaymentPolicy"] == "reduce_paid"
        assert details["paidAdjustmentAmount"] == 300000
    finally:
        db.close()


def test_change_membership_to_lower_plan_rejects_invalid_overpayment_policy(tmp_path):
    from fastapi import HTTPException
    from server.models import ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        lower_plan = ServicePackage(code="FIT-LOWER-BAD-POLICY", name="Fitness Lower Bad Policy", category="Fitness", duration_days=30, price=700000, is_pt=False, is_active=True)
        membership.final_price = 1000000
        membership.paid_amount = 1000000
        membership.deposit_amount = 1000000
        membership.debt_amount = 0
        db.add(lower_plan)
        db.commit()

        with pytest.raises(HTTPException, match="tiền dư"):
            membership_action(db, membership.id, {
                "action": "change",
                "planId": lower_plan.id,
                "finalPrice": "700000",
                "overpaymentPolicy": "bad_policy",
                "reason": "Policy không hợp lệ",
            }, None)
    finally:
        db.close()


def test_change_unpaid_membership_to_lower_plan_reduces_debt(tmp_path):
    import json
    from server.models import MembershipEvent, ServicePackage
    from server.services.members_service import membership_action

    db = make_session(tmp_path)
    try:
        _customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        lower_plan = ServicePackage(code="FIT-LOWER-UNPAID", name="Fitness Lower Unpaid", category="Fitness", duration_days=30, price=700000, is_pt=False, is_active=True)
        membership.final_price = 1000000
        membership.paid_amount = 0
        membership.deposit_amount = 0
        membership.debt_amount = 1000000
        membership.debt_due_date = date(2026, 8, 20)
        db.add(lower_plan)
        db.commit()

        membership_action(db, membership.id, {
            "action": "change",
            "planId": lower_plan.id,
            "finalPrice": "700000",
            "reason": "Khách đổi xuống khi chưa thanh toán",
        }, None)
        db.refresh(membership)

        event = db.query(MembershipEvent).filter_by(membership_id=membership.id, action="change").one()
        details = json.loads(event.details_json)

        assert membership.package_id == lower_plan.id
        assert membership.final_price == 700000
        assert membership.paid_amount == 0
        assert membership.debt_amount == 700000
        assert membership.debt_due_date == date(2026, 8, 20)
        assert details["previousDebt"] == 1000000
        assert details["newDebt"] == 700000
        assert details["overpaidAmount"] == 0
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


def test_debt_collection_uses_actual_paid_at(tmp_path):
    import asyncio
    from server.models import Payment
    from server.services.members_service import update_membership
    from server.services.dashboard_service import reports

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 7, 1),
            activated_at=date(2026, 7, 1),
        )
        membership.final_price = 1000000
        membership.paid_amount = 200000
        membership.deposit_amount = 200000
        membership.debt_amount = 800000
        membership.debt_due_date = date(2026, 7, 20)
        db.commit()

        asyncio.run(update_membership(db, membership.id, {
            "startsAt": "2026-07-01",
            "expiresAt": "2026-07-31",
            "finalPrice": "1000000",
            "paidAmount": "1000000",
            "debtDueDate": "",
            "paymentMethod": "cash",
            "status": "active",
            "paidAt": "2026-08-01T09:15",
        }, [], None))

        payment = db.query(Payment).filter(Payment.membership_id == membership.id).one()
        assert payment.paid_at == datetime(2026, 8, 1, 2, 15)
        assert payment.shift_date == date(2026, 8, 1)

        august_first = reports(db, "2026-08-01", "2026-08-01")
        assert august_first["summary"]["revenue"] == 800000
        assert august_first["revenueItems"][0]["paymentNo"] == payment.payment_no

        august_second = reports(db, "2026-08-02", "2026-08-02")
        assert august_second["summary"]["revenue"] == 0
    finally:
        db.close()


def test_membership_renewal_uses_actual_paid_at_for_revenue(tmp_path):
    import asyncio
    from server.models import Payment
    from server.services.dashboard_service import reports
    from server.services.members_service import create_membership

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="expired",
            starts_at=date(2026, 4, 1),
            activated_at=date(2026, 4, 1),
        )
        membership.expires_at = date(2026, 4, 30)
        db.commit()

        renewed = asyncio.run(create_membership(db, {
            "memberId": str(customer.id),
            "planId": str(membership.package_id),
            "startsAt": "2026-06-01",
            "activateNow": "false",
            "activationDate": "",
            "expiresAt": "2026-07-01",
            "finalPrice": "1000000",
            "paidAmount": "1000000",
            "paymentMethod": "cash",
            "paidAt": "2026-05-20",
        }, [], None))

        payment = db.query(Payment).filter(Payment.membership_id == renewed["id"]).one()
        assert payment.paid_at == datetime(2026, 5, 19, 17, 0)
        assert payment.shift_date == date(2026, 5, 20)

        may = reports(db, "2026-05-01", "2026-05-31")
        assert may["summary"]["revenue"] == 1000000
        assert may["revenueItems"][0]["paymentNo"] == payment.payment_no

        june = reports(db, "2026-06-01", "2026-06-30")
        assert june["summary"]["revenue"] == 0
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
        assert customer.status == "cancelled"

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

        assert result["summary"] == "Hủy dịch vụ Fitness Lifecycle và chuyển Lifecycle Member vào danh sách đã hủy"
        assert gym_membership.status == "cancelled"
        assert lady_membership.status == "active"
        assert customer.status == "cancelled"
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


def test_cancelled_member_is_separated_and_can_reactivate_account_only(tmp_path):
    import asyncio
    from fastapi import HTTPException
    import pytest
    from server.models import Membership, ServicePackage
    from server.services.members_service import (
        create_membership,
        list_members,
        membership_action,
        reactivate_cancelled_member,
    )

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="active",
            starts_at=date(2026, 8, 1),
            activated_at=date(2026, 8, 1),
        )
        customer.status = "active"
        membership.expires_at = date(2026, 9, 1)
        db.commit()

        membership_action(db, membership.id, {
            "action": "cancel",
            "effectiveAt": "2026-08-12",
            "reason": "Hủy tài khoản",
        }, None)

        main_rows = list_members(db, q="", member_status="all", view="all", page=1, page_size=20)
        cancelled_rows = list_members(db, q="", member_status="all", view="cancelled", page=1, page_size=20)

        assert [row["id"] for row in main_rows["items"]] == []
        assert [row["id"] for row in cancelled_rows["items"]] == [customer.id]

        with pytest.raises(HTTPException, match="kích hoạt lại trước"):
            asyncio.run(create_membership(db, {
                "memberId": customer.id,
                "planId": membership.package_id,
                "startsAt": "2026-08-13",
                "finalPrice": "100000",
                "paidAmount": "0",
            }, [], None))

        reactivated = reactivate_cancelled_member(db, customer.id, None)
        db.refresh(membership)

        assert reactivated["status"] == "lead"
        assert membership.status == "cancelled"

        new_plan = ServicePackage(
            code="FIT-NEW",
            name="Fitness New",
            category="Fitness",
            duration_days=30,
            price=120000,
            is_pt=False,
            is_active=True,
        )
        db.add(new_plan)
        db.commit()

        asyncio.run(create_membership(db, {
            "memberId": customer.id,
            "planId": new_plan.id,
            "startsAt": "2026-08-13",
            "finalPrice": "120000",
            "paidAmount": "120000",
            "paymentMethod": "cash",
        }, [], None))
        db.refresh(customer)

        assert customer.status == "active"
        assert db.query(Membership).filter_by(customer_id=customer.id, status="cancelled").count() == 1
        assert db.query(Membership).filter_by(customer_id=customer.id, status="active").count() == 1
    finally:
        db.close()


def test_normalize_cancelled_members_moves_inactive_latest_cancelled_to_cancelled_tab(tmp_path):
    from server.services.members_service import normalize_cancelled_members

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="cancelled",
            starts_at=date(2026, 7, 31),
            activated_at=None,
        )
        customer.status = "inactive"
        membership.registered_at = date(2026, 7, 31)
        membership.expires_at = date(2026, 11, 27)
        db.commit()

        assert normalize_cancelled_members(db) == 1
        db.commit()
        db.refresh(customer)

        assert customer.status == "cancelled"
    finally:
        db.close()


def test_lifecycle_refresh_keeps_cancelled_member_separate_from_inactive(tmp_path):
    from server.services.membership_lifecycle import refresh_membership_lifecycle

    db = make_session(tmp_path)
    try:
        customer, membership = seed_member_with_plan(
            db,
            status="cancelled",
            starts_at=date(2026, 7, 31),
            activated_at=None,
        )
        customer.status = "cancelled"
        membership.registered_at = date(2026, 7, 31)
        membership.expires_at = date(2026, 11, 27)
        db.commit()

        refresh_membership_lifecycle(db, today=date(2026, 8, 13))
        db.refresh(customer)

        assert customer.status == "cancelled"
    finally:
        db.close()
